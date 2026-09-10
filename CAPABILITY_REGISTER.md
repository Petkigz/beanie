# Beanie — Capability Register

> **Status:** living document · rescored at every milestone review
> **Scale (VISION §5):** 0 = Nonexistent · 1 = Hardcoded (scripted rule/schema, not
> emergent) · 2 = Emergent (happens spontaneously, unreliably) · 3 = Robust & recurring
> (consistent and measurable — **3 requires longitudinal evidence, never a demo**)

This register is the answer to every audit question this project has been asked, in one
place. Every row is a capability from an audit round (R1–R3 = the three question rounds;
Q28–Q32 = the runtime audit; Domains A–E = the five-domain audit; A1–A4 = the four
review add-ons). Each row states what kind of thing the capability is in Beanie (store /
behavior / property / measurement — see ARCHITECTURE §1), the evidence that would move it
up the scale, and the roadmap stage it lands in.

**How to use it:** score every row honestly. **Score** is the level this capability has
actually reached today; **Stage** is the roadmap stage the row is planned into (they are
different columns and a row can legitimately be scored 1 while staged 4).

*Current scores (2026-09-10):* **41 rows at level 1, 2 rows at level 0, 0 rows above level 1.**
Level 1 means "a deterministic mechanism is in place and tested" — by this scale's own
definition that is *hardcoded/scripted, not emergent*. Levels 2–3 require the capability
to show up spontaneously and then reliably, which needs a real model substrate **and**
longitudinal evidence (VISION §5); no row claims them. The two zeros (17 ontological
evolution, 36 identity fluidity) are *properties* with no demonstrated behavior yet — a
property is tested for, never "implemented". The mechanism-level detail for every row
lives in the consolidated scorecard at the bottom of this document, and the trail of how
each verdict was earned is in git history.

The project's headline metric is the number of rows that move up a level between reviews.
A row that stays at 1 for three reviews is either not real yet or not worth building —
say which.

---

## Memory & retrieval

| # | Capability (source) | Kind | Evidence / test | Stage | Score |
|---|---|---|---|---|---|
| 1 | Working (short-term) vs. long-term separation (R1.1) | Store | Distinct working context vs. persistent stores; architectural, visible in the loop | 0 | 1 |
| 2 | Episodic retrieval that changes decisions (R1.2) | Behavior + store | Past experience demonstrably alters a decision (T2/T3 episodes) | 1 | 1 |
| 3 | Compression/distillation into gists & schemas (R1.3, Domain B) | Behavior | Reflection consolidation changes future behavior without retaining raw detail (Stage 1 exit) | 1 | 1 |
| 4 | Forgetting & stale-truth decay (R1.3, Q29) | Store + behavior | `decay_profile` per volatility class; deterministic decay; T12 | 1→4 | 1 |
| 5 | Prospective memory — "remind me in 3 turns" (Domain B) | Store (§3.7) | Intention stored, checked every loop, fires on trigger | 2→4 | 1 |
| 6 | Retroactive contamination re-evaluation (Q32) | Behavior (§3.6) | T11: invalidated source → dependent beliefs flagged/downgraded | 1→4 | 1 |
| 7 | Contextual/episodic triggers (deadline → past *experience*, not just definition) (Domain B) | Behavior | Retrieval biases interpretation in a live task; bespoke probe | 4 | 1 |

## Reasoning & planning

| # | Capability (source) | Kind | Evidence / test | Stage | Score |
|---|---|---|---|---|---|
| 8 | Multi-step planning ahead (R1/R2) | Behavior | Plan generated, executed, revised on failure | 0→1 | 1 |
| 9 | Reflection & self-correction on own outputs (R1.2) | Behavior (§4.3) | T3 | 2 | 1 |
| 10 | Counterfactual reasoning — "what if X had been different" (R1.2, Domain A) | *Property* | Explains a changed-variable outcome without a simulator; probe battery | 5 | 1 |
| 11 | Object permanence / intuitive physics over environment state (Domain A) | Behavior | Hidden/changed state still tracked and factored in; no prompt-only reactivity | 3 | 1 |
| 12 | Dual-process integration: fast "gut" candidate, slow verification (R3.17) | Substrate (§2) | Fast tier emits candidate before deep tier verifies/overrules; mismatch logged | 1 | 1 |
| 13 | Effort allocation — good-enough vs. deep, stakes-aware (R3.22) | Behavior (§4.6) | Depth varies with stakes; T13 correlates effort with outcomes | 2→4 | 1 |
| 14 | Devil's-advocate meta-loop — tries to disprove own conclusions (R3.25) | Behavior (§4.7) | High-stakes outputs pass a bounded adversarial pass; found contradictions acted on | 2 | 1 |
| 15 | Incubation / background monologue (Domain D, R3.18) | Behavior (§4.8) | Hard question answered better after a time gap than at first attempt | 4 | 1 |
| 16 | Paradox tolerance — holds contradictions without forced synthesis (Domain E) | Behavior (§3.6) | Unresolved conflicts kept as flagged open questions with both sides + confidence | 1→4 | 1 |
| 17 | Ontological evolution — paradigm-shift category change (R3.21) | *Property* | Schema revision under accumulated evidence, threshold-gated, owner-approved (§9.10) | 5 | 0 |

## Learning & adaptation

| # | Capability (source) | Kind | Evidence / test | Stage | Score |
|---|---|---|---|---|---|
| 18 | Real-time learning without retraining (R1.3) | Behavior | T3/T9: behavior changes within one session, persists next session | 2 | 1 |
| 19 | Curiosity — self-initiated investigation (R1.3, R3.24) | Behavior | T5 | 2 | 1 |
| 20 | Active sensing — pulls info on its own uncertainty, interrupts to ask (R3.27) | Behavior | Mid-thought insufficiency → queries a source or asks, unprompted | 3→4 | 1 |
| 21 | Idle novelty-seeking ("boredom") (R3.24) | Behavior | Self-chosen learning task during budgeted idle time (not user-requested) | 4 | 1 |
| 22 | Learning from one demonstration / video, with transfer (core, A-video pipeline) | Behavior | T1 | 2 | 1 |
| 23 | Strategy learning from correction (A2, Q30) | Behavior (§4.4) | T9: similar-case behavior changes after "no, that's wrong" | 2 | 1 |
| 24 | Meta-learning — learns how it learns (R1.3) | *Property* | Learning rate improves across task families of one kind | 5 | 1 |

## Agency & embodiment

| # | Capability (source) | Kind | Evidence / test | Stage | Score |
|---|---|---|---|---|---|
| 25 | Self-initiated action, not purely reactive (R1.4) | Behavior | Acts on its own trigger sources (§4.2), not only owner input | 4 | 1 |
| 26 | Tool chaining & multi-step tool use (R1.4) | Body (§7) | Multi-primitive task completed; tools discovered by need, not manifest | 3 | 1 |
| 27 | Multi-modality: vision, audio, time/sequence (R1.5) | Substrate | Real inputs from ≥2 modalities affect cognition | 3 | 1 |
| 28 | Real-world grounding — durations, cause/effect, consequences before acting (R2.10) | Behavior + *property* | Duration estimates check out; consequence check before actions (§5) | 3→4 | 1 |
| 29 | Authority model: four states, growing autonomy (core) | Behavior (§5) | Asks when unsure of permission; granted rules accumulate and raise autonomy | 3→4 | 1 |

## Values, communication & self

| # | Capability (source) | Kind | Evidence / test | Stage | Score |
|---|---|---|---|---|---|
| 30 | Calibrated uncertainty *communicated* to the user (A1) | Behavior | T8: labels on answers, calibrated vs. outcomes | 1 | 1 |
| 31 | Correction channel with strategy revision (A2) | Behavior (§4.4) | T9 | 2 | 1 |
| 32 | Explanation on demand, evidence-citing, plain language (A3) | Behavior (§4.5) | T10: auditable against trace | 1→2 | 1 |
| 33 | Theory of mind — false beliefs, adaptive explanation (R3.20, R2.15) | Store + behavior (§3.5) | Guides without correcting when right; explanations track owner's actual model | 3→4 | 1 |
| 34 | Teaching the user, not just answering (R2.15) | Behavior | Learner's follow-up success improves; bespoke probe | 3 | 1 |
| 35 | Self-model: limitations, strengths, what it knows/don't (R2.14, R1.7) | Store (§3.4) | Introspection answers trace to store entries, not canned text | 1 | 1 |
| 36 | Identity fluidity across long history (Domain E, R1.7) | *Property* | T7 | 5 | 0 |
| 37 | Usefulness metric — implicit & explicit, feeds effort policy (A4) | Measurement | T13 | 0→2 | 1 |

## Measurement infrastructure

| # | Capability (source) | Kind | Evidence / test | Stage | Score |
|---|---|---|---|---|---|
| 38 | Failure taxonomy — every failure tagged with root cause (Q28) | Measurement | Trace schema includes taxonomy tags; reviews read *which organ* fails | 0 | 1 |
| 39 | Longitudinal suite with delta tracking (Q31) | Measurement | 20–30 tasks weekly; trailing-30-day delta is the tracked number | 0 | 1 |
| 40 | Eval/benchmark + consistency tracking (R2.8) | Measurement | Same question twice → same answer; suite scores trend up | 0 | 1 |
| 41 | Contradiction in the record: uncertainty/contradiction events counted (R1.2) | Measurement | Count of T2 events per week, not zero — an honest system doubts | 1 | 1 |
| 42 | Preference discovery — from statements *and* history, adopted or confirmed (VISION T4) | Behavior (§6 → owner model) | Explicit "I prefer X over Y" learned; repeated same-topic corrections yield a *proposed* preference that only explicit owner confirmation activates | 2→4 | 1 |
| 43 | Domain-general abstraction — a rule learned in one domain applied, unchanged, in a structurally similar one it has never seen (VISION T6, R2.15) | Behavior (§4.1 planning; §7 body) | T6: "group by type" demonstrated on documents/images carries to file kinds never demonstrated (`.png` beside `.jpg`), while categories the demo never covered are refused and asked about instead of guessed | 4 | 1 |

---

## Deliberately excluded — not milestones

These appeared in audit rounds and are *not* buildable deliverables. Each has its reason
and, where one exists, its behavioral proxy:

| Capability (source) | Why it is excluded | Behavioral proxy in scope |
|---|---|---|
| Subjective experience / qualia / personal stake — "cares about outcomes" (R3.23) | Unfalsifiable; simulating it would be deception (VISION §4) | T7 identity, T5 curiosity, preference learning |
| Persistent mood / affective state coloring cognition (R3.19) | Would be simulated emotion on top of a model that has none | Owner-model affect *observations* (implemented: `affect.py` — tone read from the owner's own words with markers kept as evidence, recency-bounded, cited back on request; behavior responds, the mind claims no feeling); confidence as state |
| Self-preservation drive / mortality (R3.26) | Unbuildable by prompt; dangerous to fake | Continuity as an architectural property, not a fear |
| Aesthetic preference — simplicity/beauty bias (Domain C) | Not yet testable without a defined aesthetics ground truth | T6 elegance probes (candidate, Stage 5) |
| "Surprise" detector on its own novelty (Domain C, R2.9) | No reliable self-signal to detect; likely confabulated | Contradiction engine (T2/T11) — surprise *about the world*, which is real |
| Consciousness itself (R3, Domain E) | Open research problem; not a feature | The whole test battery — behavior first, metaphysics never |

---

---

## Stagnation ledger — "say which" (register rule, answered 2026-09-10)

The rule at the top of this document says a row that stays at level 1 for three reviews is
*either not real yet or not worth building — say which*. The suite now flags those rows
mechanically (`print_stagnation`, three reviews = three archived tracked runs). Here is the
answer for every group of rows — two blockers and one definitional point, not a shrug:

| Rows | Why still at level 1 | What would move it |
|---|---|---|
| 1, 2, 3, 4, 5, 6, 8, 9, 11, 12, 13, 14, 15, 16, 18, 19, 20, 22, 23, 25, 26, 29, 30, 31, 32, 35, 37, 38, 39, 40, 41, 42 | **Real, and hardcoded by construction** — a deterministic mechanism is in place and tested, so by this scale's own wording it is level 1, not level 2. Level 2 means the capability *happens spontaneously and unreliably* in open-ended conditions: that needs a real substrate and a history of runs the same tasks. | The same tasks run weekly for 30 days on a real tier, with the delta showing these mechanisms still holding when the input is not phrased for them. |
| 7, 10, 17, 21, 27, 28, 33, 34, 43 | **Gated on the model substrate** — the mechanism is built for the sandbox/text domain and honest about it (`(sandbox)` / `(data path)` / `P` in the scorecard). The words are not the capability: text-domain generalization is what level 2 would mean here. | `BEANIE_MODEL_URL` (the owner's action) → `--check-model` → weekly suite runs with `--substrate http`. |
| 24 | **Gated on time** — the data path exists (family familiarity boosts proposals, one persistent per-family meta-lesson); "learning rate improves across families" is a longitudinal *property*. | Several weeks of runs with skills learned in more than one family. |
| 36 | **Gated on time** — the T7 probe differences two histories; identity *fluidity over a long history* needs a long history. | Months of history, then the same probe. |

Nothing here is "not worth building"; if that ever becomes true for a row, the verdict goes
in this table and the row is retired from the scorecard rather than left to rot. The ledger
is answered at every milestone review, and `make verify` prompts when a row crosses the
three-review mark.

*Every row above is traceable to a question from the founding audit rounds; every new
audit question that produces a genuinely new capability gets a row here before it gets
any code. If it cannot earn a row, it is a conversation, not a requirement.*

---

## Mechanism scorecard — current (consolidated 2026-09-10)

One row per register entry: the state *today*, not a history of it. Earlier passes
appended updates and left superseded lines behind; this table replaces them so the
scorecard cannot contradict itself.

Verdict key: **1** = mechanism implemented (deterministic, tested) · **0** = not yet
implemented · **P** = property/test: data path implemented, full pass requires a real
model substrate or longitudinal history (VISION §5: no row earns 2–3 without evidence).
`(sandbox)` marks a mechanism proven in the sandbox domain whose full-domain claim is
still gated on the model substrate.

| Row(s) | Verdict | Evidence / note |
|---|---|---|
| 1–3, 5 | 1 | Working context in the loop vs. persistent stores on disk; relevance-aware recall (stored knowledge and episodes about the turn's subjects first, recency fills the window); prospective memory in turn-count, wall-clock and conditional form; routine episodic detail folds into gist entries on the background budget with lessons surviving |
| 4 | 1 | Decay profiles + sweep + stale flags (T12 test passing) |
| 6 | 1 | Contamination propagation wired into corrections of remembered facts (T11 test passing) |
| 7 | 1 | Retrieval is trigger- and relevance-aware, not recency-only (Domain B, tests passing) |
| 8, 9 | 1 | Planner/executor loop with bounded repairs; reflection with lessons (T3 test passing) |
| 10 | 1 (sandbox) | `Simulator` replays moves and plans against a virtual tree loaded from the body; "what if I moved X to Y" and goal prediction answer without touching the body — text-domain counterfactual reasoning still needs the model tier |
| 11 | 1 (sandbox) | Location facts persist for every seen/moved object; "where is X?" answers from the world model, doubtful records trigger a fresh look, observed removals crash the fact honestly, simulations never mutate world facts |
| 12 | 1 | Fast-then-deep contract with the fast candidate logged before the deep verdict |
| 13 | 1 | Depth routing reflex/deep/deep_verified by stakes and size; the reflex budget is set by the adaptive effort policy (§4.6) |
| 14 | 1 | Bounded devil's advocate over revision history; concerns recorded per turn |
| 15 | 1 | Incubation queue with evidence-version gating (§4.8 test passing) |
| 16 | 1 | Contradictions kept as flagged open questions with both sides; owner-vs-owner conflicts keep both entries, superseded flagged |
| 17 | 0→P | Ontological evolution — a Stage-5 property (threshold-gated schema revision, owner-approved); needs substrate evidence |
| 18, 19, 20 | 1 | Real-time learning (skills within a session, persisted); curiosity open-question store with loop integration; active sensing wired as questions/asks in correction, ambiguity and authority flows — and an idle investigation's finding is surfaced to the owner on the next ordinary turn ("while idle I looked into … and found … — is that what you meant?"), exactly once, without closing the gap |
| 21 | 1 (sandbox) | Idle curiosity has content: the budget takes the oldest unexplored open question, searches the environment by the question's own terms, records the search as a perception episode, attaches files searched + candidate evidence to the question, and reports it; a keyword match never closes the gap (real evidence does, T5); with no question pending it inspects an unexplored directory — never loops. Depth beyond the sandbox needs the model tier |
| 22 | 1 | One-demonstration learning with transfer (T1 test passing); a demonstrated rule runs on new folders, unmapped files untouched |
| 23 | 1 | Correction → strategy revision (T9 test passing) |
| 24 | 1 (data path) | A proposal in a familiar family arrives boosted (0.5 → 0.6) with one persistent per-family meta-lesson; the learning-rate *property* needs longitudinal evidence |
| 25, 26 | 1 | Self-initiated triggers via tick/observe; tool chaining in plans (sense → act → verify) |
| 27 | 1 (text) / 0 | Text tier + perception episodes; vision/audio encoders are model-gated |
| 28 | 1 (sandbox) | Durations and cause/effect bounded by the sandbox; consequence checks via simulation + authority gate; real-world grounding awaits body opt-in |
| 29 | 1 | Four-state authority gate; granted rules accumulate with provenance; a blocked plan becomes one counted, owner-facing permission request (surfaced once, escalating wording on repeats) that an owner statement answers — and an explicit deny is respected without nagging (§5 tests passing) |
| 30 | 1 | Calibrated labels on every reply from the evidence state (T8 test passing) |
| 31 | 1 | Correction channel with strategy revision (T9) |
| 32 | 1 | Explanation service, auditable, plain language, on demand (T10 test passing) |
| 33 | 1 (belief layer) / P | Owner belief statements stored apart from facts; conflicts surfaced without overwriting; explanations cite the owner's model; owner *tone* is observed from their own words (evidence-backed, escaped to behavior: frustrated turns never get reflex answers, get an acknowledgement + offer to change tack, and the owner can read back exactly what was noticed) — no inner life is ever claimed. Full belief-model-driven explanation adaptation needs the model tier |
| 34 | 1 (sandbox) / P | "how do you organize X?" explains the confirmed rule in plain terms and names its origin; the general teaching property needs substrate evidence |
| 35 | 1 | Self-model introspection: "what are you unsure about?" / "what have you learned?" / "what can you do?" / "tell me about yourself" answer from open questions, lessons, body capabilities + learned skills, and the T7 identity summary with an on-record calibration line — never canned text |
| 36 | P | Identity fluidity: the T7 consolidation data path exists and an executable probe differences two histories; long-history evidence pending |
| 37 | 1 | Usefulness metric, explicit and implicit: natural-language ratings attach to the judged turn and bucket per label; follow-up/abandonment signals are recorded; low-rated or abandoned reflex-class answers count as failures in the effort-policy audit |
| 38–41 | 1 | Failure taxonomy tags on every failure; consistency + contradiction counters in the trace; consistency probe in the suite (identical input → identical text) |
| 42 | 1 | Explicit preferences learned (corroborated, superseded-not-deleted); implicit proposals from repeated corrections require owner confirmation |
| T5 | 1 | Open questions close when evidence arrives — stored facts and confirmed skills resolve matching gaps with evidence refs; idle investigation records candidates without closing on a keyword match |
| T7 | 1 (data probe) | Two histories produce measurably different identity summaries traceable to corrections/skills vs. preferences, same code, same prompts |
| T8 | 1 | `calibration_report()` per-label accuracy over trace outcomes, printed by every suite run; labels beat the unlabeled baseline |
| T13 | 1 | EffortPolicy adapts the reflex budget on failures, low ratings and abandonment, persists changes with reasons, and survives restarts |
| Q13 | 1 | A successful answer the evidence does not back (<0.55 calibrated) carries an explicit caveat and opens a recorded residual gap |
| Q15 / R2.15 | 1 | `export_knowledge()` / `import_knowledge()` transfer confirmed skills, facts and preferences between minds without sharing episodes; the receiving mind performs the taught goal |
| Q31 / §8 | 1 | Longitudinal suite of 24 multi-turn tasks (protocol target 20–30) with real action turns and honesty assertions; every run is archived together with a machine-readable scorecard snapshot, so both halves of the tracked number are covered — the runner prints the suite delta vs. the previous run, *this scorecard's row movement*, and the trailing-30-day window report (pass rate, per-task turn delta, register movement, calibration, usefulness signals) |
| §8 signals | 1 | Explicit rating, correction, follow-up and abandonment all recorded per turn; the suite prints ratings by label and implicit signal counts |
| §9 (storage scale) | 1 | Appends to every store are flat-rate: the new entry is written as one line, and the file is rewritten only when an entry was actually revised, so a long-lived mind's per-turn cost no longer grows with history (measured 18× faster seeding of a 1500-fact history; a perf test guards the regression). Memory stays the source of truth and disk always matches it — durability tests cover append, revise, explicit save and reload. The remaining §9 question (graph/relational/embedding recall at true human scale) is untouched and honestly still open |
| §2 (substrate seam) | 1 | The real-model tier is a tested seam, not a promise: configuration validation with a message naming what is missing, two-tier calls over any OpenAI-compatible endpoint, the System-1 candidate passed to the System-2 tier, hedging mapped to the failure taxonomy, unreachable tiers reported honestly, an escalated turn is not paid for twice, and tracked runs are attributed to their substrate so model runs never pollute the stub baseline — all exercised against a local mock server (no external calls). `--check-model` and `--substrate http` make the owner's endpoint action one command |
| 43 (T6 analogy) | 1 (sandbox) | The demonstrated rule is lifted from extensions to *categories*: a mapping like `.pdf → docs`, `.jpg → images` generalizes to unseen kinds of the same category (`.png`, `.gif` → images, `.docx` → docs), each inferred move is labelled with its reason in the plan, and a category the demonstration never covered is reported as an unmapped gap and asked about instead of guessed — tests passing; structurally different domains (non-file work) still need the model tier |
