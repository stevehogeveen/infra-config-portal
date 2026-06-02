from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.core.database import Base, get_session
from app.main import app


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def vm_payload() -> dict:
    return {
        "requester": "alex.admin",
        "environment": "dev",
        "site": "lab-a",
        "cluster": "compute-a",
        "vm_name": "app-dev-001",
        "template": "ubuntu-24.04",
        "cpu": 2,
        "memory_gb": 8,
        "disk_gb": 80,
        "network": "dev-vlan-100",
        "storage_tier": "silver",
        "owner": "platform-team",
        "expiry_date": (date.today() + timedelta(days=30)).isoformat(),
        "notes": "MVP mock request",
    }
