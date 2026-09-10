"""GUI navigation (§11.3, row 47): a bounded sense→propose→act loop.

Every scenario runs on the virtual limb and a scripted navigation tier, so the
loop itself — its honesty about unplannable screens, its budget, its
permission discipline — is what is demonstrated end to end.
"""

from __future__ import annotations

import pytest

from beanie.automation import Navigator, VirtualGUIDriver, NavReport
from beanie.body import AuthorityGate
from beanie.stores import Memory
from beanie.substrate import StubSubstrate


def _substrate(script: list[dict]) -> StubSubstrate:
    return StubSubstrate(scripted_gui_actions=script)


def test_navigates_a_login_screen_to_success():
    driver = VirtualGUIDriver(screens=["Username [ ]  Login", "Password [ ]  Login", "Welcome"])
    substrate = _substrate([
        {"type": "type", "target": "Username", "text": "kigz", "reason": "fill the username"},
        {"type": "type", "target": "Password", "text": "secret", "reason": "fill the password"},
        {"type": "click", "target": "Login", "x": 200, "y": 400, "reason": "submit"},
        {"type": "done", "reason": "welcome screen reached"},
    ])
    report = Navigator(driver, substrate).run("log in with the saved account")
    assert report.outcome == "completed"
    assert [step.action["type"] for step in report.steps] == ["type", "type", "click"]
    assert driver.executed[2]["type"] == "click"


def test_permission_gate_blocks_screen_control_until_allowed(tmp_path):
    driver = VirtualGUIDriver(screens=["anything"])
    substrate = _substrate([
        {"type": "click", "target": "Install", "x": 1, "y": 1},
        {"type": "done", "reason": "installed"},
    ])
    gate = AuthorityGate(Memory(tmp_path))  # no rule → default ask
    report = Navigator(driver, substrate, gate).run("click the install button")
    assert report.outcome == "needs_permission"
    assert "you may gui_control" in report.permission_question
    assert driver.executed == []  # no click without a rule
    gate.grant("gui_control", "allow")  # the owner said: you may gui_control
    report = Navigator(driver, substrate, gate).run("click the install button")
    assert report.outcome == "completed"  # the same queued actions now execute
    assert driver.executed and driver.executed[0]["type"] == "click"


def test_unplannable_screen_is_reported_never_guessed():
    substrate = _substrate([])  # tier proposes nothing
    driver = VirtualGUIDriver()
    report = Navigator(driver, substrate).run("get to the settings")
    assert report.outcome == "unplannable"
    assert "guessing" in report.note
    assert driver.executed == []


def test_out_of_vocabulary_actions_are_refused():
    substrate = _substrate([{"type": "delete_everything"}])
    driver = VirtualGUIDriver()
    report = Navigator(driver, substrate).run("open the menu")
    assert report.outcome == "unplannable"
    assert "out-of-vocabulary" in report.note or "refused" in report.note


def test_budget_notice_is_honest_not_victory():
    substrate = _substrate([{"type": "wait", "ms": 10}] * 50)
    driver = VirtualGUIDriver()
    report = Navigator(driver, substrate, max_actions=4).run("wait forever")
    assert report.outcome == "budget"
    assert "paused" in report.note and len(report.steps) == 4


def test_fail_actions_surface_the_reason():
    substrate = _substrate([{"type": "fail", "reason": "the connection panel is greyed out"}])
    driver = VirtualGUIDriver()
    report = Navigator(driver, substrate).run("open wifi settings")
    assert report.outcome == "failed"
    assert "greyed out" in report.note
