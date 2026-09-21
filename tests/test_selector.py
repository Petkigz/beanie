"""§13.5: the RSI selector is advisory — proposals from real evidence signals,
bounded action classes (it must never offer to execute), and an honest empty
report when there is nothing yet to rank."""
from beanie.learning import DemonstrationLearner, DemoAction  # noqa: F401
from beanie.mind import Mind
from beanie.select import ALLOWED_ACTION_CLASSES, ImprovementSelector
from beanie.cli import main as cli_main


def test_empty_mind_reports_no_signals_honestly(tmp_path):
    selector = ImprovementSelector(Mind(state_dir=tmp_path / "m1"))
    assert selector.proposals() == []
    report = selector.report()
    assert "advisory only" in report and "no improvement signals on record yet" in report


def _seeded_mind(root):
    mind = Mind(state_dir=root)
    proposal = mind.learner.learn(
        goal_class="organize downloads", title="pdfs to docs",
        actions=[DemoAction(capability="move_file", args={"src": "a.pdf", "dst": "docs"},
                            effect_note="move a.pdf → docs")],
    )
    return mind, proposal


def test_proposed_skill_yields_a_promote_proposal(tmp_path):
    mind, proposal = _seeded_mind(tmp_path / "m2")
    selector = ImprovementSelector(mind)
    proposals = selector.proposals()
    assert any(p.lane == "skill" and p.action_class == "promote" and
               p.evidence["skill_id"] == proposal.entry.id for p in proposals)
    assert all(p.action_class in ALLOWED_ACTION_CLASSES for p in proposals)


def test_failure_receipts_yield_a_repair_proposal_after_confirmation(tmp_path):
    mind, proposal = _seeded_mind(tmp_path / "m3")
    mind.learner.confirm(proposal.entry.id)
    mind.learner.record_failure(proposal.entry.id,
                                taxonomy="boundary_error", fix="skip hidden files")
    proposals = ImprovementSelector(mind).proposals()
    patch = [p for p in proposals if p.action_class == "patch"]
    assert patch and patch[0].evidence["failures"] == 1
    assert patch[0].risk == "medium"


def test_selector_is_deterministic_and_bounded(tmp_path):
    mind, proposal = _seeded_mind(tmp_path / "m4")
    mind.learner.record_failure(proposal.entry.id, taxonomy="tool_execution_error", fix="retry")
    selector = ImprovementSelector(mind)
    first = [p.to_line() for p in selector.proposals(limit=1)]
    second = [p.to_line() for p in selector.proposals(limit=1)]
    assert first == second                        # deterministic ranking
    assert all(p.risk in ("low", "medium") for p in selector._proposals())   # never 'high'


def test_cli_propose_flag_prints_the_advisory_report(tmp_path, capsys):
    rc = cli_main(["--state-dir", str(tmp_path / "m5"), "--propose"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "advisory only" in out and "choosing what to improve" in out
