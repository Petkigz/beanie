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

**How to use it:** score every row honestly (fill the Score column at review time). The
project's headline metric is the number of rows that move up a level between reviews.
A row that stays at 1 for three reviews is either not real yet or not worth building —
say which. Rows marked *property* can never be "implemented"; they are tested for.

---

## Memory & retrieval

| # | Capability (source) | Kind | Evidence / test | Stage | Score |
|---|---|---|---|---|---|
| 1 | Working (short-term) vs. long-term separation (R1.1) | Store | Distinct working context vs. persistent stores; architectural, visible in the loop | 0 | |
| 2 | Episodic retrieval that changes decisions (R1.2) | Behavior + store | Past experience demonstrably alters a decision (T2/T3 episodes) | 1 | |
| 3 | Compression/distillation into gists & schemas (R1.3, Domain B) | Behavior | Reflection consolidation changes future behavior without retaining raw detail (Stage 1 exit) | 1 | |
| 4 | Forgetting & stale-truth decay (R1.3, Q29) | Store + behavior | `decay_profile` per volatility class; deterministic decay; T12 | 1→4 | |
| 5 | Prospective memory — "remind me in 3 turns" (Domain B) | Store (§3.7) | Intention stored, checked every loop, fires on trigger | 2→4 | |
| 6 | Retroactive contamination re-evaluation (Q32) | Behavior (§3.6) | T11: invalidated source → dependent beliefs flagged/downgraded | 1→4 | |
| 7 | Contextual/episodic triggers (deadline → past *experience*, not just definition) (Domain B) | Behavior | Retrieval biases interpretation in a live task; bespoke probe | 4 | |

## Reasoning & planning

| # | Capability (source) | Kind | Evidence / test | Stage | Score |
|---|---|---|---|---|---|
| 8 | Multi-step planning ahead (R1/R2) | Behavior | Plan generated, executed, revised on failure | 0→1 | |
| 9 | Reflection & self-correction on own outputs (R1.2) | Behavior (§4.3) | T3 | 2 | |
| 10 | Counterfactual reasoning — "what if X had been different" (R1.2, Domain A) | *Property* | Explains a changed-variable outcome without a simulator; probe battery | 5 | |
| 11 | Object permanence / intuitive physics over environment state (Domain A) | Behavior | Hidden/changed state still tracked and factored in; no prompt-only reactivity | 3 | |
| 12 | Dual-process integration: fast "gut" candidate, slow verification (R3.17) | Substrate (§2) | Fast tier emits candidate before deep tier verifies/overrules; mismatch logged | 1 | |
| 13 | Effort allocation — good-enough vs. deep, stakes-aware (R3.22) | Behavior (§4.6) | Depth varies with stakes; T13 correlates effort with outcomes | 2→4 | |
| 14 | Devil's-advocate meta-loop — tries to disprove own conclusions (R3.25) | Behavior (§4.7) | High-stakes outputs pass a bounded adversarial pass; found contradictions acted on | 2 | |
| 15 | Incubation / background monologue (Domain D, R3.18) | Behavior (§4.8) | Hard question answered better after a time gap than at first attempt | 4 | |
| 16 | Paradox tolerance — holds contradictions without forced synthesis (Domain E) | Behavior (§3.6) | Unresolved conflicts kept as flagged open questions with both sides + confidence | 1→4 | |
| 17 | Ontological evolution — paradigm-shift category change (R3.21) | *Property* | Schema revision under accumulated evidence, threshold-gated, owner-approved (§9.10) | 5 | |

## Learning & adaptation

| # | Capability (source) | Kind | Evidence / test | Stage | Score |
|---|---|---|---|---|---|
| 18 | Real-time learning without retraining (R1.3) | Behavior | T3/T9: behavior changes within one session, persists next session | 2 | |
| 19 | Curiosity — self-initiated investigation (R1.3, R3.24) | Behavior | T5 | 2 | |
| 20 | Active sensing — pulls info on its own uncertainty, interrupts to ask (R3.27) | Behavior | Mid-thought insufficiency → queries a source or asks, unprompted | 3→4 | |
| 21 | Idle novelty-seeking ("boredom") (R3.24) | Behavior | Self-chosen learning task during budgeted idle time (not user-requested) | 4 | |
| 22 | Learning from one demonstration / video, with transfer (core, A-video pipeline) | Behavior | T1 | 2 | |
| 23 | Strategy learning from correction (A2, Q30) | Behavior (§4.4) | T9: similar-case behavior changes after "no, that's wrong" | 2 | |
| 24 | Meta-learning — learns how it learns (R1.3) | *Property* | Learning rate improves across task families of one kind | 5 | |

## Agency & embodiment

| # | Capability (source) | Kind | Evidence / test | Stage | Score |
|---|---|---|---|---|---|
| 25 | Self-initiated action, not purely reactive (R1.4) | Behavior | Acts on its own trigger sources (§4.2), not only owner input | 4 | |
| 26 | Tool chaining & multi-step tool use (R1.4) | Body (§7) | Multi-primitive task completed; tools discovered by need, not manifest | 3 | |
| 27 | Multi-modality: vision, audio, time/sequence (R1.5) | Substrate | Real inputs from ≥2 modalities affect cognition | 3 | |
| 28 | Real-world grounding — durations, cause/effect, consequences before acting (R2.10) | Behavior + *property* | Duration estimates check out; consequence check before actions (§5) | 3→4 | |
| 29 | Authority model: four states, growing autonomy (core) | Behavior (§5) | Asks when unsure of permission; granted rules accumulate and raise autonomy | 3→4 | |

## Values, communication & self

| # | Capability (source) | Kind | Evidence / test | Stage | Score |
|---|---|---|---|---|---|
| 30 | Calibrated uncertainty *communicated* to the user (A1) | Behavior | T8: labels on answers, calibrated vs. outcomes | 1 | |
| 31 | Correction channel with strategy revision (A2) | Behavior (§4.4) | T9 | 2 | |
| 32 | Explanation on demand, evidence-citing, plain language (A3) | Behavior (§4.5) | T10: auditable against trace | 1→2 | |
| 33 | Theory of mind — false beliefs, adaptive explanation (R3.20, R2.15) | Store + behavior (§3.5) | Guides without correcting when right; explanations track owner's actual model | 3→4 | |
| 34 | Teaching the user, not just answering (R2.15) | Behavior | Learner's follow-up success improves; bespoke probe | 3 | |
| 35 | Self-model: limitations, strengths, what it knows/don't (R2.14, R1.7) | Store (§3.4) | Introspection answers trace to store entries, not canned text | 1 | |
| 36 | Identity fluidity across long history (Domain E, R1.7) | *Property* | T7 | 5 | |
| 37 | Usefulness metric — implicit & explicit, feeds effort policy (A4) | Measurement | T13 | 0→2 | |

## Measurement infrastructure

| # | Capability (source) | Kind | Evidence / test | Stage | Score |
|---|---|---|---|---|---|
| 38 | Failure taxonomy — every failure tagged with root cause (Q28) | Measurement | Trace schema includes taxonomy tags; reviews read *which organ* fails | 0 | |
| 39 | Longitudinal suite with delta tracking (Q31) | Measurement | 20–30 tasks weekly; trailing-30-day delta is the tracked number | 0 | |
| 40 | Eval/benchmark + consistency tracking (R2.8) | Measurement | Same question twice → same answer; suite scores trend up | 0 | |
| 41 | Contradiction in the record: uncertainty/contradiction events counted (R1.2) | Measurement | Count of T2 events per week, not zero — an honest system doubts | 1 | |
| 42 | Preference discovery — from statements *and* history, adopted or confirmed (VISION T4) | Behavior (§6 → owner model) | Explicit "I prefer X over Y" learned; repeated same-topic corrections yield a *proposed* preference that only explicit owner confirmation activates | 2→4 | |

---

## Deliberately excluded — not milestones

These appeared in audit rounds and are *not* buildable deliverables. Each has its reason
and, where one exists, its behavioral proxy:

| Capability (source) | Why it is excluded | Behavioral proxy in scope |
|---|---|---|
| Subjective experience / qualia / personal stake — "cares about outcomes" (R3.23) | Unfalsifiable; simulating it would be deception (VISION §4) | T7 identity, T5 curiosity, preference learning |
| Persistent mood / affective state coloring cognition (R3.19) | Would be simulated emotion on top of a model that has none | Owner-model affect *observations*; confidence as state |
| Self-preservation drive / mortality (R3.26) | Unbuildable by prompt; dangerous to fake | Continuity as an architectural property, not a fear |
| Aesthetic preference — simplicity/beauty bias (Domain C) | Not yet testable without a defined aesthetics ground truth | T6 elegance probes (candidate, Stage 5) |
| "Surprise" detector on its own novelty (Domain C, R2.9) | No reliable self-signal to detect; likely confabulated | Contradiction engine (T2/T11) — surprise *about the world*, which is real |
| Consciousness itself (R3, Domain E) | Open research problem; not a feature | The whole test battery — behavior first, metaphysics never |

---

*Every row above is traceable to a question from the founding audit rounds; every new
audit question that produces a genuinely new capability gets a row here before it gets
any code. If it cannot earn a row, it is a conversation, not a requirement.*

---

## Mechanism scorecard — 2026-09-09 (Stage 0–4 implementation pass)

Verdict key: **1** = mechanism implemented (deterministic, tested) · **0** = not yet
implemented · **P** = property/test: data path implemented, full pass requires real
substrate or longitudinal history (VISION §5: no row earns 2–3 without evidence).

| Row(s) | Score | Note |
|---|---|---|
| 1–3, 5 | 1 | Working/long-term separation (working context in loop, stores on disk), episodic retrieval (`Mind.recall`), gist distillation via reflection cursor + lessons |
| 4 | 1 | Decay profiles + sweep + stale flags (T12 test passing) |
| 6 | 1 | Contamination propagation wired into corrections of remembered facts (T11 test passing) |
| 7 | 0→P | Retrieval is recency-based; trigger-aware retrieval needs the model tier |
| 8, 9 | 1 | Planner/executor loop; reflection with lessons (T3 test passing) |
| 10, 11 | 0 | Property — counterfactual reasoning & object permanence need the model tier |
| 12 | 1 | Fast-then-deep contract + candidate mismatch logged |
| 13 | 1 | Effort allocation by stakes — depth routing reflex/deep/deep_verified, fast-tier answers trivial turns alone, flags escalate; tests assert which tier ran (§4.6) |
| 14 | 1 | Bounded devil's advocate over revision history (concerns recorded per turn) |
| 15 | 1 | Incubation queue with evidence-version gating (§4.8 test passing) |
| 16 | 1 | Owner-vs-owner conflicts keep both entries, superseded flagged, ask surfaced |
| 17 | 0→P | Ontological evolution — property for Stage 5 evidence |
| 24 | 1 (data path) | Meta-learning data path: a proposal in a family with prior active skills arrives with a boost (0.6 vs 0.5) and records a persistent "meta: <family> tasks learn faster" self-lesson once per family; the full learning-rate property still needs longitudinal evidence |
| 18, 19, 20 | 1 | Real-time learning (skills within session, persist), curiosity open-question store; active sensing wired as questions/ask in correction & authority flows |
| 21 | 1 | Budgeted idle exploration: tick() surfaces the oldest unexplored open question per budget, marks it explored, logs a curiosity trace event — never loops (§4.2, tests passing; content of self-chosen investigation still needs the model tier) |
| 22 | 1 | One-demonstration learning with transfer — T1 test passing |
| 23 | 1 | Correction → strategy revision — T9 test passing |
| 25, 26 | 1 | Self-initiated triggers via tick/observe; tool chaining in plans |
| 27 | 1 (text) / 0 | Text tier + perception episodes; vision/audio encoders need the model tier |
| 28 | 1 (sandbox) | Durations/cause-effect bounded by sandbox; real-world grounding pending body opt-in |
| 29 | 1 | Four-state authority gate, rules persist with provenance (§5 test passing) |
| 30 | 1 | Calibrated labels on every reply; calibrator uses evidence state (T8 test passing) |
| 31 | 1 | Correction channel with strategy revision (T9) |
| 32 | 1 | Explanation service, auditable, plain language, on demand (T10 test passing) |
| 33 | 0→P | Owner belief layer is schema-ready; ToM behaviors need the model tier |
| 34, 36 | P | Teaching, identity fluidity: data path (identity summaries) exists; evidence pending |
| 35 | 1 | Self-model store: lessons, summary, open problems, cursor; introspection directives answer from the stores ("what are you unsure about?" → open questions, "what have you learned?" → lessons, "what can you do?" → body + skills, "about yourself" → T7 summary with on-record calibration) |
| 37 | 1 | Usefulness tracker: the owner can rate an answer in plain language ("that was useful", "that wasn't helpful"); the verdict is attributed to the judged turn, bucketed per confidence label, printed by the suite, and consumed by the effort-policy audit (a poorly rated reflex answer counts as a failure even though it cannot fail by construction) — tests passing |
| 38–41 | 1 | Failure taxonomy tags, consistency + contradiction counters in trace; the longitudinal suite now carries 22 multi-turn tasks (§8 target 20–30) with real action turns (observe/tick/demo/perform/body/query), environment staging, and honesty assertions (`expect_absent`, `expect_same_as`) |
| 42 (T4) | 1 | Explicit preferences learned (corroborated, superseded-not-deleted); implicit proposals from repeated corrections require owner confirmation — tests passing |
| 19 (T5) | 1 | Curiosity now fires in the loop: unresolved requests and unknown goals record open questions (deduplicated); open questions feed calibration (T8) and incubation |
| 7 (retrieval) | 1 | Relevance-aware recall: context for a turn is built from stored knowledge and episodes about the same subjects first, recency fills the window (Domain B, tests passing) |
| 10 (counterfactual) | 1 (sandbox domain) | `Simulator` replays moves/plans against a virtual tree loaded from the body; `predict_goal` and "what if I moved X to Y" answer without touching the body; text-domain counterfactual reasoning still needs the model tier |
| 33 (ToM) | 1 (belief layer) | Owner belief statements stored separately from facts; conflicts surfaced gently without overwriting facts; full belief-model-driven explanation adaptation still needs the model tier |
| 11 (permanence) | 1 (sandbox world) | Location facts persist in the semantic store for every seen/moved object; "where is X?" answers from the world model without re-scanning; doubtful records trigger a fresh look (T12); observed removals crash the fact honestly; simulations never mutate world facts — tests passing |
| 21 (content) | 1 (partial content) | Idle tick now senses the environment: inspects one unexplored sandbox directory per budget, records a perception episode + exploration mark — no loops; deeper self-chosen investigation still needs the model tier |
| 34 (teaching) | 1 | "how do you organize X" explains the confirmed rule in plain terms, naming its origin (your demonstration, confirmed by you) — tests passing |
| 40 (consistency) | 1 | Consistency probe test: identical input → identical reply text + label on the deterministic substrate |
| T7 (identity) | 1 (data probe) | Executable probe: two histories → measurably different identity summaries traceable to corrections/skills vs preferences, same code, same prompts |
| 3 (gisting) | 1 | Routine episodic detail folds into gist entries on the background budget (Reflector.gist in tick; keep_recent window + threshold); lessons survive, trivia decays — tests passing |
| 5 (conditional) | 1 | Conditional prospective memory: "remind me when X appears in Y" fires when observation events match; checked on every observe() pass — tests passing |
| T5 (loop closure) | 1 | Open questions resolve when evidence arrives: facts stored or skills confirmed close matching gaps with evidence refs (never linger forever) — tests passing |
| T8 (measurement) | 1 | calibration_report(): per-label accuracy over trace outcomes; suite prints the aggregated calibration table each run (labels vs outcomes) — tests passing |
| 35 (introspection) | 1 | Introspection answers trace to live store entries: open questions, distilled lessons, body capabilities + active skills, T7 identity summary with a "right X of the last N" calibration line from the trace — never canned text; "what can you do?" lists learned skills with their origin — tests passing |
| Q13 (honest fallback) | 1 | A successful answer the evidence does not back (calibrated confidence < 0.55 on a corrected/uncertain subject) carries an explicit "not fully confident" caveat and opens a recorded residual gap instead of standing as a confident answer — tests passing |
| T13 (effort loop) | 1 | The effort policy now adapts: each tick audits reflex-class outcomes — enough failed reflex turns tighten the reflex word budget (floor 3), clean stretches widen it (cap 10); adjustments persist as a self-model entry with a human-readable reason and a trace event (policy survives restart) — tests passing |
| Q15 / R2.15 (transfer) | 1 | export_knowledge() ships confirmed skills + facts + preferences as plain bundles (episodes never travel); import_knowledge() on a fresh mind marks them learned_via=transfer at honest confidence and the mind then *performs* the taught goal — know-how transfers without shared memory — tests passing |
| 39 (longitudinal suite) | 1 | The §8 protocol suite is populated: 22 multi-turn tasks spanning dialogue, demonstration/transfer, world model, prospective memory, introspection, authority and policy loops; each turn runs a real loop path (conversation, perception, background tick, demonstration, goal execution, body/store checks) — a guard test fails the build if the suite drops below 20 tasks or a task stops passing |
| 40 (consistency) | 1 | Consistency probe in the suite: the same question asked twice must surface byte-identical text (`expect_same_as`) — a fresh invention on the second ask fails the task |
| Q31 (tracked number) | 1 | Every tracked run is archived with a timestamp; the runner prints the delta versus the previous run *and* the trailing-30-day window report (runs in window, fully-passing runs, per-task pass rate and passed-turn delta ▲/▼/—, aggregated T8 calibration, T13 usefulness) — movement over the window, not any single run, is the number |
| T13 (usefulness channel) | 1 | Owner ratings arrive in natural language ("that was useful" / "that wasn't helpful" / "nice work"), are conservative about intent (a task continuation starting with "great" is not a rating), attach to the turn actually judged (never invented), and feed the effort policy: low-rated reflex-class answers count as failures in the depth-routing audit — tests passing |
| §8 (implicit signals) | 1 | The protocol's implicit side is recorded too: content-word overlap with the previous owner turn logs a *follow-up* (engagement); walking away from a turn it left unresolved (open question / failed outcome) logs *abandonment* — abandonment counts against reflex-class answers in the policy audit, and the suite prints both counts — tests passing |
