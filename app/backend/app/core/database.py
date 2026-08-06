from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _connect_args(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return

    db_path = database_url.removeprefix("sqlite:///")
    if db_path in (":memory:", ""):
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent(settings.database_url)

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args(settings.database_url),
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_database() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_device_inventory_dhcp_column(engine)


def ensure_device_inventory_dhcp_column(target_engine: Engine) -> None:
    """Upgrade pre-inventory SQLite databases without requiring Alembic."""
    if target_engine.dialect.name != "sqlite":
        return
    inspector = inspect(target_engine)
    if "device_inventory" not in inspector.get_table_names():
        return
    if "dhcp_enabled" in {column["name"] for column in inspector.get_columns("device_inventory")}:
        return
    # SQLite runs this single ADD COLUMN atomically. A process can therefore
    # restart safely after either the old or new schema, with existing rows
    # receiving the false default.
    with target_engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE device_inventory "
            "ADD COLUMN dhcp_enabled BOOLEAN NOT NULL DEFAULT 0"
        ))
