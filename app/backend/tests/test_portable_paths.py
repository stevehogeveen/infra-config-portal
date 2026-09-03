from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_checker():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "check-portable-paths.py"
    spec = importlib.util.spec_from_file_location("check_portable_paths_under_test", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    return module


checker = _load_checker()


def test_portable_path_checker_accepts_normal_repo_paths() -> None:
    assert checker.path_errors("app/backend/tests/test_api.py") == []
    assert checker.path_errors("scripts/check-portable-paths.py") == []
    assert checker.path_errors("config/firmware-baselines/real-lab.yml") == []


def test_portable_path_checker_rejects_windows_unsafe_names() -> None:
    cases = {
        'try, validation, NetApp setup, and minimal UI" ': [
            "ends with a space or dot",
            "reserved character",
        ],
        "reports/final.": ["ends with a space or dot"],
        "artifacts/CON/report.md": ["reserved Windows device name"],
        "artifacts/LPT1.txt": ["reserved Windows device name"],
        "app\\backend\\bad.py": ["contains backslash", "reserved character"],
        "app/backend/question?.py": ["reserved character"],
    }

    for path, expected_fragments in cases.items():
        errors = checker.path_errors(path)
        assert errors, path
        for fragment in expected_fragments:
            assert any(fragment in error for error in errors), (path, errors)


def test_portable_path_checker_rejects_control_characters_and_long_paths() -> None:
    assert any("control character" in error for error in checker.path_errors("app/bad\nname.py"))

    long_path = "artifacts/" + ("nested/" * 40) + "report.md"
    assert any("longer than 240" in error for error in checker.path_errors(long_path))


def test_portable_path_main_reports_success(monkeypatch, capsys) -> None:
    monkeypatch.setattr(checker, "git_paths", lambda: ["README.md", "app/backend/app/main.py"])

    assert checker.main() == 0

    captured = capsys.readouterr()
    assert "Portable path check passed (2 path(s))." in captured.out
    assert captured.err == ""


def test_portable_path_main_reports_failures(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        checker,
        "git_paths",
        lambda: ["README.md", 'try, validation, NetApp setup, and minimal UI" '],
    )

    assert checker.main() == 1

    captured = capsys.readouterr()
    assert "Portable path check failed:" in captured.err
    assert 'try, validation, NetApp setup, and minimal UI" ' in captured.err
