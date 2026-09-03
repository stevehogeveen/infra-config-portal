from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "provider_lab_live_status.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("provider_lab_live_status_script", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_live_status_parse_json_accepts_noisy_stdout() -> None:
    script = _load_script()

    assert script._parse_json('{"status": "ready"}') == {"status": "ready"}
    assert script._parse_json('warning: ignored\n{"status": "blocked", "blockers": ["x"]}\ntrailing') == {
        "status": "blocked",
        "blockers": ["x"],
    }


def test_provider_live_status_parse_json_rejects_non_object_stdout() -> None:
    script = _load_script()

    assert script._parse_json("") == {}
    assert script._parse_json("not-json") == {}
    assert script._parse_json('["not", "object"]') == {}
    assert script._parse_json("prefix {not-json} suffix") == {}


def test_provider_live_status_main_dedupes_blockers(monkeypatch, tmp_path: Path, capsys) -> None:
    script = _load_script()
    run_dir = tmp_path / "artifacts" / "codex-runs"
    monkeypatch.setattr(script, "CODEX_RUN_DIR", run_dir)
    monkeypatch.setattr(script, "REPORT", run_dir / "provider-lab-live-status-report.md")
    monkeypatch.setattr(script, "SUMMARY", run_dir / "provider-lab-live-status-redacted.json")
    monkeypatch.setattr(script, "STAGES", [("one", [], "one.md"), ("two", [], "two.md")])
    monkeypatch.setattr(script, "_real_lab_env", lambda: {})
    monkeypatch.setattr(
        script,
        "_run_stage",
        lambda name, _command, report, _env: {
            "stage": name,
            "status": "blocked",
            "report": report,
            "blockers": ["duplicate blocker", "unique blocker"] if name == "one" else ["duplicate blocker"],
            "warnings": [],
        },
    )

    assert script.main() == 0

    saved = json.loads(script.SUMMARY.read_text(encoding="utf-8"))
    assert saved["blockers"] == ["duplicate blocker", "unique blocker"]
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
