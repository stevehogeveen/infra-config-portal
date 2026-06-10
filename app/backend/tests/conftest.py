from __future__ import annotations

import asyncio
import functools
import os
import threading
from collections.abc import Generator
from concurrent.futures import Future
from datetime import date, timedelta
from typing import Any

import anyio.to_thread
import fastapi.routing
import httpx
import pytest
import starlette.concurrency
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.core.database import Base, get_session
from app.main import app


@pytest.fixture(autouse=True)
def isolate_local_lab_state(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    if "LAB_PROFILE_STORE" not in os.environ:
        monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    if "CONTROL_ACCESS_STORE" not in os.environ:
        monkeypatch.setenv("CONTROL_ACCESS_STORE", str(tmp_path / "control-access.json"))


async def _run_sync_with_asyncio_executor(
    func: Any,
    *args: Any,
    abandon_on_cancel: bool = False,
    cancellable: bool | None = None,
    limiter: Any = None,
) -> Any:
    del abandon_on_cancel, cancellable, limiter
    future: Future[Any] = Future()

    def run() -> None:
        try:
            result = func(*args)
        except BaseException as exc:
            future.set_exception(exc)
        else:
            future.set_result(result)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        while not future.done():
            await asyncio.sleep(0.001)
        return future.result()
    finally:
        thread.join(timeout=1)


anyio.to_thread.run_sync = _run_sync_with_asyncio_executor


async def _run_in_threadpool(func: Any, *args: Any, **kwargs: Any) -> Any:
    return await _run_sync_with_asyncio_executor(
        functools.partial(func, **kwargs),
        *args,
    )


fastapi.routing.run_in_threadpool = _run_in_threadpool
starlette.concurrency.run_in_threadpool = _run_in_threadpool


class SyncASGITestClient:
    def __init__(self) -> None:
        self._transport = httpx.ASGITransport(app=app)
        self._base_url = "http://testserver"

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async def send() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=self._transport,
                base_url=self._base_url,
            ) as client:
                return await client.request(method, url, **kwargs)

        return anyio.run(send)


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
    yield SyncASGITestClient()  # type: ignore[misc]
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
