"""Kit Pilot: a separate program that builds the whole lab kit and ends on one page with everything.

Run start-kit-pilot.cmd (or `python pilot.py`). Kit Pilot starts its own small local server for its
screen, opens it in the browser, and flies the build through Lab Builder's guarded API (Lab Builder
must be running: start-lab-builder.cmd). The build runs inside this program, so closing the
browser does not stop it; reopening the screen shows where it is.

The screen is a flight board: seven legs, one big button that always says the one thing to do
next, and the report when the kit is built. Approval happens once, before anything is changed,
and is tied to a snapshot of the plan; if the plan changes, it asks again.
"""

from __future__ import annotations

import html
import json
import os
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from engine import Api, ApiError, Engine, Paused, fail_fix
from flightplan import FlightPlan, PlanError
import finder
import help as stop_help  # plain-words checklists for the common stops
from flight_log import CheckedApi, LABELS, completion, report_legs, timeline_section, unknowns

HERE = Path(__file__).resolve().parent
LAB_BUILDER = os.environ.get("LAB_BUILDER_URL", "http://127.0.0.1:18001")
LAB_BUILDER_UI = os.environ.get("LAB_BUILDER_UI_URL", "http://127.0.0.1:15173")
PORT = int(os.environ.get("KIT_PILOT_PORT", "7788"))
# Demo: KIT_PILOT_CLOCK_SCALE=0.2 makes every wait five times shorter (only sensible against a simulated kit).
CLOCK_SCALE = float(os.environ.get("KIT_PILOT_CLOCK_SCALE", "1"))
VOLATILE = {"Connection check", "Nothing half-done", "Free disk space"}


class Pilot:
    """All state lives here; the screen only shows it and sends one of a few actions."""

    def __init__(self, api: Api, open_url=webbrowser.open, clock=time.sleep) -> None:
        self.api, self.open_url, self.clock = api, open_url, clock
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.state: dict = {"phase": "idle", "kit": "", "equipment": [], "legs": [], "now": "", "message": "", "where": None,
                            "label": None, "preflight": None, "warning": "", "report": None, "lab_builder": LAB_BUILDER_UI, "updated": self.clock_now(),
                            "options": {"skip": [], "replace_switch": False}, "events": [], "last_checked": None, "last_progress": None, "unknowns": []}
        self.approved_plan: str | None = None
        self.resume_from = 0

    def event(self, kind, text, leg=None):
        # Caller holds the state lock. Duplicate poll messages are checks, not progress.
        events = self.state["events"]
        if kind == "progress" and events and events[-1]["kind"] == kind and events[-1]["text"] == text:
            return
        stamp = time.time()
        if not events:
            self.event_epoch = stamp
        events.append({"kind": kind, "text": text, "leg": leg, "at": datetime.now().astimezone().isoformat(timespec="seconds"), "elapsed": stamp - self.event_epoch})
        self.state["last_progress"] = stamp

    @staticmethod
    def clock_now() -> str:
        return datetime.now().strftime("%H:%M:%S")

    # ------------------------------------------------------------- reading the kit
    def load(self) -> None:
        profiles = self.api.get("/api/v1/lab/profiles")
        active = profiles.get("active_profile") or {}
        self.profile_id = active.get("id")
        if not self.profile_id:
            raise ApiError(0, "Lab Builder has no kit selected. Choose a kit in Lab Builder first.")
        plan = self.api.get(f"/api/v1/rack-plans/{urllib.parse.quote(self.profile_id)}")
        pick = lambda kind: [{"id": e["device_id"], "name": e["name"], "model": e.get("model", "")} for e in plan["equipment"] if e["kind"] == kind and e.get("device_id")]
        self.servers, self.switches = pick("server"), pick("switch")
        legs = Engine(self.api, self.profile_id, self.servers, self.switches).legs
        with self.lock:
            self.state.update(kit=active.get("name", ""), equipment=self.servers + self.switches,
                              legs=[{"id": leg.id, "title": leg.title, "changes": leg.changes, "state": "todo", "note": ""} for leg in legs])

    def plan_snapshot(self, preflight: dict | None = None) -> str:
        """The plan as it is right now (rack revision + pre-flight details); read-only."""
        kit = f"/api/v1/rack-plans/{urllib.parse.quote(self.profile_id)}"
        plan = self.api.get(kit)
        preflight = preflight or self.api.get(kit + "/preflight")
        return json.dumps([plan.get("revision"), [[i["name"], i["detail"]] for i in preflight["items"] if i["name"] not in VOLATILE]])

    # ------------------------------------------------------------- actions
    def check(self) -> None:
        self.load()
        preflight = self.api.get(f"/api/v1/rack-plans/{urllib.parse.quote(self.profile_id)}/preflight")
        plan = FlightPlan(self.api).read()
        fails = [i for i in preflight["items"] if i["state"] == "fail"]
        with self.lock:
            self.state.update(plan=plan, last_checked=time.time(), unknowns=unknowns(plan, preflight, self.state["options"]), preflight=preflight, phase="blocked" if fails else "checked", warning="",
                              message=f"Fix the {len(fails)} red item{'s' if len(fails) != 1 else ''} in Lab Builder, then check again." if fails
                              else "Checked. Press Build to see every change and approve them.")
            self.state["where"], self.state["label"] = ("/", "Open Lab Builder") if fails else (None, None)

    def ask_approval(self) -> None:
        with self.lock:
            if self.state["phase"] != "checked":
                return
            self.state["unknowns"] = unknowns(self.state.get("plan", {}), self.state["preflight"], self.state["options"])
            self.state.update(phase="approve", message="Read the changes, then press Approve and build.")

    def approve(self) -> None:
        with self.lock:
            if self.state["phase"] != "approve" or self.thread and self.thread.is_alive():
                return
            preflight = self.state["preflight"]
        self.approved_plan = self.plan_snapshot(preflight)
        self.resume_from = 0
        self.start_flight()

    def start_flight(self) -> None:
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            for leg in self.state["legs"][self.resume_from:]:
                leg.update(state="todo", note="", reason=None, at="")
            self.state.update(phase="flying", message="", warning="", where=None, label=None)
            self.stop.clear()
            self.thread = threading.Thread(target=self.flight, name="kit-pilot-flight", daemon=True)
            self.thread.start()

    def resume(self) -> None:
        """Continue or Try again: the approval must still match the plan, otherwise check again."""
        with self.lock:
            if self.state["phase"] not in ("paused", "needs_you") or self.thread and self.thread.is_alive():
                return
            preflight = self.state["preflight"]
        if not self.approved_plan or not preflight or self.plan_snapshot() != self.approved_plan:
            self.approved_plan = None
            with self.lock:
                self.state.update(phase="idle", message="Something in the plan changed since you approved it. Check it and approve again.", where=None, label=None)
            return
        with self.lock:
            self.event("continue", "Continuing the flight")
        self.start_flight()

    def pause(self) -> None:
        with self.lock:
            if self.state["phase"] != "flying":
                return
            self.event("pause", "Pause requested")
            self.state.update(phase="pausing", message="Pausing before the next change…")
        self.stop.set()

    def flight(self) -> None:
        def say(text: str) -> None:
            with self.lock:
                self.state.update(now=text, updated=self.clock_now(), last_checked=time.time())
                self.event("progress", text)

        def warn(text: str) -> None:
            with self.lock:
                self.state["warning"] = text

        def report(index: int, result: dict) -> None:
            with self.lock:
                leg = self.state["legs"][index]
                leg.update(result, note=LABELS.get(result.get("reason"), ""), at=self.clock_now())
                self.state["last_checked"] = time.time()
                kind = "leg_start" if result["state"] == "running" else "leg_skip" if result["state"] == "skipped" else "leg_finish"
                self.event(kind, leg["title"] + ": " + (leg["note"] or "started"), leg["id"])

        with self.lock:
            options = dict(self.state["options"])
        def checked():
            with self.lock:
                self.state["last_checked"] = time.time()

        engine = Engine(CheckedApi(self.api, checked), self.profile_id, self.servers, self.switches, say=say, warn=warn, stop=self.stop, clock=self.clock,
                        locate=lambda subnet, mac: finder.find_mac(subnet, mac, exclude=finder.my_addresses()),
                        skip=set(options.get("skip") or []), replace_switch=bool(options.get("replace_switch")))
        current = self.resume_from
        try:
            def track(index: int, state: dict) -> None:
                nonlocal current
                current = index
                report(index, state)
            engine.fly(self.resume_from, track)
            path = self.write_report()
            with self.lock:
                self.state.update(phase="done", now="", message=completion(self.state["legs"]), report=path)
        except Paused:
            self.resume_from = current
            with self.lock:
                self.state["legs"][current].update(state="todo")
                self.event("paused", "Paused before the next change")
                self.state.update(phase="paused", now="", message="Paused. Nothing new is sent while paused; whatever was already running on the equipment carries on.")
        except Exception as exc:  # noqa: BLE001 - every stop is shown, never hidden
            self.resume_from = current
            where, label = fail_fix(exc, self.state["legs"][current]["id"])
            with self.lock:
                self.state["legs"][current].update(state="stopped")
                self.event("needs_you", str(exc), self.state["legs"][current]["id"])
                self.state.update(phase="needs_you", now="", message=str(exc), where=where, label=label, help=stop_help.advice(str(exc)))

    # ------------------------------------------------------------- the one page
    def write_report(self) -> str:
        data = self.api.get(f"/api/v1/rack-plans/{urllib.parse.quote(self.profile_id)}/handover")
        path = HERE / "kit-report.html"
        with self.lock:
            snapshot = json.loads(json.dumps(self.state))
        path.write_text(render_report(data, report_legs(snapshot["legs"]), snapshot), encoding="utf-8")
        return str(path)


# Extra report sections (HTML strings) added by other modules: each is called with (handover data, legs, state).
REPORT_SECTIONS: list = []
REPORT_SECTIONS.append(timeline_section)
import evidence  # noqa: E402  (the switch-configuration section)

evidence.register(REPORT_SECTIONS)


def render_report(data: dict, legs: list[dict], state: dict | None = None) -> str:
    e = html.escape
    when = lambda v: e(str(v)[:19].replace("T", " ")) if v else "—"
    dash = lambda v: e(str(v)) if v not in (None, "") else "—"
    rows = []
    for s in data.get("servers", []):
        esxi, win, acc = s.get("esxi", {}), s.get("windows", {}), s.get("acceptance") or {}
        rows.append(f"""<section><h2>{e(s['name'])} <small>{e(s.get('model') or '')}</small></h2><dl>
<dt>iLO</dt><dd>{dash(s.get('ilo', {}).get('address'))} · firmware {dash(s.get('ilo', {}).get('firmware'))} · ROM {dash(s.get('ilo', {}).get('bios'))}</dd>
<dt>Boot disks</dt><dd>{(str(len(s['boot_disks']['bays'])) + ' × bays ' + ', '.join(map(str, s['boot_disks']['bays']))) if s.get('boot_disks') else '—'}</dd>
<dt>VM storage</dt><dd>{(dash(s['data_disks'].get('raid')) + ' · bays ' + ', '.join(map(str, s['data_disks']['bays']))) if s.get('data_disks') else '—'}</dd>
<dt>ESXi</dt><dd>{dash(esxi.get('host_name'))} · {dash(esxi.get('address'))} · {'verified ' + when(esxi.get('verified_at')) if esxi.get('state') == 'verified' else dash(esxi.get('state'))}</dd>
<dt>Windows</dt><dd>{dash(win.get('vm'))} · {dash(win.get('address'))} · {dash(win.get('os'))} · {'verified ' + when(win.get('verified_at')) if win.get('state') == 'verified' else dash(win.get('state'))}</dd>
<dt>Acceptance test</dt><dd>{'Passed ' + when(acc.get('finished_at')) if acc.get('state') == 'verified' else dash(acc.get('state') or 'not run')}</dd></dl></section>""")
    for sw in data.get("switches", []):
        rows.append(f"""<section><h2>{e(sw['name'])} <small>{e(sw.get('model') or '')}</small></h2><dl>
<dt>Management</dt><dd>{dash(sw.get('address'))} · user {dash(sw.get('username'))}</dd><dt>Software</dt><dd>{dash(sw.get('software'))} · serial {dash(sw.get('serial'))}</dd>
<dt>Console</dt><dd>{dash(sw.get('console'))}</dd><dt>Last check</dt><dd>{when(sw.get('checked_at'))} · {dash(sw.get('check_status'))}</dd></dl></section>""")
    cables = (data.get("cables") or {}).get("cables") or []
    legs_html = "".join(f"<li class='{e(l['state'])}'>{e(l['title'])}{' · already done' if l['state'] == 'skipped' else ''}</li>" for l in legs)
    net = data.get("network", {})
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kit report</title>
<style>body{{font:15px/1.5 system-ui,Segoe UI,sans-serif;color:#17202a;margin:0;background:#f4f6f8}}main{{max-width:900px;margin:0 auto;padding:28px 20px 60px;background:#fff}}
h1{{margin:0;font-size:28px}}h2{{font-size:18px;margin:26px 0 8px;border-bottom:1px solid #dde3ea;padding-bottom:6px}}h2 small{{font-weight:400;color:#5b6b7b;font-size:13px}}
dl{{display:grid;grid-template-columns:150px 1fr;gap:6px 14px;margin:0}}dt{{color:#5b6b7b}}dd{{margin:0}}.muted{{color:#5b6b7b}}
ol.legs{{list-style:none;padding:0;margin:8px 0 0;display:flex;flex-wrap:wrap;gap:8px}}ol.legs li{{padding:4px 12px;border-radius:999px;background:#e7f6ec;color:#116b36;font-size:13px}}
ol.legs li.stopped{{background:#fdecea;color:#8a1c1c}}@media print{{body{{background:#fff}}}}</style></head><body><main>
<p class="muted">Kit Pilot · built {e(datetime.now().strftime('%Y-%m-%d %H:%M'))} · from Lab Builder's own checks; passwords not included</p>
<h1>{e(data.get('kit') or 'Kit')}</h1>
<ol class="legs">{legs_html}</ol>
<section><h2>Network</h2><dl><dt>Subnet</dt><dd>{dash(net.get('subnet'))}</dd><dt>Gateway</dt><dd>{dash(net.get('gateway'))}</dd><dt>DNS</dt><dd>{e(', '.join(net.get('dns') or [])) or '—'}</dd><dt>Domain</dt><dd>{dash(net.get('domain'))}</dd></dl></section>
{''.join(rows)}
<section><h2>Cables</h2>{('<ul>' + ''.join(f"<li>{e(c['server'])} {e(c['server_port'])} → {e(c['switch'])} {e(c['switch_port'])} · VLAN {e(str(c['vlan']))}</li>" for c in cables) + '</ul>') if cables else '<p class="muted">Not read (My Rack → Cables → Read cables).</p>'}</section>
{''.join(section(data, legs, state or {}) for section in REPORT_SECTIONS)}
<section><h2>Verified</h2>{('<ul>' + ''.join(f"<li><b>{e(v['area'])}</b> · {when(v['at'])} · {e(v['message'])}</li>" for v in data.get('verified', [])) + '</ul>') if data.get('verified') else '<p class="muted">Nothing verified yet.</p>'}</section>
</main></body></html>"""


class Screen(BaseHTTPRequestHandler):
    pilot: Pilot

    def log_message(self, *args) -> None:  # quiet
        pass

    def send(self, status: int, body: bytes, kind: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        files = {"/": ("ui.html", "text/html"), "/setup": ("setup.html", "text/html"), "/briefing": ("briefing.html", "text/html"), "/style.css": ("style.css", "text/css"), "/rack.js": ("rack.js", "text/javascript")}
        if self.path in files:
            name, kind = files[self.path]
            self.send(200, (HERE / name).read_bytes(), kind)
        elif self.path == "/mynet":
            self.send(200, json.dumps({"networks": finder.my_networks()}).encode())
        elif self.path == "/plan":
            try:
                self.send(200, json.dumps(FlightPlan(self.pilot.api).read()).encode())
            except ApiError as exc:
                self.send(502, json.dumps({"error": str(exc)}).encode())
        elif self.path == "/state":
            with self.pilot.lock:
                self.send(200, json.dumps(self.pilot.state).encode())
        elif self.path == "/report":
            path = HERE / "kit-report.html"
            self.send(200, path.read_bytes(), "text/html") if path.is_file() else self.send(404, b"no report yet", "text/plain")
        else:
            self.send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self.send(403, b"local only", "text/plain")
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/find":
            # Explicit click only: ping the kit's subnet and ask what answered what it is. Read-only.
            try:
                subnet = (body.get("subnet") or "").strip() or (FlightPlan(self.pilot.api).read().get("kit") or {}).get("subnet")
                if not subnet:
                    raise PlanError("Save the kit's subnet first, so I know where to look.")
                found = finder.find(subnet, exclude=finder.my_addresses())
                self.send(200, json.dumps({"subnet": subnet, "found": found}).encode())
            except (PlanError, ApiError, ValueError) as exc:
                self.send(409, json.dumps({"error": str(exc)}).encode())
            return
        if self.path in ("/save", "/read"):
            try:
                plan = FlightPlan(self.pilot.api)
                result = plan.save(body.get("section", ""), body.get("values") or {}) if self.path == "/save" else plan.read_equipment(body.get("what", ""), body)
                self.send(200, json.dumps(result).encode())
            except (PlanError, ApiError) as exc:
                self.send(409, json.dumps({"error": str(exc)}).encode())
            return
        action = body.get("action")
        if action == "options":
            with self.pilot.lock:
                if self.pilot.state["phase"] in ("flying", "pausing"):
                    self.send(409, json.dumps({"error": "Options can be changed before the flight or while it is paused."}).encode())
                    return
                wanted = body.get("options") or {}
                self.pilot.state["options"] = {"skip": [leg for leg in wanted.get("skip", []) if leg in {"firmware", "acceptance", "switch", "windows"}],
                                               "replace_switch": bool(wanted.get("replace_switch"))}
                self.send(200, json.dumps(self.pilot.state).encode())
            return
        try:
            {"check": self.pilot.check, "build": self.pilot.ask_approval, "approve": self.pilot.approve, "pause": self.pilot.pause,
             "resume": self.pilot.resume}[action]()
        except KeyError:
            self.send(400, b"unknown action", "text/plain")
            return
        except ApiError as exc:
            with self.pilot.lock:
                self.pilot.state.update(message=str(exc))
        with self.pilot.lock:
            self.send(200, json.dumps(self.pilot.state).encode())


def main() -> None:
    pilot = Pilot(Api(LAB_BUILDER), clock=lambda seconds: time.sleep(seconds * CLOCK_SCALE))
    Screen.pilot = pilot
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Screen)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Kit Pilot is at {url}  (Lab Builder at {LAB_BUILDER}). Close this window to stop it.")
    if not os.environ.get("KIT_PILOT_NO_BROWSER"):
        threading.Thread(target=lambda: (time.sleep(0.5), webbrowser.open(url)), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
