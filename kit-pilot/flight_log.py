"""Flight outcomes and report timeline. No provider calls."""
import html

LABELS = {"completed": "finished", "already_verified": "already done", "skipped_by_choice": "skipped by choice", "not_applicable": "not applicable"}

def completion(legs):
    skipped = [l for l in legs if l.get("reason") == "skipped_by_choice"]
    if not skipped:
        return "Your kit is built."
    names = {"acceptance": "Windows proof", "windows": "Windows deployment", "firmware": "Firmware", "switch": "Switch setup"}
    return "Selected steps finished; " + "; ".join(names.get(l["id"], l["title"]) + " was skipped" for l in skipped) + "."

def report_legs(legs):
    return [dict(l, state="omitted", title=l["title"] + " · " + LABELS[l["reason"]]) if l.get("reason") in ("skipped_by_choice", "not_applicable") else l for l in legs]

def timeline_section(data, legs, state):
    e = html.escape
    events = state.get("events", [])
    rows = "".join(f"<li><time>{e(v['at'])} (+{v['elapsed']:.0f}s)</time> · {e(v['text'])}</li>" for v in events)
    return f"<style>ol.legs li.omitted{{background:#eef0f2;color:#52606d}}</style><section><h2>Flight log</h2><p>{e(completion(legs))}</p><ol>{rows}</ol></section>"

def unknowns(plan, preflight, options):
    out = ["Saved settings are a plan, not a live check of the equipment.", "Cables have not been freshly checked by this preflight; link and VLAN readiness still need proof during the flight."]
    server, switch = plan.get("server") or {}, plan.get("switch") or {}
    if server.get("id"):
        out += ["Windows network and VM storage are checked after ESXi is available; saved Windows settings do not prove either works."]
        if (server.get("esxi") or {}).get("addressing") == "dhcp":
            out.append("ESXi's address is learned after installation; DHCP and host verification must still succeed.")
    if switch.get("id") and (switch.get("setup") or {}).get("mode") == "dhcp":
        out.append("The switch address arrives from DHCP during setup; saving its sign-in does not prove SSH connectivity.")
    for item in preflight.get("items", []):
        if item.get("state") == "warn":
            out.append(f"{item['name']}: {item['detail']}")
    for leg in options.get("skip", []):
        out.append({"acceptance": "Windows restart proof is skipped by choice; recovery after a restart remains unproven.", "firmware": "Firmware updates are skipped by choice; this flight will not establish that firmware is current.", "switch": "Switch setup is skipped by choice; this flight will not prove the planned switch configuration.", "windows": "Windows deployment is skipped by choice; this flight will not establish a working Windows VM."}.get(leg, leg))
    return out


class CheckedApi:
    """Observe successful engine checks without adding or changing a request."""
    def __init__(self, api, checked):
        self.api, self.checked = api, checked

    def get(self, *args, **kwargs):
        result = self.api.get(*args, **kwargs)
        self.checked()
        return result

    def post(self, *args, **kwargs):
        result = self.api.post(*args, **kwargs)
        self.checked()
        return result
