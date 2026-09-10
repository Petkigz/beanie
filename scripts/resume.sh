#!/usr/bin/env bash
# The session-resume ritual, owned by a script instead of memory (observed: the
# sandbox has reset this branch to its base commit six times, each time
# stranding committed work as "uncommitted" files and deleting .venv/).
#
# Safety rules:
#   * local tip strictly BEHIND origin  → reset --hard to origin (rollback case)
#   * local tip == origin               → synced, just verify
#   * otherwise (true divergence)       → REFUSE; human must inspect
set -euo pipefail
cd "$(dirname "$0")/.."
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
REMOTE_REF="refs/remotes/origin/${BRANCH}"

origin_tip=$(git ls-remote origin "refs/heads/${BRANCH}" | awk "{print \$1}")
[ -n "$origin_tip" ] || { echo "FATAL: origin has no ${BRANCH}"; exit 2; }
git fetch -q origin "${BRANCH}:${REMOTE_REF}" || git fetch -q origin "+${BRANCH}:${REMOTE_REF}"
local_tip=$(git rev-parse HEAD)

echo "local  ${local_tip:0:8}   vs   origin ${origin_tip:0:8}"
if [ "$local_tip" = "$origin_tip" ]; then
    echo "tips match — verifying only"
elif git merge-base --is-ancestor "$local_tip" "$origin_tip"; then
    echo "local is strictly behind origin (the rollback signature) → resetting to origin state"
    git reset --hard "$origin_tip"
else
    echo "FATAL: true divergence (local has commits origin lacks) — refusing to reset." >&2
    exit 3
fi

[ -x .venv/bin/python ] || { echo "venv missing → make setup"; make setup; }
echo "battery: $(.venv/bin/python -m pytest -q 2>&1 | tail -1)"
echo "suites:  $(.venv/bin/python -m beanie.measure --suite-dir suites --track-dir results 2>&1 | grep 'Suite summary')"
echo "resume complete."
