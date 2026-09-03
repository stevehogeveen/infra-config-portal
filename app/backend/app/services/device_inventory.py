from __future__ import annotations

import os
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    DeviceInventory,
    DeviceInventoryState,
    HpeRaidIntent,
    IloDeviceCredential,
    IloSetupIntent,
)


class DeviceInventoryNotFoundError(LookupError):
    pass


class DeviceInventoryAddressModeError(ValueError):
    pass


# ESXi is deliberately absent: it is software installed on a server, not a
# rack unit of its own. The rack shows it inside the machine that runs it,
# so seeding a standalone "ESXi Host" put the same hypervisor in two places.
SEED_DEVICES = (
    ("cisco-primary", "cisco_switch", "Cisco Switch", "CISCO_TARGET_IP"),
    ("ilo-primary", "ilo", "HPE iLO", "ILO_TEST_HOST"),
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
    seed_legacy_devices(session)
    _sync_dhcp_observed_hosts(session)
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
    effective_dhcp = payload.get("dhcp_enabled", device.dhcp_enabled)
    if "host" in payload and effective_dhcp:
        raise DeviceInventoryAddressModeError(
            "Host cannot be edited while DHCP is enabled; it is the last observed address."
        )
    for key, value in payload.items():
        setattr(device, key, value)
    session.commit()
    session.refresh(device)
    return device


def delete_device(session: Session, device_id: str) -> None:
    device = session.get(DeviceInventory, device_id)
    if device is None:
        raise DeviceInventoryNotFoundError(device_id)
    # SQLite does not enforce ON DELETE CASCADE unless a connection-level
    # pragma is enabled. Delete sensitive/device-scoped rows explicitly so
    # the normal local runtime cannot leave credentials or intents orphaned.
    for model in (IloDeviceCredential, IloSetupIntent, HpeRaidIntent):
        session.execute(delete(model).where(model.device_id == device_id))
    session.delete(device)
    session.commit()


def seed_legacy_devices(session: Session) -> None:
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


# Where a DHCP device's observed address comes from, per seeded device. These
# are the same provider-config sources the seed used: the address the app is
# actually using to reach the device right now.
DHCP_OBSERVED_HOST_SOURCES = {
    "cisco-primary": "CISCO_TARGET_IP",
    "esxi-primary": "ESXI_TEST_HOST",
    "netapp-primary": "NETAPP_CLUSTER_MGMT_IP",
    "vcenter-primary": "VCENTER_HOST",
}


def _sync_dhcp_observed_hosts(session: Session) -> None:
    """Keep DHCP-mode seeded devices' observed address current.

    Only DHCP devices are touched: their host is observed evidence, owned by
    the app. A static device's host belongs to the operator and is never
    overwritten here. iLO access updates synchronize only their selected
    inventory row in ilo_access_settings.

    Custom (non-seeded) DHCP devices have no observation source yet, so their
    last-known host is left as-is.
    """
    changed = False
    for seed_key, env_key in DHCP_OBSERVED_HOST_SOURCES.items():
        device = session.scalar(
            select(DeviceInventory).where(
                DeviceInventory.seed_key == seed_key,
                DeviceInventory.dhcp_enabled.is_(True),
            )
        )
        if device is None:
            continue
        observed = (os.getenv(env_key) or "").strip() or None
        if observed and device.host != observed:
            device.host = observed
            changed = True
    if changed:
        session.commit()
