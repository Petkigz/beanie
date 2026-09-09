# Beanie

An **artificial mind** — not an agent: a continuously existing, learning intelligence with
human-like general intelligence, embodied in its owner's digital world, whose knowledge,
behavior, and identity grow out of its own experience and history.

> **State of the repo:** the founding documents are the locked spec; the code in `src/`
> implements the roadmap's mechanisms (Stages 0–4, Stage-5 data path) so the design cannot
> drift — every module cites the `ARCHITECTURE §` section it implements and the
> conformance test fails any file that does not.

| Document | Purpose |
|---|---|
| [VISION.md](./VISION.md) | The concept, the general-intelligence filter, the test battery (T1–T13) |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | The mind diagram turned into buildable layers + implementation status (§10) |
| [CAPABILITY_REGISTER.md](./CAPABILITY_REGISTER.md) | The running audit: every capability scored 0–3, with the mechanism scorecard |

## How the code is kept from drifting away from the vision

1. **Traceability is mechanical.** Every module's docstring cites the `ARCHITECTURE §`
   section it implements; `tests/test_conformance.py` fails the build for any file without
   a citation. New code must earn a spec reference — or the docs must change first.
2. **Acceptance = the T-tests.** `tests/test_battery_*.py` execute the VISION §5 tests
   that are executable as mechanisms (T1, T2, T3, T8, T9, T10, T11, T12, T13); the rest
   await a real model substrate or longitudinal history, and nothing in the register earns
   a 2 or 3 without that evidence.
3. **The filter is standing.** Every change is judged by VISION §2: *does this make Beanie
   more generally intelligent, or merely automate one task?*
4. **Honesty is structural.** The default substrate is a documented test double; real model
   tiers plug in behind the same interface (`HTTPSubstrate`, env-configured). OS control
   is opt-in (`BEANIE_BODY_OS=1`). No capability is claimed, only implemented or not.

## Layout

```
VISION.md · ARCHITECTURE.md · CAPABILITY_REGISTER.md   the spec (locked)
suites/                        longitudinal-suite scenarios
examples/demo_mind.py          end-to-end demo (T1/T2/T9/T10, reminders)
src/beanie/
  records.py      record envelope: source, confidence, decay, revisions (§3)
  stores.py       all stores on JSONL: episodic/semantic/skills/self/owner/intentions (§3)
  belief.py       contradiction + contamination + stale-truth decay (§3.6; T2/T11/T12)
  calibration.py  evidence-state confidence labels + usefulness tracking (T8/T13)
  learning.py     demonstration learning, confirmation, correction→strategy revision (T1/T9)
  preferences.py  preference learning & implicit discovery (T4)
  body.py         sandbox + opt-in OS body; four-state authority gate (§5/§7)
  planning.py     goal→skill→plan→verify→repair + incubation (§4.8, T3); target folder inferred from goal wording (§7)
  intention.py    prospective memory (§3.7)
  reflection.py   lessons, identity summaries, consolidation-adapter seam (§4.3/Stage 5)
  explain.py      explanation service, auditable, on demand (§4.5/T10)
  cognition.py    effort allocation, devil's advocate, curiosity gaps (§4.6/4.7)
  attention.py    novelty over observed streams (§4.2)
  substrate.py    fast/deep tier interface + deterministic test double (§2)
  substrate_http.py  optional OpenAI-compatible real model tier (§2)
  mind.py         the integrated cognitive loop — step/tick/observe/demonstrate (§4.1)
  measure.py      longitudinal suite runner (§8)
  cli.py          REPL window into the mind
Makefile          setup/test/demo/suite/repl targets (venv auto-recreation)
suites/           four longitudinal scenarios (skeleton, directives, beliefs, preferences)
tests/            52 tests incl. the conformance drift guard + T-test battery
```

## Running it

```bash
make setup test      # recreate .venv if needed, then run all tests
make demo            # end-to-end demo of the mind
make suite           # longitudinal suite; archives each run under results/ and prints the delta vs the previous run (Q31)
make repl            # talk to a mind that persists in .beanie_state/
# manual equivalents:
python3 -m venv .venv && .venv/bin/pip install pytest -e .
.venv/bin/python -m pytest
.venv/bin/python -m beanie.measure --suite-dir suites --track-dir results
```

Each mind lives in a state directory (`episodes.jsonl`, `semantic.jsonl`,
`procedural.jsonl`, `self_model.jsonl`, `owner_model.jsonl`, `intentions.jsonl`,
`trace.jsonl`, `sandbox/`). A new process over the same directory is the *same mind* —
restart continuity is a Stage 0 exit criterion.

## Roadmap status (ARCHITECTURE §8/§10)

| Stage | Status |
|---|---|
| 0 — Skeleton (loop, episodic store, trace + failure taxonomy, suite) | **done** |
| 1 — Mind substrate (all stores, contradiction/contamination engine, calibrated labels, explanation service) | **mechanisms done** (T2/T8/T10 passing) |
| 2 — General learning (demonstration, curiosity, correction handler, reflection) | **mechanisms done** (T1/T3/T5/T9 passing) |
| 3 — Embodiment (capability body + four-state authority; OS opt-in) | **sandbox done** |
| 4 — Continuous cognition (tick budget: intentions, decay, incubation, attention, devil's advocate, preference discovery) | **mechanisms done** (T4 passing) |
| 5 — Individual mind (consolidation data path + adapter seam; identity summaries) | **data path done** — T6/T7 need longitudinal history |

The old prototype was abandoned as too chaotic; these documents and this code are the
restart, built so it stays what it was designed to be — an artificial mind, not an agent.
