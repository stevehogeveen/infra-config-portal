from __future__ import annotations

import asyncio
from collections.abc import Generator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
import fastapi.concurrency
import fastapi.dependencies.utils
import fastapi.routing
import starlette.concurrency
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.core.database import Base, get_session
from app.main import app


async def _run_sync_inline(func: Any, *args: Any, **kwargs: Any) -> Any:
    return func(*args, **kwargs)


@asynccontextmanager
async def _contextmanager_inline(cm: Any) -> Any:
    try:
        value = cm.__enter__()
    except AttributeError:
        value = next(cm)
    try:
        yield value
    except Exception as exc:
        if hasattr(cm, "__exit__"):
            suppress = bool(cm.__exit__(type(exc), exc, exc.__traceback__))
        else:
            suppress = False
            try:
                cm.throw(type(exc), exc, exc.__traceback__)
            except StopIteration:
                suppress = True
        if not suppress:
            raise
    else:
        if hasattr(cm, "__exit__"):
            cm.__exit__(None, None, None)
        else:
            try:
                next(cm)
            except StopIteration:
                pass


fastapi.routing.run_in_threadpool = _run_sync_inline
fastapi.routing.contextmanager_in_threadpool = _contextmanager_inline
fastapi.concurrency.contextmanager_in_threadpool = _contextmanager_inline
fastapi.dependencies.utils.contextmanager_in_threadpool = _contextmanager_inline
starlette.concurrency.run_in_threadpool = _run_sync_inline


class ASGITestClient:
    def __init__(self, app_: Any) -> None:
        self.app = app_
        self.base_url = "http://testserver"

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=True)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(send())

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)

    def close(self) -> None:
        return None


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
def client(db_session: Session) -> Generator[ASGITestClient, None, None]:
    def override_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    test_client = ASGITestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
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
