"""Owner directives §D4 / §D6 / §D9 — the whole-machine index, ambiguous task
resolution ("play me kaba"), and the decision gate that chooses the route.

These are the owner's own acceptance criteria, so they are tested with the owner's own
examples: the filenames a real song gets saved as, the request phrased the way a person
phrases it, and the fallback to the web when the file is not on the machine.
"""

import json

from beanie import Mind
from beanie.body import SandboxBody, launcher_for
from beanie.faithfulness import audit_mind
from beanie.gate import (APPROACHES, Approach, DecisionGate, RouteLedger, classify_intent)
from beanie.index import PLAYABLE, FileIndex


# Names the same song actually gets saved as, plus decoys that share its letters.
_SONG_SHAPES = [
    "kaba.mp3", "Kaba by Kapeke.m4a", "KAABA (Official Video).mpg",
    "02 - Kaba (128kbps).mp3", "kaba_by_kapeke_HQ.mp4", "Kaaba - Official Audio.flac",
    "Kapeke - Kaba [Remastered 2019].wav", "KABA_LIVE_SESSION.ogg",
    "Kaába (Áudio Oficial).mp3",
]
_DECOYS = ["kabaa_notes.txt", "kabalistic_study.pdf", "Kampala Weather Report.mp4",
           "keyboard_layout.png", "invoice_2024.pdf"]


def _seeded_index(tmp_path, deep=True) -> FileIndex:
    root = tmp_path / "disk"
    (root / "music").mkdir(parents=True)
    (root / "documents").mkdir()
    for name in _SONG_SHAPES:
        (root / "music" / name).write_text("x")
    for name in _DECOYS:
        (root / "documents" / name).write_text("x")
    if deep:
        nested = root / "somewhere" / "deep" / "nested"
        nested.mkdir(parents=True)
        (nested / "kaba (copy 2).m4a").write_text("x")
    index = FileIndex(roots=[str(root)])
    index.scan()
    return index


# --------------------------------------------------------------------- §D6 index

def test_the_same_song_is_found_under_every_name_it_gets_saved_as(tmp_path):
    """The owner's core complaint: one song, nine filenames, all of them findable."""
    index = _seeded_index(tmp_path)
    hits = index.search("kaba", kinds=PLAYABLE, limit=20)
    found = {h.name for h in hits}
    for name in _SONG_SHAPES:
        assert name in found, f"'kaba' should find {name}; got {sorted(found)}"


def test_the_song_is_found_wherever_on_the_machine_it_happens_to_be(tmp_path):
    """Not the music folder — the whole PC (§D4 step 2)."""
    root = tmp_path / "disk"
    (root / "a" / "b" / "c" / "d").mkdir(parents=True)
    (root / "a" / "b" / "c" / "d" / "Kaba (Official Audio).m4a").write_text("x")
    (root / "readme.txt").write_text("x")
    index = FileIndex(roots=[str(root)])
    index.scan()
    hit = index.find_one("kaba", kinds=PLAYABLE)
    assert hit is not None, "a file buried four folders deep must still be found"
    assert hit.path.endswith("Kaba (Official Audio).m4a")


def test_decoys_that_share_its_letters_do_not_outrank_the_song(tmp_path):
    index = _seeded_index(tmp_path)
    hits = index.search("kaba", limit=20)
    names = [h.name for h in hits]
    assert "invoice_2024.pdf" not in names
    assert "keyboard_layout.png" not in names
    if "kabalistic_study.pdf" in names:                 # may appear, but never on top
        assert names.index("kabalistic_study.pdf") > names.index("kaba.mp3")


def test_typos_abbreviations_and_accents_all_still_match(tmp_path):
    index = _seeded_index(tmp_path)
    for query in ("kaaba", "kba", "kaába", "KABA"):
        hits = index.search(query, kinds=PLAYABLE, limit=3)
        assert hits, f"'{query}' should still find the song"
        assert "kaba" in hits[0].name.lower() or "kaaba" in hits[0].name.lower()


def test_searching_by_artist_and_title_together(tmp_path):
    index = _seeded_index(tmp_path)
    hits = index.search("kaba kapeke", kinds=PLAYABLE, limit=3)
    assert hits
    assert any("kapeke" in h.name.lower() for h in hits)


def test_every_result_can_say_why_it_matched(tmp_path):
    """§D6: an unexplained result is not returned as a confident answer."""
    index = _seeded_index(tmp_path)
    for hit in index.search("kaba", limit=5):
        assert hit.why, f"{hit.name} matched without a reason"
        assert any(word in " ".join(hit.why) for word in
                   ("verbatim", "word", "trigram", "edit distance", "subsequence", "title", "stem"))
        assert hit.signals, "the signals behind the score must be recorded"
        assert 0 < hit.score <= 1


def test_a_near_tie_is_reported_as_ambiguous_not_silently_picked(tmp_path):
    root = tmp_path / "disk"
    root.mkdir()
    (root / "kaba.mp3").write_text("x")
    (root / "kaba.m4a").write_text("x")
    index = FileIndex(roots=[str(root)])
    index.scan()
    assert index.find_one("kaba") is None, "two identical scores is not a decision"
    assert len(index.search("kaba", limit=5)) == 2


def test_the_second_scan_is_incremental(tmp_path):
    """§D6: seconds, not minutes — unchanged directories are not re-read."""
    index = _seeded_index(tmp_path)
    first = index.last_scan
    assert first.reused_directories == 0
    second = index.scan()
    assert second.reused_directories > 0
    assert len(index) == first.files


def test_coverage_holes_are_reported_never_silent(tmp_path):
    root = tmp_path / "disk"
    (root / "node_modules").mkdir(parents=True)
    (root / "node_modules" / "hidden.mp3").write_text("x")
    (root / "visible.mp3").write_text("x")
    index = FileIndex(roots=[str(root)])
    report = index.scan()
    assert any("node_modules" in skipped for skipped in report.skipped)
    assert index.search("hidden", limit=3) == []        # excluded, and the report says so


def test_the_index_survives_a_reload(tmp_path):
    index = _seeded_index(tmp_path)
    store = tmp_path / "index.jsonl"
    written = index.save(store)
    reloaded = FileIndex()
    assert reloaded.load(store) == written
    assert reloaded.search("kaba", kinds=PLAYABLE, limit=1)[0].name == \
        index.search("kaba", kinds=PLAYABLE, limit=1)[0].name


def test_index_covers_every_kind_not_only_media(tmp_path):
    """§D6: 'this does not apply to media only, it applies to all files'."""
    index = _seeded_index(tmp_path)
    assert index.search("invoice", limit=1)[0].kind == "document"
    assert index.search("kabaa notes", limit=1)[0].kind == "document"
    assert set(index.stats()["kinds"]) >= {"audio", "video", "document", "image"}


# ------------------------------------------------------------------- §D4 intent

def test_an_ambiguous_request_is_read_as_the_task_it_means():
    cases = {
        "play me kaba": ("play", "kaba", PLAYABLE),
        "play the song kaba please": ("play", "kaba", PLAYABLE),
        "watch kaaba now": ("play", "kaaba", ("video",)),
        "listen to kaba": ("play", "kaba", ("audio",)),
        "find my invoice": ("find", "invoice", ()),
        "where is contract.pdf": ("where", "contract.pdf", ()),
        "open the report": ("open", "report", ()),
    }
    for text, (action, obj, kinds) in cases.items():
        intent = classify_intent(text)
        assert intent is not None, text
        assert intent.action == action, f"{text} → {intent.action}"
        assert intent.object_phrase == obj, f"{text} → {intent.object_phrase!r}"
        assert tuple(intent.kinds) == tuple(kinds)
        assert intent.why, "an intent guess must name the pattern it matched"


def test_a_request_it_does_not_recognise_is_not_guessed():
    for text in ("hello there", "how are you feeling", ""):
        assert classify_intent(text) is None


# --------------------------------------------------------------------- §D9 gate

def test_the_gate_never_proposes_a_route_this_machine_cannot_take():
    gate = DecisionGate({"open_url": "opens a browser"})          # no play_media here
    decision = gate.decide("play 'kaba'", facts={"searched": True, "action": "play",
                                                 "local_hits": 1, "playable_hit": True})
    local = decision.route("local_play")
    assert local is not None and not local.eligible
    assert "play_media" in local.missing
    assert any("play_media" in reason for reason in local.why)


def test_the_honest_fallback_never_outranks_a_route_that_can_do_the_job():
    gate = DecisionGate({"play_media": "plays"})
    decision = gate.decide("play 'kaba'", facts={"searched": True, "action": "play",
                                                 "local_hits": 1, "playable_hit": True})
    assert decision.chosen.id == "local_play"
    assert decision.route("report_gap").score < decision.chosen.score


def test_a_file_that_is_not_on_the_machine_falls_back_to_the_web():
    """§D4 step 4 — and the reason it is a route, not a shrug."""
    gate = DecisionGate({"open_url": "opens a browser"})
    decision = gate.decide("play 'kaba'", facts={"searched": True, "action": "play",
                                                 "local_hits": 0, "playable_hit": False})
    assert decision.chosen.id == "web_play"
    assert decision.route("report_gap").eligible          # still offered, still rejected


def test_every_rejected_route_carries_its_reason():
    gate = DecisionGate({"play_media": "plays"})
    decision = gate.decide("play 'kaba'", facts={"searched": True, "action": "play",
                                                 "local_hits": 1, "playable_hit": True})
    assert len(decision.routes) == len(APPROACHES)
    for route in decision.rejected:
        assert route.why, f"{route.id} was rejected without a reason"


def test_dangerous_routes_are_marked_as_needing_the_owner(tmp_path):
    """§D8: autonomous by default, permission on the operations the owner named."""
    gate = DecisionGate({"install_app": "installs software"},
                        ledger=RouteLedger(tmp_path / "ledger.jsonl"))
    decision = gate.decide("install vlc", facts={"knowledge_gap": True})
    assert decision.chosen.id == "install_tool"
    assert decision.needs_permission is True
    plain = gate.decide("play 'kaba'", facts={"searched": True, "action": "play",
                                              "local_hits": 1, "playable_hit": True})
    assert plain.needs_permission is False


def test_the_gate_learns_from_what_actually_worked(tmp_path):
    """§D9 step 3/5: history moves the score, so the gate is not static."""
    ledger = RouteLedger(tmp_path / "ledger.jsonl")
    assert ledger.prior_for("local_play") == 0.5, "no history must mean neutral, not confident"

    ledger.record("local_play", False, "player crashed")
    demoted = ledger.prior_for("local_play")
    assert demoted < 0.5
    for _ in range(8):
        ledger.record("local_play", True)
    assert ledger.prior_for("local_play") > demoted

    # one win must not look like certainty: evidence accumulates, it does not decide
    fresh = RouteLedger(tmp_path / "second.jsonl")
    fresh.record("web_play", True)
    assert fresh.prior_for("web_play") < 0.75

    # and a route with a bad history loses to an equal one with a good history
    biased = RouteLedger(tmp_path / "third.jsonl")
    for _ in range(6):
        biased.record("a", False)
        biased.record("b", True)
    two = (Approach("a", "first", condition="always", cost=0.3),
           Approach("b", "second", condition="always", cost=0.3))
    gate = DecisionGate({}, ledger=biased, approaches=two)
    assert gate.decide("task").chosen.id == "b"


def test_the_ledger_survives_a_torn_last_line(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(json.dumps({"route": "local_play", "success": True}) + "\n" + '{"route": "loc',
                    encoding="utf-8")
    ledger = RouteLedger(path)
    assert ledger.successes["local_play"] == 1            # history before the tear is kept


def test_a_launcher_is_chosen_for_every_platform_beanie_claims_to_support():
    """§D2: Windows, Linux, macOS, Android — and an unknown OS degrades, never crashes."""
    assert launcher_for("win32")[0] == "cmd"
    assert launcher_for("darwin") == ("open",)
    assert launcher_for("linux") == ("xdg-open",)
    assert launcher_for("android")[0] == "am"
    assert launcher_for("plan9") == launcher_for("linux")


def test_a_sandbox_launch_says_it_was_simulated(tmp_path):
    """Honesty rule: no payload may let a report mistake a double for a real launch."""
    body = SandboxBody(tmp_path / "sandbox")
    (body.root / "song.mp3").write_text("x")
    result = body.run("play_media", {"path": "song.mp3"})
    assert result["mode"] == "simulated"
    assert "no media player" in result["player"]
    web = body.run("open_url", {"url": "https://example.com"})
    assert web["mode"] == "simulated"


# ------------------------------------------------------- §D4 end to end in a mind

def _mind_with_media(tmp_path) -> Mind:
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    sandbox = mind.body.root
    (sandbox / "music").mkdir(parents=True)
    (sandbox / "documents").mkdir()
    (sandbox / "music" / "02 - Kaba (128kbps).mp3").write_text("x")
    (sandbox / "documents" / "invoice_2024.pdf").write_text("x")
    return mind


def test_play_me_kaba_finds_it_anywhere_on_the_machine_and_plays_it(tmp_path):
    mind = _mind_with_media(tmp_path)
    reply = mind.step("play me kaba")
    assert reply.success
    assert "Kaba" in reply.text or "kaba" in reply.text
    assert "Playing" in reply.text
    assert "Why this one" in reply.text                   # the match explains itself
    assert "simulated" in reply.text or "recorded, not performed" in reply.text


def test_a_song_that_is_not_on_the_machine_is_played_from_youtube(tmp_path):
    mind = _mind_with_media(tmp_path)
    reply = mind.step("play me somethingnotonthispc")
    assert "youtube.com" in reply.text.lower()
    assert "not on this PC" in reply.text
    assert "recorded, not opened" in reply.text           # no network in a sandbox body


def test_a_document_is_not_played_as_though_it_were_a_song(tmp_path):
    mind = _mind_with_media(tmp_path)
    reply = mind.step("play me invoice")
    assert "document" in reply.text
    assert "invoice_2024.pdf" in reply.text
    assert "Which do you want?" in reply.text             # asks instead of guessing


def test_find_reports_the_location_instead_of_playing_it(tmp_path):
    mind = _mind_with_media(tmp_path)
    reply = mind.step("find my invoice")
    assert reply.text.startswith("Found")
    assert "invoice_2024.pdf" in reply.text
    assert "Playing" not in reply.text


def test_a_question_the_index_cannot_answer_falls_through_to_normal_cognition(tmp_path):
    """The index must not swallow questions it has nothing to say about."""
    mind = Mind(state_dir=tmp_path / "mind")
    reply = mind.step("where is the best sushi place")
    assert reply.success
    assert reply.text.startswith("Received")


def test_the_route_choice_is_recorded_explainable_and_auditable(tmp_path):
    """§D9 step 4 + §9.9: the choice and its alternatives are on the record."""
    mind = _mind_with_media(tmp_path)
    mind.step("play me kaba")

    decisions = [e for e in mind.trace.events if e.kind == "decision" and e.payload.get("routes")]
    assert len(decisions) == 1
    payload = decisions[0].payload
    assert payload["chosen"] == "local_play"
    assert payload["intent"]["action"] == "play"
    assert len(payload["routes"]) == len(APPROACHES)

    text = mind.explain(turn_id="turn-00001")
    assert "How I decided to do it" in text
    assert "local_play" in text
    assert "read the request as 'play'" in text

    reports, summary = audit_mind(mind)
    assert summary["violations"] == 0 and summary["unaudited"] == 0
    assert all(r.faithful for r in reports)


def test_the_gate_records_what_worked_so_the_next_time_is_better(tmp_path):
    mind = _mind_with_media(tmp_path)
    mind.step("play me kaba")
    mind.step("play me kaba")
    stats = mind.decision_gate.ledger.stats()
    assert stats["local_play"]["success"] == 2
    assert stats["local_play"]["prior"] > 0.5


def test_index_roots_come_from_the_owner_not_from_a_guess(tmp_path, monkeypatch):
    """§D6 coverage is declared: BEANIE_INDEX_ROOTS decides what 'the whole PC' means."""
    from beanie.mind import index_roots
    monkeypatch.setenv("BEANIE_INDEX_ROOTS", "/mnt/data:/mnt/media")
    assert index_roots(tmp_path) == ["/mnt/data", "/mnt/media"]
    monkeypatch.delenv("BEANIE_INDEX_ROOTS", raising=False)
    assert index_roots(tmp_path) == [str(tmp_path / "sandbox")]


def test_a_near_tie_is_broken_by_a_declared_ladder_not_by_list_order(tmp_path):
    """Two equally good matches: the shallower one wins, and the reply says so."""
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    sandbox = mind.body.root
    (sandbox / "music").mkdir(parents=True)
    (sandbox / "a" / "b" / "c").mkdir(parents=True)
    # the same filename at two depths: identical text evidence, so the scores differ
    # only by the depth bonus — a genuine near-tie, and the ladder must break it
    (sandbox / "a" / "b" / "c" / "kaba.mp3").write_text("x")
    (sandbox / "music" / "kaba.mp3").write_text("x")

    reply = mind.step("play me kaba")
    assert reply.success, reply.text
    assert "Playing" in reply.text, "an equal score must not stall the task"
    assert "within 0.02" in reply.text, "the tie-break must be stated, not silent"
    assert "shallower folder" in reply.text, "the ladder's reason must be stated"
    assert "clear best match" not in reply.text, "a broken tie is not a clear winner"


def test_permission_is_asked_for_once_and_then_remembered(tmp_path):
    """§D8: the gate is the single choke point — and a grant becomes a rule."""
    mind = Mind(state_dir=tmp_path / "mind")          # default policy: ask
    sandbox = mind.body.root
    (sandbox / "music").mkdir(parents=True)
    (sandbox / "music" / "kaba.mp3").write_text("x")

    first = mind.step("play me kaba")
    assert "permission" in first.text.lower()
    assert not first.success, "an ungated launch must not be reported as done"

    mind.gate.grant("play_media", action="allow", note="owner allowed playback")
    second = mind.step("play me kaba")
    assert second.success
    assert "Playing" in second.text
    # the same question is never asked twice
    assert mind.gate.check("play_media").state == "act"
