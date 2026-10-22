from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import socket

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.automation import router as automation_router
from app.api.rack_plans import router as rack_plans_router
from app.api.disk_preparation import router as disk_preparation_router
from app.api.firmware_review import router as firmware_review_router
from app.api.firmware_execution import router as firmware_execution_router
from app.api.drive_return_to_service import router as drive_return_to_service_router
from app.api.raid_rebuild import router as raid_rebuild_router
from app.api.esxi_install import router as esxi_install_router
from app.api.parts_update import router as parts_update_router
from app.api.windows_deploy import router as windows_deploy_router
from app.api.kit_contract import router as kit_contract_router
from app.api.switch_access import router as switch_access_router
from app.api.switch_setup import router as switch_setup_router
from app.api.build_history import router as build_history_router
from app.api.kit_jobs import router as kit_jobs_router
from app.api.kit_reset import router as kit_reset_router
from app.api.kit_insight import router as kit_insight_router
from app.api.runtime_write_scope import router as runtime_write_scope_router
from app.api.spp_update import router as spp_update_router
from app.services.runtime_write_scope import WriteScopeActivityMiddleware
from app.core.config import settings
from app.core.database import init_database


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    init_database()
    worker = None
    provider = getattr(application.state, "spp_backend", None)
    if provider is None and settings.provider_mode == "local-lab-readwrite":
        from app.core.database import SessionLocal
        from app.providers.hpe_spp_boot import OfflineTransport
        from app.services.spp_offline_boot import OfflineBackend

        provider = OfflineBackend(SessionLocal, OfflineTransport())
        application.state.spp_backend = provider
    if provider is not None:
        from app.core.database import SessionLocal
        from app.services.spp_update_runtime import Worker

        worker = Worker(SessionLocal, provider)
        worker.start()
    try:
        yield
    finally:
        if worker is not None:
            worker.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_without_input(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Like FastAPI's default 422, minus the echoed input: a rejected field may be a password."""
    errors = [{key: value for key, value in error.items() if key not in {"input", "ctx", "url"}} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})
app.add_middleware(WriteScopeActivityMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str | list[str] | None]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "provider_mode": settings.provider_mode,
        "operator_runtime_mode": "dev_test" if settings.provider_mode == "mock" else "real_lab",
        "expected_runtime_mode": "local-lab-readwrite",
        "lab_subnet_cidr": settings.lab_subnet_cidr,
        "host_ipv4_addresses": _host_ipv4_addresses(),
        "dev_test_banner": (
            "PROVIDER_MODE=mock is test mode only. Real lab status, reports, and certification require local-lab-readwrite."
            if settings.provider_mode == "mock"
            else None
        ),
    }


def _host_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    hostnames = {socket.gethostname(), socket.getfqdn()}
    for hostname in hostnames:
        try:
            for _, _, _, _, sockaddr in socket.getaddrinfo(hostname, None, socket.AF_INET):
                address = sockaddr[0]
                if address and not address.startswith("127."):
                    addresses.add(address)
        except OSError:
            continue
    try:
        for address in socket.gethostbyname_ex(socket.gethostname())[2]:
            if address and not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


app.include_router(router)
app.include_router(automation_router)
app.include_router(rack_plans_router)
app.include_router(disk_preparation_router)
app.include_router(firmware_review_router)
app.include_router(firmware_execution_router)
app.include_router(drive_return_to_service_router)
app.include_router(raid_rebuild_router)
app.include_router(esxi_install_router)
app.include_router(parts_update_router)
app.include_router(windows_deploy_router)
app.include_router(kit_contract_router)
app.include_router(switch_access_router)
app.include_router(switch_setup_router)
app.include_router(build_history_router)
app.include_router(kit_jobs_router)
app.include_router(kit_reset_router)
app.include_router(kit_insight_router)
app.include_router(runtime_write_scope_router)
app.include_router(spp_update_router)
