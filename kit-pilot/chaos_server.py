"""The chaos fake kit as an HTTP server, so other engines (the in-app wizard's TypeScript engine)
can be flown through the same faults and judged by the same laws as Kit Pilot's engine.

The client decides the fault per request with an X-Chaos header:
  lost  - apply the change, then drop the connection (the reply never arrives)
  503   - refuse without applying
Control endpoints: POST /__reset (new kit), POST /__paused (mark: nothing may be written after
this point), GET /__result (what the kit received), GET /__laws (the laws, as in chaos.py).
Run: python chaos_server.py [port]  (prints the port, serves until killed)
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from chaos import FakeKit, laws


def demo_settings() -> dict:
    return {"profile": {"id": "fixture", "name": "Practice kit (simulated)", "subnet_cidr": "192.0.2.0/27", "gateway": "192.0.2.1", "dns": ["192.0.2.53"],
                        "global_settings": {"gateway": "192.0.2.1", "dns_servers": ["192.0.2.53"], "domain_name": "lab.test"}},
            "rack": {"revision": 1, "rack_units": 12, "equipment": []}, "ilo": {"host": None, "username": None, "password_configured": False},
            "esxi": {"hostname": None, "addressing": "dhcp", "management_ip": None, "vlan_id": 0, "management_nic": "vmnic0", "datastore_name": "VMdata", "saved_at": None, "password_set": False},
            "iso": None, "win": {"image": None, "vm_name": None, "datastore": None, "network": None, "saved_at": None}, "guest": {"username": None, "password_saved": False},
            "swaccess": {"username": None, "password_configured": False, "host": None}, "console": None, "console_last": None, "swsetup": {}, "demo_probe": True}


class State:
    def __init__(self) -> None:
        self.demo = demo_settings()
        self.kit = FakeKit()
        self.lock = threading.Lock()
        self.requests = 0
        self.paused_at: int | None = None
        self.writes_after_pause = 0


STATE = State()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def reply(self, status: int, payload) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        with STATE.lock:
            if self.path == "/__reset":
                demo = STATE.demo  # a reset is a new flight; the plan stays
                STATE.__init__()
                STATE.demo = demo
                return self.reply(200, {"ok": True})
            if self.path == "/__paused":
                if STATE.paused_at is not None:
                    STATE.writes_after_pause += len(STATE.kit.writes) - STATE.paused_at
                STATE.paused_at = len(STATE.kit.writes)
                return self.reply(200, {"ok": True})
            if self.path == "/__unpause":
                if STATE.paused_at is not None:
                    STATE.writes_after_pause += len(STATE.kit.writes) - STATE.paused_at
                STATE.paused_at = None
                return self.reply(200, {"ok": True})
            if self.path.startswith("/__result") or self.path.startswith("/__laws"):
                if STATE.paused_at is not None:
                    STATE.writes_after_pause += len(STATE.kit.writes) - STATE.paused_at
                    STATE.paused_at = len(STATE.kit.writes)
                outcome = self.path.split("outcome=")[-1] if "outcome=" in self.path else "done"
                result = {"outcome": outcome, "stops": [], "writes": STATE.kit.writes, "advances": STATE.kit.advances, "scope": STATE.kit.scope,
                          "volume_deletes": STATE.kit.volume_deletes, "writes_after_pause": STATE.writes_after_pause, "requests": STATE.requests}
                return self.reply(200, laws(result, {}) if self.path.startswith("/__laws") else result)
            # Demo mode: what Kit Pilot asks about the kit itself, and the settings it saves (not part of the chaos laws).
            D = STATE.demo
            clean = self.path.split("?", 1)[0]
            if clean == "/api/v1/lab/profiles" and method == "GET":
                return self.reply(200, {"active_profile": D["profile"]})
            if clean == "/api/v1/lab/profiles" and method == "POST":
                D["profile"] = {"id": "fixture", **body}
                return self.reply(201, D["profile"])
            if clean.startswith("/api/v1/lab/profiles/") and clean.endswith("/activate"):
                return self.reply(200, {"active_profile": D["profile"]})
            if clean.startswith("/api/v1/lab/profiles/") and method == "PUT":
                D["profile"] = {**(D["profile"] or {}), "id": "fixture", **body}
                return self.reply(200, D["profile"])
            if clean == "/api/v1/rack-plans/fixture":
                if method == "PUT":
                    for item in body["equipment"]:
                        item["device_id"] = item.get("device_id") or ("srv" if item["kind"] == "server" else "sw")
                    D["rack"] = {**body, "revision": body["revision"] + 1}
                return self.reply(200, D["rack"])
            if clean == "/api/v1/providers/ilo-redfish/access-settings":
                if method == "PUT":
                    D["ilo"].update({k: v for k, v in body.items() if k != "password"}, password_configured=D["ilo"].get("password_configured") or "password" in body)
                return self.reply(200, D["ilo"])
            if clean == "/api/v1/rack-plans/fixture/esxi/settings":
                if method == "PUT":
                    D["esxi"].update({k: v for k, v in body.items() if k != "root_password"}, saved_at="now", password_set=D["esxi"].get("password_set") or "root_password" in body)
                return self.reply(200, D["esxi"])
            if clean == "/api/v1/rack-plans/fixture/esxi/media":
                if method == "POST":
                    D["iso"] = body["path"]
                return self.reply(200, {"isos": [{"path": "esxi-8.iso", "name": "VMware-ESXi-8.0.3 (practice).iso"}], "selected": {"path": D["iso"]} if D["iso"] else None})
            if clean == "/api/v1/rack-plans/fixture/windows/setup":
                if method == "PUT":
                    D["win"].update(body, saved_at="now")
                return self.reply(200, {**D["win"], "images": [{"path": "win2022.ova", "name": "win2022-practice.ova", "missing": []}], "host": {"address": None, "datastores": [], "networks": [], "default_datastore": None}})
            if clean == "/api/v1/rack-plans/fixture/windows/guest-signin":
                if method == "PUT":
                    D["guest"] = {"username": body["username"], "password_saved": True}
                return self.reply(200, D["guest"])
            if clean == "/api/v1/devices/sw/switch-access":
                if method == "PUT":
                    D["swaccess"].update({k: v for k, v in body.items() if "password" not in k}, password_configured=D["swaccess"].get("password_configured") or "password" in body)
                return self.reply(200, {**D["swaccess"], "console": {"port": D["console"], "last": D["console_last"]}})
            if clean == "/api/v1/devices/sw/switch-console/ports":
                return self.reply(200, {"ports": [{"port": "COM3", "description": "Intel AMT SOL", "recommended": False, "candidate_fingerprint": "f3", "recommended_bauds": [9600]},
                                                   {"port": "COM5", "description": "Prolific USB-to-Serial", "recommended": True, "candidate_fingerprint": "f5", "recommended_bauds": [9600]}], "problem": None})
            if clean == "/api/v1/devices/sw/switch-console/identify":
                D["console"], D["console_last"] = body["port"], {"answered": True, "model": "C9300-48T (practice)", "state_text": "The switch is new: at its first-setup questions."}
                return self.reply(200, {**D["console_last"], "port": body["port"]})
            if clean == "/api/v1/rack-plans/fixture/switch-setup/setup":
                if method == "PUT":
                    D["swsetup"] = {k: v for k, v in body.items() if "password" not in k}
                return self.reply(200, {"settings": D["swsetup"] or None, "defaults": {"hostname": "cisco-switch-1"}, "username": D["swaccess"].get("username"), "password_configured": D["swaccess"].get("password_configured")})
            if clean == "/api/v1/providers/ilo-redfish/probe" and D.get("demo_probe"):
                D["ilo"].update(last_probe_status="ok", last_probe_is_current=True)
                return self.reply(200, {"status": "ok", "message": "iLO answered.", "systems": [{"Model": "ProLiant DL360 Gen10 (practice)"}]})
            if self.path == "/api/v1/rack-plans/fixture/preflight":
                k = STATE.kit
                return self.reply(200, {"state": "ok", "checked_at": "now", "items": [
                    {"group": "Rack", "name": "Rack layout", "state": "ok", "detail": "2 pieces of equipment", "fix": None},
                    {"group": "Network", "name": "Network settings", "state": "ok", "detail": "192.0.2.0/24 via 192.0.2.1", "fix": None},
                    {"group": "Server", "name": "iLO sign-in", "state": "ok", "detail": "iLO 192.0.2.10", "fix": None},
                    {"group": "Media", "name": "ESXi installer", "state": "ok", "detail": "VMware-ESXi-8.0.3 (practice).iso", "fix": None},
                    {"group": "Media", "name": "Windows image", "state": "ok", "detail": "win2022-practice.ova", "fix": None},
                    {"group": "Media", "name": "Firmware package", "state": "ok", "detail": "SPP 2026.05 (practice)", "fix": None},
                    {"group": "Switch", "name": "Console port", "state": "ok", "detail": "COM5 at 9600", "fix": None},
                    {"group": "Disks", "name": "RAID volumes", "state": "warn" if k.volumes else "ok", "detail": f"{k.volumes} existing" if k.volumes else "none yet", "fix": None}]})
            if self.path == "/api/v1/rack-plans/fixture/handover":
                k = STATE.kit
                return self.reply(200, {"kit": "Practice kit (simulated)", "network": {"subnet": "192.0.2.0/24", "gateway": "192.0.2.1", "dns": ["192.0.2.53"], "domain": "lab.test"},
                    "servers": [{"name": next((e["name"] for e in STATE.demo["rack"]["equipment"] if e["kind"] == "server"), "Server"), "model": "HPE DL360 Gen10", "ilo": {"address": STATE.demo["ilo"].get("host") or "192.0.2.10", "firmware": "3.10", "bios": "U32 3.66"},
                                 "boot_disks": {"bays": [1, 2]}, "data_disks": {"raid": "RAID 5", "bays": [3, 4, 5]},
                                 "esxi": {"state": k.esxi, "host_name": "esx01", "address": "192.0.2.20", "verified_at": "2026-10-16T12:00:00"},
                                 "windows": {"state": k.win, "vm": "windows01", "address": "192.0.2.77", "os": "Windows Server 2022", "verified_at": "2026-10-16T12:10:00"},
                                 "acceptance": {"state": k.test, "finished_at": "2026-10-16T12:20:00"}}],
                    "switches": [{"name": "Cisco switch (practice)", "model": "Catalyst 9300", "address": "192.0.2.2", "username": "admin", "software": "17.9.4", "serial": "FOC0000X000", "console": "COM5", "checked_at": "2026-10-16T11:30:00", "check_status": "ok"}],
                    "cables": {"cables": [{"server": "HPE DL360 (practice)", "server_port": "vmnic0", "switch": "Cisco switch (practice)", "switch_port": "Gi1/0/1", "vlan": 100}]},
                    "verified": [{"area": "ESXi", "at": "2026-10-16T12:00:00", "message": "ESXi verified at 192.0.2.20."}, {"area": "Windows", "at": "2026-10-16T12:10:00", "message": "windows01 is running Windows."}]})
            STATE.requests += 1
            fault = self.headers.get("X-Chaos")
            if fault == "503":
                return self.reply(503, {"detail": "Service Unavailable"})
            if self.path.endswith("/write-scope/preview"):
                STATE.kit._pending_scope = body["target_scope"]
            try:
                payload = STATE.kit.apply(method, self.path, body)
            except AssertionError as exc:
                return self.reply(404, {"detail": str(exc)})
            if fault == "lost":
                self.close_connection = True
                return  # the change happened; the reply is gone
            self.reply(200, payload)

    def do_GET(self) -> None:
        self.serve("GET")

    def do_POST(self) -> None:
        self.serve("POST")

    def do_PUT(self) -> None:
        self.serve("PUT")

    def do_PATCH(self) -> None:
        self.serve("PATCH")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(server.server_port, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
