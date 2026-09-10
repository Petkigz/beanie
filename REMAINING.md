# What is left — and exactly what opens each gate

Written 2026-09-10, refreshed after the embodiment expansion. Honest state of the
build: **51 capability rows, 49 at level 1, 2 at level 0, 0 above level 1**
(`CAPABILITY_REGISTER.md`), 216 tests green, the 25/25 tracked suite green (now
including the `media_intent` acceptance task), and every remaining gap assigned to a
gate instead of a shrug.

**New since the audit addendum**: the §11 embodiment layer is built — the decision
gate (§11.1, the owner's "biggest problem"), the Everything-class file index and
local-first media flow with the labeled YouTube fallback (§11.2), the GUI navigation
loop with virtual/pyautogui limbs (§11.3), the real OS body with openers/installers/
docker and dry-run previews (§11.4), the adb phone limb (§11.5), the voice organ
(§11.6), the stdlib WebUI + Android companion (§11.7), and LM Studio as the intended
local tier (keyless `local-model` defaults). All deterministic and tested end-to-end;
**the level-2 gate for rows 44–51 is repeated success on the owner's live PC**, which
no CI environment can provide — that gate is the owner's machine itself.

**Owner onboarding for the new layer** (in order):

```bash
export BEANIE_MODEL_URL=http://localhost:1234/v1   # LM Studio server running, any model
export BEANIE_BODY_OS=1                            # real OS body: open/play/install/uri/shell
# optional: BEANIE_BODY_DRYRUN=1 first as an audition — every action reports its plan
export BEANIE_AUTOMATION=1 && pip install pyautogui  # screen eyes+hands (optional)
export BEANIE_ANDROID=1                            # phone as a limb, usb-debugging on (optional)
export BEANIE_VOICE=1                              # platform speech engine (optional)
.venv/bin/python -m beanie.webui --state-dir .beanie_state --host 0.0.0.0 --port 8080
```

Then: *"play me kaba"*, *"open firefox"*, *"install obs studio"* (counts as a
permission ask the very first time; *"you may install_app"* answers it and grants
a real standing rule), *"on my phone, open whatsapp"* — each with its permission
preview.

Two gates remain beyond the code: a **real model tier** (still Gate A — LM Studio
makes opening it one local server start instead of an account) and **calendar time**
(Gate B, unchanged — VISION §5 longitudinal evidence).

---

## Audit addendum (2026-09-10, post-`bad21d9` change audit)

A full capability/rot audit found two real regressions and restored them; nothing was
pruned, so no capability was lost or abandoned:

1. **The §4.7 pre-flight adversarial pass was wired but inert** (register row 14). The
   guard in `Mind._default_turn` read `not outcome.failure`, but `FailureTaxonomy.NONE`
   is a truthy enum member, so the devil's advocate never ran — zero executions across
   the battery, masked by an assertion that checked only that a `concerns` key exists in
   the payload (it is always written). The guard now compares against `NONE` explicitly;
   `test_effort_allocation.py` asserts the pass *ran*, and a new regression test
   (`test_pre_flight_finds_contradiction_history_about_the_subject`) proves a stored
   supersession surfaces as a named concern, costs confidence, and is cited as the
   losing alternative in the explanation.
2. **Exposed by restoring it**: `faithfulness.resolve_ref` routed real
   `decision.concerns[i]` citations to the event-kind lookup (where they correctly look
   "unknown") before the decision-payload branch could index them. The real-concern
   citation failed to resolve while a *fabricated* one failed-passes by accident — a
   bite test that bit by luck. Decision refs now resolve first; fabricated citations to
   empty concern lists still fail.

Also repaired: a missing `typing.Optional` import in `attention.py` (latent
`get_type_hints` `NameError`, no runtime effect) and a stray placeholder-less f-string.

Deliberately *not* pruned (an audit argues; it does not delete):

- `Memory.entries_of` (stores.py) and `NoveltyDetector.reset` (attention.py) — zero
  callers anywhere; unused public surface kept until a deliberate decision.
- `PromptedReflector` (reflection.py) — the Gate-A reflection seam; never constructed by
  the loop or tests. Verified: with the stub tier it degrades honestly
  ("nothing invented"), exactly as documented.
- `OSBody` — opt-in real body behind `BEANIE_BODY_OS=1`; untouched by all tests by design.
- `Incubator.park()` — now also fed automatically: a `failed` outcome in `perform_goal`
  parks the goal (with its failure taxonomy + base_dir) so the tick budget revisits it
  when evidence has moved (§4.8; closes the audit's own continuation note).
- `Mind.predict_goal` — public counterfactual API; covered by tests but not reachable
  from the CLI/suite surface.

State after this audit: 216 tests green, 25/25 suite green (the media_intent acceptance
scenario joins the battery), the §9.9 audit re-run over all suite + demo turns: 0
violations, 0 unaudited.

---

## Gate A — the model substrate (owner action: three environment variables)

The substrate seam is built and tested (`src/beanie/substrate_http.py`,
`tests/test_substrate_http.py`): fast/deep tiers over any OpenAI-compatible endpoint, with
the honesty rules wired in — a failed or hedged fast tier escalates instead of answering,
and the System-1 candidate travels with the escalation. Stub-substrate runs and
HTTP-substrate runs are never compared to each other, because different substrates are
different conditions.

**To open it:**

```bash
export BEANIE_MODEL_URL=https://your-endpoint/v1     # OpenAI-compatible
export BEANIE_MODEL_NAME=your-model-name             # LM Studio default: local-model
export BEANIE_API_KEY=your-key                       # LM Studio: not needed (leave unset)
# LM Studio: just `export BEANIE_MODEL_URL=http://localhost:1234/v1` — that's all

python -m beanie.cli --check-model                   # prints endpoint/model + fast/deep pings
python -m beanie.measure --suite-dir suites --track-dir results --substrate http
```

`--check-model` exits `2` with the missing variable names if nothing is configured, and `1`
if the deep tier is unreachable — it never pretends the tier is there.

**What it opens** (register "Stagnation ledger", group 2 — the mechanism is built for the
sandbox/text domain and the words are not the capability):

| Row | Capability | What the real tier tests |
|---|---|---|
| 7 | Contextual/episodic triggers — deadline → past *experience* | Whether retrieval keys on meaning, not phrasing |
| 10 | Counterfactual reasoning ("what if X had been different") | The same replay on open-ended narratives |
| 17 | Ontological evolution — paradigm-shift category change | The threshold-gated half (still level 0 by design) |
| 21 | Idle novelty-seeking | Curiosity that is novel to a reader, not just to the log |
| 27 | Multi-modality — vision/audio/time | Real encoders: the vision/audio half is the other level-0 row |
| 28 | Real-world grounding — durations, cause/effect, consequences | Consequences outside the simulator |
| 33 | Theory of mind — false beliefs, adaptive explanation | Belief modelling in unscripted dialogue |
| 34 | Teaching the user, not just answering | Explanations that land with a human |
| 43 | Domain-general abstraction applied across domains | Transfer between genuinely different domains |

## Gate B — time (nothing to install; just keep running)

```bash
make verify        # tests + the 24/24 tracked suite; archives one review
```

Each tracked run appends a dated review to `results/`. The window report then shows the
suite delta, register and level movement, the stagnation prompt, calibration and
usefulness — and skips deltas across different substrates on purpose.

**What it opens:**

| Rows | What is missing | What moves it |
|---|---|---|
| 24 | Meta-learning — learns how it learns | Weeks of runs with skills learned in more than one family |
| 36 | Identity fluidity across long history | Months of history, then the T7 probe that differences two histories |
| all 1-scores | VISION §5: level 2 means the capability *happens spontaneously and unreliably* in open-ended conditions | The same tasks, run weekly, with the delta showing the mechanism still holds when the input is not phrased for it |

Until then the stagnation prompt will keep naming rows that have sat at level 1 for three
reviews, which is exactly what it is for.

---

## Two things I deliberately did not decide for you

These need an owner's decision, not permission to build:

1. **Compute budget for background cognition** (ARCHITECTURE §9.1). `Mind.tick()` already
   runs reminders, decay, incubation and idle exploration on a configurable budget, but
   *when Beanie may think without you present, and who pays*, is a policy question — your
   answer, not mine.
2. **Privacy boundary** (ARCHITECTURE §9.5). `access_scope` exists in the envelope; its
   enforcement (local-only stores, encryption, what the deep tier may never see) is still
   unspecified, and it should be settled before a real tier sees real memory.

Also still explicitly open, and recorded as such in the register: the graph/relational
index at true human-scale history (§9.2 — appends are now flat-rate, the recall structure
is not) and the fine-tune path (§9.4).

**Explanation faithfulness (§9.9) is now answered, with its boundary stated.** Explanations
are provenance-first, and `python -m beanie.cli --audit-explanations` re-resolves every
citation against the trace: unknown citations, value drift, unrendered values, silent
material inputs and unbacked summaries all fail, and turns without a decision trace are
reported rather than passed. What it does *not* prove: that the trace captured everything
the substrate did internally — that needs a model tier whose internals can be read, and it
stays recorded as open in ARCHITECTURE §9.9 rather than papered over.
