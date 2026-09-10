# Beanie — Architecture

> **Status:** founding document · Dated 2026-09-09
> **Companion:** [VISION.md](./VISION.md) — the concept, the filter, the test battery (T1–T7).
> This document turns the mind diagram into something buildable: every capability is
> classified as a **store**, a **behavior**, or a **property**, then staged in §8.

---

## 1. From diagram to buildable layers

The concept's mind diagram is a map of human faculties. A transformer is not a set of
switchable modules — it is one associative substrate. Therefore every box in the diagram
must be labeled with *what kind of thing it is in Beanie*:

| Label | Meaning | Examples |
|---|---|---|
| **Store** | Real data structures we build, with schema, provenance, confidence | Episodic memory, semantic/world model, procedural memory, self-model, owner model |
| **Behavior** | A policy/cognitive loop executed over the substrate (prompted or fine-tuned) | Reflection, curiosity, contradiction resolution, planning, permission negotiation |
| **Property** | Something we hope emerges; we **test for it** (T1–T7), we never claim to have built it | Abstraction, imagination, understanding, personality |

A box that cannot be labeled goes into the vision section with a test attached — never into
the milestone architecture. This rule is what keeps the diagram from becoming a filing
cabinet of prompts.

The refined diagram — the same mind, classified:

```
                        BEANIE — ARTIFICIAL MIND
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
    PERCEPTION               COGNITION                MEMORY
    (behaviors)              (behaviors)              (stores)
          │                       │                       │
   vision (screen/cam)      reasoning      learning   episodic
   hearing/mic              planning       curiosity  semantic+world
   environment/OS events    prediction     discovery  procedural
   documents/files          explanation    abstraction*  self
   web                       ...          ...        owner/social
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  │
                    WORLD MODEL ◄─┘  (the spine: stores carrying
                    self · owner · environment · concepts ·   provenance,
                    events · skills · values                  confidence)
                                  │
                     MOTIVATION (behaviors: goals, needs, curiosity,
                                 commitments, owner's authority rules)
                                  │
                  DECISION — think ⇄ act ; act ⇒ TOOLS = BODY
                                  │
                EXPERIENCE → REFLECTION → CONSOLIDATION
                                  │
                        MIND CHANGES (stores update; behavior changes;
                                  *property checks run)
```

Three structural consequences, stated as rules:

1. **The world model is the spine.** Everything Beanie knows lives in stores that are
   versioned, evidenced, and confidence-weighted; everything Beanie does flows through them
   and writes back to them.
2. **Tools are downstream of cognition.** Beanie does not *start* from a tool manifest. It
   starts from a need/understanding, discovers what capability that need implies, and
   resolves that to a body action. (Humans have no 151-entry keyword manifest.)
3. **Learning closes a loop.** episode → reflection → consolidation → model update →
   changed future behavior. If future behavior does not change, learning did not happen.

---

## 2. Substrate (layer 0)

The base brain. Heterogeneous, because cognition has different costs:

- **Fast tier ("System 1")** — small model(s) for perception triage, novelty detection,
  routing, and low-latency conversation reflexes. In decision contexts the fast tier emits a
  *candidate* answer or intuition *before* the deep tier engages; the deep tier then
  verifies, corrects, or overrules it (dual-process integration, Q17). The mismatch between
  the two — fast said X, slow concluded Y — is itself a signal worth logging.
- **Deep tier ("System 2")** — the most capable model available for reasoning, planning,
  reflection, consolidation. Engaged *deliberately*, at a depth chosen by effort allocation
  (§4.6), not for every token.
- **Perception encoders** — vision (screen, camera, images/video), audio/speech, document
  and web parsers.
- **Action layer** — OS/device/browser primitives behind a permission gate (§5).

The substrate is swappable. **Nothing about Beanie's identity lives in the substrate.**
Prompts are stateless lenses over stores; if all prompts were deleted, Beanie would lose
its behaviors but not its mind. If the stores were deleted, Beanie would be a newborn.

## 3. Stores — Beanie's explicit long-term self

All stores share one record envelope so that every belief can be corrected and reasoned
about:

```
Entry = {
  id, kind,
  content,                 # structured or natural
  source,                  # perception, owner, web, inference, self-reflection
  created_at, updated_at, last_observed_at,
  confidence,              # 0..1, moves with evidence (T2)
  decay_profile,           # how confidence erodes while unobserved:
                           #   rate per volatility class of this entity kind (T12)
  evidence_refs,           # pointers to episodes/entries that support it
  revision_history,        # every prior version, incl. why it changed
  access_scope             # what/who may read it (owner privacy rules)
}
```

### 3.1 Episodic store
Raw(ish) experience: what happened, when, why, outcome, consequences. The seed of
everything else. Episodes are compressed over time (detail decays, lesson survives).

### 3.2 Semantic store + world model
Entities and relations — people, places, objects, software, files, devices, accounts,
procedures — plus the causal links between events ("when X happens, Y usually follows").
This is the persistent answer to *"this is my computer… yesterday I was working on this
project… it was unfinished…"*. The world model is the store where **contradictions surface**
(§3.6).

### 3.3 Procedural store
Skills — *not* keyword-triggered recipes. A skill records: goal class, context conditions,
steps or policy, what can vary, failure modes, confidence, how it was learned (demonstrated?
discovered? derived?), and which episodes evidence it. Skills are candidates for
consolidation into the deep tier over time, and for re-derivation when they fail (T3).

### 3.4 Self-model
Beanie's representation of itself: capabilities and their limits, what it knows vs. doesn't
know, its history of successes/failures, its commitments and promises, its current goals,
its learned values. The self-model is what makes "who is Beanie?" a computation over history
(T7) and what enables honest uncertainty ("I don't know whether I'm allowed").

### 3.5 Owner / social model
The person: preferences, habits, communication style, goals, relationship history,
boundaries and authority rules the owner has granted — each with provenance and confidence
so it can be updated when the owner changes their mind (T4, T2).

The owner model additionally carries a **belief layer** (theory of mind): entries of the
form *"owner believes P"* — including *false* beliefs — with their own confidence that the
owner indeed holds them, and evidence refs to what the owner said or did. This is what
lets Beanie adapt an explanation to what the owner actually knows, choose guidance over
correction when correction isn't what the owner needs (Q20), and notice when the owner's
belief has drifted from reality (T9, T10). Communication-style adaptation (formal/casual,
technical/simple) reads from the same layer.

### 3.6 Contradiction & confidence engine
The rule that makes stores *intelligence-bearing* rather than a wiki:

```
new evidence arrives
  → locate affected entries
  → agrees          → confidence ↑ (bounded)
  → conflicts       → confidence ↓
       ├─ if owner-derived rule conflicts → ASK (highest authority)
       ├─ if resolvable by evidence       → investigate, then update
       └─ if unresolved                   → keep both, mark open question
  → revision_history.append(reason)
  → if confidence < threshold → demote/flag entry
```

**Contamination propagation (T11).** Invalidation is not a single-row update. When an
entry is invalidated or its source is revealed as unreliable (e.g., "I lied about my
name"), the engine walks `evidence_refs` in reverse: every entry that *depended* on the
invalidated one loses confidence proportionally, gets a revision reason naming the
invalidated source, and is marked for re-verification or an owner question. Knowledge
and understanding differ exactly here: the first updates one fact, the second suspects
everything that fact touched.

**Stale-truth handling (T12).** Confidence decays while an entry goes unobserved,
following the `decay_profile` appropriate to its volatility class (a file's existence
decays slower than a process's `running` flag). Decay is deterministic and profiled, and
it has teeth: a planned action that depends on a high-stakes, volatile, long-unobserved
state triggers a **proactive re-check** (perceive first, then act) instead of trusting
the stale entry. Empirical decay constants per class are an open question (§9.8).

### 3.7 Intentions & commitments (prospective memory)
A store for deferred cognitive work the mind has promised or chosen: *"remind me in 3
turns to challenge my assumption," "finish the migration plan before Friday," "verify
claim X once I have internet."* Each intention carries its trigger condition, deadline or
turn-count, priority, and origin episode. The loop checks this store against every new
perception and turn — this is how Beanie can focus on the current topic while a
background intent still fires (Domain B). Intentions that die silently (owner said "never
mind") are logged as revisions, not ghosts.

## 4. Cognitive loop & behaviors

### 4.1 The loop

```
                    ┌──────────────────────────────┐
                    │        TRIGGER SOURCES       │
                    │  owner input · scheduled     │
                    │  reflection · novelty in     │
                    │  observed stream · internal  │
                    │  contradiction · curiosity   │
                    └──────────────┬───────────────┘
                                   ▼
        perceive → update episodic → update world model → understand
                                   │
                                   ▼
            reason/plan (think) ⇄ decide — act (tools) / ask (authority)
                                   │
                                   ▼
                  observe outcome → experience recorded
                                   │
                                   ▼
           REFLECTION (delayed, scheduled): distill episode
                   → semantic facts · skill updates ·
                     self-model updates · owner-model updates
                                   │
                                   ▼
                    CONSOLIDATION → future behavior changed
```

### 4.2 Triggers (there is no "exist → think" idle loop)
Continuous cognition is event-driven, else it is an expensive no-op:

| Trigger | Detected by | Leads to |
|---|---|---|
| Owner input (any channel) | front door | normal cognition turn |
| Scheduled reflection | timer after N episodes / idle time | consolidation pass (§4.3) |
| Novelty in an observed stream | fast-tier diffing (screen, files, events) | attention, optional episode |
| Contradiction | §3.6 | investigation or question |
| Curiosity gap | planner notices "I don't know how X works here" | self-initiated investigation (T5) |
| Commitment / unfinished goal | self-model scan | resumption ("yesterday we were working on…") |
| Owner correction / negative feedback | correction handler (§4.4) | **high-priority** belief revision + strategy revision (T9) |
| Stale high-stakes state | decay monitor (T12) | proactive re-check before acting |
| Due intention | intention store (§3.7) | fire reminder / deferred action |
| Hard problem after a time gap | incubation queue (§4.8) | return to it with fresh context (budgeted) |

### 4.3 Reflection & consolidation (the learning engine)
Periodically (and after significant episodes) Beanie runs a reflection pass that answers:
*What happened? What did I learn? What belief changed? What should I do differently? What
am I unsure about? Should I ask the owner?* Outputs land in the correct stores with
provenance and confidence, and — critically — change a stored policy or skill so future
behavior differs. Reflection is a behavior over the deep tier, bounded by compute budget.

### 4.4 Correction handler (the "no, that's wrong" channel)
User feedback is the highest-authority evidence stream. On explicit correction:

```
"No, that's wrong" (explicit, or high-confidence implicit: "wait", "no",
  immediate rephrase of the request)
  → classify: fact error? intent misinterpretation? strategy/approach error?
  → route:  semantic store (§3.2)  ·  owner model (§3.5)  ·  procedural store (§3.3)
  → update the specific entry through §3.6 (confidence, provenance, revision reason)
  → if misinterpretation or strategy: revise the interpretation/strategy policy
    for SIMILAR cases (not just this case) — T9
  → log a learning episode with evidence refs
  → high priority: bypasses normal consolidation queue (T2 applies, but no waiting)
```

Implicit feedback (silence after a complex explanation, immediate correction patterns,
abandoned requests) is a weaker signal: it updates an owner-model entry with low
confidence and may prompt a check-in — it never asserts a fact alone (Q30).

### 4.5 Explanation service
A user-facing summarization layer over the trace, available on demand for any recent
decision: *the conclusion, the evidence it rested on (named, with freshness/quality), the
alternatives considered and why they lost, and the residual uncertainty* — in plain
language matched to the owner model's belief layer (§3.5). Raw chain-of-thought is never
exposed by this service; what is exposed must be auditable against the trace (T10).
Distinct from evaluation tracing: one is for the machine, one is for the person.

### 4.6 Effort allocation (cognitive laziness, done deliberately)
Not every question deserves the deep tier. Beanie carries an effort policy: perceived
stakes, volatility, and owner expectations select a depth (reflex → fast tier → single
deep pass → multi-pass with verification). "Good enough" is a valid answer when the stakes
are low — and the communicated confidence label (§3.6, T8) tells the owner which mode
just answered. Effort policy is itself learned from outcomes: if low-effort answers
correlate with corrections, the stakes estimator recalibrates (T13). This is the
engineered version of human energy conservation — not a bug, a policy.

### 4.7 Pre-flight adversarial check ("devil's advocate", bounded)
Before high-stakes or high-confidence outputs ship, a bounded adversarial pass tries to
disprove the conclusion: it hunts for contradicting store entries, assumptions that could
be false, and cases where the same evidence supports a different answer. Findings either
downgrade confidence, trigger investigation (T5), or are logged as rejected alternatives
(which makes explanations in §4.5 honest about what lost and why). The pass is bounded by
budget and stakes — Beanie doubts itself on purpose, never on every token (Q25).

### 4.8 Incubation (budgeted background cognition)
Hard problems that hit a dead end are not abandoned: they are parked in an incubation
queue with their partial state, open branches, and what was tried. On a later budget
(scheduled reflection slot, idle period, next relevant trigger), the queue returns to
them with whatever has changed in the meantime — new episodes, new evidence, a fresh
fast-tier candidate. Success criterion: Beanie sometimes answers a hard question better
after a time gap than it did at first attempt (Domain D, Q18). Background cognition is
always budgeted and scheduled (§9.1) — there is still no free-running idle loop.

## 5. Authority — agency with permission, not crippling

Four states replace "level 1–4 intelligence tiers":

```
Beanie understands: "I can do this."            → act
Beanie understands: "I am allowed to do this."  → act
Beanie understands: "I need permission."        → ask, with a clear
                                                 request and rationale
Beanie understands: "I don't know if I'm allowed." → ask (also: learn
                                                 the rule for next time)
```

- Authority rules live in the owner model with provenance ("the owner said I may install
  software without asking on this machine, 2026-08-14, still valid").
- Every permission granted/denied is an episode → reflected into a durable rule (T4).
- Autonomy *grows* as trust and rules accumulate. The system never fake-limits capability,
  only authorizes it.

## 6. Learning taxonomy → where each kind lands

| Learning kind | Example | Target |
|---|---|---|
| Fact | "The project lives at ~/proj/x" | Semantic store (with confidence/source) |
| Concept | "This application is a 3D modeling program" | World model taxonomy |
| Procedural | "Here is how we render a scene" | Procedural store |
| Causal | "When X happens, Y usually follows" | World model relations |
| Social | "My owner prefers to be asked before I touch files" | Owner model |
| Preference | "When uncertain, ask rather than guess" | Owner model + behavior |
| Strategy | "The previous approach failed; this works better" | Procedural + self-model |
| Meta | "I learn this kind of task faster after one example" | Self-model → consolidation target |

**Learning from demonstration** (the interaction model): the owner shows, Beanie watches
(episodes), reflection infers the *goal*, the *state changes*, the *conditions*, what can
*vary*, then proposes the general rule: *"You group files by type and keep project
screenshots where they are — is that the rule to remember?"* — a question, not a form to
fill. The same pipeline handles video ("what is happening, what is the person trying to
achieve, which actions cause which state changes, what general principle can I learn?").

## 7. Embodiment — tools as the body

The tool surface (OS control, filesystem, browser, screen, camera/mic, phone, internet,
terminal, keyboard/mouse) is a **capability interface**, not a mind manifest.

```
MIND  → capability need ("I need to see the desktop")
      → capability discovery (what body parts can sense/act on this?)
      → permission check (§5)
      → action primitive → perception of result → verify → reflect
```

Tools do not define intelligence; they give intelligence a world to act in. New capabilities
are described to the mind in terms of what they *sense* and what they *change*, so the mind
can discover them by need rather than by keyword.

## 8. Roadmap & exit criteria

Each stage ships only when its tests (VISION §5) pass. Tests T1–T2–T3–T8 are the backbone;
everything else hangs off them.

| Stage | Content | Exit criteria |
|---|---|---|
| **0 — Skeleton** | Substrate wiring (fast + deep tiers), loop entry point, one minimal store (episodic), owner input/output, trace with **failure-taxonomy tagging**, longitudinal-suite scaffold | End-to-end conversation with persistence; restart continuity; every failure in the trace carries a root-cause tag feeding metrics |
| **1 — Mind substrate** | All stores (§3) with the shared envelope (incl. decay profiles), reflection pass, contradiction engine incl. contamination propagation, calibrated uncertainty labels on answers, explanation service (basic) | T2, T8, T10 pass; consolidation demonstrably changes future behavior |
| **2 — General learning** | Learning from conversation, documents, images, live demonstration, video; curiosity trigger; correction handler (§4.4); bounded pre-flight adversarial check (§4.7) | T1, T3, T5, T9 pass |
| **3 — Embodiment** | OS/filesystem/browser/phone action layer behind authority gate; proactive re-check of stale high-stakes state before acting on the environment | A demonstration learned in stage 2 is performed on the real environment (T1 end-to-end); T12 re-check behavior present |
| **4 — Continuous cognition** | Attention/novelty over observed streams, scheduled reflection, incubation queue (§4.8), prospective memory (§3.7), resumption of unfinished goals, full §5 authority negotiation | T4, T11, T12 pass; autonomy grows via accumulated rules, not config; intentions and incubation fire correctly on budget |
| **5 — Individual mind** | Long-horizon consolidation (adapter fine-tunes as *one* mechanism), identity as history, effort-policy recalibration from usefulness data | T6, T7 pass; usefulness trend (T13) measurably shapes effort allocation; personality differs measurably across histories |

### Measurement protocol (mandatory from Stage 0)

From the first run, every turn records: the decision trace with evidence refs; a
**failure-taxonomy tag** when the outcome was wrong — prompt ambiguity / missing context /
evidence misweighting / causal mis-modeling / tool execution error (Q28) — so we know
*which organ* failed, not just that one did; the communicated confidence label; and
usefulness signals (explicit rating, correction, follow-up, abandonment).

A **longitudinal suite** of 20–30 complex multi-turn tasks (planning a project across
sessions, debugging with incomplete information, decisions with conflicting goals…) runs
weekly from Stage 0. The tracked number is the **delta**: suite score and
[capability-register](./CAPABILITY_REGISTER.md) movement over the trailing 30 days. A
system that shuffles code but never improves on the *same* tasks is not learning (Q31).

## 9. Open questions (deliberately unresolved)

1. **Compute budget for reflection** — when may Beanie "think" without an owner present,
   and who pays for it? (Stage 4 depends on this.)
2. **Storage substrate** — graph vs. relational vs. hybrid for the world model at
   human-scale history; embedding recall vs. structured query.
3. **What "confidence" means per store kind** — statistical for facts, negotiated for
   owner rules; one number may not fit all (see §3.6).
4. **Consolidation timing** — how much history, how often, and what triggers a fine-tune
   vs. an in-context behavior update (Stage 5).
5. **Privacy boundaries** — access_scope exists in the envelope but its enforcement model
   (local-only stores? encryption? what the deep tier may never see?) is undecided.
6. **Failure of T1–T13 under real workloads** — which tests must be *first* in the roadmap
   if compute is scarce.
7. **Calibration mapping** — how the evidence state (count, quality, source, freshness,
   contradiction level) maps to the *communicated* label and its thresholds — and how T8
   calibration is measured without the system gaming the labeler.
8. **Decay constants** — empirical `decay_profile` values per entity volatility class
   (T12); how to measure them before real failures accumulate.
9. **Explanation faithfulness** — the audit protocol proving the explanation service cites
   the *actual* reasons a decision was made, not plausible ones (T10).
10. **Paradigm-shift gating** — ontological evolution (Q21) changes the schema itself:
    what evidence threshold, whose approval (owner?), and what rollback path?
11. **CoT privacy line** — exactly where raw chain-of-thought ends and the §4.5
    summarization layer begins, per owner settings.

### Resolutions recorded by the implementation (2026-09-09)

Provisional answers the build settled; each stays open for revision under evidence.

| Question | Resolution in code |
|---|---|
| §9.1 compute budget for background cognition | Deterministic budget scheduler implemented as `Mind.tick()` (reminders, decay sweep, incubation revisits, preference mining, one idle-exploration pass, reflection at `reflect_every`); owner-configurable budget amounts and idle-time policy remain open |
| §9.2 storage substrate | JSONL envelope-per-kind chosen for current scale (`Memory`, all six stores share `records.Entry`); graph/relational hybrid is the revisit path at human-scale history. Addendum 2026-09-10: appends were O(history) because every write rewrote the file — now flat-rate (one line per append, full rewrite only when an entry was actually revised), which removes the quadratic per-turn cost at 10-year scale while keeping disk == memory |
| §9.3 what "confidence" means per store kind | One 0–1 number with decay + revision history across kinds for now; `Calibrator` keeps labels evidence-derived (T8). Owner-rule vs statistical semantics: authority rules default high-confidence owner provenance |
| §9.4 consolidation timing | Reflection cursor + identity summaries refresh in `StubReflector.consolidate()`; `ConsolidationAdapter` seam defined with `NoopConsolidationAdapter` default — a fine-tune plugs in without changing the loop |
| §9.7 calibration mapping | Provisional thresholds in `records.confidence_label` (≥0.80 / ≥0.55); T8 guards gaming by construction — labels derive from evidence state + substrate signal, never from the reply text itself |
| §9.8 decay constants | Provisional defaults (half-lives per volatility class in `records.DecayProfile`); empirical tuning scheduled for the longitudinal protocol once real workloads accumulate |
| §9.9 explanation faithfulness | **Audit protocol implemented** (`beanie/faithfulness.py`, `--audit-explanations`): explanations are provenance-first claim lists, and the audit re-resolves every citation against the trace/stores — unknown citations, value drift, unrendered values, silent material inputs and unbacked summaries all fail, and turns without a decision trace are reported as unaudited (93 suite turns + the 34-turn demo: 0 violations, 0 unaudited). The boundary is explicit: this proves the explanation matches the *recorded* trace; whether the trace captured everything the substrate did internally stays open, and needs a model tier whose internals can be read |
| §9.11 CoT privacy line | Raw chain-of-thought is never persisted or exposed; only curated summary payloads (candidate, concerns, residual) reach the trace and the §4.5 service |

## 10. Implementation status (2026-09-09)

The mechanisms for Stages 0–4 and the data path of Stage 5 are implemented in `src/beanie/`,
each module citing the section it implements (enforced by `tests/test_conformance.py`).
The T-test battery (`tests/test_battery_*.py`) executes T1, T2, T3, T4, T8, T9, T10, T11,
T12, T13 mechanisms, and T5 curiosity gaps now fire inside the loop (unresolved requests
and unknown goals record open questions). T6/T7 data paths exist and await a real
substrate or longitudinal history for their full pass criterion (VISION §5).

| Stage | Status |
|---|---|
| 0 — Skeleton | **done** — loop, episodic store, trace + failure taxonomy, continuity (tests pass) |
| 1 — Mind substrate | **done (mechanisms)** — all stores, envelope with decay, contradiction + contamination engine, calibrated labels, explanation service |
| 2 — General learning | **done (mechanisms)** — demonstration learning with transfer (T1), correction handler (T4.4, T9), self-correction/repairs (T3), reflection (T4.3); document/video/image distillation is substrate-gated (`PromptedReflector`) |
| 3 — Embodiment | **done (mechanisms, §11)** — sandbox body + four-state authority gate; the §11 organ layer is implemented end-to-end: decision gate, file index + media flow, OS body with dry-run previews (all opt-in `BEANIE_BODY_OS=1`), GUI navigation loop, adb phone limb, voice organ, stdlib WebUI + Android companion shell; LM Studio-ready tier defaults (`local-model`, keyless) |
| 4 — Continuous cognition | **done (mechanisms)** — tick() budget loop: intentions (T3.7), decay sweep (T12), incubation revisits (T4.8), reflection schedule; novelty attention (T4.2); effort allocation + bounded devil's advocate (T4.6/4.7) |
| 5 — Individual mind | **data path done** — reflection consolidation writes identity summaries (T7 data); `ConsolidationAdapter` seam for fine-tuning; long-horizon T6/T7 evidence still required |

Module → spec map: `records` §3 envelope · `stores` §3.1–3.7 · `belief` §3.6 + T2/T11/T12 ·
`calibration` T8/T13 · `learning` §6 + T1/T3/T9 · `preferences` §6/T4 · `body` §5/§7/§11.4 ·
`planning` T1/T3/T12/§4.8 · `simulate` Domain A / rows 10–11 (counterfactual replay over
the body, never touching it) · `intention` §3.7 · `reflection` §4.3 · `explain` §4.5/T10 ·
`cognition` §4.6/4.7/T5 · `attention` §4.2 · `mind` §4.1 (incl. relevance-aware recall,
row 7, and the owner-belief layer, row 33) · `searchindex` §11.2 · `streaming` §11.2 ·
`decision` §11.1 · `automation` §11.3 · `accessibility` §11.3 · `android` §11.5 · `voice` §11.6 · `webui` §11.7 · `research` §11.1 (learning sources).

Honesty ledger — what is *not* yet true: the default substrate is a documented test double
(real tiers plug in via `HTTPSubstrate`; LM Studio is the intended local server — keyless,
`local-model` default); the §11 organs are level-1 mechanisms — deterministic and tested
end-to-end with virtual limbs and dry-run previews — while *repeatedly succeeding on the
owner's live PC* is the level-2 gate none of rows 44–51 has crossed; OS control, GUI
automation, the android body and fine-tuning remain opt-in seams; no register row has
earned a 2 or 3 yet (they require observed, recurring behavior with a real substrate
over time — VISION §5 scoring rules).

---

## 11. Embodiment on the real machine

Stage 3 stopped at the sandbox body and an opt-in shell. This section is the design for
Beanie operating the owner's actual computer — the human-shaped arrangement the owner
asked for: one mind, with senses (eyes/file index), a voice (mouth/ears), and limbs
(OS body, GUI navigator, phone) — each organ swappable, each honest about itself.

### 11.1 The decision gate (owner's words: "the biggest problem")

Between understanding a request and using anything, there is a gate that answers *what
is actually being asked* — and never feeds the body a misclassified command.

1. **Deterministic first.** `DecisionGate.classify` maps action-flavored phrases to a
   bounded, closed vocabulary of needs: `play_media`, `search_file`, `open_app`,
   `install_app`, `uninstall_app`, `shell`, `docker_run`, `phone`, `web`, `learn`,
   `conversation`, `unknown`. Each carries `target`, `danger`, `needs_learning`, and a
   citable `reason` (why this kind was chosen — the §9.9 audit trail starts here).
2. **Danger is classified, not felt.** Installation, removal, shell, docker and any
   destructive/side-effect phone action are always `danger=True`, which the authority
   gate (§5) turns into an ask with a real command preview. The owner is at the top of
   the permission chain; autonomy is default for the *non-dangerous* kinds only.
3. **Model-assisted ambiguity.** When no deterministic rule fires and the request is
   not ordinary conversation (greetings/questions never pay for classification, §4.6),
   the deep tier classifies into the *same* vocabulary — a heuristic template against
   the answer keeps it honest: an invalid or unreachable tier yields `unknown`, not a
   guess; `unknown` says "I don't know how yet" and falls to conversation/curiosity.

### 11.2 Senses — the file index (Everything-class) and media

`searchindex.py` is the machine's sense of its own filesystem: a persistent,
incrementally-refreshed `FileIndex` over one or more roots (user folders when the OS
body is live; the sandbox root otherwise), with:

* kind hints for media classes (`song`→audio… via the T6 category table, extended with
  legacy formats like `.mpg`/`.m4a`); meta-words (`file`, notes/report…) never hijack
  name-like terms;
* scoring across basename tokens, stem-phrase (the bare name beats decorated variants),
  directory words, and fuzzy near-spelling against token *and* bigram candidates —
  "kabba" finds `ka_bba`, and the "why" is citable per hit;
* honesty as a property: zero matches is an answer ("I couldn't find it"), never a
  fabricated path (the acceptance test's `test_missing_files` stays green).

Media is then *local-first*: "play X" resolves against the index, and only misses fall
to `streaming.youtube_top_result`, which returns a watch URL *marked whether it is a
specific video or only a search page* — the reply exposes exactly which happened.

### 11.3 Hands & eyes — the GUI navigation loop

`automation.py` runs the bounded sense→propose→act→sense loop: the driver reads the
screen, the model tier proposes **one** next action from a closed vocabulary
(`click/type/key/wait/done/fail`, extended per-driver — the phone adds
`swipe/open_app`), the authority gate (§5) vets `gui_control` first, the limb executes,
and the loop senses again. Honest exits: `unplannable` (no proposal → nothing clicked;
guessing is never the fallback), `budget` (default 8 actions — §4.2 bounded cognition,
"paused, not abandoned"), `needs_permission` (with the exact grant phrase),
`failed` with the tier's own reason. Limbs: `VirtualGUIDriver` (scripted — what tests
drive) and `PyAutoGUIDriver` (opt-in `BEANIE_AUTOMATION=1`; its `read_screen` honestly
refuses — OCR is not the vision tier).

### 11.4 The OS body — openers, installers, docker sandboxes

`OSBody` (§7's opt-in real body) grows the higher-level hands: platform openers
(`open`/`cmd /c start`/`xdg-open` for files, URLs and default-player media),
application launches (`open -a`/binary name), package-manager install/uninstall
(`winget`/`brew`/`apt-get`), and `docker run --rm` for tasks that want another OS or
an isolated room (`shutil.which("docker")` honesty — missing tool is a `BodyError`,
not a crash). All builders are pure functions, and `dry_run` (env
`BEANIE_BODY_DRYRUN=1` or explicit) turns any action into its preview — the plan an
owner reads before granting a dangerous command. A new capability is a new `_op_*`
registered on `run()` — capability dispatch, never if/else ladders.

### 11.5 The phone as a limb

`android.py` gives the mind a second hand: the owner's Android device, driven over
`adb` from the PC (opt-in `BEANIE_ANDROID=1`). States are *discovered*
(`adb devices -l` → serial/state/model), never asserted — unplugged is "isn't
connected — nothing was attempted". Screen reading is `uiautomator dump` text; pixels
say so when the vision tier needs them (`screenshot()`); actions are `input
tap/swipe/text/keyevent`, app launches are `monkey -p` intents. `VirtualAndroidDriver`
answers the same interface so the §11.3 navigator runs phone and desktop with one loop.

### 11.6 Voice — mouth and ears

`voice.py`: the mouth is the platform's own engine (Windows SAPI via PowerShell,
macOS `say`, Linux `espeak`/`spd-say`), opt-in `BEANIE_VOICE=1`, dry-run reports
"would speak" — silent deception (`spoken: true` without sound) is a test-forbidden
state. The ears are honest about the harder half: transcription exists when a
`faster-whisper`/`speech_recognition` engine is installed, and its absence is
*reported* with the zero-install alternative (browser speech recognition in §11.7)
rather than faked.

### 11.7 Windows into the mind — WebUI & Android companion

`webui.py` is a stdlib-only `ThreadingHTTPServer` window: an embedded dark chat page
(mic button via `webkitSpeechRecognition`, spoken answers via `speechSynthesis`
— both in the page, zero installs) and a tiny JSON API where `POST /api/step` runs
the *same* `Mind.step` the CLI calls. Reminders, permission asks and state counters
(open questions, pending permissions, skills, episodes) travel over the wire — a
browser is a second face on one mind, never a parallel fake. `/api/state` also serves
the overseer instrument panel straight from the mind's own snapshot (`day_activity`,
`work_queue`): today's trace count, pending asks rendered as Allow/Never buttons that
speak the genuine grant sentences, and ⏸ chips for paused takeovers and parked incubator
problems — the phone is an audit console, not just a chat window. `android_app/` is the
Kotlin WebView companion (host field + runtime mic permission) that turns a phone into
that window on the LAN; this sandbox cannot compile it and its README says so.

### 11.8 What stays true

Everything from §1–§10 holds: LM Studio (or any OpenAI-compatible tier) can drive the
classifier and the navigation proposals without new code — a local server is just
`BEANIE_MODEL_URL=http://localhost:1234/v1`, no key required. No embodiment turns the
sandbox semantics off: the tests and suites still run entirely inside the virtual
body; the real machine is entered one permission answer at a time.

## 11. Embodiment — the real PC (owner-directed)

The owner's brief: Beanie must *actually use the computer* — see the files, play the
music, open the apps, install and uninstall software, run the phone from the PC, and
decide for itself *what knowledge or tool* a task needs. This section is the design;
register rows 44–51 track the evidence.

### 11.1 The decision gate — needs before tools (owner: "the biggest problem")

Before *anything* executes, `DecisionGate.classify` (decision.py) maps the owner's
utterance to a **bounded need vocabulary**
(`play_media | search_file | open_app | install_app | uninstall_app | shell |
docker_run | phone | web | learn | conversation | unknown`) with a `target`, a `danger`
flag, and a citable `reason`. The discipline:

1. **Deterministic rules first** — ordinary pattern-laden requests classify without
   burning tokens, and the chosen kind always prints *why* (trace decision payload).
2. **Danger is classified, not intuited** — install/uninstall/shell/docker are always
   dangerous and land in the §5 four-state gate with the *exact command preview*
   ("This would run: winget install …"); everything else defaults to autonomy.
3. **Model assist only for genuinely ambiguous requests** — the deep tier must answer
   in the same vocabulary; an unparseable or failed tier response yields `unknown`,
   not a guess, and everyday chatter never pays for a classification (§4.6 guard: the
   effort-budget regression test asserts no deep wake-up for "hi there").
4. **Unknown is an answer** — an unclassifiable request is *said*, logged as a
   curiosity gap, and falls through to ordinary conversation instead of guessing.

Routing position: after all linguistic directives (reminders, corrections, beliefs,
explanations, ratings), before plain conversation. The organ trail is in the turn's
trace (`media`/`body`/`phone` events ⇢ `Mind.organ_hint`) so §9.9 can audit which
organ answered, and why it thought it could.

### 11.2 Senses — the file index (Everything-class) and streaming fallback

*Learning sources* (`research.py`): when the gate says `learn`, the tier-driven path
fetches the top YouTube result, parses its caption tracks (bracket-depth JSON, English
preferred), converts timedtext into a transcript, extracts step-shaped lines by speech
cues (never paraphrase), then has the tier condense a checklist **and name the source's
gaps** — because most how-to videos omit pieces, a "what does this source NOT explain?"
pass is part of the mechanism, and each gap lands as its own open question. A video
without captions is treated as pictures the mind cannot yet read: the reply says so and
hands the owner the link, versus pretending comprehension.



`FileIndex` (searchindex.py) is the PC's filesystem sense: incremental multi-root
scan skipping system/cache directories, persisted to a state file, refreshed
incrementally by *mtime+size* so only changed files rescan, ghosts pruned. Search is
semantic over names, not literal:

* **kind hints** — "song/audio" → media categories from the analogy table (`mp3,
  m4a, mpg…`), "video", "picture/photo/image", "document/pdf", "media" (either);
* **fuzzy near-spelling** — every name token *and its adjacent-token bigrams* are
  fuzzy candidates at `0.78` cutoff, so `kabba` lands `ka_bba.live.mpg` and says
  "near spelling: kabba" as its reason;
* **everything must match** — no partial-match fabrication; zero matches is an answer,
  and a self-test (`missing files resolve to nothing`) guards it;
* **bare name beats decorated** — `kaba.mp3` outranks `Kaba by Kapeke.m4a` for "kaba"
  (extra bare-stem bonus), while "kaba by kapeke" finds the decorated file exactly.

The source of truth for *what the machine holds*. `streaming.py` is the outside
world: YouTube/Google URL builders + `youtube_top_result(query, fetch=…)` which
resolves a specific `watch?v=` deep link when it can and honestly degrades to the
labelled search-results URL when it cannot (network errors same answer). The play
flow states which of the two happened — "opened the top result" vs "opened the search".

### 11.3 Hands & eyes — GUI navigation loop (screen)

`automation.py`: `Navigator.run(goal)` = sense → propose → gate → act → sense, with a
hard action budget (default 8 — §4.2 boundedness) and the four-state authority gate in
the loop at the top of *every* iteration (`gui_control`). Proposals come from the
model tier's `propose_next_action(goal, screen, history)` — one small JSON action
(`click/type/key/wait/done/fail` — drivers may extend the vocabulary, e.g. the phone's
`swipe/open_app`). Outcomes and their honesty:

- `completed` — the tier said done with its reason attached;
- `budget` — "out of budget after N actions — paused, not abandoned" (never a fake win);
- `unplannable` — no action proposed: **reported, never guessed** ("I say so instead
  of guessing where to click");
- `needs_permission` — with the exact grant phrase to copy ("you may gui_control");
- `failed` — the tier's `fail` proposal or the limb's error, reported.

Limbs: `VirtualGUIDriver` (scripted screens; tests/demo), `PyAutoGUIDriver` (opt-in
`BEANIE_AUTOMATION=1`; *its `read_screen` refuses* — pixels are not text; a vision
substrate turns screenshots into the screen summary the loop consumes).

### 11.4 The OS body — openers, installers, docker sandboxes

`OSBody` (body.py) — the real-machine body, opt-in only (`BEANIE_BODY_OS=1`), with
`dry_run` ("would run: …") for previews, permission asks and tests. Platform-aware
pure command builders: openers per OS (`cmd /c start`, `open`, `xdg-open`), app
launch (`open -a`, direct binary), package managers (`winget`/`brew`/`apt-get install`
and the matching uninstalls), `docker run --rm [image [cmd]]` sandboxes — missing
docker raises a *missing tool* BodyError, never a confusing crash. Capabilities also
include `shell`/`open_file`/`open_url`/`play_media`; all dispatched through the same
`run(capability, args)` table as the sandbox body (§7), so plan executors, simulators
and the authority gate keep working unchanged over the real body.

### 11.5 The android body — the phone as a limb

`android.py`: `ADBDriver` (opt-in `BEANIE_ANDROID=1`; constructor verifies adb exists
on PATH) with *availability discovery* — `available()` runs `adb devices` and answers
honestly whether a device is connected. Actions: tap/swipe/text/keyevent over
`adb shell input`, app launch over `monkey`, screen text over `uiautomator dump`,
screenshots over `exec-out screencap`. `VirtualAndroidDriver` mirrors the interface so
the navigator drives the phone with the same loop as the desktop. When the mind sees
no phone it says so plainly: *"…no adb device answering… nothing was attempted."*

### 11.6 Voice — mouth and ears

`voice.py`: the mouth uses the *platform's own engine* — Windows SAPI via PowerShell,
macOS `say`, Linux `espeak`/`spd-say` — opt-in (`BEANIE_VOICE=1`), with dry-run
reporting "would speak", never "I said it" when it didn't. The ears gate on an
installed transcription engine (`faster-whisper` or `speech_recognition`); no engine
is an honest *no_engine / no transcription engine installed* reply that *points at the
WebUI's zero-install browser speech recognition* — the ear exists everywhere Chrome
or Edge runs, even before anything is pip-installed.

### 11.7 Windows into the mind — WebUI and Android companion

`webui.py`: a stdlib `ThreadingHTTPServer` serving an embedded page (dark design, the
owner's chat) plus a JSON API — `GET /` (the page), `POST /api/step` (a genuine
`Mind.step` — the same loop the CLI uses, returned with labels/reminders/surfaced
questions), `POST /api/tick` (background cognition report, flattened for display),
`GET /api/state` (live counters: open questions, pending permissions, skills,
episodes), `POST /api/explain` (the §9.9 validation trail). Voice runs in the browser:
`webkitSpeechRecognition` for ears, `SpeechSynthesis` for mouth — no installs.
The page also renders notice rows for reminders and proactive questions so nothing
silent is lost. `android_app/` is the Kotlin WebView shell pointing at the same URL
on the LAN (host setting persisted, runtime mic permission forwarded into the page);
its README declares the sandbox couldn't compile it — Android Studio on the owner's
machine is the build step, and that is stated, not implied.

---

*Every file, module, and prompt added to this repository must be traceable to a store, a
behavior, or a tested property in this document — or it must change this document first.*
