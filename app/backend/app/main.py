from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.core.database import init_database


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_database()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str | None]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "provider_mode": settings.provider_mode,
        "operator_runtime_mode": "dev_test" if settings.provider_mode == "mock" else "real_lab",
        "expected_runtime_mode": "local-lab-readwrite",
        "dev_test_banner": (
            "PROVIDER_MODE=mock is test mode only. Real lab status, reports, and certification require local-lab-readwrite."
            if settings.provider_mode == "mock"
            else None
        ),
    }


app.include_router(router)
