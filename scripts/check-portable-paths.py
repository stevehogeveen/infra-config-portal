#!/usr/bin/env python3
"""Fail when tracked or unignored paths are unsafe for Windows/Linux checkouts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import PurePosixPath


WINDOWS_RESERVED_CHARS = set('<>:"\\|?*')
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def git_paths() -> list[str]:
    output = subprocess.check_output(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ]
    )
    return [path.decode("utf-8", "replace") for path in output.split(b"\0") if path]


def path_errors(path: str) -> list[str]:
    errors: list[str] = []
    parts = PurePosixPath(path).parts

    if "\\" in path:
        errors.append("contains backslash")

    for part in parts:
        if part in {"", ".", ".."}:
            errors.append(f"contains unsafe path component {part!r}")
            continue
        if part.endswith(" ") or part.endswith("."):
            errors.append(f"component {part!r} ends with a space or dot")
        if any(ord(char) < 32 for char in part):
            errors.append(f"component {part!r} contains a control character")
        bad_chars = sorted(WINDOWS_RESERVED_CHARS.intersection(part))
        if bad_chars:
            errors.append(f"component {part!r} contains reserved character(s) {''.join(bad_chars)!r}")
        stem = part.split(".", 1)[0].upper()
        if stem in WINDOWS_RESERVED_NAMES:
            errors.append(f"component {part!r} uses reserved Windows device name {stem!r}")

    if len(path) > 240:
        errors.append("path is longer than 240 characters")

    return errors


def main() -> int:
    try:
        paths = git_paths()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"portable path check failed to read git paths: {exc}", file=sys.stderr)
        return 2

    failures = [(path, path_errors(path)) for path in paths]
    failures = [(path, errors) for path, errors in failures if errors]

    if not failures:
        print(f"Portable path check passed ({len(paths)} path(s)).")
        return 0

    print("Portable path check failed:", file=sys.stderr)
    for path, errors in failures:
        print(f"  {path}", file=sys.stderr)
        for error in errors:
            print(f"    - {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    if os.name == "nt":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
