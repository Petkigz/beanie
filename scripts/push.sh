#!/usr/bin/env bash
# The push gate. Born 2026-09-11 from commit 486745a: a commit pushed claiming
# "271 tests green" while the runner printed "1 failed, 270 passed" — writer
# error (selective reading), exactly the class of failure that memory-rules
# cannot catch but exit codes can. This script makes 'merge-and-tell' one
# word: `bash scripts/push.sh "<message>"` — and blocks on ANY red.
#
# Exit codes: 2 = dirty-ish inputs, 5 = test/suite red, else git's own codes.
set -euo pipefail
cd "$(dirname "$0")/.."
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
MSG="${1:?usage: bash scripts/push.sh \"commit message\"}"

[ -x .venv/bin/python ] || { echo "venv missing → make setup"; make setup; }

bat_out="$(.venv/bin/python -m pytest -q 2>&1)"; bat_rc=$?
bat_line="$(printf '%s' "$bat_out" | tail -1)"
echo "battery: $bat_line (exit $bat_rc)"
if [ "$bat_rc" -ne 0 ] || printf '%s' "$bat_line" | grep -qE "[1-9][0-9]* (failed|error)"; then
    echo "HOLD: the battery is red; pushing a claim it is not."; exit 5
fi

sui_out="$(.venv/bin/python -m beanie.measure --suite-dir suites --track-dir results 2>&1)"; sui_rc=$?
sui_line="$(printf '%s' "$sui_out" | grep 'Suite summary')"
echo "suites:  $sui_line (exit $sui_rc)"
if [ "$sui_rc" -ne 0 ] || ! printf '%s' "$sui_line" | grep -qE "^Suite summary: ([0-9]+)/\1 "; then
    echo "HOLD: the suite is red or mis-capped; pushing a claim it is not."; exit 5
fi

git add -A
if git diff --cached --quiet; then
    echo "nothing staged; nothing to commit (push gate passed, nothing to do)."
    exit 0
fi
git commit -q -m "$MSG"
git push -q origin "$BRANCH"
echo -n "pushed: "
git ls-remote origin "refs/heads/$BRANCH" | awk '{print $1}'
echo "push gate complete: $(git log --oneline -1)"
