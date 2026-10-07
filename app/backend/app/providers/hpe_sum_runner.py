"""Private, bounded SUM subprocess transport. Exit status is never installation proof.

Callers authenticate the complete runtime/baseline and own durable dispatch
authority. This module does not discover targets or grant permissions.
"""

import hashlib
import os
import re
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from app.providers.hpe_sum_assessment import ReportInvocation, report_invocation


class SumRunnerError(ValueError):
    """Fixed messages only: never include raw SUM output or input-file credentials."""


@dataclass(frozen=True)
class SumResult:
    returncode: int
    reports: tuple[tuple[str, bytes], ...] = field(repr=False)


def install_invocation(*, components, reboot_allowed: bool, **connection):
    """Build the vendor-documented firmware-only, component-restricted command.

    No force, rewrite, downgrade, TPM bypass, discovery, or recovery-set changes.
    Online FWPKG dispatch on iLO7 requires its own qualified versioned adapter.
    """
    if type(reboot_allowed) is not bool or not 1 <= len(components) <= 256:
        raise ValueError("Explicit component selection and restart policy required.")
    if len(set(components)) != len(components) or any(
        not isinstance(name, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,240}\.(rpm|exe|scexe)", name)
        or ".." in name
        for name in components
    ):
        raise ValueError("Unsupported SUM component filename.")
    read = report_invocation(report="preview", **connection)
    content = read.input_content.replace("DRYRUN = YES\n", "")
    content = content.replace(
        "[TARGETS]\n",
        "\n".join(
            [
                "ROMONLY = YES",
                "REWRITE = NO",
                "DOWNGRADE = NO",
                "SKIPTARGET = YES",
                "REBOOTALLOWED = " + ("YES" if reboot_allowed else "NO"),
                "REBOOTALWAYS = NO",
                "COMPONENTSLIST = " + ", ".join(components),
                "[TARGETS]",
                "",
            ]
        ),
    )
    return ReportInvocation(
        argv=tuple(arg for arg in read.argv if arg not in {"--report", "--dryrun"}),
        environment=read.environment,
        input_content=content,
        network_target=read.network_target,
        report="install",  # Internal command kind; never accepted as a report-mode argument.
    )


class SumRunner:
    def __init__(self, executable: Path, expected_sha256: str, job_root: Path, timeout=1800):
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256) or not 1 <= timeout <= 14400:
            raise ValueError("Invalid authenticated runtime identity or timeout.")
        self.executable = executable
        self.expected_sha256 = expected_sha256
        self.root = job_root
        self.timeout = timeout

    def _validate(self):
        if os.name != "posix":
            raise SumRunnerError("SUM transport requires the isolated Linux runner.")
        if (
            not self.executable.is_absolute()
            or self.executable.is_symlink()
            or not self.executable.is_file()
        ):
            raise SumRunnerError("SUM executable is not a regular authenticated file.")
        with self.executable.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != self.expected_sha256:
            raise SumRunnerError("SUM executable changed after authentication.")
        if not self.root.is_absolute() or self.root.is_symlink():
            raise SumRunnerError("SUM job root must be a private local directory.")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.stat().st_mode & 0o077:
            raise SumRunnerError("SUM job root permissions must be private.")

    def run(self, build_invocation, *, dispatch_id: str | None = None) -> SumResult:
        """Build secrets only within a private job. Caller parses report bytes.

        Installation requires an operation/step-scoped one-shot dispatch ID.
        Its durable marker intentionally survives errors and runner restarts.
        """
        self._validate()
        with TemporaryDirectory(prefix="sum-", dir=self.root) as temp:
            work = Path(temp)
            report_dir = work / "reports"
            report_dir.mkdir(mode=0o700)
            input_path = work / "input.txt"
            invocation = build_invocation(str(input_path), str(report_dir))
            if (
                invocation.argv[0] != str(self.executable)
                or "--inputfile" not in invocation.argv
                or invocation.argv[invocation.argv.index("--inputfile") + 1] != str(input_path)
                or "--reportdir" not in invocation.argv
                or invocation.argv[invocation.argv.index("--reportdir") + 1] != str(report_dir)
            ):
                raise SumRunnerError("SUM invocation does not match its private job.")
            installing = invocation.report == "install"
            if installing:
                if not dispatch_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", dispatch_id):
                    raise SumRunnerError("An exact durable dispatch claim is required.")
                try:
                    fd = os.open(
                        self.root / (dispatch_id + ".claimed"),
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                    )
                    with os.fdopen(fd, "w") as marker:
                        marker.write(self.expected_sha256)
                        marker.flush()
                        os.fsync(marker.fileno())
                    directory = os.open(self.root, os.O_DIRECTORY)
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                except FileExistsError:
                    raise SumRunnerError(
                        "This SUM dispatch was already claimed; no retry sent."
                    ) from None
            elif dispatch_id is not None or "--dryrun" not in invocation.argv:
                raise SumRunnerError("Assessment must remain explicitly read-only.")
            fd = os.open(input_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(invocation.input_content)
            env = dict(invocation.environment)
            env.update({"HOME": str(work), "TMPDIR": str(work), "LC_ALL": "C"})
            process = None
            try:
                process = subprocess.Popen(
                    invocation.argv,
                    cwd=work,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    umask=0o077,
                )
                code = process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                raise SumRunnerError(
                    "SUM timed out; an installation outcome remains unknown."
                ) from None
            except OSError:
                raise SumRunnerError(
                    "SUM process could not be started; no automatic retry."
                ) from None
            finally:
                if process is not None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                input_path.unlink(missing_ok=True)
            reports = []
            total = 0
            for entry in report_dir.iterdir():
                if entry.suffix.lower() != ".xml":
                    continue
                if entry.is_symlink() or not entry.is_file() or len(reports) >= 32:
                    raise SumRunnerError("SUM report files exceed the supported bounds.")
                if entry.stat().st_size > 8 * 1024 * 1024:
                    raise SumRunnerError("SUM report is too large.")
                data = entry.read_bytes()
                total += len(data)
                if len(data) > 8 * 1024 * 1024 or total > 32 * 1024 * 1024:
                    raise SumRunnerError("SUM report output exceeds the supported limit.")
                reports.append((entry.name, data))
            return SumResult(code, tuple(reports))
