from pathlib import Path

import pytest

from app.providers.hpe_sum_reports import LIMIT, SumReportError, parse_repository_report

FIXTURE = Path(__file__).parent / "fixtures" / "sum1270-inventory.xml"


def test_observed_repository_report_preserves_warning_not_authority():
    report = parse_repository_report(FIXTURE.read_bytes())
    component = report.components[0]
    assert component.version == "3.19"
    assert component.status == "Component signature file missing"
    assert component.reboot_required == "No"
    assert not report.can_apply and not report.signature_verified
    assert not report.target_applicability_verified
    assert len(report.sha256) == 64
    assert "/fixture/baseline" not in repr(report)


@pytest.mark.parametrize(
    "old,new",
    [
        ("<report_type>0", "<report_type>1"),
        ("SUM 12.7.0", "SUM 99.0.0"),
        ("<language>en", "<language>ja"),
        ("<report>", '<report xmlns="unknown">'),
        ("<report>", '<!DOCTYPE report [<!ENTITY x "bad">]><report>'),
        ("<version>3.19</version>", "<version>3.19</version><version>1.48</version>"),
        ("<version>3.19</version>", "<version></version>"),
        ("firmware-ilo5-3.19-1.1.x86_64.rpm", "../payload.rpm"),
        ("<typeofcomponent>Firmware", "<typeofcomponent>Software"),
        ("</component>", "<unexpected>value</unexpected></component>"),
        ("</report>", ""),
    ],
)
def test_unknown_ambiguous_or_unsafe_report_rejected(old, new):
    with pytest.raises(SumReportError):
        parse_repository_report(FIXTURE.read_text().replace(old, new).encode())


@pytest.mark.parametrize("data", [b"", b"x" * (LIMIT + 1), b"\xff", b"<report>\x00</report>"])
def test_bounded_input(data):
    with pytest.raises(SumReportError):
        parse_repository_report(data)


def test_duplicate_component_rejected():
    text = FIXTURE.read_text()
    component = text[text.index("<component>") : text.index("</component>") + len("</component>")]
    with pytest.raises(SumReportError):
        parse_repository_report(
            text.replace("</inventoryreport>", component + "</inventoryreport>").encode()
        )
