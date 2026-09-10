# The First Session (a.k.a. the Level-2 evidence runbook)

This repo's codebase is shell-complete at **level‑1 evidence**: every mechanism
exists and is proven under test/simulation. Level‑2 means *observed working on a
real machine with a real model*. This file is the ladder between the two: a
~30-minute golden path, each step with the behavior you should see (the honest
failure phrasing included) and which `CAPABILITY_REGISTER` row it promotes.

Everything below assumes the same state dir for continuity: `.beanie_state/`.

## Stage A — seat the organs (rows 35, 41, 45, 46)

```bash
git pull && make setup                 # venv + editable install (rebuilt if missing)
# 1. LM Studio: Developer tab → load a chat-capable model → Status: Running
export BEANIE_MODEL_URL=http://localhost:1234/v1
export BEANIE_BODY_OS=1                # the machine's body is opt-in
export BEANIE_AUTOMATION=1             # screen navigation is opt-in; `pip install pyautogui`
make status
```

**Expected:** `model_tier` ◉ marked *reachable* (if it says UNREACHABLE, the fix line is
right there: LM Studio → Developer → Running). `os_body` ◉, `gui_control` ◉ when
pyautogui is present. This single command's output is the level‑2 evidence line
for row 35 (`--status` pronounced correctly on a real box).

## Stage B — the golden path (rows 42–44)

```bash
.venv/bin/python -m beanie.cli --state-dir .beanie_state
```

1. `play me kaba`
   → **First time:** *"I'm indexing your files first — one moment"* … then either
   serves a local match via the dry-run preview (row 42), or answers
   *"no local match for 'kaba' — your outside door: <youtube search url>"* (rows 43–44).
   Ask **in your phone in the WebUI** (`make webui`, open `http://<pc-ip>:8080`):
   say the same sentence; the pending permission ask appears as ⚠ chips with
   **Allow / Never**. Tap Allow once — the PC obeys the rule everywhere afterwards.
2. `no, the other one` (after a multi-match serve)
   → walks the **media trail**: *"(2 of 4)"* until exhaustion, which ends with
   *"...no untouched alternatives remain on this machine... outside door: <url>"*.
3. `install obs studio`
   → *"Resolved 'obs studio' → OBSProject.OBSStudio (…); also matching: OBS Virtual Camera"*
   then the **permission ask** with the exact `winget/apt/brew` command previewed.
   Answer `you may install_app` → the real install runs (row 46).
4. `research the difference between rust's Rc and Arc`
   → a tier-summarized, dated answer *"— a live lookup from DuckDuckGo (date), kept
   apart from my memory…"* (row 51 + live-web) — or, network down, the honest
   *"I couldn't reach the web…"* you'll never mistake for a fact.

## Stage C — the takeover arc (row 47)

With `BEANIE_AUTOMATION=1` + `pyatspi` (Linux) or `pywinauto` (Windows) installed:

- `log me in to github`
  → asks *"To operate the screen I need permission for gui_control — say 'you may
  gui_control'…"* before the first click. Grant once, repeat: the navigator reads
  the accessibility tree, clicks *by element name*, and reports
  *"Done — completed under supervision: N actions"*. If your screen confuses the
  model tier, you get *"I could not complete… nothing was guessed"* — a stopped
  loop is never narrated as done. Long tasks can reply *budget… say 'continue'*
  → `continue` resumes.

## Stage D — oversight as conversation (rows 32, 35, 48–50)

- `what did we do today?` → today's trace, counted per kind.
- `what are you working on?` → live queue with grant sentences. WebUI shows the same.
- `why did you say that?` → a citation-carrying explanation (`record:<id>`, `turn:<id>`).
- `make status` — note the difference between down and unconfigured once more.

## The Level-2 checklist (fill with dates as you observe them)

| Row | Observation to record | Date ✔ |
|---|---|---|
| 35 | `--status` output on a real box with the model reachable | |
| 41/42 | A real file/music index built and served a real media item | |
| 43/44 | An honest nothing-on-disk / outside-door answer on your actual library | |
| 45 | Media trail walked to exhaustion with your actual duplicates | |
| 46 | One real install with resolved id + command you approved | |
| 47 | One real GUI takeover completed (or honestly failed) on your desktop | |
| 48 | Phone WebUI grant buttons drove a real PC-side action | |
| 49 | Voice replied aloud on the PC (`--speak`, engine installed) | |
| 50 | The overseer panel chips showed your real day's queue | |
| 51 | A research/learn answer dated and separated from memory, on demand | |
| 29/§5 | `make verify` green weekly; the trailing-window line prints deltas | |

After **seven days of normal use** + this checklist ticked, edit
`CAPABILITY_REGISTER.md`'s evidence cells to say "level 2 (live, <date>)" for the
observed rows — the register header counts are conformance-enforced, so the battery
will force header updates in the same commit. That *is* the promotion protocol; it
is deliberately not automatic.
