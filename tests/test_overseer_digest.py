"""Overseer day-digest (§5, brief #7): "what did we do today?" is a first-class question.

The human overseer should never need log files for a normal audit. Two
conversational routes answer from the record itself: the day digest counts
what the trace actually holds for today (or yesterday), and the working-on
report surfaces what is live — pending permission asks, a paused takeover,
parked incubator problems. Inventory from the record, or none; never
invented activity, never a facsimile of activity.
"""

from __future__ import annotations

import datetime

from beanie import Mind


def _harvest_day(mind: Mind, day: datetime.date) -> dict[str, int]:
    from collections import Counter

    kinds = Counter(
        event.kind for event in mind.trace.events if event.at.startswith(day.isoformat())
    )
    return dict(kinds)


def test_day_digest_counts_what_today_holds_never_more(tmp_path, monkeypatch):
    monkeypatch.delenv("BEANIE_BODY_OS", raising=False)
    mind = Mind(state_dir=tmp_path / "state")
    mind.step("hello there")

    reply = mind.step("what did we do today?")
    today = datetime.date.today().isoformat()
    harvested = _harvest_day(mind, datetime.date.today())
    assert today in reply.text or "today" in reply.text
    assert "decision" in reply.text.lower()          # a real route ran and is counted
    assert str(harvested.get("decision", 0)) in reply.text   # the number matches the record
    reply = mind.step("what did we do yesterday?")
    assert "nothing" in reply.text.lower()           # yesterday holds zero events — honestly


def test_working_on_reports_live_permission_asks(tmp_path, monkeypatch):
    monkeypatch.delenv("BEANIE_BODY_OS", raising=False)
    mind = Mind(state_dir=tmp_path / "state")
    # create one live ask through the real wall
    from beanie.planning import PlanResult

    result = PlanResult(skill_id="sk", steps=[], outcome="needs_permission")
    result.last_result = {"capability": "open_url"}
    question = mind._note_permission_need("open the dashboard", result)
    assert question

    reply = mind.step("what are you working on?")
    assert "open_url" in reply.text                 # the live ask is surfaced by name
    assert "you may open_url" in reply.text         # with the exact grant sentence


def test_working_on_with_nothing_live_says_so(tmp_path, monkeypatch):
    monkeypatch.delenv("BEANIE_BODY_OS", raising=False)
    mind = Mind(state_dir=tmp_path / "state")
    reply = mind.step("what are you working on?")
    assert "nothing live" in reply.text.lower() or "nothing pending" in reply.text.lower()


def test_paused_takeover_is_part_of_working_on(tmp_path, monkeypatch):
    from beanie.automation import VirtualGUIDriver
    from beanie.substrate import StubSubstrate

    monkeypatch.delenv("BEANIE_AUTOMATION", raising=False)
    mind = Mind(state_dir=tmp_path / "state",
                substrate=StubSubstrate(scripted_gui_actions=[
                    *[{"type": "click", "target": f"step{i}"} for i in range(8)],
                ]))
    driver = VirtualGUIDriver(screens=["setup wizard"])
    mind._gui_driver_override = driver
    mind.step("you may gui_control")
    mind.step("take over and do the remaining setup steps")
    assert mind._gui_paused is not None

    reply = mind.step("what are you working on?")
    assert "paused" in reply.text.lower() and "setup steps" in reply.text
