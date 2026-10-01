"""Package one studio for the customer's own server: its own database (only this studio), its photos,
the application code, a ready .env, a Caddyfile for their domain and an installer.

The package contains no other studio's data. Plan `self_hosted` hides «Работает на …»; the operator
panel is switched off (ADMIN_ENABLED=false)."""
import secrets
import shutil
import sqlite3
import tarfile
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.engine import make_url

from .. import db as database
from ..config import API_ROOT, get_settings
from ..models import Membership, Tenant, TenantSettings, now_s
from . import domains

REPO = API_ROOT.parent
TEMPLATES = REPO / "deploy" / "selfhosted"

CODE_IGNORE = shutil.ignore_patterns(
    ".venv", "__pycache__", "*.pyc", ".pytest_cache", "data", "tests", "node_modules", ".next", "test-results", "playwright-report",
    "e2e", "shot*.mjs", "probe*.mjs", "_sw.js", ".claude", "*.tsbuildinfo", ".env", "requirements-dev.txt", "requirements.lock", "playwright.config.ts",
    "vitest.config.ts", "*.test.ts",
)

# tables copied for the exported studio, in dependency order, with their tenant filter
_TENANT_TABLES = ["tenant_settings", "resources", "services", "service_resources", "working_hours", "resource_hours", "resource_exceptions", "schedule_exceptions", "gallery_photos"]
_BOOKING_TABLES = ["clients", "bookings", "resource_occupancies", "occupancy_cells", "payments"]


class ExportError(Exception):
    pass


def _source_db_path() -> Path:
    url = make_url(get_settings().db_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise ExportError("export needs a SQLite database")
    return Path(url.database)


def _migrate(target: Path) -> None:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{target}")
    command.upgrade(cfg, "head")


def _copy_database(source: Path, target: Path, tenant_id: int, domain: str, with_bookings: bool) -> dict:
    _migrate(target)
    con = sqlite3.connect(target)
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("ATTACH DATABASE ? AS src", (str(source),))
        con.execute("INSERT INTO main.tenants SELECT * FROM src.tenants WHERE id = ?", (tenant_id,))
        con.execute(
            "UPDATE main.tenants SET plan='self_hosted', status='active', trial_ends_at=NULL, paid_until=NULL, suspended=0, notes='', published_at=COALESCE(published_at, ?)",
            (now_s(),),
        )
        con.execute("INSERT INTO main.users SELECT * FROM src.users WHERE id IN (SELECT user_id FROM src.memberships WHERE tenant_id = ?)", (tenant_id,))
        con.execute("INSERT INTO main.memberships SELECT * FROM src.memberships WHERE tenant_id = ?", (tenant_id,))
        tables = _TENANT_TABLES + (_BOOKING_TABLES if with_bookings else [])
        for table in tables:
            con.execute(f"INSERT INTO main.{table} SELECT * FROM src.{table} WHERE tenant_id = ?", (tenant_id,))
        con.execute("INSERT INTO main.tenant_domains (tenant_id, host, status, verified_at, created_at) VALUES (?, ?, 'active', ?, ?)", (tenant_id, domain, now_s(), now_s()))
        con.commit()
        bad = con.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise ExportError(f"foreign key check failed: {bad[:3]}")
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ExportError("integrity check failed")
        stats = {
            "owners": con.execute("SELECT count(*) FROM memberships").fetchone()[0],
            "bookings": con.execute("SELECT count(*) FROM bookings").fetchone()[0] if with_bookings else 0,
        }
        con.execute("DETACH DATABASE src")
        con.execute("PRAGMA journal_mode=DELETE")  # one clean file, no -wal/-shm
        con.execute("VACUUM")
        return stats
    finally:
        con.close()


def _env_file(domain: str, name: str) -> str:
    # no inline comments (systemd's EnvironmentFile does not strip them); values with spaces are quoted so that
    # both systemd and `. .env` in a shell read them correctly
    name = "".join(ch for ch in name if ch not in '"$`\\\n')
    return "\n".join(
        [
            "DATA_DIR=/srv/clientus/data",
            f"SECRET_KEY={secrets.token_hex(32)}",
            f"INTERNAL_TOKEN={secrets.token_hex(24)}",
            "COOKIE_SECURE=true",
            f"PUBLIC_ORIGINS=https://{domain}",
            "PLATFORM_HOSTS=localhost,127.0.0.1",
            f'PLATFORM_NAME="{name}"',
            "PLATFORM_URL=",
            "PLATFORM_IPS=",
            "ADMIN_ENABLED=false",
            "TRIAL_DAYS=0",
            "INTERNAL_API_URL=http://127.0.0.1:8000",
            "VAPID_PUBLIC_KEY=",
            "VAPID_PRIVATE_KEY_PATH=/srv/clientus/data/vapid_private.pem",
            f"VAPID_SUBJECT=mailto:admin@{domain}",
            "VSELLM_BASE_URL=",
            "VSELLM_TOKEN=",
            "VSELLM_MODEL=",
            "NEXT_PUBLIC_LIQUID_GL=",
            "",
        ]
    )


def _render(template: Path, values: dict[str, str]) -> str:
    text = template.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(f"@{key}@", value)
    return text


def export_studio(slug: str, *, out_dir: Path, domain: str, with_bookings: bool = True) -> dict:
    try:
        host = domains.normalize_host(domain)
    except domains.DomainError as exc:
        raise ExportError(f"invalid domain: {exc.code}") from exc
    with database.read_session() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
        if not tenant:
            raise ExportError(f"studio '{slug}' not found")
        if tenant.status != "active":
            raise ExportError(f"studio '{slug}' is not live (status: {tenant.status}); hand it over first")
        if not db.scalar(select(Membership).where(Membership.tenant_id == tenant.id)):
            raise ExportError(f"studio '{slug}' has no owner")
        tid = tenant.id
        with database.read_session(tid) as scoped:
            name = scoped.scalar(select(TenantSettings.name)) or slug

    pkg = Path(out_dir) / f"{slug}-package"
    if pkg.exists():
        shutil.rmtree(pkg)
    (pkg / "data").mkdir(parents=True)

    # 1. code (no other studio's data, no development files)
    shutil.copytree(REPO / "api", pkg / "api", ignore=CODE_IGNORE)
    shutil.copytree(REPO / "web", pkg / "web", ignore=CODE_IGNORE)
    shutil.copytree(REPO / "deploy", pkg / "deploy", ignore=shutil.ignore_patterns("selfhosted", "Caddyfile", "nginx.conf"))
    (pkg / "scripts").mkdir()
    shutil.copy(REPO / "scripts" / "py.sh", pkg / "scripts" / "py.sh")
    shutil.copy(REPO / "package.json", pkg / "package.json")
    (pkg / "web" / "public").mkdir(exist_ok=True)

    # 2. this studio's data
    stats = _copy_database(_source_db_path(), pkg / "data" / "app.db", tid, host, with_bookings)
    media_src = get_settings().media_dir / slug
    if media_src.is_dir():
        shutil.copytree(media_src, pkg / "data" / "media" / slug)
    cfg_src = REPO / "tenants" / slug
    if cfg_src.is_dir():
        shutil.copytree(cfg_src, pkg / "tenants" / slug)
    else:
        (pkg / "tenants").mkdir()

    # 3. configuration and installer
    values = {"DOMAIN": host, "SLUG": slug, "NAME": name}
    (pkg / ".env").write_text(_env_file(host, name), encoding="utf-8")
    (pkg / "Caddyfile").write_text(_render(TEMPLATES / "Caddyfile.tmpl", values), encoding="utf-8")
    (pkg / "install.sh").write_text(_render(TEMPLATES / "install.sh", values), encoding="utf-8")
    (pkg / "install.sh").chmod(0o755)
    (pkg / "README-INSTALL.md").write_text(_render(TEMPLATES / "README-INSTALL.md.tmpl", values), encoding="utf-8")

    # 4. archive
    archive = Path(out_dir) / f"{slug}-package-{datetime.now():%Y%m%d}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(pkg, arcname=f"{slug}-package")
    return {"archive": str(archive), "dir": str(pkg), "size_mb": archive.stat().st_size / 1_048_576, **stats}
