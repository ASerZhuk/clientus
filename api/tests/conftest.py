import os
import shutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app import db as database
from app.config import get_settings

API_ROOT = Path(__file__).resolve().parents[1]
os.environ["VSELLM_TOKEN"] = ""  # tests never call the external LLM, whatever .env says


@pytest.fixture(scope="session")
def template_db(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("tpl") / "template.db"
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "head")
    return path


@pytest.fixture()
def app_db(tmp_path, monkeypatch, template_db):
    """Fresh migrated database + media dir per test."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    target = tmp_path / "app.db"
    shutil.copy(template_db, target)
    database.configure(f"sqlite:///{target}")
    yield target
    get_settings.cache_clear()


@pytest.fixture()
def make_client(app_db):
    from fastapi.testclient import TestClient

    from app.main import app

    def factory() -> TestClient:
        return TestClient(app, base_url="http://testserver")

    return factory


@pytest.fixture()
def client(make_client):
    return make_client()
