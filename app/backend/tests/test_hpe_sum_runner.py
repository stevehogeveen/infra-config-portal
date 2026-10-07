"""Fake local executables test transport, not SUM compatibility or installation."""

import hashlib
import os
import sys

import pytest

from app.providers.hpe_sum_assessment import report_invocation
from app.providers.hpe_sum_runner import SumRunner, SumRunnerError, install_invocation

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Linux-only subprocess transport")


@pytest.fixture
def setup(tmp_path):
    binary = tmp_path / "packages" / "x64" / "sum_bin_x64"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        f"#!{sys.executable}\n"
        + """import os, pathlib, sys
args = sys.argv
inp = pathlib.Path(args[args.index("--inputfile") + 1])
assert inp.stat().st_mode & 0o777 == 0o600
assert "fixture-password" in inp.read_text()
assert "fixture-password" not in " ".join(args)
root = pathlib.Path(args[args.index("--reportdir") + 1])
(root / "fixture.xml").write_text("<report>fixture only</report>")
"""
    )
    binary.chmod(0o700)
    runner = SumRunner(
        binary, hashlib.sha256(binary.read_bytes()).hexdigest(), tmp_path / "jobs", timeout=2
    )

    def args(input_path, report_dir):
        return dict(
            executable=str(binary),
            input_path=input_path,
            report_dir=report_dir,
            baseline=str(tmp_path / "baseline"),
            host="192.0.2.10",
            username="fixture",
            password="fixture-password",
        )

    return runner, args


def test_report_job_private_and_removed_without_leaking_secrets(setup):
    runner, args = setup
    result = runner.run(lambda i, r: report_invocation(report="preview", **args(i, r)))
    assert result.returncode == 0
    assert result.reports == (("fixture.xml", b"<report>fixture only</report>"),)
    assert list(runner.root.iterdir()) == []
    assert "fixture" not in repr(result)


def test_install_claim_survives_new_runner_and_never_repeats(setup):
    runner, args = setup
    def command(i, r):
        return install_invocation(
            components=["firmware.rpm"], reboot_allowed=False, **args(i, r)
        )
    built = command("/tmp/input", "/tmp/reports")
    assert "--dryrun" not in built.argv and "--report" not in built.argv
    assert "COMPONENTSLIST = firmware.rpm" in built.input_content
    assert "ROMONLY = YES" in built.input_content and "REBOOTALLOWED = NO" in built.input_content
    assert "fixture-password" not in repr(built)
    with pytest.raises(SumRunnerError):
        runner.run(command)
    assert runner.run(command, dispatch_id="op_step").returncode == 0
    restarted = SumRunner(runner.executable, runner.expected_sha256, runner.root)
    with pytest.raises(SumRunnerError, match="already claimed"):
        restarted.run(command, dispatch_id="op_step")
    assert [p.name for p in runner.root.iterdir()] == ["op_step.claimed"]


@pytest.mark.parametrize("filename", ["../x.rpm", "x.rpm, y.rpm", "x.rpm\nFORCE=YES", "x.fwpkg"])
def test_unqualified_component_types_or_injection_rejected(setup, filename):
    _, args = setup
    with pytest.raises(ValueError):
        install_invocation(components=[filename], reboot_allowed=False, **args("/tmp/i", "/tmp/r"))


def test_runtime_change_stops_before_launch(setup):
    runner, args = setup
    runner.executable.write_text("changed")
    with pytest.raises(SumRunnerError, match="changed"):
        runner.run(lambda i, r: report_invocation(report="preview", **args(i, r)))


def test_timeout_keeps_claim_and_discards_credentials(setup):
    runner, args = setup
    runner.executable.write_text(f"#!{sys.executable}\nimport time; time.sleep(30)\n")
    runner.expected_sha256 = hashlib.sha256(runner.executable.read_bytes()).hexdigest()
    with pytest.raises(SumRunnerError, match="unknown"):
        runner.run(
            lambda i, r: install_invocation(
                components=["firmware.rpm"], reboot_allowed=False, **args(i, r)
            ),
            dispatch_id="timeout",
        )
    assert [p.name for p in runner.root.iterdir()] == ["timeout.claimed"]
