import io
from types import SimpleNamespace

import pytest

from app.providers import hpe_sum_assessment as provider
from app.services.firmware_packages import FirmwarePackageError


def invocation(**changes):
    return provider.report_invocation(
        report="firmware",
        executable="/runner/x64/sum_bin_x64",
        input_path="/run/private/input.txt",
        report_dir="/run/reports",
        baseline="/baseline",
        host="192.0.2.10",
        username="fixture",
        password="private-fixture",
        **changes,
    )


@pytest.mark.parametrize("report", ["preview", "firmware", "dependency", "inventory"])
def test_only_report_commands_no_secrets_in_argv_or_repr(report):
    value = provider.report_invocation(
        report=report,
        executable="/runner/x64/sum_bin_x64",
        input_path="/run/input",
        report_dir="/run/reports",
        baseline="/baseline",
        host="192.0.2.10",
        username="fixture",
        password="private-fixture",
    )
    assert ("--report" if report == "preview" else f"--{report}_report") in value.argv
    assert "--dryrun" in value.argv
    assert dict(value.environment)["LEGACYMODE"] == "1"
    assert dict(value.environment)["SUM_ROOT"] == "/runner"
    assert dict(value.environment)["INPUTFILEPATH"] == "/run/input"
    assert "DRYRUN = YES" in value.input_content
    assert "private-fixture" not in repr(value)
    assert "private-fixture" not in " ".join(value.argv)
    assert "192.0.2.10" not in repr(value)
    assert "--reboot" not in value.argv


@pytest.mark.parametrize(
    "field,value",
    [
        ("report", "installed"),
        ("report", "combined"),
        ("report", "deploy"),
        ("host", "192.0.2.10\nREBOOT=YES"),
        ("host", "https://example.invalid/path"),
        ("password", "pass\n[END]\nFORCEALL=YES"),
        ("username", "fixture\r\nHOST=other"),
        ("baseline", "/baseline;deploy"),
        ("input_path", "/tmp/../secret"),
        ("executable", "relative"),
        ("report_dir", "/reports with spaces"),
    ],
)
def test_uncontrolled_arguments_and_mutating_report_modes_rejected(field, value):
    args = dict(
        report="firmware",
        executable="/runner/x64/sum_bin_x64",
        input_path="/run/input",
        report_dir="/run/reports",
        baseline="/baseline",
        host="192.0.2.10",
        username="fixture",
        password="private-fixture",
    )
    args[field] = value
    with pytest.raises(ValueError):
        provider.report_invocation(**args)


@pytest.fixture
def iso(monkeypatch):
    state = {"markers": ["sum1270_b16.txt"], "symlink": False, "length": 7, "changed": False}

    class ISO:
        def open(self, path):
            pass

        def close(self):
            pass

        def walk(self, **kwargs):
            return [("/packages", [], state["markers"])]

        def get_record(self, **kwargs):
            return SimpleNamespace(data_length=state["length"], is_symlink=lambda: state["symlink"])

        def open_file_from_iso(self, **kwargs):
            return io.BytesIO(b"fixture")

    monkeypatch.setattr(provider.pycdlib, "PyCdlib", ISO)
    monkeypatch.setattr(provider, "media_path", lambda path: path)
    monkeypatch.setattr(provider, "package_unchanged", lambda package: not state["changed"])
    return state


def test_bundle_inspection_is_not_authentication_or_hardware_support(iso):
    result = provider.inspect_sum_bundle({"path": "fixture.iso"})
    assert result["build_marker"] == "sum1270_b16.txt"
    assert len(result["members"]) == 3
    for key in (
        "binary_authenticated",
        "runtime_verified",
        "hardware_support_verified",
        "can_apply",
    ):
        assert result[key] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("markers", []),
        ("markers", ["sum1270_b16.txt", "sum1260_b10.txt"]),
        ("symlink", True),
        ("length", 10000000),
        ("length", 8),
        ("changed", True),
    ],
)
def test_ambiguous_unsafe_or_changed_bundle_rejected(iso, field, value):
    iso[field] = value
    with pytest.raises(FirmwarePackageError):
        provider.inspect_sum_bundle({"path": "fixture.iso"})
