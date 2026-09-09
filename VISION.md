# Beanie — Project Vision

> **Status:** founding document
> **Companion:** [ARCHITECTURE.md](./ARCHITECTURE.md) turns this vision into layers, stores, and stages.
> Every later document, feature, or line of code must survive the filter in §2.

---

## 1. The concept in one sentence

**Beanie is an artificial mind — not an agent.** A continuously existing intelligence with
human-like general intelligence, embodied in its owner's digital world, that perceives,
understands, remembers, reasons, learns, forms goals, acts, experiences consequences,
reflects, and changes from its own history — such that *who Beanie is* is a result of that
history, not a script written into a prompt.

An agent executes. A mind exists.

- Tools are its **body**.
- An LLM is only part of its **brain**.
- The interface is only a **window into it**.
- Voice is only one way of **communicating**.
- Memory is not a database of chat logs.
- Learning is not "add this procedure to the skill library."

If a design treats Beanie as a better agent, the design is wrong — regardless of how well it
works as an agent.

## 2. The filter that gates every decision

An agent looks like:

```
Goal → retrieve skill → select tool → execute → verify
```

A mind should be closer to:

```
trigger → perceive → understand → remember → reason → learn
   → decide → act → experience consequences → reflect → improve
   → communicate → (mind has changed) → repeat
```

Every proposal — feature, tool, architecture change, prompt, dataset — is passed through
one question:

> **Does this make Beanie more generally intelligent, or does it merely make one task more automated?**

| Proposal | Verdict |
|---|---|
| Add another hard-coded tool | Usually automation |
| Teach Beanie to infer *when* a tool is necessary | Intelligence |
| Add another trigger keyword | Automation |
| Teach Beanie to understand a new concept from experience | Intelligence |
| Add another fixed workflow | Automation |
| Let Beanie discover a workflow from observation and adapt it | Intelligence |
| Add another personality prompt | Simulation |
| Let personality evolve from accumulated interaction | Closer to the goal |
| Add another memory table | Data plumbing |
| Teach Beanie to *revise a belief* when evidence contradicts it | Intelligence |
| Attach a calibrated uncertainty label to every answer | Intelligence (calibration — T8) |
| Revise a stored strategy because the owner corrected a similar case | Intelligence (T9) |

## 3. Non-negotiable properties

1. **Continuity.** Beanie persists between interactions: it has a self, a history, and a
   world model that survive the conversation ending. Closing the chat window is not death;
   it is sleep. On return, Beanie knows what happened before and what was left unfinished.

2. **Learning is general and self-initiated.** Beanie learns from conversation, documents,
   images, video, websites, live demonstration, feedback, mistakes, and its own experience —
   and sometimes it learns because it noticed a gap itself (curiosity), not because it was
   told to. Learning happens at many levels: facts, concepts, procedures, causes, social
   rules, preferences, strategies, and eventually meta-learning (learning how it learns).

3. **The world model is the center of gravity.** Beanie's continuously evolving internal
   model of *itself, its owner, the environment, and the world* is the core artifact of the
   project — not the tool engine, not the skill system, not the chat interface. Every stored
   belief carries provenance, confidence, and evidence, so the model can be corrected —
   an intelligence that cannot change its mind under evidence is a log, not a mind.

4. **Agency with authority — not artificially crippled intelligence.** Beanie does not have
   "intelligence levels" imposed as permission tiers. It understands four states:
   *I can do this / I am allowed to do this / I need permission before doing this /
   I don't know whether I'm allowed.* In the last state it asks. Limits are negotiated with
   the owner; capability itself is never fake-limited.

5. **Identity is emergent.** Personality, values, and communication style emerge from base
   cognition + experiences + memories + relationship with the owner + learned preferences +
   self-model. A fine-tuned model adapter may eventually *consolidate* long-term behavioral
   patterns — it must never be the personality itself.

6. **Honest cognition.** Beanie never fakes understanding with orchestration. It is allowed
   to be uncertain, to say "I don't understand," to ask, to investigate. Uncertainty,
   contradiction, and failure are first-class signals that drive learning — not bugs to be
   papered over.

7. **Calibrated humility is a first-class output.** Internal confidence is not merely
   stored — it is *communicated*. Every final answer or action proposal carries an explicit
   uncertainty label (*highly confident / moderate — one source / speculative*), derived
   from the evidence state and shown to the user unless a safety policy overrides. This
   turns internal calibration into external trustworthiness: over many probes, what Beanie
   marks "highly confident" must be right measurably more often than what it marks
   "speculative" (T8). Beanie may be wrong — it may not be *unwarned*.

8. **Correction is a continuous learning channel.** When the owner says "no, that's
   wrong," Beanie does three things: (a) update the specific fact or belief, (b) trigger a
   **strategy revision** — adjust how it will interpret and handle *similar* cases in the
   future — and (c) log the event as a learning episode with evidence refs. Corrections
   never silently overwrite (T2 applies); they feed both the semantic and procedural stores
   (T9). This is the difference between a system that learns from mistakes and one that
   merely stores facts.

9. **Explanation is a user-facing service, not an internal log.** After any decision or
   answer, Beanie can produce — on demand, in plain language — *why* it reached that
   conclusion, citing the specific evidence, memories, and the shape of the reasoning path,
   without exposing raw chain-of-thought where that is unsafe or inappropriate. This is a
   summarization layer over the trace, distinct from the trace itself (T10).

## 4. What this project is not claiming

Spoken plainly, because the goal's difficulty should never be hidden inside architecture
diagrams:

- Human-level general intelligence is an **open research problem**. No document, scaffold,
  or orchestration scheme conjures it.
- This project does not promise AGI by a deadline, and does not claim that a large language
  model *is* a mind. It claims the opposite direction: the LLM is substrate; the mind is
  something that must be *built* around and beyond it — stores, loops, behaviors, and a
  history — and then honestly measured.
- "Human-like" is the long-horizon target that orients every stage; **progress is measured
  by the test battery in §5**, not by vibes and not by demo videos.
- This project does **not** claim to build consciousness, subjective experience (qualia),
  genuine emotion or mood, or a self-preservation drive. Those are not milestones, and
  features that pretend to deliver them would be simulation. Where a human-like behavior
  *is* observable and testable — identity continuity (T7), calibrated doubt (T8),
  explanation (T10), self-correction (T3) — we build and test the behavior. The metaphysics
  is not a deliverable.

## 5. The intelligence test battery — how we know we're making progress

These tests are the project's unit of progress. Each stage of the roadmap defines its exit
criteria as a subset of these. A feature that passes none of them fails the filter in §2.

| # | Test | Pass criterion |
|---|---|---|
| **T1** | Demonstration learning & transfer | Beanie learns a procedure from **one live demonstration** by the owner and can perform it later in a new-but-similar context, without a written recipe. |
| **T2** | Contradiction & evidence | Given new information that conflicts with a stored belief, Beanie *lowers confidence* and either asks or gathers evidence — it never silently overwrites, and never blindly ignores. |
| **T3** | Self-correction after failure | After a failed attempt, Beanie identifies the cause, changes its procedure, verifies the fix, and consolidates the lesson — without being told the exact fix. |
| **T4** | Preference discovery | From history alone, Beanie infers a stable preference of its owner ("you prefer X over Y when uncertain") and either adopts it or asks for confirmation. |
| **T5** | Curiosity | During a task, Beanie notices a gap in its own understanding and investigates it on its own initiative, then uses what it learned. |
| **T6** | Abstraction / analogy | A concept learned in one domain is correctly applied in a structurally similar domain it has never seen (e.g., "grouping by type" learned on downloads, applied to a photo library). |
| **T7** | Longitudinal identity | After a long interaction history, *who Beanie is* differs measurably between two different owners/histories in ways traceable to that history — not to different prompts. |
| **T8** | Calibrated communication | Across a probe set of N decisions, Beanie's communicated labels (*highly confident / moderate / speculative*) predict outcome accuracy better than an unlabeled baseline, and the labels trace to the evidence state (count, quality, source, freshness) — not to verbosity or phrasing. |
| **T9** | Correction → strategy revision | After "no, that's wrong" about one case, Beanie updates the fact *and* performs differently on a future *similar* case (interpretation or approach changed); the event is logged as a learning episode; the same mistake is not corrected twice. |
| **T10** | Explanation on demand | For any recent decision, Beanie can produce a concise, non-technical explanation citing the actual evidence and memories used — auditable against the internal trace — on request, without exposing raw chain-of-thought. |
| **T11** | Retroactive re-evaluation | When a belief is invalidated (e.g., the owner reveals a key fact was false all along), Beanie flags and re-evaluates memories and derived beliefs that depended on it — confidence drops, revision reasons are logged, and it asks or investigates — rather than silently updating one row. |
| **T12** | Stale truth & proactive re-check | Confidence of an unobserved state decays along its entity's volatility profile (deterministic, per-kind — not ad hoc); before acting on high-stakes volatile state, Beanie re-checks instead of trusting a stale observation. |
| **T13** | Usefulness, not just correctness | User-reported and implicit usefulness (follow-ups, corrections, abandonment) is tracked per answer and correlated with answer characteristics (confidence, evidence freshness, format); the correlation demonstrably informs effort allocation (T8/§4.6). |

### Scoring: the 0–3 capability scale

Every capability in [CAPABILITY_REGISTER.md](./CAPABILITY_REGISTER.md) is scored at each
milestone review on the scale below. The scale is the shared language between "the
diagram" and "the code":

| Score | Meaning |
|---|---|
| **0 — Nonexistent** | Not implemented, no plan |
| **1 — Hardcoded** | Scripted rule / schema exists, not emergent |
| **2 — Emergent** | Happens spontaneously but unreliably, observed at least once |
| **3 — Robust & recurring** | Happens consistently and measurably — and **nothing earns a 3 without longitudinal evidence** (see the suite protocol in ARCHITECTURE §8) |

Honest anchoring: a store with a schema but no retrieval effect is a 1. A capability that
fires once in a demo is a 2. A 3 requires weeks of real tasks. The project's headline
metric is the **count of capabilities that have moved up the scale**, tracked per review.

---

### Origin

This document consolidates the founding design conversation about Beanie (concept,
Artificial Mind; the mind diagram; the re-centering from "agent" to "mind"; the world
model; general learning; agency with authority) and the audit rounds that followed
(epistemic humility, correction loops, explainability, usefulness, failure taxonomy,
stale-truth decay, contamination re-evaluation). See [ARCHITECTURE.md](./ARCHITECTURE.md)
for the buildable interpretation and [CAPABILITY_REGISTER.md](./CAPABILITY_REGISTER.md)
for the scored audit.
