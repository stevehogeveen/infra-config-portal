from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import ValidationError

from app.api import routes
from app.providers.probe_cache import get_probe_result
from app.schemas import CiscoConsoleIdentityVerifyCreate
from app.services import cisco_console_identity as identity


@dataclass
class FakePortInfo:
    device: str
    description: str = "Prolific USB-to-Serial Comm Port"
    manufacturer: str = "Prolific"
    product: str = "USB Serial Port"
    interface: str = "USB Serial"
    hwid: str = "USB VID:PID=067B:2303 SER=ADAPTER-1 LOCATION=1-2"
    vid: int | None = 0x067B
    pid: int | None = 0x2303
    serial_number: str | None = "ADAPTER-1"
    location: str | None = "1-2"


class FakeSerialConnection:
    def __init__(
        self,
        *,
        passive: bytes = b"",
        responses: dict[bytes, bytes] | None = None,
    ) -> None:
        self._buffer = bytearray(passive)
        self._responses = responses or {}
        self.writes: list[bytes] = []
        self.closed = False

    @property
    def in_waiting(self) -> int:
        return len(self._buffer)

    def read(self, size: int) -> bytes:
        if not self._buffer:
            return b""
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    def write(self, payload: bytes) -> int:
        self.writes.append(payload)
        self._buffer.extend(self._responses.get(payload, b""))
        return len(payload)

    def close(self) -> None:
        self.closed = True

    def reset_input_buffer(self) -> None:
        raise AssertionError("the explicit identity path must not reset the input buffer")

    def send_break(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the explicit identity path must not send break")


class ChunkedSerialConnection:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)

    @property
    def in_waiting(self) -> int:
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, _size: int) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""


def _candidate(
    port: str = "COM5",
    **updates: Any,
) -> tuple[FakePortInfo, str]:
    port_info = FakePortInfo(device=port, **updates)
    result = identity.list_cisco_console_identity_candidates(
        port_enumerator=lambda: [port_info],
    )
    return port_info, result["candidates"][0]["candidate_fingerprint"]


def _allow_readonly_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity, "_readonly_contact_blockers", lambda _mode: [])


def test_candidate_enumeration_is_passive_and_redacts_adapter_serial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_serial = "PRIVATE-ADAPTER-SERIAL"
    port_info = FakePortInfo(
        device="COM5",
        description=f"USB Serial Port {raw_serial}",
        hwid=f"USB VID:PID=067B:2303 SER={raw_serial} LOCATION=2-7",
        serial_number=raw_serial,
        location="2-7",
    )
    monkeypatch.setattr(
        identity,
        "_open_explicit_serial_connection",
        lambda *_args: pytest.fail("candidate listing must never open a serial port"),
    )

    result = identity.list_cisco_console_identity_candidates(
        port_enumerator=lambda: [port_info],
    )

    assert result["status"] == "ready"
    assert result["baud_is_identity_proof"] is False
    assert result["raw_identifiers_redacted"] is True
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate == {
        "port": "COM5",
        "candidate_fingerprint": candidate["candidate_fingerprint"],
        "description": "USB Serial Port [redacted]",
        "manufacturer": "Prolific",
        "transport": "usb-serial",
        "vid_pid": "067B:2303",
        "usb_location": "2-7",
        "serial_present": True,
        "recommended_bauds": [9600, 115200],
        "recommended": False,
    }
    assert len(candidate["candidate_fingerprint"]) == 64
    assert raw_serial not in str(result)


def test_by_id_port_is_exposed_as_redacted_label_but_opens_exact_internal_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_adapter_serial = "PRIVATE-ADAPTER-SERIAL"
    raw_port = f"/dev/serial/by-id/usb-Prolific_{raw_adapter_serial}-if00"
    port_info = FakePortInfo(
        device=raw_port,
        serial_number=raw_adapter_serial,
        location="1-4",
    )
    candidates = identity.list_cisco_console_identity_candidates(
        port_enumerator=lambda: [port_info],
    )
    candidate = candidates["candidates"][0]
    connection = FakeSerialConnection(
        passive=b"Cisco IOS XE Software\r\nSwitch#",
        responses={
            identity.SHOW_VERSION_BYTES: (
                b"Cisco IOS XE Software, Version 17.09.04a\r\n"
                b"cisco C9300-24T (X86) processor\r\n"
                b"Processor board ID FOC1234ABCD\r\nSwitch#"
            )
        },
    )
    opened: list[tuple[str, int]] = []
    _allow_readonly_contact(monkeypatch)

    result = identity.verify_cisco_console_identity(
        port=candidate["port"],
        baud=9600,
        candidate_fingerprint=candidate["candidate_fingerprint"],
        port_enumerator=lambda: [port_info],
        connection_opener=lambda port, baud: (
            opened.append((port, baud)) or connection
        ),
        read_window_seconds=0,
    )

    assert candidate["port"].startswith("/dev/serial/by-id/[redacted-")
    assert raw_adapter_serial not in str(candidates)
    assert raw_port not in str(candidates)
    assert result["status"] == "ready"
    assert opened == [(raw_port, 9600)]
    assert raw_port not in str(result)


@pytest.mark.parametrize("passive", [b"LOADER-A>", b"cluster-01::>"])
def test_verify_blocks_netapp_without_any_show_command(
    monkeypatch: pytest.MonkeyPatch,
    passive: bytes,
) -> None:
    port_info, fingerprint = _candidate()
    connection = FakeSerialConnection(passive=passive)
    _allow_readonly_contact(monkeypatch)

    result = identity.verify_cisco_console_identity(
        port="COM5",
        baud=9600,
        candidate_fingerprint=fingerprint,
        port_enumerator=lambda: [port_info],
        connection_opener=lambda port, baud: connection,
        read_window_seconds=0,
    )

    assert result["status"] == "blocked"
    assert result["detected_vendor"] == "netapp"
    assert result["identity_verified"] is False
    assert result["commands_attempted"] == []
    assert connection.writes == []
    assert connection.closed is True


def test_generic_switch_prompt_allows_only_one_show_version_discriminator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port_info, fingerprint = _candidate()
    connection = FakeSerialConnection(
        responses={identity.INITIAL_PROMPT_BYTES: b"Switch#"},
    )
    _allow_readonly_contact(monkeypatch)

    result = identity.verify_cisco_console_identity(
        port="COM5",
        baud=9600,
        candidate_fingerprint=fingerprint,
        port_enumerator=lambda: [port_info],
        connection_opener=lambda port, baud: connection,
        read_window_seconds=0,
    )

    assert result["status"] == "blocked"
    assert result["detected_vendor"] == "unknown"
    assert result["prompt_state"] == "privileged-exec"
    assert result["commands_attempted"] == ["show version"]
    assert result["verification_method"] == "show-version-discriminator"
    assert connection.writes == [b"\r\n", b"show version\r\n"]
    assert b"\x03" not in connection.writes
    assert b"\x1a" not in connection.writes


def test_fresh_generic_exec_discriminator_verifies_only_after_cisco_show_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port_info, fingerprint = _candidate()
    connection = FakeSerialConnection(
        responses={
            identity.INITIAL_PROMPT_BYTES: b"Switch#",
            identity.SHOW_VERSION_BYTES: (
                b"Cisco IOS XE Software, Version 17.09.04a\r\n"
                b"cisco C9300-24T (X86) processor\r\n"
                b"Processor board ID FOC1234ABCD\r\nSwitch#"
            ),
        },
    )
    _allow_readonly_contact(monkeypatch)

    result = identity.verify_cisco_console_identity(
        port="COM5",
        baud=9600,
        candidate_fingerprint=fingerprint,
        port_enumerator=lambda: [port_info],
        connection_opener=lambda port, baud: connection,
        read_window_seconds=0,
    )

    assert result["status"] == "ready"
    assert result["detected_vendor"] == "cisco"
    assert result["identity_verified"] is True
    assert result["verification_method"] == "show-version-discriminator"
    assert result["commands_attempted"] == ["show version"]
    assert connection.writes == [b"\r\n", b"show version\r\n"]
    assert "non-empty setup-wizard answers" in result["not_attempted"]
    assert any("one blank CR/LF" in warning for warning in result["warnings"])


@pytest.mark.parametrize(
    "fresh_observation",
    [
        b"Switch(config)#",
        b"Username:",
        b"Would you like to enter the initial configuration dialog? [yes/no]:",
        b"rommon 1 >",
        b"switch:",
        b"--More--",
        b"root#",
        b"UEFI Shell>",
        b"NetApp AFF-A300 SP login:",
    ],
)
def test_unsafe_fresh_prompt_never_runs_show_version_discriminator(
    monkeypatch: pytest.MonkeyPatch,
    fresh_observation: bytes,
) -> None:
    port_info, fingerprint = _candidate()
    connection = FakeSerialConnection(
        responses={identity.INITIAL_PROMPT_BYTES: fresh_observation},
    )
    _allow_readonly_contact(monkeypatch)

    result = identity.verify_cisco_console_identity(
        port="COM5",
        baud=9600,
        candidate_fingerprint=fingerprint,
        port_enumerator=lambda: [port_info],
        connection_opener=lambda port, baud: connection,
        read_window_seconds=0,
    )

    assert result["status"] == "blocked"
    assert result["identity_verified"] is False
    assert result["commands_attempted"] == []
    assert connection.writes == [b"\r\n"]


@pytest.mark.parametrize(
    "text",
    [
        "NetApp AFF-A300 service processor",
        "FAS8200 booting",
        "SP login:",
        "BMC login:",
    ],
)
def test_plain_netapp_hardware_and_service_processor_banners_block(text: str) -> None:
    classification = identity._classify_console_identity(text)

    assert classification.detected_vendor == "netapp"
    assert classification.safe_cisco_exec is False


@pytest.mark.parametrize(
    ("current_observation", "expected_state"),
    [
        ("Cisco IOS XE Software\nSwitch(config)#", "config-mode"),
        ("Cisco IOS XE Software\nUsername:", "login-required"),
        (
            "Cisco IOS XE Software\nWould you like to enter the initial configuration dialog? [yes/no]:",
            "setup-wizard",
        ),
        ("Cisco IOS XE Software\nrommon 1 >", "rommon-bootloader"),
        ("Cisco IOS XE Software\nswitch:", "rommon-bootloader"),
        ("Cisco IOS XE Software\nSwitch#\nPassword:", "login-required"),
        ("Cisco IOS XE Software\nSwitch#\nboot still running", "unknown"),
    ],
)
def test_current_last_line_blocks_non_exec_cisco_states(
    current_observation: str,
    expected_state: str,
) -> None:
    classification = identity._classify_console_identity(current_observation)

    assert classification.detected_vendor == "cisco"
    assert classification.prompt_state == expected_state
    assert classification.safe_cisco_exec is False


def test_initial_dialog_without_cisco_marker_is_not_vendor_proof() -> None:
    classification = identity._classify_console_identity(
        "Would you like to enter the initial configuration dialog? [yes/no]:"
    )

    assert classification.detected_vendor == "unknown"
    assert classification.prompt_state == "setup-wizard"
    assert classification.safe_cisco_exec is False


def test_verify_high_confidence_cisco_exec_hashes_serial_without_raw_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chassis_serial = "FOC1234ABCD"
    port_info, fingerprint = _candidate()
    connection = FakeSerialConnection(
        passive=b"Cisco IOS XE Software\r\nSwitch#",
        responses={
            identity.SHOW_VERSION_BYTES: (
                b"Cisco IOS XE Software, Version 17.09.04a\r\n"
                b"cisco C9300-24T (X86) processor with 123456K bytes of memory.\r\n"
                b"Processor board ID " + raw_chassis_serial.encode() + b"\r\nSwitch#"
            )
        },
    )
    opened: list[tuple[str, int]] = []
    _allow_readonly_contact(monkeypatch)

    def open_selected(port: str, baud: int) -> FakeSerialConnection:
        opened.append((port, baud))
        return connection

    result = identity.verify_cisco_console_identity(
        port="COM5",
        baud=9600,
        candidate_fingerprint=fingerprint,
        port_enumerator=lambda: [
            port_info,
            FakePortInfo(
                device="COM6",
                serial_number="NETAPP-ADAPTER",
                location="1-3",
            ),
        ],
        connection_opener=open_selected,
        read_window_seconds=0,
    )

    assert result["status"] == "ready"
    assert result["detected_vendor"] == "cisco"
    assert result["identity_verified"] is True
    assert result["prompt_state"] == "privileged-exec"
    assert result["model"] == "C9300-24T"
    assert result["software_version"] == "17.09.04a"
    assert len(result["serial_fingerprint"]) == 64
    assert raw_chassis_serial not in str(result)
    assert result["commands_attempted"] == ["show version"]
    assert connection.writes == [b"show version\r\n"]
    assert opened == [("COM5", 9600)]


def test_verify_uses_inventory_only_when_version_identity_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chassis_serial = "FOC9876ZYXW"
    port_info, fingerprint = _candidate()
    connection = FakeSerialConnection(
        passive=b"Cisco IOS XE Software\r\nSwitch#",
        responses={
            identity.SHOW_VERSION_BYTES: (
                b"Cisco IOS XE Software, Version 17.12.03\r\nSwitch#"
            ),
            identity.SHOW_INVENTORY_BYTES: (
                b'NAME: "Switch 1 Chassis", DESCR: "C9300 chassis"\r\n'
                b"PID: C9300-24T-L, VID: V02, SN: "
                + raw_chassis_serial.encode()
                + b"\r\nSwitch#"
            ),
        },
    )
    _allow_readonly_contact(monkeypatch)

    result = identity.verify_cisco_console_identity(
        port="COM5",
        baud=115200,
        candidate_fingerprint=fingerprint,
        port_enumerator=lambda: [port_info],
        connection_opener=lambda port, baud: connection,
        read_window_seconds=0,
    )

    assert result["status"] == "ready"
    assert result["model"] == "C9300-24T-L"
    assert result["commands_attempted"] == ["show version", "show inventory"]
    assert connection.writes == [b"show version\r\n", b"show inventory\r\n"]
    assert raw_chassis_serial not in str(result)


def test_show_version_pager_blocks_before_ready_or_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port_info, fingerprint = _candidate()
    connection = FakeSerialConnection(
        passive=b"Cisco IOS XE Software\r\nSwitch#",
        responses={
            identity.SHOW_VERSION_BYTES: (
                b"Cisco IOS XE Software, Version 17.09.04a\r\n"
                b"cisco C9300-24T (X86) processor\r\n"
                b"Processor board ID FOC1234ABCD\r\n--More--"
            )
        },
    )
    _allow_readonly_contact(monkeypatch)

    result = identity.verify_cisco_console_identity(
        port="COM5",
        baud=9600,
        candidate_fingerprint=fingerprint,
        port_enumerator=lambda: [port_info],
        connection_opener=lambda port, baud: connection,
        read_window_seconds=0,
    )

    assert result["status"] == "blocked"
    assert result["identity_verified"] is False
    assert "pager" in result["blockers"][0]
    assert connection.writes == [b"show version\r\n"]


def test_truncated_show_version_without_current_prompt_cannot_verify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port_info, fingerprint = _candidate()
    connection = FakeSerialConnection(
        passive=b"Cisco IOS XE Software\r\nSwitch#",
        responses={
            identity.SHOW_VERSION_BYTES: (
                b"Cisco IOS XE Software, Version 17.09.04a\r\n"
                b"cisco C9300-24T (X86) processor\r\n"
                b"Processor board ID FOC1234ABCD"
            )
        },
    )
    _allow_readonly_contact(monkeypatch)

    result = identity.verify_cisco_console_identity(
        port="COM5",
        baud=9600,
        candidate_fingerprint=fingerprint,
        port_enumerator=lambda: [port_info],
        connection_opener=lambda port, baud: connection,
        read_window_seconds=0,
    )

    assert result["status"] == "blocked"
    assert result["identity_verified"] is False
    assert "did not return to a current safe exec prompt" in result["blockers"][0]
    assert result["serial_fingerprint"] is None
    assert connection.writes == [b"show version\r\n"]


def test_show_inventory_pager_blocks_before_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port_info, fingerprint = _candidate()
    connection = FakeSerialConnection(
        passive=b"Cisco IOS XE Software\r\nSwitch#",
        responses={
            identity.SHOW_VERSION_BYTES: (
                b"Cisco IOS XE Software, Version 17.09.04a\r\n"
                b"cisco C9300-24T (X86) processor\r\n"
                b"Processor board ID FOC1111AAAA\r\n"
                b"Switch Ports Model SW Version SW Image\r\nSwitch#"
            ),
            identity.SHOW_INVENTORY_BYTES: b'NAME: "Switch 1 Chassis"\r\n--More--',
        },
    )
    _allow_readonly_contact(monkeypatch)

    result = identity.verify_cisco_console_identity(
        port="COM5",
        baud=9600,
        candidate_fingerprint=fingerprint,
        port_enumerator=lambda: [port_info],
        connection_opener=lambda port, baud: connection,
        read_window_seconds=0,
    )

    assert result["status"] == "blocked"
    assert result["identity_verified"] is False
    assert "pager" in result["blockers"][0]
    assert connection.writes == [b"show version\r\n", b"show inventory\r\n"]


def test_multiple_inventory_chassis_identities_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port_info, fingerprint = _candidate()
    connection = FakeSerialConnection(
        passive=b"Cisco IOS XE Software\r\nSwitch#",
        responses={
            identity.SHOW_VERSION_BYTES: (
                b"Cisco IOS XE Software, Version 17.09.04a\r\nSwitch#"
            ),
            identity.SHOW_INVENTORY_BYTES: (
                b'NAME: "Switch 1 Chassis", DESCR: "C9300 chassis"\r\n'
                b"PID: C9300-24T-L, VID: V02, SN: FOC1111AAAA\r\n"
                b'NAME: "Switch 2 Chassis", DESCR: "C9300 chassis"\r\n'
                b"PID: C9300-24T-L, VID: V02, SN: FOC2222BBBB\r\nSwitch#"
            ),
        },
    )
    _allow_readonly_contact(monkeypatch)

    result = identity.verify_cisco_console_identity(
        port="COM5",
        baud=9600,
        candidate_fingerprint=fingerprint,
        port_enumerator=lambda: [port_info],
        connection_opener=lambda port, baud: connection,
        read_window_seconds=0,
    )

    assert result["status"] == "blocked"
    assert result["identity_verified"] is False
    assert "Multiple Cisco chassis or stack identities" in result["blockers"][0]
    assert result["serial_fingerprint"] is None


def test_reader_handles_delayed_chunks_and_uses_baud_sized_hard_deadline() -> None:
    connection = ChunkedSerialConnection(
        [
            b"Cisco IOS",
            b"",
            b" XE Software\r\n",
            b"",
            b"\x1b[32mSwitch#\x1b[0m",
        ]
    )

    text = identity._read_serial_text(
        connection,
        baud=9600,
        hard_deadline_seconds=0.25,
        quiet_seconds=0.01,
    )

    assert "Cisco IOS XE Software" in text
    assert identity._safe_exec_prompt_state(text) == "privileged-exec"
    assert 18.0 <= identity._identity_hard_deadline_seconds(9600) <= 20.0


@pytest.mark.parametrize(
    ("selected_port", "selected_fingerprint", "expected"),
    [
        ("COM6", "a" * 64, "no longer present"),
        ("COM5", "b" * 64, "fingerprint changed"),
    ],
)
def test_missing_or_changed_candidate_blocks_before_port_open(
    monkeypatch: pytest.MonkeyPatch,
    selected_port: str,
    selected_fingerprint: str,
    expected: str,
) -> None:
    port_info, _fingerprint = _candidate()
    opens: list[tuple[str, int]] = []
    _allow_readonly_contact(monkeypatch)

    result = identity.verify_cisco_console_identity(
        port=selected_port,
        baud=9600,
        candidate_fingerprint=selected_fingerprint,
        port_enumerator=lambda: [port_info],
        connection_opener=lambda port, baud: opens.append((port, baud)),
        read_window_seconds=0,
    )

    assert result["status"] == "blocked"
    assert expected in result["blockers"][0]
    assert opens == []


def test_candidate_without_stable_usb_binding_blocks_before_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port_info, fingerprint = _candidate(
        serial_number=None,
        location=None,
        hwid="USB VID:PID=067B:2303",
    )
    opens: list[tuple[str, int]] = []
    _allow_readonly_contact(monkeypatch)

    result = identity.verify_cisco_console_identity(
        port="COM5",
        baud=9600,
        candidate_fingerprint=fingerprint,
        port_enumerator=lambda: [port_info],
        connection_opener=lambda port, baud: opens.append((port, baud)),
        read_window_seconds=0,
    )

    assert result["status"] == "blocked"
    assert "stable serial, USB location, or by-id binding" in result["blockers"][0]
    assert opens == []


def test_identity_request_schema_rejects_scan_or_network_inputs() -> None:
    with pytest.raises(ValidationError):
        CiscoConsoleIdentityVerifyCreate(
            port="COM5",
            baud=57600,
            candidate_fingerprint="a" * 64,
        )
    with pytest.raises(ValidationError):
        CiscoConsoleIdentityVerifyCreate(
            port="tcp://127.0.0.1:2001",
            baud=9600,
            candidate_fingerprint="a" * 64,
        )
    with pytest.raises(ValidationError):
        CiscoConsoleIdentityVerifyCreate(
            port="COM5",
            baud=9600,
            candidate_fingerprint="not-a-fingerprint",
        )


def test_explicit_identity_path_does_not_update_legacy_probe_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port_info, fingerprint = _candidate()
    connection = FakeSerialConnection(
        passive=b"Cisco IOS XE Software\r\nSwitch#",
        responses={
            identity.SHOW_VERSION_BYTES: (
                b"Cisco IOS XE Software, Version 17.09.04a\r\n"
                b"cisco C9300-24T (X86) processor\r\n"
                b"Processor board ID FOC1234ABCD\r\nSwitch#"
            )
        },
    )
    _allow_readonly_contact(monkeypatch)
    assert get_probe_result(identity.PROVIDER_ID) == (None, None)

    identity.list_cisco_console_identity_candidates(
        port_enumerator=lambda: [port_info],
    )
    identity.verify_cisco_console_identity(
        port="COM5",
        baud=9600,
        candidate_fingerprint=fingerprint,
        port_enumerator=lambda: [port_info],
        connection_opener=lambda port, baud: connection,
        read_window_seconds=0,
    )

    assert get_probe_result(identity.PROVIDER_ID) == (None, None)


def test_identity_routes_use_new_backend_contract_not_legacy_prompt_readiness(
    client: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_payload = identity.list_cisco_console_identity_candidates(
        port_enumerator=lambda: [FakePortInfo(device="COM5")],
    )
    fingerprint = candidate_payload["candidates"][0]["candidate_fingerprint"]
    verify_payload = identity._base_verification_result(
        port="COM5",
        baud=9600,
        candidate_fingerprint=fingerprint,
    )
    verify_payload.update(
        {
            "status": "ready",
            "message": "verified",
            "detected_vendor": "cisco",
            "identity_verified": True,
            "prompt_state": "privileged-exec",
            "model": "C9300-24T",
            "software_version": "17.09.04a",
            "serial_fingerprint": "c" * 64,
            "commands_attempted": ["show version"],
            "blockers": [],
        }
    )
    monkeypatch.setattr(
        routes,
        "list_cisco_console_identity_candidates",
        lambda: candidate_payload,
    )
    monkeypatch.setattr(
        routes,
        "verify_cisco_console_identity",
        lambda **_kwargs: verify_payload,
    )

    candidates_response = client.get(
        "/api/v1/providers/cisco-console/identity-candidates"
    )
    verify_response = client.post(
        "/api/v1/providers/cisco-console/verify-identity",
        json={
            "port": "COM5",
            "baud": 9600,
            "candidate_fingerprint": fingerprint,
        },
    )

    assert candidates_response.status_code == 200
    assert candidates_response.json()["candidates"][0]["port"] == "COM5"
    assert verify_response.status_code == 200
    assert verify_response.json()["identity_verified"] is True
    assert verify_response.json()["serial_fingerprint"] == "c" * 64
