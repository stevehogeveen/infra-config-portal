from __future__ import annotations

import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import DeviceInventory, DeviceInventoryState
from app.services.ilo_access_settings import read_ilo_access_settings


class DeviceInventoryNotFoundError(LookupError):
    pass


SEED_DEVICES = (
    ("cisco-primary", "cisco_switch", "Cisco Switch", "CISCO_TARGET_IP"),
    ("ilo-primary", "ilo", "HPE iLO", "ILO_TEST_HOST"),
    ("esxi-primary", "esxi_host", "ESXi Host", "ESXI_TEST_HOST"),
    ("netapp-primary", "netapp", "NetApp ONTAP", "NETAPP_CLUSTER_MGMT_IP"),
)


def _seed_devices() -> tuple[tuple[str, str, str, str], ...]:
    # vCenter is part of the lab only when it is actually configured; labs
    # without one (VCENTER_CONFIGURED unset/false and no host) get no phantom
    # node, while labs that had a vCenter on the old profile-driven map keep it.
    if (os.getenv("VCENTER_CONFIGURED") or "").strip().lower() == "true" or (
        os.getenv("VCENTER_HOST") or ""
    ).strip():
        return SEED_DEVICES + (("vcenter-primary", "vcenter", "vCenter", "VCENTER_HOST"),)
    return SEED_DEVICES


def list_devices(session: Session) -> list[DeviceInventory]:
    _seed_legacy_devices(session)
    _sync_primary_ilo_host(session)
    return list(session.scalars(select(DeviceInventory).order_by(DeviceInventory.created_at, DeviceInventory.id)))


def create_device(session: Session, payload: dict[str, Any]) -> DeviceInventory:
    device = DeviceInventory(**payload)
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


def update_device(session: Session, device_id: str, payload: dict[str, Any]) -> DeviceInventory:
    device = session.get(DeviceInventory, device_id)
    if device is None:
        raise DeviceInventoryNotFoundError(device_id)
    for key, value in payload.items():
        setattr(device, key, value)
    session.commit()
    session.refresh(device)
    return device


def delete_device(session: Session, device_id: str) -> None:
    device = session.get(DeviceInventory, device_id)
    if device is None:
        raise DeviceInventoryNotFoundError(device_id)
    session.delete(device)
    session.commit()


def _seed_legacy_devices(session: Session) -> None:
    if session.get(DeviceInventoryState, "legacy-seed-v1") is not None:
        return
    # The marker is not the only source of truth: a crashed or concurrent
    # earlier request can leave seed rows behind without the marker, and the
    # seed_key UNIQUE constraint would then 500 every list call forever.
    # Skip rows that already exist, and treat a lost insert race as success.
    existing_seed_keys = set(
        session.scalars(
            select(DeviceInventory.seed_key).where(DeviceInventory.seed_key.is_not(None))
        )
    )
    try:
        for seed_key, device_type, display_name, env_key in _seed_devices():
            if seed_key in existing_seed_keys:
                continue
            host = os.getenv(env_key) or None
            session.add(DeviceInventory(
                device_type=device_type,
                display_name=display_name,
                host=host,
                notes="Imported from the existing lab profile/provider configuration.",
                seed_key=seed_key,
            ))
        session.add(DeviceInventoryState(id="legacy-seed-v1"))
        session.commit()
    except IntegrityError:
        # A concurrent request seeded first; its commit carries the marker.
        session.rollback()


def _sync_primary_ilo_host(session: Session) -> None:
    device = session.scalar(select(DeviceInventory).where(DeviceInventory.seed_key == "ilo-primary"))
    if device is None:
        return
    canonical_host = read_ilo_access_settings().get("host")
    if device.host != canonical_host:
        device.host = canonical_host
        session.commit()
