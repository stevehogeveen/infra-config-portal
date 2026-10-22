"""Chaos checker for the Kit Pilot engine: every request, every kind of failure, every law checked.

A simulated kit (FakeKit) starts from nothing: switch not set up, firmware out of date, no RAID,
no ESXi, no Windows. The real engine (engine.py) flies it. Then the checker replays the flight and,
at request N, injects one fault:
  lost     - the change is applied, but the reply never arrives (the worst kind: a resend is tempting)
  503      - the request is refused with a gateway error and nothing is applied
  pause    - the operator pauses just before the request
  kill     - the program dies just before the request (no clean stop; a fresh engine resumes later)
After the fault the flight is resumed, as the operator would with Try again / Continue, until it
ends. Then the laws are checked against what the kit actually received:
  L1 each change is sent at most once per device (power-off, RAID apply/boot, installs, starts)
  L2 every write arrives while exactly its write permission is on
  L3 write permission is read-only when the flight is over
  L4 after a pause, nothing new is sent
  L5 RAID is never applied while volumes exist (and nothing ever deletes a volume)
  L6 every flight ends in a definite state: done, or stopped with a message
Single faults are exhaustive over every request position; then random multi-fault runs.
Run: python chaos.py [random-runs]
"""

from __future__ import annotations

import random
import sys
import threading
from dataclasses import dataclass, field
from typing import Any

from engine import Api, ApiError, Engine, NeedsYou, Paused

P, S, W = "fixture", "srv", "sw"
SERVERS = [{"id": S, "name": "Server"}]
SWITCHES = [{"id": W, "name": "Switch"}]
CHANGES = {"switch-setup/start": "switch_setup_only", "parts-update/start": "firmware_only", "firmware-update/apply": "firmware_only",
           "raid-rebuild/shutdown": "storage_only", "raid-rebuild/apply": "storage_only", "raid-rebuild/boot": "storage_only",
           "esxi/install": "esxi_install_only", "windows/start": "vm_deploy_only", "windows/acceptance/start": "vm_deploy_only"}
ADVANCES = {"switch-setup/advance": "switch_setup_only", "parts-update/advance": "firmware_only", "esxi/install/check": "esxi_install_only",
            "windows/advance": "vm_deploy_only", "windows/acceptance/advance": "vm_deploy_only", "raid-rebuild/verify": "storage_only"}


class Killed(Exception):
    pass


@dataclass
class FakeKit:
    """The whole kit, from nothing to built, with the same states Lab Builder reports."""

    scope: str = "read_only"
    sw: str = "not_started"      # not_started | running | verified
    sw_gone: bool = False        # a verified switch that no longer answers SSH
    sw_ticks: int = 0
    parts: str = "not_started"
    parts_ticks: int = 0
    spp: str = "not_started"     # not_started | running | verified
    spp_ticks: int = 0
    power: str = "On"
    power_ticks: int = 0
    raid: str = "not_started"    # not_started | staged | waiting | verified
    raid_ticks: int = 0
    volumes: int = 0
    esxi: str = "not_started"
    esxi_ticks: int = 0
    win: str = "not_started"
    win_ticks: int = 0
    test: str = "not_started"
    test_ticks: int = 0
    writes: list[tuple[str, str]] = field(default_factory=list)      # (change, scope at the time)
    advances: list[tuple[str, str]] = field(default_factory=list)
    volume_deletes: int = 0

    def apply(self, method: str, path: str, body: dict) -> Any:
        path = path.split("?", 1)[0]
        kit = f"/api/v1/rack-plans/{P}/"
        key = path[len(kit):] if path.startswith(kit) else path
        if method != "GET" and key in CHANGES:
            self.writes.append((key, self.scope))
        if method != "GET" and key in ADVANCES:
            self.advances.append((key, self.scope))
        # --- write permission
        if path == "/api/v1/runtime/write-scope":
            return {"scope": self.scope}
        if path == "/api/v1/runtime/write-scope/preview":
            return {"review_token": "t", "confirmation_phrase": "", "blockers": [], "target_scope": body["target_scope"]}
        if path == "/api/v1/runtime/write-scope/apply":
            self.scope = self._pending_scope
            return {"scope": self.scope}
        # --- connect
        if path.startswith("/api/v1/providers/ilo-redfish/probe"):
            return {"status": "ok", "message": "ok"}
        # --- switch
        if key == "switch-setup/status":
            return {"state": self.sw, "active": self.sw == "running", "message": self.sw}
        if path.startswith("/api/v1/devices/") and path.endswith("/switch-access/check"):
            return {"status": "ok" if self.sw == "verified" and not self.sw_gone else "unreachable", "message": "checked"}
        if key == "switch-setup/review":
            return {"blockers": [], "replace_needed": False}
        if key == "switch-setup/start":
            self.sw = "running"
            return {"state": self.sw, "active": True, "message": ""}
        if key == "switch-setup/advance":
            self.sw_ticks += 1
            if self.sw_ticks >= 2:
                self.sw = "verified"
            return {"state": self.sw, "active": self.sw == "running", "message": self.sw, "step": None}
        # --- firmware
        if key == "parts-update/status":
            return {"state": self.parts, "active": self.parts == "running", "message": self.parts}
        if key == "parts-update/review":
            return {"review_id": "r1", "parts": [{"component": "ROM"}] if self.parts != "verified" else [], "blockers": []}
        if key == "parts-update/start":
            self.parts = "running"
            return {"state": "running", "active": True, "message": ""}
        if key == "parts-update/advance":
            self.parts_ticks += 1
            if self.parts_ticks >= 2:
                self.parts = "verified"
            return {"state": self.parts, "active": self.parts == "running", "message": self.parts}
        if key == "firmware-update/status":
            if self.spp == "running":
                self.spp_ticks += 1
                if self.spp_ticks >= 2:
                    self.spp = "verified"
            return {"status": self.spp, "active": self.spp == "running", "message": self.spp}
        if key == "firmware-update/plan":
            need = self.spp != "verified"
            return {"updates": [{"component": "disk"}] if need else [], "can_apply": need, "review_token": "rt" if need else None, "confirmation_phrase": "ONLY" if need else None, "blockers": []}
        if key == "firmware-update/apply":
            self.spp = "running"
            return {"status": "running", "active": True, "message": ""}
        # --- raid
        if key == "raid-rebuild/status":
            return {"operation": "create" if self.raid != "not_started" else None, "status": self.raid}
        if key == "disk-preparation":
            return {"blockers": [], "volumes": [{"name": "v"}] * self.volumes}
        if key == "raid-rebuild/preview":
            return {"preview_id": "pv", "confirmation": "c", "apply_enabled": self.power == "Off", "blockers": [] if self.power == "Off" else ["Shut down the server cleanly first"], "empty_bays": []}
        if key == "raid-rebuild/power-state":
            if self.power == "going-off":
                self.power_ticks += 1
                if self.power_ticks >= 2:
                    self.power = "Off"
            return {"power": "On" if self.power != "Off" else "Off", "pending_changes": False}
        if key == "raid-rebuild/shutdown-preview":
            return {"preview_id": "sp", "confirmation": "c", "apply_enabled": True, "blockers": [], "force": body.get("force")}
        if key == "raid-rebuild/shutdown":
            self.power = "going-off"
            return {"message": "sent"}
        if key == "raid-rebuild/apply":
            if self.volumes:
                self.volume_deletes += 1
            self.raid = "staged"
            return {"message": "staged"}
        if key == "raid-rebuild/boot-preview":
            return {"preview_id": "bp", "confirmation": "c", "apply_enabled": True, "blockers": []}
        if key == "raid-rebuild/boot":
            self.raid = "waiting"
            self.power = "On"
            return {"status": "waiting", "message": ""}
        if key == "raid-rebuild/verify":
            self.raid_ticks += 1
            if self.raid == "waiting" and self.raid_ticks >= 2:
                self.raid, self.volumes = "verified", 2
            return {"status": self.raid, "message": self.raid, "verified": self.raid == "verified"}
        # --- esxi
        if key == "esxi/install" and method == "GET":
            return {"state": self.esxi, "active": self.esxi == "installing", "message": self.esxi}
        if key == "esxi/installer":
            return {"status": "ready", "blockers": []}
        if key == "esxi/install":
            self.esxi = "installing"
            return {"state": "installing", "active": True, "message": ""}
        if key == "esxi/install/check":
            self.esxi_ticks += 1
            if self.esxi == "installing" and self.esxi_ticks >= 2:
                self.esxi = "verified"
            return {"state": self.esxi, "active": self.esxi == "installing", "message": self.esxi}
        # --- windows
        if key == "windows/status":
            return {"state": self.win, "active": self.win == "running", "message": self.win}
        if key == "windows/review":
            return {"ready": True, "blockers": []}
        if key == "windows/start":
            self.win = "running"
            return {"state": "running", "active": True, "message": ""}
        if key == "windows/advance":
            self.win_ticks += 1
            if self.win_ticks >= 2:
                self.win = "verified"
            return {"state": self.win, "active": self.win == "running", "message": self.win}
        # --- acceptance
        if key == "windows/acceptance":
            return {"state": self.test, "active": self.test == "running", "message": self.test, "lookup": "x", "default_lookup": "x", "signin": {"password_saved": True}, "phases": []}
        if key == "windows/acceptance/start":
            self.test = "running"
            return {"state": "running", "active": True, "message": "", "phases": []}
        if key == "windows/acceptance/advance":
            self.test_ticks += 1
            if self.test_ticks >= 2:
                self.test = "verified"
            return {"state": self.test, "active": self.test == "running", "message": self.test, "phases": []}
        raise AssertionError(f"unexpected {method} {path}")

    _pending_scope: str = "read_only"


class ChaosApi(Api):
    """The engine's API client, wired straight to the fake kit, with faults by request number."""

    def __init__(self, kit: FakeKit, faults: dict[int, str], stop: threading.Event) -> None:
        super().__init__("http://fake")
        self.kit, self.faults, self.stop = kit, faults, stop
        self.n = 0
        self.trace: list[str] = []
        self.paused_at: int | None = None

    def _call(self, method: str, path: str, body: Any = None, timeout: float | None = None) -> Any:
        self.n += 1
        self.trace.append(f"{method} {path.split('?')[0].split(P + '/')[-1]}")
        fault = self.faults.get(self.n)
        if fault == "kill":
            raise Killed()
        if fault == "503":
            raise ApiError(503, "Service Unavailable")
        if path.endswith("/write-scope/preview"):
            self.kit._pending_scope = body["target_scope"]
        result = self.kit.apply(method, path, body or {})
        if fault == "pause":
            # The pause arrives while this request is in flight: it cannot be un-sent, but nothing may follow it.
            self.stop.set()
            self.paused_at = len(self.kit.writes)
        if fault == "lost":
            raise ApiError(0, "Lab Builder did not answer (timed out).")
        return result


def fly(kit: FakeKit, faults: dict[int, str]) -> dict[str, Any]:
    """One flight with faults; resumes after each stop like the operator would. Returns the outcome."""
    stop = threading.Event()
    api = ChaosApi(kit, faults, stop)
    start, outcome, stops, writes_after_pause = 0, "", [], 0
    for attempt in range(6):
        engine = Engine(api, P, SERVERS, SWITCHES, stop=stop, clock=lambda s: None)
        current = start
        try:
            def track(index: int, state: str) -> None:
                nonlocal current
                current = index
            engine.fly(start, track)
            outcome = "done"
            break
        except Paused:
            stops.append(("paused", current))
            if api.paused_at is not None:
                writes_after_pause += len(kit.writes) - api.paused_at
                api.paused_at = None
            stop.clear()
            start = current
        except Killed:
            stops.append(("killed", current))
            start = current
        except (NeedsYou, ApiError) as exc:
            stops.append(("needs_you", current, str(exc)[:80]))
            start = current
    else:
        outcome = "unfinished"
    if not outcome:
        outcome = "done"
    return {"outcome": outcome, "stops": stops, "writes": kit.writes, "advances": kit.advances, "scope": kit.scope,
            "volume_deletes": kit.volume_deletes, "writes_after_pause": writes_after_pause, "requests": api.n}


def laws(result: dict[str, Any], faults: dict[int, str]) -> list[str]:
    broken = []
    counts: dict[str, int] = {}
    for change, _ in result["writes"]:
        counts[change] = counts.get(change, 0) + 1
    for change, n in counts.items():
        limit = 2 if change == "raid-rebuild/shutdown" else 1  # a forced power-off may follow a soft one
        if n > limit:
            broken.append(f"L1 {change} sent {n} times")
    for change, scope in result["writes"]:
        if scope != CHANGES[change]:
            broken.append(f"L2 {change} sent under {scope}")
    for change, scope in result["advances"]:
        if scope != ADVANCES[change]:
            broken.append(f"L2 {change} (advance) under {scope}")
    if result["scope"] != "read_only":
        broken.append(f"L3 ended with scope {result['scope']}")
    if result["writes_after_pause"]:
        broken.append(f"L4 {result['writes_after_pause']} write(s) after a pause")
    if result["volume_deletes"]:
        broken.append("L5 RAID applied over existing volumes")
    if result["outcome"] != "done":
        broken.append(f"L6 ended {result['outcome']}: {result['stops'][-3:]}")
    return broken


def main() -> int:
    baseline = fly(FakeKit(), {})
    assert baseline["outcome"] == "done" and not laws(baseline, {}), baseline
    total = baseline["requests"]
    print(f"baseline flight: {total} requests, {len(baseline['writes'])} changes, laws hold")
    failures: list[tuple[dict[int, str], list[str]]] = []
    scenarios = 0
    for position in range(1, total + 1):
        for fault in ("lost", "503", "pause", "kill"):
            faults = {position: fault}
            result = fly(FakeKit(), faults)
            scenarios += 1
            broken = laws(result, faults)
            if broken:
                failures.append((faults, broken))
    print(f"single faults: {scenarios} scenarios, {len(failures)} broke a law")
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    rng = random.Random(2026)
    multi_failures = 0
    for _ in range(runs):
        faults = {rng.randint(1, total + 40): rng.choice(("lost", "503", "pause", "kill")) for _ in range(rng.randint(2, 4))}
        result = fly(FakeKit(), faults)
        broken = laws(result, faults)
        if broken:
            multi_failures += 1
            if len(failures) < 40:
                failures.append((faults, broken))
    print(f"random multi-fault: {runs} flights, {multi_failures} broke a law")
    seen: set[str] = set()
    for faults, broken in failures:
        line = f"  {faults} -> {broken}"
        key = str(sorted(set(b.split(' sent')[0].split(' ended')[0] for b in broken)))
        if key not in seen or len(seen) < 12:
            seen.add(key)
            print(line[:300])
    return 1 if failures or multi_failures else 0


if __name__ == "__main__":
    sys.exit(main())
