"""Evidence sections for Kit Pilot's report: what the switch's configuration actually is after the setup
(as read back over the console by Lab Builder, secrets masked there), and what the setup changed.
Secrets are masked again here, defensively, before anything is rendered."""

from __future__ import annotations

import html
import re

SECRET_PREFIXES = [
    r"username \S+ .*?(?:secret|password)(?: \d)?", r"enable (?:secret|password)(?: level \d+)?(?: \d)?", r"password(?: \d)?",
    r"(?:tacacs|radius)(?:-server)? .*?\bkey(?: \d)?", r"key(?: \d)?", r"key-string(?: \d)?", r"snmp-server community",
    r"snmp-server user .*?(?:auth|priv) \S+", r"ntp authentication-key \d+ md5", r"standby \d+ authentication(?: md5 key-string(?: \d)?| text)?",
    r"vrrp \d+ authentication(?: md5 key-string(?: \d)?| text)?", r"ppp (?:chap|pap) (?:password|sent-username \S+ password)(?: \d)?",
    r"ip (?:ftp|http client) password(?: \d)?", r"crypto isakmp key(?: \d)?", r"pre-shared-key(?: local| remote)?(?: \d)?",
    r"(?:wpa-psk|psk)(?: (?:ascii|hex))?(?: \d)?", r"key-hash \S+", r"aaa .*?\bkey(?: \d)?", r"neighbor \S+ password(?: \d)?", r".*\b(?:secret|password)(?: \d)?",
]
SECRET_LINE = re.compile(r"^(\s*(?:" + "|".join(SECRET_PREFIXES) + r"))\s+\S.*$", re.M | re.I)
HEX_BLOB = re.compile(r"^\s*[0-9A-F]{8}(?: [0-9A-F]{8})+\s*$", re.M)
SYSLOG_LINE = re.compile(
    r"\r?\n?\*?(?:[A-Z][a-z]{2} +\d{1,2} \d\d:\d\d:\d\d(?:\.\d+)?(?: [A-Z]{2,5})?: )?"
    r"%[A-Z0-9_-]+-\d-[A-Z0-9_]+: [^\r\n]*?(?:\.(?=[a-z!])|(?=\r?\n|$))")
KEEP_WORDS = re.compile(r"^\s*(?:no |service |ip ssh version|ip ssh bulk|login |transport |aaa new-model|password encryption)", re.I)


def mask_secrets(text: str) -> str:
    def mask(match: re.Match) -> str:
        line = match.group(0)
        if KEEP_WORDS.match(line) and not re.search(r"\b(?:secret|key-string|community)\b", line, re.I):
            return line
        return match.group(1) + " ********"
    return HEX_BLOB.sub("  [certificate or key data removed]", SECRET_LINE.sub(mask, SYSLOG_LINE.sub("", text or "")))


def switch_config_section(data: dict, legs: list, state: dict) -> str:
    e = html.escape
    parts = []
    for sw in data.get("switches") or []:
        config = sw.get("config") or {}
        if not config.get("after"):
            continue
        after = mask_secrets(config["after"])
        diff_lines = [mask_secrets(line) if line[:1] in "+-" else line for line in (config.get("diff") or [])]
        changed = [line for line in diff_lines if line[:1] in "+-" and not line.startswith(("+++", "---"))]
        diff = "\n".join(diff_lines[2:])
        parts.append(f"""<section><h2>{e(sw['name'])}: configuration after the first setup <small>read {e(str(config.get('at', ''))[:19].replace('T', ' '))} · secrets masked · {len(changed)} line{'s' if len(changed) != 1 else ''} changed</small></h2>
{f'<h3>What the setup changed</h3><pre class="diff">{e(diff)}</pre>' if diff else ''}
<h3>Running configuration</h3><pre>{e(after)}</pre></section>""")
    return "".join(parts)


def register(sections: list) -> None:
    if switch_config_section not in sections:
        sections.append(switch_config_section)
