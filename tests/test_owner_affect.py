"""Owner-model affect observations (§3.5 / row 33 proxy): tone is *observed*,
cited, and shapes behavior — the mind never claims to feel anything."""

from beanie import Mind
from beanie.substrate import StubSubstrate


def test_tone_is_read_conservatively(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    assert mind.affect.read("please move the files") is None      # no tone expressed
    assert mind.affect.read("hello there") is None
    assert mind.affect.read("this is broken, it keeps failing!")["tone"] == "frustration"
    assert mind.affect.read("can you do this ASAP?")["tone"] == "urgency"
    assert mind.affect.read("thanks, that works")["tone"] == "satisfaction"
    assert mind.affect.read("WHY DID YOU DO THAT")["tone"] in {"frustration", "urgency"}


def test_observation_is_evidence_backed_and_recorded(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("ugh, still not right")
    observations = mind.memory.query(kind="owner_model", type="affect_observation")
    assert len(observations) == 1
    content = observations[0].content
    assert content["tone"] == "frustration"
    assert content["markers"]                              # the owner's own words, kept
    assert content["status"] == "active"
    assert observations[0].source.value == "owner"
    assert any(e.kind == "affect" for e in mind.trace.events)


def test_frustrated_turn_is_acknowledged_and_asks_what_to_change(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    reply = mind.step("this is broken!")
    assert "You sound frustrated" in reply.text
    assert reply.questions and "change" in reply.questions[0]
    # the streak escalates the wording instead of repeating itself
    second = mind.step("ugh, still not right")
    assert "2 frustrated messages in a row" in second.text
    # neutral turns are untouched
    assert "frustrated" not in mind.step("hello there").text


def test_frustration_raises_the_effort_floor(tmp_path):
    """A cheap answer is the last thing that helps a frustrated owner (§4.6)."""
    substrate = StubSubstrate()
    mind = Mind(substrate=substrate, state_dir=tmp_path / "mind")
    mind.step("hi there")
    assert substrate.deep_calls == 0  # short, unstressed → reflex

    mind.step("this is broken and keeps failing!")
    before = substrate.deep_calls
    mind.step("not working")  # two words: reflex-sized, but tone raises the floor
    assert substrate.deep_calls == before + 1
    decisions = [e for e in mind.trace.events if e.kind == "decision"]
    assert decisions[-1].payload["depth"] == "deep"


def test_owner_can_read_back_what_was_noticed(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    empty = mind.step("how do you think i'm feeling?")
    assert "haven't noted anything" in empty.text        # honest empty state
    assert "don't guess at feelings" in empty.text       # no invented inner life

    mind.step("this is broken!")
    read_back = mind.step("how am I doing?")
    assert "observations, not guesses" in read_back.text
    assert "this is broken!" in read_back.text           # cites the owner's words
