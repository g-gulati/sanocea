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
VENVS_DIR="${SANOCEA_ROOT}/shared/venvs"
SOURCE_REPO="${SANOCEA_DEPLOY_SOURCE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Floor for the EARLY guard below - deliberately well above GPE Order Flow's own CRITICAL threshold
# (12% free / ~17.4GB on this host's 145GB root disk - see /opt/gpe-vnext/of_engine/config.py) plus
# headroom for a worst-case fresh venv build (~6.7GB) on a dependency-set cache miss, so a Sanocea
# deploy can never itself be what pushes the shared host disk toward GPE's thresholds.
MIN_FREE_MB="${SANOCEA_DEPLOY_MIN_FREE_MB:-20480}"
# How many most-recent releases to keep after a successful deploy (current + this many older ones).
KEEP_RELEASES="${SANOCEA_DEPLOY_KEEP_RELEASES:-1}"

fail() {
    echo "DEPLOY FAILED: $1" >&2
    exit 1
}

echo "== Step 0: disk guard (before touching anything) =="
# Runs BEFORE any release/venv is created - preflight_check.py's own disk_space check (500MB floor)
# only runs AFTER the candidate release+venv already exist, which is too late to prevent exactly the
# kind of transient disk pressure that pushed GPE Order Flow into STORAGE_PRESSURE/CRITICAL earlier.
FREE_MB="$(df --output=avail -m "${SANOCEA_ROOT}" | tail -1 | tr -d ' ')"
[ "${FREE_MB}" -ge "${MIN_FREE_MB}" ] || fail "only ${FREE_MB}MB free (need >= ${MIN_FREE_MB}MB before deploying - see GPE Order Flow's own storage thresholds); free space or override SANOCEA_DEPLOY_MIN_FREE_MB only if you have verified why this is safe"
echo "  ${FREE_MB}MB free, above the ${MIN_FREE_MB}MB floor."

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

echo "== Step 3: create release, install dependencies (shared, content-addressed venv store) =="
RELEASE_ID="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
RELEASE_DIR="${RELEASES_DIR}/${RELEASE_ID}"
mkdir -p "${RELEASE_DIR}"
# P0.3 finding: a real checkout can accumulate gitignored local-dev cruft (e.g. `.local/` - Windows-only
# tool binaries and stale local Postgres data dirs observed during this step, together >150MB) that must
# never ship in a release.
rsync -a --exclude='.git' --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.local' "${SOURCE_REPO}/" "${RELEASE_DIR}/sanocea/"

# Dependency LIST extraction is pure text (tomllib against pyproject.toml) - doesn't need a venv, so this
# runs with the system interpreter, before any venv (shared or fresh) is chosen/built.
"${PYTHON_BIN}" - "${RELEASE_DIR}/sanocea/pyproject.toml" <<'PYEOF' > "${RELEASE_DIR}/dependencies.txt"
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

# Content-addressed by the dependency LIST only (not the whole pyproject.toml, which also carries
# unrelated metadata/formatting that changes far more often than actual dependencies do) - this is what
# makes "new release, same dependencies" a no-op here instead of a fresh ~6.7GB install every time.
# Each distinct hash gets its own venv, built ONCE and never mutated afterward - old releases keep
# pointing at the exact byte-identical environment they were tested against (see rollback.sh, which
# only requires `<release>/.venv` to exist as a directory - a symlink to one still satisfies that).
DEP_HASH="$(sha256sum "${RELEASE_DIR}/dependencies.txt" | cut -d' ' -f1)"
VENV_TARGET="${VENVS_DIR}/${DEP_HASH}"
mkdir -p "${VENVS_DIR}"

if [ -f "${VENV_TARGET}/.complete" ]; then
    echo "  dependency set ${DEP_HASH:0:12}... unchanged - reusing existing shared venv, no install needed."
else
    echo "  dependency set ${DEP_HASH:0:12}... not cached - building a fresh shared venv (this is the ~6.7GB path, only on genuine dependency changes)."
    BUILD_DIR="${VENV_TARGET}.building.$$"
    # flock guards against two concurrent deploys racing to build the SAME missing hash; released
    # automatically when this subshell/fd closes (process exit or explicit close).
    (
        flock -x -w 900 200 || fail "timed out waiting for another deploy's venv build lock on ${DEP_HASH:0:12}"
        if [ -f "${VENV_TARGET}/.complete" ]; then
            echo "  another deploy finished building this dependency set while we waited - reusing it."
        else
            rm -rf "${BUILD_DIR}"
            "${PYTHON_BIN}" -m venv "${BUILD_DIR}"
            "${BUILD_DIR}/bin/pip" install --quiet --upgrade pip
            "${BUILD_DIR}/bin/pip" install --quiet -r "${RELEASE_DIR}/dependencies.txt"
            rm -rf "${VENV_TARGET}"
            mv -T "${BUILD_DIR}" "${VENV_TARGET}"
            date -u +%Y-%m-%dT%H-%M-%SZ > "${VENV_TARGET}/.complete"
        fi
    ) 200>"${VENVS_DIR}/.${DEP_HASH}.lock"
fi

ln -s "${VENV_TARGET}" "${RELEASE_DIR}/.venv"
echo "  release ${RELEASE_ID} staged at ${RELEASE_DIR} (.venv -> ${VENV_TARGET})."

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

echo "== Step 8: retention (keep current + ${KEEP_RELEASES} previous release(s); GC unreferenced shared venvs) =="
# Only runs after a CONFIRMED-healthy deploy - never prunes anything if step 7 failed and exited above.
mapfile -t ALL_RELEASES < <(find "${RELEASES_DIR}" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
KEEP_COUNT=$((KEEP_RELEASES + 1))
if [ "${#ALL_RELEASES[@]}" -gt "${KEEP_COUNT}" ]; then
    PRUNE_COUNT=$((${#ALL_RELEASES[@]} - KEEP_COUNT))
    for old_id in "${ALL_RELEASES[@]:0:${PRUNE_COUNT}}"; do
        echo "  removing old release ${old_id}"
        rm -rf "${RELEASES_DIR:?}/${old_id}"
    done
fi
# GC: a shared venv is kept iff SOME remaining release directory's .venv symlink still points at it -
# scans every remaining release (not just current+previous), so a release someone keeps around outside
# this policy is never left with a dangling .venv.
if [ -d "${VENVS_DIR}" ]; then
    declare -A REFERENCED_HASHES
    for release_dir in "${RELEASES_DIR}"/*/; do
        venv_link="${release_dir}.venv"
        [ -L "${venv_link}" ] || continue
        REFERENCED_HASHES["$(basename "$(readlink -f "${venv_link}")")"]=1
    done
    for venv_dir in "${VENVS_DIR}"/*/; do
        [ -d "${venv_dir}" ] || continue
        hash_name="$(basename "${venv_dir}")"
        if [ -z "${REFERENCED_HASHES[${hash_name}]:-}" ]; then
            echo "  removing unreferenced shared venv ${hash_name:0:12}..."
            rm -rf "${venv_dir}"
        fi
    done
fi

echo "DEPLOY PASSED: release ${RELEASE_ID} is active and healthy."
exit 0
