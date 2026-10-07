import pytest

from app.services.blocker_guidance import (
    RULES,
    BlockerDetail,
    describe_blockers,
    with_blocker_details,
)


@pytest.mark.parametrize("rule", RULES, ids=[r[0] for r in RULES])
def test_known_codes_and_actions_preserve_original_message(rule):
    code, prefixes, kind, fix, action = rule
    for prefix in prefixes:
        text = prefix + " fixture detail"
        detail = describe_blockers([text])[0]
        assert detail == dict(code=code, text=text, fix_kind=kind, fix=fix, action=action)
        BlockerDetail.model_validate(detail)


def test_unknown_messages_never_guess_a_repair_or_unlock():
    original = {"blockers": ["Unexpected vendor failure", "Do not run erase"], "can_apply": False}
    result = with_blocker_details(original)
    assert result["blockers"] == original["blockers"] and result["can_apply"] is False
    assert "blocker_details" not in original
    assert all(
        d["code"] == "review_required" and d["action"] == "none" for d in result["blocker_details"]
    )


def test_no_blockers_means_no_guidance():
    assert with_blocker_details({"blockers": []})["blocker_details"] == []


def test_unknown_action_cannot_enter_contract():
    with pytest.raises(ValueError):
        BlockerDetail(code="x", text="x", fix_kind="app", fix="x", action="erase")
