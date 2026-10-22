"""Kit Pilot engine: flies the whole kit build, one leg at a time, through Lab Builder's guarded API.

Kit Pilot is its own program. It never talks to equipment itself: every change goes through Lab
Builder's runs, which send each change once, confirm it, and record it. This engine only starts
those runs, watches them, and decides what to do next.

Legs, in order: connect, switch, firmware, raid, esxi, windows, acceptance. For each leg it reads
what Lab Builder has recorded: a verified leg is skipped, a run already underway is watched (never
started again), and only a leg not yet done is started.

Safety:
- stop_if() runs before every request that can change equipment and after every wait; a paused
  build raises Paused there, so nothing new is sent after a pause.
- a leg takes exactly the write permission it needs (also when watching a run already underway),
  and permission returns to read-only after every leg and on any stop.
- anything the engine cannot decide for the operator (a blocker, a run needing attention, an
  unclear result) raises NeedsYou with what to do and the Lab Builder page to do it on.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

HEADERS = {"Content-Type": "application/json", "X-Local-User": "local-operator"}
TRANSIENT = re.compile(r"timed out|timeout|connection|refused|reset|502|503|504|restarting", re.I)
OUTAGE_LIMIT = 60
RAID_HANDLED = re.compile(r"live-operation scope|Shut down the server cleanly first", re.I)
SCOPES = {"switch": "switch_setup_only", "firmware": "firmware_only", "raid": "storage_only",
          "esxi": "esxi_install_only", "windows": "vm_deploy_only", "acceptance": "vm_deploy_only"}


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class NeedsYou(Exception):
    """The build stopped at something only the operator can decide; `where` is the Lab Builder page."""

    def __init__(self, message: str, where: str, label: str) -> None:
        super().__init__(message)
        self.where, self.label = where, label


class LegResult(dict):
    """Structured result; string comparison retained for older callback consumers."""
    def __eq__(self, other):
        return self["state"] == other if isinstance(other, str) else super().__eq__(other)


class Paused(Exception):
    pass


class Api:
    def __init__(self, base: str, timeout: float = 180.0) -> None:
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _call(self, method: str, path: str, body: Any = None, timeout: float | None = None) -> Any:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                detail = json.loads(raw).get("detail", raw)
            except ValueError:
                detail = f"HTTP {exc.code} {exc.reason}" if raw.lstrip().lower().startswith(("<!doctype", "<html")) else raw[:300]
            if isinstance(detail, list):
                detail = "; ".join(str(item.get("msg", item)) if isinstance(item, dict) else str(item) for item in detail)
            raise ApiError(exc.code, str(detail) or f"HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ApiError(0, f"Lab Builder did not answer ({getattr(exc, 'reason', exc)}).") from None

    def get(self, path: str, **params: Any) -> Any:
        return self._call("GET", path + (("?" + urllib.parse.urlencode(params)) if params else ""))

    def post(self, path: str, body: Any = None, timeout: float | None = None, **params: Any) -> Any:
        return self._call("POST", path + (("?" + urllib.parse.urlencode(params)) if params else ""), body if body is not None else {}, timeout)


@dataclass
class Leg:
    id: str
    title: str
    changes: str
    run: Callable[["Engine"], str]  # returns "done" or "skipped"


@dataclass
class Engine:
    api: Api
    profile_id: str
    servers: list[dict[str, str]]
    switches: list[dict[str, str]]
    say: Callable[[str], None] = lambda text: None
    warn: Callable[[str], None] = lambda text: None
    stop: threading.Event = field(default_factory=threading.Event)
    clock: Callable[[float], None] = time.sleep
    # (subnet, mac) -> address or None. A DHCP ESXi is found this way after its install; None disables it.
    locate: Callable[[str, str], str | None] | None = None
    # Flight options chosen in the briefing: legs to skip this run, and whether a switch that already
    # has settings may have its users, address and SSH replaced by the first setup.
    skip: set[str] = field(default_factory=set)
    replace_switch: bool = False

    # ------------------------------------------------------------- helpers
    def kit(self, action: str, device: str | None = None) -> str:
        path = f"/api/v1/rack-plans/{urllib.parse.quote(self.profile_id)}/{action}"
        return path + (f"?device_id={urllib.parse.quote(device)}" if device else "")

    def stop_if(self) -> None:
        if self.stop.is_set():
            raise Paused()

    def sleep(self, seconds: float) -> None:
        """Wait in half-second steps so a pause is noticed quickly; the clock is replaceable for tests."""
        self.stop_if()
        steps, rest = divmod(seconds, 0.5)
        for _ in range(int(steps)):
            self.clock(0.5)
            self.stop_if()
        if rest:
            self.clock(rest)
        self.stop_if()

    def scope(self, target: str) -> None:
        current = self.api.get("/api/v1/runtime/write-scope")
        if current.get("scope") == target:
            return
        review = self.api.post("/api/v1/runtime/write-scope/preview", {"target_scope": target})
        if review.get("blockers"):
            raise NeedsYou(" ".join(review["blockers"]), "/", "Open Lab Builder")
        self.api.post("/api/v1/runtime/write-scope/apply", {"review_token": review["review_token"], "confirmation_phrase": review.get("confirmation_phrase") or ""})

    def lock(self) -> bool:
        """Return permission to read-only; a few tries, then say so. Never silently leaves it on."""
        last: Exception | None = None
        for _ in range(3):
            try:
                self.scope("read_only")
                return True
            except ApiError as exc:
                last = exc
                self.clock(1.0)
        self.warn(f"Write permission is still on: {last}")
        return False

    def poll(self, every: float, read: Callable[[], Any], done: Callable[[Any], bool], stuck: Callable[[Any], str | None]) -> Any:
        failures = 0
        while True:
            self.stop_if()
            value = None
            try:
                value = read()
                failures = 0
            except ApiError as exc:
                # Equipment restarting is expected (no answer, or a gateway error); a real refusal stops at once.
                transient = exc.status in (502, 503, 504) or (exc.status == 0 and TRANSIENT.search(str(exc)))
                if not transient:
                    raise
                failures += 1
                if failures >= OUTAGE_LIMIT:
                    raise
            if value is not None:
                if done(value):
                    return value
                problem = stuck(value)
                if problem:
                    raise NeedsYou(problem, "/", "Open Lab Builder")
            self.sleep(every)

    # ------------------------------------------------------------- legs
    def leg_connect(self) -> str:
        for server in self.servers:
            self.stop_if()
            self.say(f"Reading {server['name']} through its iLO…")
            probe = self.api.post("/api/v1/providers/ilo-redfish/probe", device_id=server["id"])
            if probe.get("status") != "ok":
                raise NeedsYou(f"{server['name']}: {probe.get('message') or 'the iLO did not answer.'}", "/setup/connect", "Open Connect")
        return "done"

    def leg_switch(self) -> str:
        did = False
        for sw in self.switches:
            where = ("/setup/connect", "Open Set up the switch")
            status = self.api.get(self.kit("switch-setup/status", sw["id"]))
            if status["state"] == "verified":
                # A record from an earlier day is not proof: the switch may have been reset or re-cabled since.
                # One read-only SSH check decides; a switch that no longer answers is set up again.
                check = self.api.post(f"/api/v1/devices/{urllib.parse.quote(sw['id'])}/switch-access/check")
                if check.get("status") == "ok":
                    continue
                self.say(f"{sw['name']} no longer answers at {status.get('address') or 'its saved address'} ({check.get('message') or 'no answer'}); setting it up again.")
                status = {**status, "state": "not_started", "active": False}
            if status["state"] == "needs_attention":
                raise NeedsYou(f"{sw['name']}: {status['message']}", *where)
            if not status["active"]:
                review = self.api.post(self.kit("switch-setup/review", sw["id"]))
                if review.get("blockers"):
                    raise NeedsYou(f"{sw['name']}: {review['blockers'][0]}", *where)
                if review.get("replace_needed") and not self.replace_switch:
                    raise NeedsYou(f"{sw['name']} already has settings. Choose 'Replace them' in the briefing, or set it up on Set up the switch.", *where)
                self.stop_if()
                self.scope("switch_setup_only")
                self.stop_if()
                self.say(f"Setting up {sw['name']} over the console…")
                self.api.post(self.kit("switch-setup/start", sw["id"]), {"replace_existing": bool(review.get("replace_needed") and self.replace_switch)})
            else:
                self.scope("switch_setup_only")
            self.poll(5, lambda: self.api.post(self.kit("switch-setup/advance", sw["id"]), timeout=120),
                      lambda s: s["state"] == "verified",
                      lambda s: (self.say(f"{sw['name']}: {s.get('step') or s['message']}") or (s["message"] if s["state"] in ("needs_attention", "failed") else None)))
            did = True
        return "done" if did else "skipped"

    def leg_firmware(self) -> str:
        did = False
        for server in self.servers:
            where = ("/setup/check-firmware", "Open Check firmware")
            parts = self.api.get(self.kit("parts-update/status", server["id"]))
            spp = self.api.get(self.kit("firmware-update/status", server["id"]))
            if parts["state"] == "needs_attention":
                raise NeedsYou(f"{server['name']}: {parts['message']}", *where)
            if spp["status"] == "uncertain":
                raise NeedsYou(f"{server['name']}: {spp['message']}", *where)
            parts_active = parts["active"]
            if not parts_active and not spp["active"]:
                self.say(f"Comparing {server['name']}'s firmware with the package…")
                plan = self.api.post(self.kit("parts-update/review", server["id"]), timeout=180)
                if plan.get("blockers"):
                    raise NeedsYou(f"{server['name']}: {plan['blockers'][0]}", *where)
                if plan["parts"]:
                    self.stop_if()
                    self.scope("firmware_only")
                    self.stop_if()
                    self.api.post(self.kit("parts-update/start", server["id"]), {"review_id": plan["review_id"]}, timeout=1200)
                    parts_active = True
            elif parts_active:
                self.scope("firmware_only")
            if parts_active:
                did = True
                self.poll(10, lambda: self.api.post(self.kit("parts-update/advance", server["id"]), timeout=1200),
                          lambda s: not s["active"] and s["state"] == "verified",
                          lambda s: (self.say(f"{server['name']}: {s['message']}") or (s["message"] if s["state"] == "needs_attention" or (not s["active"] and s["state"] != "verified") else None)))
            disc_running = spp["active"]
            if not disc_running:
                plan = self.api.post(self.kit("firmware-update/plan", server["id"]), {"device_id": server["id"]}, timeout=180)
                if plan["updates"] and not (plan.get("can_apply") and plan.get("review_token") and plan.get("confirmation_phrase")):
                    reason = (plan.get("blockers") or ["some firmware can only be installed from HPE's boot disc, and it cannot start yet."])[0]
                    raise NeedsYou(f"{server['name']}: {reason}", *where)
                if plan["updates"]:
                    self.stop_if()
                    self.scope("firmware_only")
                    self.stop_if()
                    self.say(f"{server['name']}: installing the rest from HPE's boot disc…")
                    self.api.post(self.kit("firmware-update/apply", server["id"]), {"review_token": plan["review_token"], "confirmation_phrase": plan["confirmation_phrase"], "idempotency_key": str(uuid.uuid4())})
                    disc_running = True
            else:
                self.scope("firmware_only")
            if disc_running:
                did = True
                self.poll(15, lambda: self.api.get(self.kit("firmware-update/status", server["id"])),
                          lambda s: not s["active"] and s["status"] == "verified",
                          lambda s: (self.say(f"{server['name']}: {s['message']}") or (s["message"] if s["status"] == "uncertain" or (not s["active"] and s["status"] != "verified") else None)))
        return "done" if did else "skipped"

    def power_off(self, server: dict[str, str]) -> None:
        def on() -> bool:
            self.stop_if()
            return self.api.get(self.kit("raid-rebuild/power-state", server["id"])).get("power") != "Off"
        if not on():
            return
        self.say(f"Turning {server['name']} off…")
        soft = self.api.post(self.kit("raid-rebuild/shutdown-preview", server["id"]), {"force": False})
        if not soft.get("apply_enabled"):
            raise NeedsYou((soft.get("blockers") or ["The server can't be turned off yet."])[0], "/setup/disks", "Open Disks & RAID")
        self.stop_if()
        self.api.post(self.kit("raid-rebuild/shutdown", server["id"]), {"preview_id": soft["preview_id"], "confirmation": soft["confirmation"], "downtime_confirmed": True, "data_loss_confirmed": True})
        for _ in range(13):
            self.sleep(10)
            if not on():
                return
        self.stop_if()  # the forced power-off is its own decision point
        self.say(f"{server['name']} didn't turn off by itself, so it's being powered off…")
        hard = self.api.post(self.kit("raid-rebuild/shutdown-preview", server["id"]), {"force": True})
        if not hard.get("apply_enabled"):
            raise NeedsYou((hard.get("blockers") or ["The server can't be powered off yet."])[0], "/setup/disks", "Open Disks & RAID")
        self.stop_if()
        self.api.post(self.kit("raid-rebuild/shutdown", server["id"]), {"preview_id": hard["preview_id"], "confirmation": hard["confirmation"], "downtime_confirmed": True, "data_loss_confirmed": True})
        for _ in range(12):
            self.sleep(10)
            if not on():
                return
        raise NeedsYou(f"{server['name']} still reports power on. Nothing else was sent. Check its power in the iLO.", "/setup/disks", "Open Disks & RAID")

    def start_to_apply(self, server: dict[str, str]) -> None:
        boot = self.api.post(self.kit("raid-rebuild/boot-preview", server["id"]), timeout=120)
        if boot.get("blockers") or not boot.get("apply_enabled"):
            raise NeedsYou((boot.get("blockers") or ["The server start can't be requested yet."])[0], "/setup/disks", "Open Disks & RAID")
        self.stop_if()
        self.api.post(self.kit("raid-rebuild/boot", server["id"]), {"preview_id": boot["preview_id"], "confirmation": boot["confirmation"],
                                                                     "pending_changes_reviewed": True, "data_loss_confirmed": True, "maintenance_confirmed": True})

    def leg_raid(self) -> str:
        did = False
        for server in self.servers:
            where = ("/setup/disks", "Open Disks & RAID")
            status = self.api.get(self.kit("raid-rebuild/status", server["id"]))
            if status.get("operation") == "create" and status.get("status") == "verified":
                continue
            if status.get("operation") == "create" and status.get("status") in ("uncertain", "needs_attention", "failed"):
                raise NeedsYou(f"{server['name']}: the last RAID build needs attention.", *where)
            underway = status.get("operation") == "create" and status.get("status") in ("waiting", "staged")
            if not underway:
                self.say(f"Reading {server['name']}'s disks…")
                probe = self.api.post("/api/v1/providers/ilo-redfish/probe", device_id=server["id"])
                if probe.get("status") != "ok":
                    raise NeedsYou(f"{server['name']}: {probe.get('message') or 'the iLO did not answer.'}", "/setup/connect", "Open Connect")
                view = self.api.get(self.kit("disk-preparation", server["id"]))
                if view.get("blockers"):
                    raise NeedsYou(f"{server['name']}: {view['blockers'][0]}", *where)
                if view.get("volumes"):
                    raise NeedsYou(f"{server['name']} already has RAID volumes. Keep them or wipe them on Disks & RAID; Kit Pilot never deletes volumes.", *where)
                review = self.api.post(self.kit("raid-rebuild/preview", server["id"]), {"operation": "create"}, timeout=120)
                left = [item for item in review.get("blockers", []) if not RAID_HANDLED.search(item)]
                if left:
                    raise NeedsYou(f"{server['name']}: {left[0]}", *where)
                self.stop_if()
                self.scope("storage_only")
                self.power_off(server)
                self.say(f"Saving the RAID layout on {server['name']}'s controller…")
                fresh = self.api.post(self.kit("raid-rebuild/preview", server["id"]), {"operation": "create"}, timeout=120)
                if not fresh.get("apply_enabled") or fresh.get("blockers"):
                    raise NeedsYou(f"{server['name']}: {(fresh.get('blockers') or ['the RAID plan cannot be applied yet.'])[0]}", *where)
                self.stop_if()
                self.api.post(self.kit("raid-rebuild/apply", server["id"]), {"preview_id": fresh["preview_id"], "confirmation": fresh["confirmation"], "data_loss_confirmed": True,
                                                                              "backups_confirmed": True, "health_reviewed": True, "firmware_reviewed": True, "empty_bays_confirmed": fresh.get("empty_bays", [])})
                self.say(f"Starting {server['name']} so the controller builds the RAID…")
                self.start_to_apply(server)
            else:
                self.scope("storage_only")
                if status.get("status") == "staged":
                    self.start_to_apply(server)
            did = True
            self.say(f"{server['name']} is building its RAID (it restarts)…")
            self.poll(15, lambda: self.api.post(self.kit("raid-rebuild/verify", server["id"]), timeout=120),
                      lambda r: bool(r.get("verified")), lambda r: r.get("message") if r.get("status") == "failed" else None)
        return "done" if did else "skipped"

    def leg_esxi(self) -> str:
        did = False
        for server in self.servers:
            where = ("/setup/prepare-esxi", "Open Prepare ESXi")
            status = self.api.get(self.kit("esxi/install", server["id"]))
            if status["state"] == "verified":
                continue
            if status["state"] in ("needs_attention", "closed"):
                raise NeedsYou(f"{server['name']}: {status['message']}", *where)
            if status["state"] == "reachable":
                raise NeedsYou(f"{server['name']}: ESXi answers but has not been verified yet. Finish the check on Prepare ESXi.", *where)
            if not status["active"]:
                build = self.api.get(self.kit("esxi/installer", server["id"]))
                if build["status"] in ("not_built", "stale"):
                    self.say(f"Building {server['name']}'s ESXi installer (about a minute; nothing touches the server)…")
                    build = self.api.post(self.kit("esxi/installer", server["id"]), timeout=600)
                if build["status"] != "ready":
                    raise NeedsYou(f"{server['name']}: {(build.get('blockers') or ['the ESXi installer is not ready.'])[0]}", *where)
                self.stop_if()
                self.scope("esxi_install_only")
                self.stop_if()
                self.say(f"Installing ESXi on {server['name']} (about 20 minutes)…")
                self.api.post(self.kit("esxi/install", server["id"]), timeout=300)
            else:
                self.scope("esxi_install_only")
            did = True
            found: dict[str, Any] = {"address": None, "tries": 0}

            def check() -> Any:
                # With DHCP, once ESXi is late answering, look the host up by its management NIC's MAC and hand
                # that address to Lab Builder's check (read-only; the check still proves it is this host).
                if found["address"] is None and self.locate and status.get("addressing") == "dhcp" and found["tries"] < 6:
                    found["tries"] += 1
                    if found["tries"] >= 3:
                        settings = self.api.get(self.kit("esxi/settings", server["id"]))
                        mac, subnet = settings.get("management_nic") or "", (settings.get("kit") or {}).get("subnet")
                        if ":" in mac and subnet:
                            self.say(f"Looking for {server['name']}'s ESXi on {subnet} by its network port {mac}…")
                            found["address"] = self.locate(subnet, mac)
                body = {"address": found["address"]} if found["address"] else None
                return self.api.post(self.kit("esxi/install/check", server["id"]), body, timeout=180)
            self.poll(30, check,
                      lambda s: s["state"] == "verified",
                      lambda s: (self.say(f"{server['name']}: {s['message']}") or (s["message"] if s["state"] in ("needs_attention", "closed")
                                 else "ESXi answers but could not be verified. Finish the check on Prepare ESXi." if s["state"] == "reachable" and not s["active"] else None)))
        return "done" if did else "skipped"

    def leg_windows(self) -> str:
        did = False
        for server in self.servers:
            where = ("/setup/install-windows", "Open Install Windows")
            status = self.api.get(self.kit("windows/status", server["id"]))
            if status["state"] == "verified":
                continue
            if status["state"] == "needs_attention":
                raise NeedsYou(f"{server['name']}: {status['message']}", *where)
            if not status["active"]:
                review = self.api.post(self.kit("windows/review", server["id"]), timeout=120)
                if not review.get("ready"):
                    raise NeedsYou(f"{server['name']}: {(review.get('blockers') or ['Windows is not ready to deploy.'])[0]}", *where)
                self.stop_if()
                self.scope("vm_deploy_only")
                self.stop_if()
                self.say(f"Importing Windows onto {server['name']} (large images take a while)…")
                self.api.post(self.kit("windows/start", server["id"]), timeout=120)
            else:
                self.scope("vm_deploy_only")
            did = True
            self.poll(15, lambda: self.api.post(self.kit("windows/advance", server["id"]), timeout=120),
                      lambda s: s["state"] == "verified",
                      lambda s: (self.say(f"{server['name']}: {s['message']}") or (s["message"] if s["state"] in ("needs_attention", "failed") else None)))
        return "done" if did else "skipped"

    def leg_acceptance(self) -> str:
        did = False
        for server in self.servers:
            where = ("/setup/install-windows", "Open Install Windows")
            status = self.api.get(self.kit("windows/acceptance", server["id"]))
            if status["state"] == "verified":
                continue
            if status["state"] == "needs_attention":
                raise NeedsYou(f"{server['name']}: {status['message']}", *where)
            if not status["active"]:
                if not status["signin"]["password_saved"]:
                    raise NeedsYou(f"Save {server['name']}'s Windows administrator sign-in (Install Windows, step 4).", *where)
                self.stop_if()
                self.scope("vm_deploy_only")
                self.stop_if()
                self.say(f"Testing Windows on {server['name']}…")
                self.api.post(self.kit("windows/acceptance/start", server["id"]), {"name": status.get("lookup") or status.get("default_lookup") or None}, timeout=60)
            else:
                self.scope("vm_deploy_only")
            did = True

            def stuck(s: dict[str, Any]) -> str | None:
                now = next((p for p in s.get("phases", []) if p.get("state") == "running"), None)
                if now:
                    self.say(f"{server['name']}: {now['label']}…")
                return s["message"] if s["state"] in ("needs_attention", "failed") else None
            self.poll(10, lambda: self.api.post(self.kit("windows/acceptance/advance", server["id"]), timeout=180), lambda s: s["state"] == "verified", stuck)
        return "done" if did else "skipped"

    @property
    def legs(self) -> list[Leg]:
        return [
            Leg("connect", "Connect the servers", "Read-only: signs in to each iLO and reads the server.", Engine.leg_connect),
            Leg("switch", "Set up the switch", "Sends the reviewed first setup over the console cable (name, admin user, management address, SSH), then checks SSH.", Engine.leg_switch),
            Leg("firmware", "Update firmware", "Installs the firmware the package says is out of date, through the iLO and, if needed, HPE's boot disc. The server restarts, possibly several times.", Engine.leg_firmware),
            Leg("raid", "Build RAID", "Turns the server off (forced off if it has not shut down after two minutes), saves the planned RAID layout and starts the server so it builds it. Any data on the planned disks is lost. Disks that already have volumes are never touched: the build stops instead.", Engine.leg_raid),
            Leg("esxi", "Install ESXi", "Attaches the ESXi installer built from your ISO, boots it once and installs ESXi on the boot disks, then creates the VM datastore.", Engine.leg_esxi),
            Leg("windows", "Deploy Windows", "Imports the chosen Windows image onto the VM datastore as a new VM and powers it on.", Engine.leg_windows),
            Leg("acceptance", "Prove it works", "Checks Windows from outside and inside, restarts it once, and checks it is back.", Engine.leg_acceptance),
        ]

    def fly(self, start: int, report: Callable[[int, dict], None]) -> None:
        """Run from `start`; report(index, {state, reason}) at each transition.

        Terminal reasons distinguish completed work, prior verification, operator choice,
        and absent targets. Running has no terminal reason. Provider request order is unchanged.
        Read-only after every leg and on every exit.
        """
        still_on = NeedsYou("Write permission could not be returned to read-only. Open Lab Builder and set Read-only mode, then press Try again.", "/", "Open Lab Builder")
        locked = True
        try:
            for index, leg in enumerate(self.legs):
                if index < start:
                    continue
                self.stop_if()
                if leg.id in self.skip:
                    report(index, LegResult(state="skipped", reason="skipped_by_choice"))
                    continue
                report(index, LegResult(state="running", reason=None))
                result = leg.run(self)
                if not self.lock():
                    raise still_on
                reason = "completed" if result == "done" else "already_verified"
                if not (self.switches if leg.id == "switch" else self.servers):
                    reason = "not_applicable"
                report(index, LegResult(state="skipped" if reason == "not_applicable" else result, reason=reason))
        finally:
            locked = self.lock()
        if not locked:
            raise still_on


def fail_fix(err: Exception, leg_id: str) -> tuple[str, str]:
    """Where to send the operator when an error is not a NeedsYou."""
    where = {"connect": ("/setup/connect", "Open Connect"), "switch": ("/setup/connect", "Open Set up the switch"),
             "firmware": ("/setup/check-firmware", "Open Check firmware"), "raid": ("/setup/disks", "Open Disks & RAID"),
             "esxi": ("/setup/prepare-esxi", "Open Prepare ESXi"), "windows": ("/setup/install-windows", "Open Install Windows"),
             "acceptance": ("/setup/install-windows", "Open Install Windows")}
    return (err.where, err.label) if isinstance(err, NeedsYou) else where.get(leg_id, ("/", "Open Lab Builder"))
