"""Ask the lab: answer "why is VLAN 100 here?" from the app's own records, never from guesses.

The question is turned into search terms (VLAN numbers, addresses, names, words). Matches come
from three places, each shown with when and where it was recorded:
  plan    - what was planned or saved (kit network settings, switch / ESXi / Windows settings);
  changes - what the app sent (runs and attempts);
  checks  - what was read back or verified (results and completions).
Secrets are never searched or returned: values under keys that look like passwords are skipped.
"""

from __future__ import annotations

import ipaddress
import json
import re
from datetime import UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent

STOP = {"why", "what", "where", "when", "who", "how", "is", "are", "was", "were", "the", "a", "an", "this", "that", "here", "there",
        "on", "in", "at", "of", "for", "to", "and", "or", "it", "its", "did", "does", "do", "we", "our", "my", "which", "with", "set", "get"}
SECRET_KEY = re.compile(r"pass|secret|token|key|hash|credential", re.I)
# Only these plain record fields are searched (never free-form payloads, which could hold anything).
FIELDS = ("vlan", "vlan_id", "hostname", "host", "address", "management_ip", "vm_name", "vm", "network", "datastore", "image",
          "phase", "outcome", "console_port", "mode", "uplink", "uplink_mode", "gateway", "subnet", "name", "model", "serial",
          "version", "lookup", "area", "resource")
SECRET_TEXT = re.compile(r"((?:pass(?:word)?|secret|token|key)\s*[:=]\s*)\S+", re.I)
PLAN = re.compile(r"(settings|_saved|\.saved|planned|rack_plan|\.run$)")
CHANGE = re.compile(r"(\.attempt$|\.applied$|_applied$|\.sent$)")
CHECK = re.compile(r"(\.result$|\.done$|\.verified$|_verified$)")
SKIP = re.compile(r"(preview|progress|heartbeat|observed|observation|\.queued|diagnosis)")
SCAN = 3000


def terms(question: str) -> list[dict[str, Any]]:
    text = question.strip()[:200]
    found: list[dict[str, Any]] = []
    for number in re.findall(r"\bvlan\s*(\d{1,4})\b", text, re.I):
        found.append({"kind": "vlan", "value": int(number), "label": f"VLAN {int(number)}",
                      "pattern": re.compile(rf"\bvlan\s*{int(number)}\b|\"vlan(?:_id)?\":\s*{int(number)}\b", re.I)})
    rest = re.sub(r"\bvlan\s*\d{1,4}\b", " ", text, flags=re.I)
    for address in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b", rest):
        try:
            ipaddress.ip_interface(address)
        except ValueError:
            continue
        found.append({"kind": "address", "value": address, "label": address, "pattern": re.compile(r"(?<![\d.])" + re.escape(address) + r"(?![\d.])")})
        rest = rest.replace(address, " ")
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_.:-]{2,}", rest):
        if word.lower() in STOP:
            continue
        found.append({"kind": "word", "value": word, "label": word, "pattern": re.compile(rf"\b{re.escape(word)}\b", re.I)})
    unique, seen = [], set()
    for term in found:
        if term["label"].lower() not in seen:
            seen.add(term["label"].lower())
            unique.append(term)
    return unique[:6]


def _public(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _public(v) for k, v in value.items() if not SECRET_KEY.search(str(k))}
    if isinstance(value, list):
        return [_public(v) for v in value]
    return value


def redact(text: str) -> str:
    return SECRET_TEXT.sub(r"\1[hidden]", text)


def _score(found: list[dict[str, Any]], text: str) -> int:
    return sum(1 for term in found if term["pattern"].search(text))


def _where(event_type: str) -> str:
    from app.api.build_history import _area

    return _area(event_type)


def _bucket(event_type: str) -> str | None:
    if SKIP.search(event_type):
        return None
    if CHANGE.search(event_type):
        return "changes"
    if CHECK.search(event_type):
        return "checks"
    if PLAN.search(event_type):
        return "plan"
    return None


def _settings_sources(session: Session) -> list[dict[str, Any]]:
    """Current saved settings that are not audit records: the kit's network and each switch's setup."""
    from app.models import SwitchDeviceCredential
    from app.services.lab_profiles import active_lab_profile_context

    sources = []
    try:
        context = active_lab_profile_context()
        active = context.get("active_profile") or {}
        sources.append({"where": "Kit network settings", "at": None,
                        "text": json.dumps(_public({"subnet": active.get("subnet_cidr"), "gateway": active.get("gateway"), "dns": active.get("dns"),
                                                    "settings": active.get("global_settings")}), default=str),
                        "message": f"Kit network: subnet {active.get('subnet_cidr') or '—'}, gateway {active.get('gateway') or '—'}"})
    except Exception:  # noqa: BLE001 - only an extra source
        pass
    for record in session.scalars(select(SwitchDeviceCredential)):
        setup = (record.credentials_json or {}).get("setup") if isinstance(record.credentials_json, dict) else None
        if isinstance(setup, dict):
            sources.append({"where": "Switch setup settings", "at": record.updated_at.isoformat() if record.updated_at else None,
                            "text": json.dumps(_public(setup), default=str),
                            "message": f"Switch {setup.get('hostname') or ''}: management VLAN {setup.get('vlan')}, {setup.get('mode')}"
                                       + (f", uplink {setup.get('uplink')} ({setup.get('uplink_mode')})" if setup.get("uplink") else "")})
    return sources


def ask(session: Session, question: str) -> dict[str, Any]:
    found = terms(question)
    if not found:
        return {"question": question, "terms": [], "plan": [], "changes": [], "checks": [], "summary": "Ask about a VLAN, an address, a name or a step."}
    need = max(1, len(found) if len(found) <= 2 else len(found) - 1)
    buckets: dict[str, list[dict[str, Any]]] = {"plan": [], "changes": [], "checks": []}
    for source in _settings_sources(session):
        if _score(found, source["text"] + " " + source["message"]) >= need:
            buckets["plan"].append({"where": source["where"], "at": source["at"], "message": source["message"]})
    rows = session.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(SCAN))
    for event in rows:
        bucket = _bucket(event.event_type)
        if bucket is None or len(buckets[bucket]) >= 8:
            continue
        data = event.data_json if isinstance(event.data_json, dict) else {}
        plain = {key: data[key] for key in FIELDS if isinstance(data.get(key), (str, int, float, bool))}
        message = redact(event.message or "")
        text = f"{message} {json.dumps(plain, default=str)}"
        if _score(found, text) < need:
            continue
        at = event.created_at if event.created_at.tzinfo else event.created_at.replace(tzinfo=UTC)
        outcome = str(data.get("outcome") or data.get("status") or "")
        buckets[bucket].append({"where": _where(event.event_type), "at": at.isoformat(), "message": message, "outcome": outcome or None, "id": event.id})
    labels = ", ".join(term["label"] for term in found)
    parts = []
    if buckets["plan"]:
        parts.append(f"planned in {buckets['plan'][0]['where'].lower()}")
    if buckets["changes"]:
        parts.append(f"sent by {buckets['changes'][0]['where']} ({buckets['changes'][0]['at'][:10]})")
    proven = next((c for c in buckets["checks"] if c.get("outcome") in {"ok", "verified"}), None)
    if proven:
        parts.append(f"checked by {proven['where']} ({proven['at'][:10]})")
    summary = (f"{labels}: " + "; ".join(parts) + ".") if parts else f"Nothing in the app's records mentions {labels}."
    return {"question": question, "terms": [term["label"] for term in found], **buckets, "summary": summary}
