"""Desired kit document and bounded, approval-bound installer ticks.

Reads use records only. All discovery, review and dispatch is confined to _tick,
which is called exclusively by reconcile. Existing services own write admission,
duplicate-send protection and verification; this module never dispatches directly.

Admission rechecks the digest under _lock immediately before each dispatch.
Residual race: settings writers do not share this lock; downstream services reread
settings. A concurrent commit after the check can still change dispatched inputs.
This is not an atomic database snapshot or cross-process admission lock.
Whole-SPP updates must be admitted separately in Check firmware, never here.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime

from sqlalchemy import select

from app.models import AuditEvent
from app.services import (
    acceptance,
    esxi_install,
    handover,
    parts_update,
    runtime_write_scope,
    switch_setup,
    windows_deploy,
)
from app.services.audit import record_audit_event

ORDER = ("connect", "switch", "firmware", "raid", "esxi", "windows", "acceptance")
TITLES = dict(
    zip(ORDER, ("Connect", "Switch setup", "Firmware", "RAID", "ESXi", "Windows", "Acceptance"))
)
LINKS = dict(
    zip(
        ORDER,
        (
            "/setup/connect",
            "/setup/connect",
            "/setup/check-firmware",
            "/setup/disks",
            "/setup/prepare-esxi",
            "/setup/install-windows",
            "/setup/install-windows",
        ),
    )
)
SCOPES = {
    "switch": "switch_setup_only",
    "firmware": "firmware_only",
    "raid": "storage_only",
    "esxi": "esxi_install_only",
    "windows": "vm_deploy_only",
    "acceptance": "vm_deploy_only",
}
_lock = threading.Lock()  # overlapping browser polls must not interleave power/RAID sequences


class ContractError(ValueError):
    pass


def _latest(session, event_type, **match):
    query = select(AuditEvent).where(AuditEvent.event_type == event_type)
    for key, value in match.items():
        query = query.where(AuditEvent.data_json[key].as_string() == value)
    return session.scalar(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(1)
    )


def _settings(session, event, keys, **match):
    row = _latest(session, event, **match)
    return {key: (row.data_json if row else {}).get(key) for key in keys}


def _desired(session, profile_id):
    from app.api.rack_plans import get_plan, kit_profile
    from app.services.hpe_raid import get_hpe_raid_intent
    from app.services.ilo_access_settings import read_ilo_access_settings
    from app.services.lab_profiles import active_lab_profile_context

    profile = kit_profile(profile_id)
    network = esxi_install._kit(active_lab_profile_context(profile))
    network = {k: network.get(k) for k in ("subnet", "gateway", "dns", "ntp", "domain_name")}
    package = _settings(
        session, "kit.firmware_package_selected", ["package"], profile_id=profile_id
    )["package"]
    items = []
    for device in get_plan(profile_id, session).equipment:
        if not device.device_id or device.kind not in {"server", "switch"}:
            continue
        d = device.device_id
        if device.kind == "switch":
            setup = switch_setup.get_setup(session, d, device.name)
            values = {
                "switch": {
                    "settings": setup["settings"],
                    "username": setup["username"],
                    "console": {k: setup["console"].get(k) for k in ("port", "baud")},
                }
            }
        else:
            access = read_ilo_access_settings(session, d)
            esxi = _settings(
                session,
                "kit.esxi_settings_saved",
                [
                    "hostname",
                    "addressing",
                    "management_ip",
                    "vlan_id",
                    "management_nic",
                    "datastore_name",
                ],
                profile_id=profile_id,
                device_id=d,
            )
            media = _settings(
                session,
                "kit.esxi_media_selected",
                ["path", "name", "size_bytes"],
                profile_id=profile_id,
                device_id=d,
            )
            intent = get_hpe_raid_intent(session, d).model_dump(mode="json")
            raid = {k: intent.get(k) for k in ("controller_ref", "volumes")}
            # Lookup is desired configuration, never the last run's (possibly older) lookup.
            previous_test = _latest(
                session, "kit.acceptance.run", profile_id=profile_id, device_id=d
            )
            lookup = (
                previous_test.data_json.get("lookup") if previous_test else None
            ) or acceptance._default_lookup(session, profile_id, d)
            values = {
                "connect": {"host": access.get("host"), "username": access.get("username")},
                "firmware": {"package": package},
                "raid": raid,
                "esxi": {
                    **esxi,
                    "media": media,
                    "volumes": raid["volumes"],
                    "profile_version": profile.get("version"),
                    "network": network,
                    "disk_identities": _disk_identities(session, d),
                },
                "windows": _settings(
                    session,
                    "kit.windows.settings",
                    ["image", "vm_name", "datastore", "network"],
                    profile_id=profile_id,
                    device_id=d,
                ),
                "acceptance": {"lookup": lookup},
            }
        for step, desired in values.items():
            items.append(
                {
                    "id": f"{step}:{d}",
                    "step": step,
                    "device_id": d,
                    "title": f"{device.name} — {TITLES[step]}",
                    "desired": desired,
                    "href": LINKS[step],
                }
            )
    items.sort(key=lambda item: (ORDER.index(item["step"]), item["device_id"]))
    return {
        "profile_id": profile_id,
        "kit": profile.get("name"),
        "network": network,
        "items": items,
    }


def _contract(session, profile_id):
    """Stable desired values only: no probe timestamps, evidence or secrets in the hash."""
    data = _desired(session, profile_id)
    data["digest"] = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return data


def _disk_identities(session, device_id):
    # These helpers read recorded inventory only. Exclude read timestamps.
    return {
        kind: {key: (volume or {}).get(key) for key in ("disk_id", "bays")}
        for kind, volume in (
            ("boot", esxi_install._boot_volume(session, device_id)),
            ("data", esxi_install._data_volume(session, device_id)),
        )
    }


def _display(item):
    desired = item["desired"]
    if item["step"] == "firmware":
        package = desired.get("package") or {}
        desired = {key: package.get(key) for key in ("file_name", "release_hint", "size_bytes")}
    elif item["step"] == "esxi":
        network = desired.get("network") or {}
        desired = {
            **{
                key: desired.get(key)
                for key in (
                    "hostname",
                    "addressing",
                    "management_ip",
                    "vlan_id",
                    "management_nic",
                    "datastore_name",
                )
            },
            "media": (desired.get("media") or {}).get("name"),
            "network_summary": f"{network.get('subnet') or 'Not saved'} via {network.get('gateway') or 'Not saved'}",
        }
    return {**item, "desired": desired}


def contract(session, profile_id):
    data = _contract(session, profile_id)
    return {**data, "items": [_display(item) for item in data["items"]]}


def _dispatch(session, profile_id, function, *args, **kwargs):
    session.expire_all()
    approval = _latest(session, "kit.contract.approved", profile_id=profile_id)
    invalid = _latest(session, "kit.contract.invalidated", profile_id=profile_id)
    if (
        not approval
        or (invalid and invalid.created_at >= approval.created_at)
        or approval.data_json["digest"] != _contract(session, profile_id)["digest"]
    ):
        raise ContractError(
            "Contract drift: settings changed before dispatch. Review and approve again."
        )
    return function(*args, **kwargs)


def _raid_payload(payload):
    # planned_payload uses the same Redfish builder, then adds this default.
    return [
        {**volume, "SpareDrives": volume.get("SpareDrives") or []}
        for volume in payload.get("LogicalDrives", [])
    ]


def approve(session, profile_id, actor, digest):
    with _lock:
        current = _contract(session, profile_id)
        if digest != current["digest"]:
            raise ContractError("The contract changed. Read it again before approving.")
        record_audit_event(
            session,
            actor=actor,
            event_type="kit.contract.approved",
            message="Approved the desired kit contract and its installer changes.",
            data={"profile_id": profile_id, "digest": digest},
        )
        session.commit()
        return {"digest": digest, "state": "converging"}


def _plain(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _observed(session, profile_id, item):
    step, d = item["step"], item["device_id"]
    if step == "connect":
        from app.services.ilo_access_settings import read_ilo_access_settings

        access = read_ilo_access_settings(session, d)
        from app.services.status_source import DEFAULT_STALE_AFTER_SECONDS

        at = access.get("last_probe_time")
        try:
            fresh = (
                0
                <= (
                    datetime.now(UTC) - datetime.fromisoformat(at).replace(tzinfo=UTC)
                ).total_seconds()
                < DEFAULT_STALE_AFTER_SECONDS
            )
        except (ValueError, TypeError):
            fresh = False
        return {
            "state": "verified"
            if fresh
            and access.get("last_probe_status") == "ok"
            and access.get("last_probe_is_current")
            and access.get("last_probe_target_matches_access_host")
            else "not_checked",
            "active": False,
            "checked_at": at,
        }
    if step == "raid":
        from app.api.raid_rebuild import rebuild_status

        result = rebuild_status(profile_id, d, session)
        if result.get("operation") != "create" and not result.get("active"):
            return {**result, "state": "not_started"}
        attempt = (
            session.get(AuditEvent, result.get("attempt_id")) if result.get("attempt_id") else None
        )
        if attempt and result.get("status") == "verified":
            from app.services.hpe_raid import _redfish_settings_payload, get_hpe_raid_intent

            wanted = _raid_payload(_redfish_settings_payload(get_hpe_raid_intent(session, d)))
            result = {
                **result,
                "matches_desired": attempt.data_json.get("profile_id") == profile_id
                and _raid_payload(attempt.data_json.get("payload", {})) == wanted,
                "volumes": attempt.data_json.get("payload", {}).get("LogicalDrives"),
            }
        return {**result, "state": result["status"]}
    if step == "firmware":
        from app.services.spp_update_runtime import recorded_status

        parts = parts_update.status(session, profile_id, d)
        spp = _plain(recorded_status(session, profile_id, d))
        bad = next(
            (
                v
                for v in (parts, spp)
                if v.get("state", v.get("status")) in {"needs_attention", "uncertain", "failed"}
            ),
            None,
        )
        receipt = _latest(
            session, "kit.contract.firmware_checked", profile_id=profile_id, device_id=d
        )
        complete = (
            receipt
            and receipt.data_json.get("desired") == item["desired"]
            and receipt.data_json.get("parts_run_id") == parts.get("run_id")
            and receipt.data_json.get("disc_operation_id") == spp.get("operation_id")
            and not parts.get("active")
            and not spp.get("active")
        )
        return {
            "state": (bad or {}).get("state", (bad or {}).get("status"))
            or (
                "verified"
                if complete
                else "running"
                if parts.get("active") or spp.get("active")
                else "not_started"
            ),
            "active": bool(parts.get("active") or spp.get("active")),
            "message": (bad or {}).get("message", ""),
            "parts": parts,
            "spp": spp,
            "verified_at": receipt.created_at.isoformat() if complete else None,
        }
    service = {
        "switch": switch_setup.status,
        "esxi": esxi_install.install_status,
        "windows": windows_deploy.status,
        "acceptance": acceptance.status,
    }[step]
    observed = service(session, profile_id, d)
    # The underlying status remains authoritative. Bind its recorded run to saved
    # inputs as well: a green old run is not proof of a newly edited document.
    if observed.get("state") != "verified":
        return observed
    event = {
        "switch": "kit.switch",
        "esxi": "kit.esxi_install",
        "windows": "kit.windows",
        "acceptance": "kit.acceptance",
    }[step]
    run = _latest(session, event + ".run", profile_id=profile_id, device_id=d)
    if run:
        done = _latest(session, event + ".done", run_id=observed.get("run_id", ""))
        observed = {
            **observed,
            "verified_at": observed.get("verified_at")
            or (done.created_at.replace(tzinfo=UTC).isoformat() if done else None),
        }
        if step == "switch":
            saved = session.scalar(
                select(AuditEvent)
                .where(
                    AuditEvent.event_type == "kit.switch.settings",
                    AuditEvent.data_json["device_id"].as_string() == d,
                    AuditEvent.created_at <= run.created_at,
                )
                .order_by(AuditEvent.created_at.desc())
                .limit(1)
            )
            expected = item["desired"]
            matches = bool(saved) and all(
                saved.data_json.get(k) == v for k, v in (expected.get("settings") or {}).items()
            )
            matches = matches and run.data_json.get("username") == expected.get("username")
            matches = matches and all(
                v is None or run.data_json.get({"port": "console_port", "baud": "baud"}[k]) == v
                for k, v in expected.get("console", {}).items()
            )
            observed = {
                **observed,
                "matches_desired": matches,
                "settings": {k: saved.data_json.get(k) for k in switch_setup.SETTING_KEYS}
                if saved
                else None,
            }
        elif step == "esxi":
            built = session.scalar(
                select(AuditEvent)
                .where(
                    AuditEvent.event_type == "kit.esxi_installer_built",
                    AuditEvent.data_json["profile_id"].as_string() == profile_id,
                    AuditEvent.data_json["device_id"].as_string() == d,
                    AuditEvent.created_at <= run.created_at,
                )
                .order_by(AuditEvent.created_at.desc())
                .limit(1)
            )
            desired = item["desired"]
            matches = (
                bool(built)
                and built.data_json.get("iso_sha256") == run.data_json.get("iso_sha256")
                and built.data_json.get("media_path") == (desired.get("media") or {}).get("path")
                and built.data_json.get("profile_version") == desired.get("profile_version")
            )
            matches = matches and all(
                v is None or run.data_json.get(k) == v
                for k, v in desired.items()
                if k not in {"media", "network", "volumes", "profile_version", "disk_identities"}
            )
            proof = _latest(session, "kit.contract.esxi_inputs", profile_id=profile_id, device_id=d)
            matches = (
                matches
                and bool(proof)
                and proof.data_json.get("desired") == desired
                and proof.data_json.get("iso_sha256") == run.data_json.get("iso_sha256")
                and proof.created_at <= run.created_at
            )
            observed = {
                **observed,
                "matches_desired": matches,
                "vlan_id": run.data_json.get("vlan_id"),
                "management_nic": run.data_json.get("management_nic"),
                "profile_version": built.data_json.get("profile_version") if built else None,
            }
    return observed


def _matches(item, observed):
    if observed.get("state") != "verified" or observed.get("matches_desired") is False:
        return False
    # Status values are actual run inputs, never the current saved settings.
    fields = {
        "switch": {"hostname": (item["desired"].get("settings") or {}).get("hostname")},
        "esxi": {
            k: item["desired"].get(k)
            for k in ("hostname", "addressing", "management_ip", "datastore_name")
        },
        "windows": item["desired"],
        "acceptance": item["desired"],
    }.get(item["step"], {})
    return all(value is None or observed.get(key) == value for key, value in fields.items())


def _items(session, current):
    return [
        {
            **item,
            "observed": (observed := _observed(session, current["profile_id"], item)),
            "state": "verified"
            if _matches(item, observed)
            else "drift"
            if observed.get("state") == "verified"
            else observed.get("state", "not_checked"),
        }
        for item in current["items"]
    ]


def _scope(session, actor, target):
    if runtime_write_scope.state(session)["scope"] == target:
        return
    review = runtime_write_scope.preview(session, actor, target)
    if review.get("blockers"):
        raise ContractError(" ".join(review["blockers"]))
    runtime_write_scope.apply(
        session, actor, review["review_token"], review.get("confirmation_phrase") or ""
    )


def _lock_if_idle(session, actor, result):
    if not runtime_write_scope.active_operations(session):
        try:
            _scope(session, actor, "read_only")
        except Exception as exc:
            result.update(
                state="blocked",
                message=f"Could not return write permission to read-only: {exc}",
                href="/contract",
            )
    return result


def _check(review, ready=None):
    if review.get("blockers"):
        raise ContractError(str(review["blockers"][0]))
    if ready and not review.get(ready):
        raise ContractError("The reviewed operation is not ready. Open its settings to resolve it.")


def _probe(session, d):
    from app.api.routes import probe_provider

    result = _plain(probe_provider("ilo-redfish", d, session))
    if result["status"] != "ok":
        raise ContractError(result.get("message") or "The iLO did not answer. Open Connect.")


def _spp_backend():
    # Same installed vendor adapter as the existing firmware-update routes.
    from app.main import app

    provider = getattr(app.state, "spp_backend", None)
    if provider is None:
        raise ContractError("Whole-SPP vendor adapter is not configured. Open Check firmware.")
    return provider


def _firmware(session, p, d, actor, item):
    from app.services import spp_update_runtime as spp

    parts, disc = item["observed"]["parts"], item["observed"]["spp"]
    package_path = (item["desired"].get("package") or {}).get("path")
    receipt = _latest(session, "kit.contract.firmware_checked", profile_id=p, device_id=d)
    reviewed = _latest(session, "kit.contract.parts_reviewed", profile_id=p, device_id=d)
    same_parts = any(
        row
        and row.data_json.get("package_path") == package_path
        and row.data_json.get("parts_run_id") == parts.get("run_id")
        for row in (receipt, reviewed)
    )
    if disc.get("active"):
        raise ContractError(
            "An SPP run is active outside this contract. Open Check firmware to monitor it."
        )
    if parts.get("active"):
        _scope(session, actor, "firmware_only")
        return _dispatch(session, p, parts_update.advance, session, p, d, actor)
    if parts.get("state") != "verified" or not same_parts:
        review = parts_update.review(session, p, d, actor)
        _check(review)
        if review["parts"]:
            _scope(session, actor, "firmware_only")
            result = _dispatch(
                session, p, parts_update.start, session, p, d, actor, review["review_id"]
            )
            parts = parts_update.status(session, p, d)
            record_audit_event(
                session,
                actor=actor,
                event_type="kit.contract.parts_reviewed",
                message="Parts run bound to selected package.",
                data={
                    "profile_id": p,
                    "device_id": d,
                    "package_path": package_path,
                    "parts_run_id": parts.get("run_id"),
                },
            )
            session.commit()
            return result
    plan = _plain(spp.plan(session, _spp_backend(), p, d, actor))
    _check(plan)
    if plan["updates"]:
        raise ContractError("SPP updates needed. Open Check firmware to review and run the update.")
    record_audit_event(
        session,
        actor=actor,
        event_type="kit.contract.firmware_checked",
        message="Fresh firmware comparison verified; no SPP worker admitted.",
        data={
            "profile_id": p,
            "device_id": d,
            "desired": item["desired"],
            "package_path": package_path,
            "parts_run_id": parts.get("run_id"),
            "disc_operation_id": disc.get("operation_id"),
        },
    )
    session.commit()


def _raid(session, p, d, actor, observed):
    from app.api import raid_rebuild as raid
    from app.api.disk_preparation import disk_preparation

    if observed.get("active"):
        if observed.get("operation") != "create":
            raise ContractError("Another storage operation is unresolved. Open Disks & RAID.")
        _scope(session, actor, "storage_only")
        if observed["state"] == "staged":
            boot = raid.preview_boot(p, d, session, actor)
            _check(boot, "apply_enabled")
            return _dispatch(
                session,
                p,
                raid.apply_boot,
                p,
                d,
                raid.BootApply(
                    preview_id=boot["preview_id"],
                    confirmation=boot["confirmation"],
                    pending_changes_reviewed=True,
                    data_loss_confirmed=True,
                    maintenance_confirmed=True,
                ),
                session,
                actor,
            )
        return _dispatch(session, p, raid.verify_rebuild, p, d, session, actor)
    _dispatch(session, p, _probe, session, d)
    view = _plain(disk_preparation(p, d, session))
    _check(view)
    if view["volumes"]:
        raise ContractError(
            "Existing RAID volumes: keep or wipe them on Disks & RAID. The contract never deletes volumes."
        )
    review = raid.preview_rebuild(p, d, raid.RebuildPreview(operation="create"), session, actor)
    remaining = [
        b
        for b in review["blockers"]
        if "live-operation scope" not in b and "Shut down the server cleanly first" not in b
    ]
    if remaining:
        raise ContractError(remaining[0])
    _scope(session, actor, "storage_only")
    if raid.read_reset_power(p, d, session)["power"] != "Off":
        # Resume the same shutdown across bounded ticks. Never send a second soft shutdown.
        prior = raid.latest_event(session, d, "shutdown_attempt")
        boot = raid.latest_event(session, d, "boot_attempt")
        if prior and (not boot or prior.created_at > boot.created_at):
            elapsed = (datetime.now(UTC) - prior.created_at.replace(tzinfo=UTC)).total_seconds()
            if prior.data_json.get("force"):
                if elapsed > 120:
                    raise ContractError(
                        "The server still reports power on after forced power-off. Check its iLO; nothing was resent."
                    )
                return
            if elapsed < 130:
                return
            force = True
        else:
            force = False
        shutdown = raid.preview_shutdown(p, d, raid.ShutdownPreview(force=force), session, actor)
        _check(shutdown, "apply_enabled")
        return _dispatch(
            session,
            p,
            raid.apply_shutdown,
            p,
            d,
            raid.ShutdownApply(
                preview_id=shutdown["preview_id"],
                confirmation=shutdown["confirmation"],
                downtime_confirmed=True,
                data_loss_confirmed=True,
            ),
            session,
            actor,
        )
    fresh = raid.preview_rebuild(p, d, raid.RebuildPreview(operation="create"), session, actor)
    _check(fresh, "apply_enabled")
    # Boot is its own next tick. The existing ledger records staging before returning.
    return _dispatch(
        session,
        p,
        raid.apply_rebuild,
        p,
        d,
        raid.RebuildApply(
            preview_id=fresh["preview_id"],
            confirmation=fresh["confirmation"],
            data_loss_confirmed=True,
            backups_confirmed=True,
            health_reviewed=True,
            firmware_reviewed=True,
            empty_bays_confirmed=fresh["empty_bays"],
        ),
        session,
        actor,
    )


def _tick(session, p, actor, item):
    step, d, observed = item["step"], item["device_id"], item["observed"]
    if step == "connect":
        return _dispatch(session, p, _probe, session, d)
    if step == "firmware":
        return _firmware(session, p, d, actor, item)
    if step == "raid":
        return _raid(session, p, d, actor, observed)
    if observed.get("active"):
        _scope(session, actor, SCOPES[step])
        advance = {
            "switch": switch_setup.advance,
            "esxi": esxi_install.check_install,
            "windows": windows_deploy.advance,
            "acceptance": acceptance.advance,
        }[step]
        return _dispatch(session, p, advance, session, p, d, actor)
    if observed.get("state") == "verified":
        raise ContractError(
            "The verified run differs from the desired values. Review it in settings; nothing was resent."
        )
    if step == "switch":
        review = switch_setup.review(session, d)
        _check(review)
        if review.get("replace_needed"):
            raise ContractError(
                "The switch already has settings. Confirm replacement on Set up the switch."
            )
    elif step == "esxi":
        build = esxi_install.build_status(session, p, d)
        proof = _latest(session, "kit.contract.esxi_inputs", profile_id=p, device_id=d)
        built = _latest(session, "kit.esxi_installer_built", profile_id=p, device_id=d)
        if (
            build["status"] in {"not_built", "stale"}
            or not proof
            or proof.data_json.get("desired") != item["desired"]
            or not built
            or proof.data_json.get("iso_sha256") != built.data_json.get("iso_sha256")
        ):
            build = _dispatch(session, p, esxi_install.build_installer, session, p, d, actor)
            if build["status"] == "ready":
                built = _latest(session, "kit.esxi_installer_built", profile_id=p, device_id=d)
                record_audit_event(
                    session,
                    actor=actor,
                    event_type="kit.contract.esxi_inputs",
                    message="Complete installer inputs recorded.",
                    data={
                        "profile_id": p,
                        "device_id": d,
                        "desired": item["desired"],
                        "iso_sha256": built.data_json.get("iso_sha256") if built else None,
                    },
                )
                session.commit()
        _check(build, None)
        if build["status"] != "ready":
            raise ContractError("The ESXi installer is not ready. Open Prepare ESXi.")
    elif step == "windows":
        _check(windows_deploy.review(session, p, d), "ready")
    elif not (observed.get("signin") or {}).get("password_saved"):
        raise ContractError("Save the Windows administrator sign-in on Install Windows, step 4.")
    _scope(session, actor, SCOPES[step])
    start = {
        "switch": switch_setup.start,
        "esxi": esxi_install.start_install,
        "windows": windows_deploy.start,
        "acceptance": acceptance.start,
    }[step]
    if step == "acceptance":
        return _dispatch(
            session, p, start, session, p, d, actor, item["desired"].get("lookup") or ""
        )
    return _dispatch(session, p, start, session, p, d, actor)


def reconcile(session, profile_id, actor):
    """One bounded tick. No timer, background loop, or implicit approval here."""
    with _lock:
        current = _contract(session, profile_id)
        approval = _latest(session, "kit.contract.approved", profile_id=profile_id)
        invalid = _latest(session, "kit.contract.invalidated", profile_id=profile_id)
        rows = _items(session, current)
        result = {
            "state": "unapproved",
            "item": None,
            "message": "Approve this contract before starting or resuming.",
            "items": rows,
        }
        if not approval or (invalid and invalid.created_at >= approval.created_at):
            return _lock_if_idle(
                session, actor, {**result, "items": [_display(row) for row in rows]}
            )
        if approval.data_json["digest"] != current["digest"]:
            record_audit_event(
                session,
                actor=actor,
                event_type="kit.contract.invalidated",
                message="Desired settings changed; approval invalidated.",
                data={"profile_id": profile_id, "digest": approval.data_json["digest"]},
            )
            session.commit()
            return _lock_if_idle(
                session,
                actor,
                {
                    **result,
                    "items": [_display(row) for row in rows],
                    "state": "blocked",
                    "message": "Contract drift: settings changed since approval. Review and approve again.",
                    "href": "/contract",
                },
            )
        item = next((row for row in rows if row["state"] != "verified"), None)
        try:
            if not rows:
                raise ContractError("Add equipment to this kit before approving a build.")
            if item:
                bad = next(
                    (
                        row
                        for row in rows
                        if row["state"]
                        in {"needs_attention", "uncertain", "failed", "closed", "reachable"}
                    ),
                    None,
                )
                if bad:
                    item = bad
                    raise ContractError(
                        bad["observed"].get("message")
                        or "This step needs attention; nothing was resent."
                    )
                _tick(session, profile_id, actor, item)
                rows = _items(session, current)
            result = {
                "state": "converging"
                if any(r["state"] != "verified" for r in rows)
                else "converged",
                "item": item["id"] if item else None,
                "message": "Working toward the approved contract."
                if item
                else "Every contract item is verified.",
                "items": rows,
            }
            bad = next(
                (
                    r
                    for r in rows
                    if r["state"]
                    in {"needs_attention", "uncertain", "failed", "closed", "reachable"}
                ),
                None,
            )
            if bad:
                result.update(
                    state="blocked",
                    item=bad["id"],
                    message=bad["observed"].get("message") or "This step needs attention.",
                    href=bad["href"],
                )
        except Exception as exc:
            # Existing services commit write-attempt records before dispatch. Never retry here.
            result = {
                **result,
                "state": "blocked",
                "item": item["id"] if item else None,
                "message": str(getattr(exc, "detail", exc)),
                "href": item["href"] if item else "/rack",
            }
        finally:
            _lock_if_idle(session, actor, result)
        result["items"] = [_display(row) for row in result["items"]]
        return result


def certificate(session, profile_id):
    """As-built evidence; incomplete records remain explicitly unverified."""
    current = _contract(session, profile_id)
    rows = _items(session, current)
    evidence = handover.build(session, profile_id)
    return {
        "digest": current["digest"],
        "generated_at": datetime.now(UTC).isoformat(),
        "state": "converged"
        if rows and all(r["state"] == "verified" for r in rows)
        else "incomplete",
        "items": [
            {
                **_display(r),
                "verified": r["observed"] if r["state"] == "verified" else None,
                "verified_at": r["observed"].get("verified_at")
                or r["observed"].get("finished_at")
                or r["observed"].get("checked_at"),
            }
            for r in rows
        ],
        "handover": evidence,
    }
