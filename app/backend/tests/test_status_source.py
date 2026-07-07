from __future__ import annotations

from app.services.status_source import status_source_metadata


def test_status_source_evidence_artifacts_keeps_scalar_string_whole() -> None:
    metadata = status_source_metadata(
        source_type="historical_artifact",
        evidence_artifacts="artifacts/codex-runs/build-verification-report.md",
    )

    assert metadata["evidence_artifacts"] == [
        "artifacts/codex-runs/build-verification-report.md"
    ]


def test_status_source_evidence_artifacts_strips_and_dedupes_iterables() -> None:
    metadata = status_source_metadata(
        source_type="historical_artifact",
        evidence_artifacts=[
            " artifacts/one.md ",
            "",
            "artifacts/one.md",
            None,
            "artifacts/two.md",
        ],
    )

    assert metadata["evidence_artifacts"] == ["artifacts/one.md", "artifacts/two.md"]


def test_status_source_evidence_artifacts_accepts_scalar_values() -> None:
    metadata = status_source_metadata(
        source_type="historical_artifact",
        evidence_artifacts=123,
    )

    assert metadata["evidence_artifacts"] == ["123"]
