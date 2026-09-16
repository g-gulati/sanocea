#!/usr/bin/env bash
# Step P0.2 - the one bounded production deployment entry point. See docs/operations/production-
# deployment.md Part K for the full narrative; this script IS the authoritative implementation, that
# document explains WHY each step is ordered the way it is.
#
# Usage: scripts/deploy.sh
# Reads all configuration from /opt/sanocea/shared/env/sanocea.env and this repository's own checkout -
# takes NO command-line arguments, so no secret can ever be passed as one. Every wait this script
# performs is bounded (preflight_check.py and health_check.py each own their own timeouts) - never a
# manual/interactive step, never something a human needs to babysit.
#
# Exits 0 only on full PASS. Exits 1, with a specific printed reason, on any failure - never silent
# success. A failure at or before step 4 (preflight) leaves /opt/sanocea/sanocea and /opt/sanocea/.venv
# pointed at whatever release they already pointed at - this script never mutates those symlinks until
# step 5, and step 5 only runs after step 4 has explicitly passed.

set -euo pipefail

SANOCEA_ROOT="${SANOCEA_ROOT:-/opt/sanocea}"
ENV_FILE="${SANOCEA_ROOT}/shared/env/sanocea.env"
RELEASES_DIR="${SANOCEA_ROOT}/releases"
SOURCE_REPO="${SANOCEA_DEPLOY_SOURCE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

fail() {
    echo "DEPLOY FAILED: $1" >&2
    exit 1
}

echo "== Step 1: host prerequisites =="
# P0.3 finding: do not hardcode `python3.11` - pyproject.toml's actual constraint is >=3.11, and
# real Ubuntu hosts (24.04 confirmed) ship python3.12 by default with no python3.11 package available
# without adding a third-party PPA. Installing one just to match a literal binary name would violate the
# "do not install unrelated tooling" rule for zero benefit. Discover whichever interpreter on PATH
# actually satisfies the real constraint instead.
PYTHON_BIN=""
for candidate in python3.11 python3.12 python3.13 python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        ver="$("${candidate}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        major="${ver%%.*}"; minor="${ver##*.}"
        if [ "${major}" -eq 3 ] && [ "${minor}" -ge 11 ]; then
            PYTHON_BIN="${candidate}"
            PYTHON_VERSION="${ver}"
            break
        fi
    fi
done
[ -n "${PYTHON_BIN}" ] || fail "no python3.11+ interpreter found on PATH"
command -v rsync >/dev/null 2>&1 || fail "rsync not found on PATH"
command -v systemctl >/dev/null 2>&1 || fail "systemctl not found on PATH (this script targets a systemd host)"
echo "  ${PYTHON_BIN} (${PYTHON_VERSION}), rsync, systemctl present."

echo "== Step 2: config presence =="
[ -f "${ENV_FILE}" ] || fail "${ENV_FILE} does not exist - create it before deploying (see production-configuration.md)"
ENV_PERMS="$(stat -c '%a' "${ENV_FILE}")"
[ "${ENV_PERMS}" = "600" ] || fail "${ENV_FILE} must be mode 600, found ${ENV_PERMS}"
echo "  ${ENV_FILE} exists and is mode 600."

echo "== Step 3: create release, install dependencies =="
RELEASE_ID="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
RELEASE_DIR="${RELEASES_DIR}/${RELEASE_ID}"
mkdir -p "${RELEASE_DIR}"
# P0.3 finding: a real checkout can accumulate gitignored local-dev cruft (e.g. `.local/` - Windows-only
# tool binaries and stale local Postgres data dirs observed during this step, together >150MB) that must
# never ship in a release.
rsync -a --exclude='.git' --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.local' "${SOURCE_REPO}/" "${RELEASE_DIR}/sanocea/"
"${PYTHON_BIN}" -m venv "${RELEASE_DIR}/.venv"
"${RELEASE_DIR}/.venv/bin/pip" install --quiet --upgrade pip
# NOT `pip install -e .` - verified directly (Part R) that this repository's pyproject.toml has no
# [build-system]/packages configuration and setuptools refuses to build it ("Multiple top-level packages
# discovered in a flat-layout: ['apps', 'infra', 'sanocea', 'workers', 'packages', 'connectors']"). This
# repository has never been an installable Python package - `sanocea.*` only resolves via the checked-
# out `sanocea/` directory sitting under WorkingDirectory (see production-deployment.md Part F/Part A;
# CLAUDE.md's own convention: run as `python -m sanocea.scripts.X` from the PARENT directory). Only the
# third-party dependencies declared in pyproject.toml's [project.dependencies] need installing here.
"${RELEASE_DIR}/.venv/bin/python" - "${RELEASE_DIR}/sanocea/pyproject.toml" <<'PYEOF' > "${RELEASE_DIR}/dependencies.txt"
import sys
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
with open(sys.argv[1], "rb") as f:
    data = tomllib.load(f)
for dep in data["project"]["dependencies"]:
    print(dep)
PYEOF
"${RELEASE_DIR}/.venv/bin/pip" install --quiet -r "${RELEASE_DIR}/dependencies.txt"
echo "  release ${RELEASE_ID} staged at ${RELEASE_DIR}."

echo "== Step 4: pre-flight validation (BEFORE touching the active release) =="
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
# Invoked as `-m sanocea.scripts.preflight_check` with cwd=RELEASE_DIR (the parent of the `sanocea/`
# checkout) - NOT as a direct file path. Verified directly (Part R): running the script by file path
# only puts its own scripts/ directory on sys.path, so `import sanocea....` fails with
# "No module named 'sanocea'" even though the exact same file works when invoked this way, matching
# CLAUDE.md's own stated convention for every standalone script in this repository.
(cd "${RELEASE_DIR}" && "${RELEASE_DIR}/.venv/bin/python" -m sanocea.scripts.preflight_check --release-path "${RELEASE_DIR}") \
    || fail "preflight validation failed for release ${RELEASE_ID} - active release left untouched"
echo "  preflight passed."

echo "== Step 5: switch active release (atomic) =="
ln -sfn "${RELEASE_DIR}/sanocea" "${SANOCEA_ROOT}/sanocea.tmp"
mv -T "${SANOCEA_ROOT}/sanocea.tmp" "${SANOCEA_ROOT}/sanocea"
ln -sfn "${RELEASE_DIR}/.venv" "${SANOCEA_ROOT}/.venv.tmp"
mv -T "${SANOCEA_ROOT}/.venv.tmp" "${SANOCEA_ROOT}/.venv"
echo "  ${SANOCEA_ROOT}/sanocea and ${SANOCEA_ROOT}/.venv now point at ${RELEASE_ID}."

echo "== Step 6: install/refresh systemd unit, restart service =="
# P0.3 finding: the unit file's own header comment claimed deploy.sh installs it - it did not. Fixed:
# idempotently install/update from this release's own copy (so unit-file changes ship with releases like
# everything else), then daemon-reload + enable (idempotent) + restart.
UNIT_SRC="${RELEASE_DIR}/sanocea/infra/systemd/sanocea-api.service.example"
UNIT_DST="/etc/systemd/system/sanocea-api.service"
if [ ! -f "${UNIT_DST}" ] || ! cmp -s "${UNIT_SRC}" "${UNIT_DST}"; then
    sudo cp "${UNIT_SRC}" "${UNIT_DST}"
    sudo systemctl daemon-reload
    echo "  installed/updated ${UNIT_DST}."
fi
sudo systemctl enable --quiet sanocea-api
sudo systemctl restart sanocea-api

echo "== Step 7: bounded health verification =="
if ! "${RELEASE_DIR}/.venv/bin/python" "${RELEASE_DIR}/sanocea/scripts/health_check.py"; then
    echo "DEPLOY FAILED: health check did not pass after switching to release ${RELEASE_ID}." >&2
    echo "  The active release now points at ${RELEASE_ID}, which is unhealthy." >&2
    echo "  Recover with: scripts/rollback.sh" >&2
    exit 1
fi

echo "DEPLOY PASSED: release ${RELEASE_ID} is active and healthy."
exit 0
