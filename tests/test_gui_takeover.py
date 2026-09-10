"""The spoken GUI takeover (§11.3, row 47): the sentence IS the task intake.

"log me in to github" must reach the supervised navigator: eyes read the
screen, every action passes the authority gate, the budget is bounded, and
the owner hears the outcome in the outcome's own words — never "done" when
the loop merely stopped, never a blind click when the limb is a test double.
"""

from __future__ import annotations

from beanie import Mind


def test_gui_task_without_seated_limbs_is_a_seat_it_answer(tmp_path, monkeypatch):
    for var in ("BEANIE_AUTOMATION",):
        monkeypatch.delenv(var, raising=False)
    mind = Mind(state_dir=tmp_path / "state")
    reply = mind.step("log me in to github")
    assert "not seated" in reply.text and "BEANIE_AUTOMATION" in reply.text
    assert reply.success is False
    events = [e for e in mind.trace.events_for(reply.turn_id) if e.kind == "gui_takeover"]
    assert events and events[0].payload["outcome"] == "unseated"


def test_gui_task_asks_permission_before_the_first_action(tmp_path, monkeypatch):
    from beanie.automation import VirtualGUIDriver

    monkeypatch.delenv("BEANIE_AUTOMATION", raising=False)
    mind = Mind(state_dir=tmp_path / "state")
    driver = VirtualGUIDriver(screens=["login page: Username Password Login"])
    mind._gui_driver_override = driver

    reply = mind.step("log me in to github")
    assert "you may gui_control" in reply.text
    assert driver.executed == []                    # no click before the owner rules
    events = [e for e in mind.trace.events_for(reply.turn_id) if e.kind == "gui_takeover"]
    assert events and events[0].payload["outcome"] == "needs_permission"


def test_granted_gui_task_completes_and_narrates_the_real_action_count(tmp_path, monkeypatch):
    from beanie.automation import VirtualGUIDriver
    from beanie.substrate import StubSubstrate

    monkeypatch.delenv("BEANIE_AUTOMATION", raising=False)
    mind = Mind(state_dir=tmp_path / "state",
                substrate=StubSubstrate(scripted_gui_actions=[
                    {"type": "click", "target": "Login"},
                    {"type": "done", "reason": "reached the dashboard"},
                ]))
    driver = VirtualGUIDriver(screens=["login page"])
    mind._gui_driver_override = driver

    mind.step("you may gui_control")
    reply = mind.step("log me in to github")
    assert reply.success is True
    assert "Done" in reply.text and "1 action" in reply.text and "dashboard" in reply.text
    assert driver.executed == [{"type": "click", "target": "Login"}]
    events = [e for e in mind.trace.events_for(reply.turn_id) if e.kind == "gui_takeover"]
    assert events and events[0].payload["outcome"] == "completed"


def test_unplannable_screen_is_reported_as_could_not_complete_never_as_done(tmp_path, monkeypatch):
    from beanie.automation import VirtualGUIDriver

    monkeypatch.delenv("BEANIE_AUTOMATION", raising=False)
    mind = Mind(state_dir=tmp_path / "state")  # stub tier proposes no action — honest by default
    driver = VirtualGUIDriver(screens=["an opaque screen"])
    mind._gui_driver_override = driver
    mind.step("you may gui_control")

    reply = mind.step("log me in to github")
    assert reply.success is False
    assert "could not complete" in reply.text.lower()
    assert "done" not in reply.text.lower().replace("not complete", "")
    assert driver.executed == []                    # a stopped loop clicked nothing
