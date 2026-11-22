# Beanie — Owner Directives (D-series)

> **Status:** canon · locked by the owner · dated 2026-09-10
> These are requirements stated by the owner **after** VISION/ARCHITECTURE/CAPABILITY_REGISTER
> were locked. They extend the spec; they do not replace it. Every module built from here
> cites the directive number it answers (D1, D2, …), and the register gains a row for each.
>
> **Authority model, stated once, applied everywhere (D8):** the owner is the decider of
> what is right and wrong for this system. Beanie carries no moral veto of its own and adds
> no refusal layer the owner did not ask for. What it *does* carry — because the owner asked
> for it — is a **permission gate at the top**: autonomous by default, explicit ask on
> dangerous/irreversible operations, and every ask plus every grant is recorded and
> auditable. "No limitations, just permission from me where necessary."

---

## D1 — Model substrate: LM Studio, local, with internet

- Models run **locally on the owner's PC via LM Studio** (OpenAI-compatible server,
  default `http://localhost:1234/v1`). No cloud model dependency for ordinary operation.
- The machine **has internet access**, so tasks that need the internet are in scope.
- Wiring already exists: `substrate_http.py` speaks OpenAI-compatible HTTP
  (`BEANIE_MODEL_URL` / `BEANIE_MODEL_NAME` / `BEANIE_API_KEY`), with `--check-model`
  to prove the endpoint answers before anything depends on it.
- **Consequence:** local tier = privacy + no per-token cost; the fast/deep split maps onto
  a small local model and a large local model (or the same model with different settings).

## D2 — OS control: every platform the owner uses

Real control of the owner's machines, not a toy sandbox:

| Target | Adapter | Primary mechanism |
|---|---|---|
| Windows | `oscontrol/windows.py` | PowerShell + Win32/UIA; Everything (§D6) for search |
| Linux | `oscontrol/linux.py` | X11 (`xdotool`) / Wayland (`ydotool`, portal), `xdg-open`, package managers |
| macOS | `oscontrol/macos.py` | AppleScript/`osascript`, Accessibility API, `open` |
| Android | `oscontrol/android.py` | ADB (`adb shell input`, `uiautomator dump`), intents, package manager |
| Other OSes | `oscontrol/tail.py` | Capability-probing fallback: run what exists, report what doesn't |

- **App operation to a human degree (D2a):** open an app, navigate it, and know **where to
  click** — i.e. read the UI (accessibility tree where available, screenshot + vision model
  otherwise), locate the target control, act, then **verify by looking again**. Not scripted
  coordinates: a perceived UI state → intended next state → action → re-perception loop.
- **Install / uninstall software (D2b)** when the task requires it, gated by §D8.
- **Sandbox first when a task is risky or needs a different OS (D2c):** Docker is installed
  on the owner's PC, so a task needing Linux tooling on a Windows host, or anything
  destructive, runs in a container/VM rather than on the host.

## D3 — Interface: WebUI + Android app, voice or typing

- **WebUI** with a professional, fine-tuned interface; **Android app**.
- Both are **conversational**: the owner speaks or types, Beanie answers in kind.
- Voice in **and** out (ears/mouth), human-like phrasing — never a log dump.
- The same mind serves both; the UI is a window, not a second brain (one §D7 brain).

## D4 — Ambiguous, real-world tasks are the acceptance bar

Worked example given by the owner: **"play me kaba."**

1. Know that *kaba* here means a **song / video / audio** — not a literal filename.
2. Search the **whole PC**, not the music folder — the file can be anywhere.
3. Play it with a **media player on the PC**.
4. If it is not found locally, **play it on YouTube**.

Matching must be as forgiving as YouTube's: the same song appears as `kaba.mp3`,
`Kaba by Kapeke.m4a`, `KAABA (Official Video).mpg`, `kaba_official_audio_128kbps.mp3`,
`02 - Kaba.mp4`… many formats, many names, many typos. **This applies to all files, not
only media** (§D6).

## D5 — Learn on demand, from the internet, including video

- Beanie must **know when it needs to learn**: recognise "I cannot do this yet — I need to
  learn it first", then go and learn rather than fail or guess.
- **Go online and search for the required knowledge.**
- **Most knowledge is in videos** → Beanie must **analyse video and images as a human
  would**: see it, know it, and understand **why** it is like that / made that way.
  (Mechanically: transcript + sampled frames + UI-tree capture → vision model → a
  *demonstration-shaped* lesson that lands in the same learning path as §T1.)
- **The hard part the owner named:** confirming whether information is **true** and
  **actually useful**, and detecting that most videos **do not contain the relevant or
  complete information**. So every learned item carries provenance, a coverage verdict
  (complete / partial / off-topic), corroboration count, and an outcome-verified score
  that decays if acting on it fails.

## D6 — Whole-machine search index ("Everything"-grade)

- An index that makes **searching the entire PC take seconds** and **match well**, in the
  spirit of voidtools *Everything*: full coverage, instant response, excellent partial /
  typo-tolerant matching.
- **Applies to all files**, not only media.
- Matching signals required: exact substring, token match, subsequence (`kbd`→`keyboard`),
  n-gram similarity, edit distance, diacritic/case/separator normalisation, noise-token
  stripping (`official`, `video`, `hq`, bitrate, year), artist↔title splitting, and
  kind-by-extension — combined into a **ranked score**.
- **Every result must say why it matched** (which signals fired, with what values). This is
  the §9.9 faithfulness protocol applied to search: a result that cannot explain itself is
  not returned as a confident answer.
- Index is **incremental**: first scan builds it, later scans touch only changed directories.

## D7 — One brain, human-shaped organs

The owner's framing, adopted literally as the module map — **one brain**, with organs
around it. Each organ is a module with a declared capability surface, and each decision
records **which organ answered** (already enforced by `faithfulness.py`).

| Organ | Sense/role | Module |
|---|---|---|
| Brain | reasoning, decisions, memory | `mind.py`, `cognition.py`, `stores.py` |
| Eyes | vision — screens, photos, video frames | `vision.py` |
| Ears | speech → text | `speech.py` |
| Mouth | text → speech | `speech.py` |
| Hands | OS control, apps, tools | `oscontrol/*`, `body.py`, `planning.py` |
| Nose/attention | novelty in observed streams | `attention.py` |
| Memory of the body | where things are, what changed | `index.py`, world model |
| **Decision gate** | **how a task gets done and with what** | `gate.py` |

## D9 — The decision gate is the crux

The owner's own assessment, recorded verbatim in intent: the **decision gate** — which
decides *how* a task is done and *what* to use — is what makes Beanie as strong as it
should be, "or just another generic AI."

So the gate is a **first-class, auditable mechanism**, not a chain of `if` statements:

1. **Enumerate** candidate approaches for the goal (local index → local app → web → sandbox
   → container/VM → ask the owner), each with required capabilities.
2. **Filter** by what this machine can actually do right now (probe, never assume).
3. **Score** by: capability fit, expected cost/latency, risk class (§D8), and — decisively —
   **what has worked before**, from the usefulness tracker and outcome history. The gate
   therefore *improves with use* rather than staying static.
4. **Choose**, and record the choice **with its alternatives and their scores** — so
   "why did you do it that way?" has a provenance-backed answer (§9.9) instead of a shrug.
5. **Re-decide on failure**: a failed approach is demoted, the next candidate runs, and the
   demotion is remembered.

## D8 — Permission gate (restated as the rule every module obeys)

- **Autonomous by default.**
- **Ask** when an operation is dangerous or irreversible (destructive file ops outside a
  working area, uninstall, system settings, sending messages/money on the owner's behalf,
  installing software, anything touching another person's data or account).
- The owner's answer is **persisted as a rule**, so the same question is not asked twice.
- Every ask, grant, denial and autonomous action is **traceable** — the four-state authority
  gate (ARCHITECTURE §5) already implements this; D8 widens what it covers and keeps it the
  single choke point. No module may act on the host OS without passing through it.

---

## Build order (this document's own roadmap)

Phases are ordered by *what can be proven in the development sandbox* versus *what can only
be proven on the owner's machines*. Anything that cannot be proven here is still built, but
ships with a **self-test the owner runs** (`python -m beanie.selftest`) and a documented
test double — the same honesty rule the model substrate already follows.

| Phase | Delivers | Provable in sandbox? |
|---|---|---|
| **P1** | §D6 whole-machine index + §D4 ambiguous-task resolution ("play me kaba") + §D9 decision gate v1 | **Yes** — fake filesystems, doubles, full tests |
| **P2** | §D7 organs: `vision.py`, `speech.py` (ears/mouth), wired to LM Studio multimodal | Partially — protocol + doubles here; `--check-model` proves it live |
| **P3** | §D2 OS-control adapters (Windows/Linux/macOS/Android/tail) + UI-act-verify loop + §D2c Docker sandbox | No — built against doubles, proven by `selftest` on the owner's PC |
| **P4** | §D3 WebUI (voice + typing) then Android app | Partially — served locally, previewable; phone install needs the owner |
| **P5** | §D5 learn-from-web/video + truth & coverage verification | Partially — pipeline + doubles here; live needs a model tier |

**Not claimed until measured.** Each phase lands with tests, register rows scored at the
level actually reached, and an explicit statement of what remains unproven.
