# What is left — and exactly what opens each gate

Written 2026-09-10, at `bad21d9`. Honest state of the build: **43 capability rows, 41 at
level 1, 2 at level 0, 0 above level 1** (`CAPABILITY_REGISTER.md`), 150 tests green, the
24/24 tracked suite green, and every remaining gap assigned to a gate instead of a shrug.

There is nothing left in the deterministic queue. Two gates remain, and both are outside
the code: they need a **real model tier** and **calendar time**. This page is the runbook
for both.

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
export BEANIE_MODEL_NAME=your-model-name
export BEANIE_API_KEY=your-key

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
