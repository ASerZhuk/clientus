import io
import re
import sqlite3
import tarfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app import cli
from app import db as database
from app import tenants
from app.config import get_settings
from app.main import app
from app.models import Tenant
from app.services import exporter
from tests.api_helpers import BOOK, first_slot, service_id
from tests.helpers import PWD, publish


def png(color=(10, 90, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (640, 420), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture()
def sold(app_db, tmp_path, client):
    """Two live studios with a booking each; alpha is being exported."""
    publish(tmp_path, "alpha", plan="domain", name="Alpha Auto Service")
    publish(tmp_path, "beta", plan="standard", name="Beta Secret Studio")
    tenants.create_owner("alpha", "owner@alpha.test", PWD)
    tenants.create_owner("beta", "owner@beta.test", PWD)
    sid = service_id(client, "alpha")
    booked = client.post("/api/s/alpha/bookings", json={**BOOK, "service_id": sid, "start_min": first_slot(client, "alpha", sid)}, headers={"Idempotency-Key": "alpha-key-0001"})
    assert booked.status_code == 201
    sidb = service_id(client, "beta")
    client.post("/api/s/beta/bookings", json={**BOOK, "phone": "+7 999 999-99-99", "service_id": sidb, "start_min": first_slot(client, "beta", sidb)}, headers={"Idempotency-Key": "beta-key-0001"})
    return tmp_path


def extract(archive, into):
    with tarfile.open(archive) as tar:
        tar.extractall(into, filter="data")
    return into / "alpha-package"


def test_export_contains_only_this_studio_and_no_dev_files(sold):
    result = exporter.export_studio("alpha", out_dir=sold / "exports", domain="https://Book.Alpha.ru/")
    pkg = extract(result["archive"], sold / "unpacked")
    for name in ("install.sh", ".env", "Caddyfile", "README-INSTALL.md", "data/app.db", "api/app/main.py", "api/requirements.txt", "web/src", "web/pnpm-lock.yaml", "deploy/clientus-api.service", "deploy/backup.sh", "scripts/py.sh"):
        assert (pkg / name).exists(), name
    assert (pkg / "install.sh").stat().st_mode & 0o111
    for absent in (".venv", "node_modules", ".next", "api/tests", "api/data", "web/e2e", "tenants/beta", "deploy/selfhosted", "web/test-results"):
        assert not (pkg / absent).exists(), absent
    assert [p.name for p in (pkg / "tenants").iterdir()] in (["alpha"], [])
    db = sqlite3.connect(pkg / "data" / "app.db")
    assert db.execute("select slug, plan, status, trial_ends_at, paid_until, suspended from tenants").fetchall() == [("alpha", "self_hosted", "active", None, None, 0)]
    assert db.execute("select email from users").fetchall() == [("owner@alpha.test",)]
    assert db.execute("select count(*) from bookings").fetchone()[0] == 1 == result["bookings"]
    assert db.execute("select host, status from tenant_domains").fetchall() == [("book.alpha.ru", "active")]
    for empty in ("operators", "admin_sessions", "audit_log", "owner_sessions", "push_subscriptions", "notification_jobs", "idempotency_keys"):
        assert db.execute(f"select count(*) from {empty}").fetchone()[0] == 0, empty
    assert db.execute("pragma foreign_key_check").fetchall() == [] and db.execute("pragma integrity_check").fetchone()[0] == "ok"
    db.close()
    # nothing of the other studio anywhere in the package (text files and database)
    for f in pkg.rglob("*"):
        if f.is_file() and f.suffix in (".py", ".ts", ".tsx", ".json", ".md", ".sh", ".env", ".service", ".css", ".db", "") and f.stat().st_size < 5_000_000:
            data = f.read_bytes()
            assert b"Beta Secret Studio" not in data and b"owner@beta.test" not in data, f
    env = (pkg / ".env").read_text()
    assert "PUBLIC_ORIGINS=https://book.alpha.ru" in env and "ADMIN_ENABLED=false" in env and "COOKIE_SECURE=true" in env
    assert "test-secret" not in env and not re.search(r"^[^#\n=]+=[^#\n]*\s#", env, re.M)  # fresh secrets, no inline comments (systemd)
    # sourcing the file in a shell must work (install.sh does it): quoted names with spaces are safe
    import subprocess

    shell = subprocess.run(["sh", "-c", f"set -a; . {pkg / '.env'}; echo \"$PLATFORM_NAME|$PUBLIC_ORIGINS\""], capture_output=True, text=True)
    assert shell.returncode == 0 and shell.stdout.strip().endswith("|https://book.alpha.ru"), shell
    assert "book.alpha.ru {" in (pkg / "Caddyfile").read_text() and "@DOMAIN@" not in (pkg / "install.sh").read_text()


def test_exported_package_runs_on_its_own(sold, client, monkeypatch):
    """Boot the exported database as a fresh installation: the owner keeps the password, history is intact, no branding."""
    result = exporter.export_studio("alpha", out_dir=sold / "exports", domain="book.alpha.ru")
    pkg = extract(result["archive"], sold / "unpacked")
    monkeypatch.setenv("DATA_DIR", str(pkg / "data"))
    monkeypatch.setenv("ADMIN_ENABLED", "false")
    get_settings.cache_clear()
    database.configure(f"sqlite:///{pkg / 'data' / 'app.db'}")
    fresh = TestClient(app)
    cfg = fresh.get("/api/s/alpha").json()
    assert cfg["branding"]["show"] is False and cfg["booking_enabled"] is True and cfg["subscription_state"] == "active"
    assert fresh.get("/api/s/beta").status_code == 404  # the other studio does not exist here
    assert cfg["hero_url"] and fresh.get(cfg["hero_url"]).status_code == 200  # photos came along
    login = fresh.post("/api/s/alpha/owner/login", json={"email": "owner@alpha.test", "password": PWD})
    assert login.status_code == 200
    assert len(fresh.get("/api/s/alpha/owner/schedule", params={"days": 31}).json()["bookings"]) == 1
    host = fresh.get("/api/internal/host", params={"host": "book.alpha.ru"}, headers={"X-Internal-Token": get_settings().internal_token})
    assert host.json()["slug"] == "alpha"
    sid = service_id(fresh, "alpha")
    again = fresh.post("/api/s/alpha/bookings", json={**BOOK, "phone": "+7 900 000-00-10", "service_id": sid, "start_min": first_slot(fresh, "alpha", sid)}, headers={"Idempotency-Key": "on-own-server-01"})
    assert again.status_code == 201  # a new booking works on the exported database


def test_export_without_history_and_guards(sold):
    result = exporter.export_studio("alpha", out_dir=sold / "exports", domain="book.alpha.ru", with_bookings=False)
    db = sqlite3.connect(extract(result["archive"], sold / "unpacked") / "data" / "app.db")
    assert db.execute("select count(*) from bookings").fetchone()[0] == 0 and db.execute("select count(*) from clients").fetchone()[0] == 0
    assert db.execute("select count(*) from services").fetchone()[0] > 0
    for bad_domain in ("localhost", "1.2.3.4", "single"):
        with pytest.raises(exporter.ExportError):
            exporter.export_studio("alpha", out_dir=sold / "exports", domain=bad_domain)
    with pytest.raises(exporter.ExportError):
        exporter.export_studio("ghost", out_dir=sold / "exports", domain="book.ghost.ru")
    publish(sold, "draft", activate=False)
    with pytest.raises(exporter.ExportError) as e:
        exporter.export_studio("draft", out_dir=sold / "exports", domain="book.draft.ru")
    assert "not live" in str(e.value)


# ------------------------------------------------------------ sales workflow
def test_sample_then_handover_workflow(app_db, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tenants, "tenants_root", lambda: tmp_path / "tenants")
    photos = tmp_path / "photos"
    photos.mkdir()
    for i, c in enumerate([(200, 30, 30), (30, 200, 30), (30, 30, 200)]):
        (photos / f"{i}.png").write_bytes(png(c))
    assert cli.main(["tenant:sample", "avto-test", "--name", "Автосервис Тест", "--type", "auto", "--phone", "+7 900 111-22-33", "--address", "Казань, ул. Тестовая, 1", "--photos", str(photos)]) == 0
    out = capsys.readouterr().out
    assert "/s/avto-test/" in out
    with database.read_session() as db:
        t = db.scalar(select(Tenant).where(Tenant.slug == "avto-test"))
        assert (t.status, t.plan, t.trial_ends_at, t.paid_until) == ("preview", "standard", None, None)
    root = tmp_path / "tenants" / "avto-test"
    assert (root / "hero.jpg").exists() and (root / "work-2.jpg").exists() and not (root / "work-3.jpg").exists()
    cfg = tenants.validate(root)
    assert cfg.name == "Автосервис Тест" and cfg.phone == "+7 900 111-22-33" and len(cfg.gallery) == 2
    assert cli.main(["tenant:sample", "avto-test", "--name", "x"]) == 1  # never overwrites

    monkeypatch.setenv("OWNER_PW", "long-owner-password-1")
    assert cli.main(["tenant:handover", "avto-test", "--email", "Boss@Avto.ru", "--plan", "domain", "--password-env", "OWNER_PW"]) == 0
    text = capsys.readouterr().out
    assert "boss@avto.ru" in text and "long-owner-password-1" in text and "/s/avto-test/owner" in text
    with database.read_session() as db:
        t = db.scalar(select(Tenant).where(Tenant.slug == "avto-test"))
        assert (t.status, t.plan, t.trial_ends_at, t.paid_until) == ("active", "domain", None, None)  # lifetime: no trial, no dates
    c = TestClient(app)
    assert c.get("/api/s/avto-test").json()["subscription_state"] == "active"
    assert c.post("/api/s/avto-test/owner/login", json={"email": "boss@avto.ru", "password": "long-owner-password-1"}).status_code == 200
    with pytest.raises(SystemExit):  # unknown package names are rejected by the command line itself
        cli.main(["tenant:handover", "avto-test", "--email", "boss@avto.ru", "--plan", "gold"])


def test_sample_without_photos_and_export_command(app_db, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tenants, "tenants_root", lambda: tmp_path / "tenants")
    monkeypatch.setattr(exporter, "REPO", exporter.REPO)
    assert cli.main(["tenant:sample", "salon-test", "--name", "Салон Тест", "--type", "beauty_studio"]) == 0
    assert cli.main(["tenant:handover", "salon-test", "--email", "s@salon.ru", "--plan", "self_hosted"]) == 0
    capsys.readouterr()
    assert cli.main(["tenant:export", "salon-test", "--domain", "book.salon.ru", "--out", str(tmp_path / "out")]) == 0
    assert "package:" in capsys.readouterr().out and list((tmp_path / "out").glob("salon-test-package-*.tar.gz"))
    assert cli.main(["tenant:export", "salon-test", "--domain", "nope", "--out", str(tmp_path / "out")]) == 1


def test_lifetime_is_the_default_and_trials_are_opt_in(app_db, tmp_path, monkeypatch):
    from app.services import subscription

    t = Tenant(slug="x", status="active")
    subscription.start_trial(t)
    assert t.trial_ends_at is None and subscription.state_of(t) == "active"
    monkeypatch.setenv("TRIAL_DAYS", "14")
    get_settings.cache_clear()
    subscription.start_trial(t)
    assert t.trial_ends_at is not None and subscription.state_of(t) == "trial"
