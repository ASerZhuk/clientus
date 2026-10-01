from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.models import Base

target_metadata = Base.metadata


def _url() -> str:
    return context.config.get_main_option("sqlalchemy.url") or get_settings().db_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
        conn.commit()  # persist alembic_version together with the DDL
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
