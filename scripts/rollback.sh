#!/usr/bin/env bash
# Step P0.2 - controlled rollback. See docs/operations/production-deployment.md Part O for the full
# narrative, including the explicit, permanent limitation this script never tries to work around: it
# NEVER touches the database. Rolling the application back does not roll any migration back - see
# Part G/O for when that makes rollback unsafe.
#
# Usage:
#   scripts/rollback.sh                 # roll back to the release before the current one
#   scripts/rollback.sh <release-id>    # roll back to a specific, named release directory

set -euo pipefail

SANOCEA_ROOT="${SANOCEA_ROOT:-/opt/sanocea}"
RELEASES_DIR="${SANOCEA_ROOT}/releases"

fail() {
    echo "ROLLBACK FAILED: $1" >&2
    exit 1
}

echo "== Step 1: select target release =="
if [ "${1:-}" != "" ]; then
    TARGET_ID="$1"
else
    CURRENT_TARGET="$(readlink -f "${SANOCEA_ROOT}/sanocea" 2>/dev/null || true)"
    CURRENT_ID="$(basename "$(dirname "${CURRENT_TARGET}")")"
    # Lexicographic sort of the release-id naming scheme (UTC timestamp) is chronological.
    TARGET_ID="$(find "${RELEASES_DIR}" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
        | sort | awk -v cur="${CURRENT_ID}" '$0<cur{prev=$0} END{print prev}')"
fi
[ -n "${TARGET_ID:-}" ] || fail "could not determine a previous release to roll back to - pass one explicitly"
RELEASE_DIR="${RELEASES_DIR}/${TARGET_ID}"
[ -d "${RELEASE_DIR}/sanocea" ] && [ -d "${RELEASE_DIR}/.venv" ] || fail "release ${TARGET_ID} at ${RELEASE_DIR} is missing sanocea/ or .venv/ - cannot roll back to it"
echo "  rolling back to release ${TARGET_ID}."

echo "== Step 2: switch active release (atomic) =="
ln -sfn "${RELEASE_DIR}/sanocea" "${SANOCEA_ROOT}/sanocea.tmp"
mv -T "${SANOCEA_ROOT}/sanocea.tmp" "${SANOCEA_ROOT}/sanocea"
ln -sfn "${RELEASE_DIR}/.venv" "${SANOCEA_ROOT}/.venv.tmp"
mv -T "${SANOCEA_ROOT}/.venv.tmp" "${SANOCEA_ROOT}/.venv"
echo "  ${SANOCEA_ROOT}/sanocea and ${SANOCEA_ROOT}/.venv now point at ${TARGET_ID}."

echo "== Step 3: restart service =="
sudo systemctl restart sanocea-api

echo "== Step 4: bounded health verification =="
if ! "${RELEASE_DIR}/.venv/bin/python" "${RELEASE_DIR}/sanocea/scripts/health_check.py"; then
    fail "release ${TARGET_ID} is also unhealthy after rollback - this requires manual operator investigation, not another automatic rollback"
fi

echo "ROLLBACK PASSED: release ${TARGET_ID} is active and healthy."
echo "NOTE: no database change was made. If the release you rolled AWAY FROM ran a non-additive migration, verify schema/code compatibility manually (see production-deployment.md Part G/O) before trusting this state."
exit 0
