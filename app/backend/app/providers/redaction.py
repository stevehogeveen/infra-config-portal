from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

SENSITIVE_KEYWORDS = (
    "authorization",
    "cookie",
    "password",
    "secret",
    "session",
    "token",
)

SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(password|token|secret|authorization|cookie)(\s*[=:]\s*)([^,\s]+)"
)

NON_SECRET_EVIDENCE_KEYS = {
    "ansible_cisco_enable_password",
    "cisco_enable_password",
    "enable_command_sent",
    "enable_commands_attempted",
    "enable_password_sources_configured",
    "enable_password_sources_tried",
    "password_recovery_guidance_report",
    "password_prompt_seen",
    "settings.cisco_enable_password",
    "settings.cisco_test_password",
}


def redact_sensitive(value: Any, secrets: Iterable[str | None] = ()) -> Any:
    secret_values = [secret for secret in secrets if secret]

    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                redacted[str(key)] = "REDACTED"
            else:
                redacted[str(key)] = redact_sensitive(item, secret_values)
        return redacted

    if isinstance(value, list):
        return [redact_sensitive(item, secret_values) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_sensitive(item, secret_values) for item in value)

    if isinstance(value, str):
        redacted_value = value
        for secret in secret_values:
            redacted_value = redacted_value.replace(secret, "REDACTED")
        return SENSITIVE_VALUE_RE.sub(r"\1\2REDACTED", redacted_value)

    return value


def _is_sensitive_key(key: str) -> bool:
    lower_key = key.lower()
    if lower_key in NON_SECRET_EVIDENCE_KEYS:
        return False
    if lower_key.endswith("_configured") or lower_key.endswith("configured"):
        return False
    return any(keyword in lower_key for keyword in SENSITIVE_KEYWORDS)
