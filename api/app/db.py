"""SQLite engines: WAL, foreign keys ON, writes under BEGIN IMMEDIATE.

Two engines share one file: the read engine opens deferred transactions,
the write engine takes the write lock at BEGIN so a check-then-insert
sequence cannot interleave with another writer.
"""
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from . import tenancy  # noqa: F401  (registers the tenant-scoping session events)
from .config import get_settings

_state: dict = {}


def _make_engine(url: str, immediate: bool) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        dbapi_conn.isolation_level = None  # we emit BEGIN ourselves
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=15000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE" if immediate else "BEGIN")

    return engine


def configure(url: str | None = None) -> None:
    """(Re)build engines. Tests call this with a temp database."""
    for key in ("read_engine", "write_engine"):
        if key in _state:
            _state[key].dispose()
    url = url or get_settings().db_url
    _state["read_engine"] = _make_engine(url, immediate=False)
    _state["write_engine"] = _make_engine(url, immediate=True)
    _state["read_factory"] = sessionmaker(_state["read_engine"], expire_on_commit=False)
    _state["write_factory"] = sessionmaker(_state["write_engine"], expire_on_commit=False)


def _ensure() -> None:
    if "read_engine" not in _state:
        configure()


def write_engine() -> Engine:
    _ensure()
    return _state["write_engine"]


@contextmanager
def read_session(tenant_id: int | None = None) -> Iterator[Session]:
    _ensure()
    db: Session = _state["read_factory"]()
    if tenant_id is not None:
        db.info["tenant_id"] = tenant_id
    try:
        yield db
    finally:
        db.close()  # releases the connection; loaded attributes stay readable


@contextmanager
def write_session(tenant_id: int | None = None) -> Iterator[Session]:
    """One BEGIN IMMEDIATE transaction; commit on success, rollback on error."""
    _ensure()
    db: Session = _state["write_factory"]()
    if tenant_id is not None:
        db.info["tenant_id"] = tenant_id
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
