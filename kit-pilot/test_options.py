"""Flight options from the briefing: skipped legs are never flown; a switch with settings is replaced only when chosen."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chaos  # noqa: E402
from engine import Engine, NeedsYou  # noqa: E402


class Kit(chaos.FakeKit):
    def __init__(self, configured_switch=False):
        super().__init__()
        self.configured_switch = configured_switch
        self.replace_sent = None

    def apply(self, method, path, body):
        key = path.split("?")[0].split("fixture/")[-1]
        if key == "switch-setup/review":
            return {"blockers": [], "replace_needed": self.configured_switch}
        if key == "switch-setup/start":
            self.replace_sent = body.get("replace_existing")
        return super().apply(method, path, body)


def fly(kit, **options):
    api = chaos.ChaosApi(kit, {}, __import__("threading").Event())
    engine = Engine(api, chaos.P, chaos.SERVERS, chaos.SWITCHES, clock=lambda s: None, **options)
    states = {}
    engine.fly(0, lambda i, state: states.__setitem__(engine.legs[i].id, state))
    return states


def test_skipped_legs_send_nothing():
    kit = Kit()
    states = fly(kit, skip={"firmware", "acceptance"})
    assert states["firmware"] == "skipped" and states["acceptance"] == "skipped"
    assert not any(change in ("parts-update/start", "firmware-update/apply", "windows/acceptance/start") for change, _ in kit.writes)
    assert kit.scope == "read_only"


def test_a_switch_with_settings_stops_unless_replacement_was_chosen():
    kit = Kit(configured_switch=True)
    api = chaos.ChaosApi(kit, {}, __import__("threading").Event())
    with pytest.raises(NeedsYou, match="Replace them"):
        Engine(api, chaos.P, chaos.SERVERS, chaos.SWITCHES, clock=lambda s: None).leg_switch()
    assert kit.replace_sent is None
    kit = Kit(configured_switch=True)
    fly(kit, replace_switch=True)
    assert kit.replace_sent is True
    kit = Kit(configured_switch=False)
    fly(kit, replace_switch=True)
    assert kit.replace_sent is False  # a new switch is never flagged as replaced


def test_a_verified_switch_that_stopped_answering_is_set_up_again():
    kit = Kit(configured_switch=True)
    kit.sw = "verified"
    kit.sw_gone = True
    states = fly(kit, replace_switch=True)
    assert states["switch"] == "done" and kit.replace_sent is True


def test_a_verified_switch_that_still_answers_is_left_alone():
    kit = Kit()
    kit.sw = "verified"
    states = fly(kit)
    assert states["switch"] == "skipped" and kit.replace_sent is None
