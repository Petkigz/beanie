"""The §9.9 faithfulness audit (T10): explanations must cite the *actual*
reasons a decision was made, not plausible ones.

Half of these tests are bite tests: they fabricate the failure modes the protocol
exists to catch (invented citations, omitted deciding factors, drifted values,
free-floating summaries) and assert the audit fails them. A guard that cannot
bite is decoration.
"""

from types import SimpleNamespace

from beanie import Mind

from beanie.faithfulness import audit_explanation, audit_mind
from beanie.learning import DemoAction
from beanie.explain import Claim


def _conversation(tmp_path) -> Mind:
    """A conversation exercising reflex, escalation, pre-flight, determinism,
    correction and feedback — the decision shapes the audit has to cover."""
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    mind.step("hello there")                                              # reflex
    mind.step("please do something ambiguous here")                       # reflex → deep (flag)
    mind.step("delete the permanent file right now please")               # deep_verified + concerns
    mind.step("remember that the kettle is in the kitchen")               # deterministic organ
    mind.step("no, that's wrong about the kettle")                        # correction channel
    mind.step("that was useful")                                          # feedback handler
    return mind


def test_every_explanation_in_a_real_conversation_is_faithful(tmp_path):
    """The audit passes on the actual implementation, over real turns."""
    mind = _conversation(tmp_path)
    reports, summary = audit_mind(mind)

    assert summary["turns"] >= 6
    assert summary["violations"] == 0
    assert summary["unaudited"] == 0, "a turn with no decision trace cannot be audited"
    assert summary["claims"] >= 20, "explanations must actually say something"
    assert all(r.faithful for r in reports)


def test_explanation_names_effort_evidence_and_confidence_reasoning(tmp_path):
    """§4.5 content: the conclusion, the effort, the evidence, the reasons."""
    mind = _conversation(tmp_path)
    text = mind.explain(turn_id="turn-00003")

    assert "What I was answering" in text
    assert "How much effort it took" in text
    assert "deep_verified" in text          # the depth that actually ran is named
    assert "Evidence I used" in text
    assert "How the confidence was reached" in text
    assert "Residual uncertainty" in text


def test_invented_citation_is_caught(tmp_path):
    """A plausible-sounding citation that exists nowhere must fail (§9.9)."""
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("hello there")
    explanation = mind.explainer.explain_turn("turn-00001")
    explanation.claims.append(
        Claim(section="evidence", text="an earlier demonstration showed this",
              ref="record:rec-99999", asserted={"confidence": 0.9}, actual={"confidence": 0.9})
    )
    report = audit_explanation(explanation, trace=mind.trace, memory=mind.memory)
    assert not report.faithful
    assert any(v["kind"] == "unknown_citation" for v in report.violations)


def test_fabricated_alternative_is_caught(tmp_path):
    """Claiming a concern that was never raised is the classic plausible lie."""
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("hello there")
    explanation = mind.explainer.explain_turn("turn-00001")
    explanation.claims.append(
        Claim(section="alternative", text="contradiction_history: the record conflicted — noted, not decisive",
              ref="turn:turn-00001:decision.concerns[0]", asserted={"kind": "contradiction_history"}, actual={})
    )
    report = audit_explanation(explanation, trace=mind.trace, memory=mind.memory)
    assert any(v["kind"] == "unknown_citation" for v in report.violations)


def test_unknown_ref_scheme_cannot_escape_auditing(tmp_path):
    """A claim kind the auditor does not know is a violation, not a pass."""
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("hello there")
    explanation = mind.explainer.explain_turn("turn-00001")
    explanation.claims.append(
        Claim(section="evidence", text="trust me", ref="vibes:1", asserted={}, actual={})
    )
    report = audit_explanation(explanation, trace=mind.trace, memory=mind.memory)
    assert any(v["kind"] == "unknown_citation" and v["ref"] == "vibes:1" for v in report.violations)


def test_omitted_deciding_factor_is_caught(tmp_path):
    """An explanation that reads well and leaves out the real reason fails."""
    mind = _conversation(tmp_path)
    explanation = mind.explainer.explain_turn("turn-00002")

    # the escalation is the reason this turn took two tiers; drop its claim
    explanation.claims = [c for c in explanation.claims if c.section != "effort"
                          or "escalated" not in c.text]
    report = audit_explanation(explanation, trace=mind.trace, memory=mind.memory)
    assert any(v["kind"] == "silent_material_input" and "effort was raised" in v["detail"]
               for v in report.violations)


def test_value_drift_between_sentence_and_source_is_caught(tmp_path):
    """A sentence that states a different value than the trace holds fails."""
    mind = _conversation(tmp_path)
    explanation = mind.explainer.explain_turn("turn-00001")
    for claim in explanation.claims:
        if claim.asserted:
            claim.asserted = dict(claim.asserted)
            claim.asserted[next(iter(claim.asserted))] = "tampered"
            break
    report = audit_explanation(explanation, trace=mind.trace, memory=mind.memory)
    assert any(v["kind"] in ("asserted_mismatch", "unrendered_value") for v in report.violations)


def test_summary_must_be_rendered_from_a_claim(tmp_path):
    """No free-floating sentence may be added to an explanation."""
    mind = _conversation(tmp_path)
    explanation = mind.explainer.explain_turn("turn-00001")
    explanation.summary = explanation.summary + " I was very careful."
    report = audit_explanation(explanation, trace=mind.trace, memory=mind.memory)
    assert any(v["kind"] == "unbacked_summary" for v in report.violations)


def test_action_turns_are_audited_and_cite_the_skill_that_ran(tmp_path):
    """An action in the world is a decision too — with its skill and its gate."""
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    mind.body.run("mkdir", {"dir": "downloads"})
    mind.body.run("mkdir", {"dir": "docs"})
    mind.body.run("write_file", {"path": "downloads/invoice.pdf", "content": "invoice"})
    proposal = mind.demonstrate(
        title="pdfs to docs", goal_class="organize downloads",
        actions=[DemoAction("move_file", {"src": "downloads/invoice.pdf", "dst": "docs"})],
    )
    mind.confirm_skill(proposal.skill_id)
    result = mind.perform_goal("organize downloads")
    assert result.outcome == "success"

    reports, summary = audit_mind(mind)
    action_reports = [r for r in reports if r.turn_id == "act"]
    assert summary["unaudited"] == 0
    assert action_reports and all(r.faithful for r in action_reports)

    text = mind.explain(turn_id="act")
    assert "no model tier was used" in text      # determinism stated, not implied
    assert "pdfs to docs" in text                # the learned skill is named


def test_turn_without_a_decision_trace_is_reported_never_silently_passed(tmp_path):
    """A future code path that forgets its decision event shows up as a gap."""
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("hello there")
    mind.trace.append("turn-99999", "outcome", {"record_id": "rec-00001", "success": True})

    reports, summary = audit_mind(mind)
    assert summary["unaudited"] == 1
    assert any(v["kind"] == "no_decision_trace" for r in reports for v in r.violations)


def test_cli_audit_explanations(tmp_path, capsys):
    """The owner can run the protocol themselves."""
    from beanie.cli import main

    state = tmp_path / "mind"
    for text in ("hello there", "remember that the kettle is in the kitchen"):
        assert main(["--state-dir", str(state), "--say", text]) == 0
    capsys.readouterr()

    assert main(["--state-dir", str(state), "--audit-explanations"]) == 0
    out = capsys.readouterr().out
    assert "explanation audit:" in out
    assert "0 violation(s)" in out
    assert "faithful" in out


def test_cli_audit_explanations_fails_loudly_on_a_violation(tmp_path, capsys, monkeypatch):
    """Exit code 1 — a failed audit must be visible to a script, not a footnote."""
    from beanie import cli, faithfulness

    state = tmp_path / "mind"
    assert cli.main(["--state-dir", str(state), "--say", "hello there"]) == 0
    capsys.readouterr()

    real = faithfulness.audit_mind

    def doctored(mind, limit=0):
        reports, summary = real(mind, limit=limit)
        reports[0].violations.append({"kind": "unknown_citation", "ref": "record:x", "detail": "made up"})
        summary["violations"] = 1
        summary["faithful"] -= 1
        return reports, summary

    monkeypatch.setattr(faithfulness, "audit_mind", doctored)
    assert cli.main(["--state-dir", str(state), "--audit-explanations"]) == 1
    assert "made up" in capsys.readouterr().out
