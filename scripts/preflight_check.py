from __future__ import annotations

import argparse
import os
import shutil
import sys

"""Step P0.2 - pre-flight validation, run BEFORE scripts/deploy.sh switches the active release.

Every check below prints only variable NAMES and pass/fail status - never a secret value. Exits 0 only
if every REQUIRED check passes; exits 1 (with the specific failing check named) otherwise. Intended to
be run from inside the CANDIDATE release's own virtualenv (so the exact Python/dependency versions that
would actually serve traffic are what gets validated), against the CANDIDATE release's own environment
file - never against the currently-active release.

Portable stdlib script (same pattern as scripts/run_recovery_worker.py) - runs identically on this
Windows dev host (for the checks that don't require a real Linux service, e.g. config format
validation) and on the real Ubuntu target (P0.3). Checks that need a real running service (Postgres,
object storage) are marked UNVERIFIED UNTIL P0.3 in the test report when run without that
infrastructure actually present - this script does not pretend otherwise; it reports exactly what it
could and could not verify in the environment it ran in.
"""


class CheckFailure(Exception):
    pass


def check_python_version() -> str:
    if sys.version_info < (3, 11):
        raise CheckFailure(f"Python 3.11+ required, found {sys.version_info.major}.{sys.version_info.minor}")
    return f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def check_required_env_vars() -> str:
    missing = [name for name in ("SANOCEA_PG_DSN", "SANOCEA_CRED_MASTER_KEY_CURRENT") if not os.environ.get(name)]
    if missing:
        raise CheckFailure(f"missing required environment variable(s): {', '.join(missing)}")
    if os.environ.get("SANOCEA_USE_IN_MEMORY_STORE") == "1":
        raise CheckFailure("SANOCEA_USE_IN_MEMORY_STORE=1 must never be set in a production environment file")
    return "SANOCEA_PG_DSN and SANOCEA_CRED_MASTER_KEY_CURRENT present; SANOCEA_USE_IN_MEMORY_STORE not set"


def check_master_key_format() -> str:
    try:
        from sanocea.packages.domain_contract.credentials import build_production_credential_provider
    except ImportError as exc:
        raise CheckFailure(f"cannot import credential provider module: {exc}") from exc
    dsn = os.environ.get("SANOCEA_PG_DSN", "")
    try:
        provider = build_production_credential_provider(dsn)
    except Exception as exc:
        raise CheckFailure(f"master key configuration invalid: {type(exc).__name__}: {exc}") from exc
    health = provider.health()
    return f"current key version {health['current_key_version']!r}, {len(health['known_key_versions'])} version(s) loaded"


def check_postgres_connectivity() -> str:
    import psycopg2

    dsn = os.environ.get("SANOCEA_PG_DSN", "")
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
        conn.close()
    except Exception as exc:
        raise CheckFailure(f"cannot connect to Postgres: {type(exc).__name__}: {exc}") from exc
    return "Postgres connection succeeded"


def check_object_storage_config() -> str:
    bucket = os.environ.get("SANOCEA_S3_BUCKET")
    if not bucket:
        return "SANOCEA_S3_BUCKET not set - object storage checks skipped (OPTIONAL, see production-configuration.md)"
    missing = [n for n in ("SANOCEA_S3_ACCESS_KEY", "SANOCEA_S3_SECRET_KEY") if not os.environ.get(n)]
    if missing:
        raise CheckFailure(f"SANOCEA_S3_BUCKET is set but missing: {', '.join(missing)}")
    try:
        from sanocea.packages.object_storage import S3ObjectStorage

        storage = S3ObjectStorage(
            endpoint_url=os.environ.get("SANOCEA_S3_ENDPOINT"),
            access_key_id=os.environ["SANOCEA_S3_ACCESS_KEY"],
            secret_access_key=os.environ["SANOCEA_S3_SECRET_KEY"],
            bucket=bucket,
        )
        result = storage.health()
    except Exception as exc:
        raise CheckFailure(f"object storage health check failed: {type(exc).__name__}: {exc}") from exc
    return f"object storage reachable: {result}"


def check_temporal_config() -> str:
    target = os.environ.get("SANOCEA_TEMPORAL_TARGET")
    if not target:
        return "SANOCEA_TEMPORAL_TARGET not set - by design, this topology does not depend on a real Temporal server (see production-deployment.md Part I)"
    return f"SANOCEA_TEMPORAL_TARGET is set to a value ({len(target)} chars) - note: this is a best-effort /health probe only, not a startup dependency"


def check_disk_space(release_path: str, minimum_mb: int = 500) -> str:
    total, used, free = shutil.disk_usage(release_path)
    free_mb = free // (1024 * 1024)
    if free_mb < minimum_mb:
        raise CheckFailure(f"only {free_mb}MB free at {release_path}, need at least {minimum_mb}MB")
    return f"{free_mb}MB free at {release_path}"


def check_release_path_writable(release_path: str) -> str:
    if not os.path.isdir(release_path):
        raise CheckFailure(f"release path does not exist: {release_path}")
    if not os.access(release_path, os.W_OK):
        raise CheckFailure(f"release path is not writable: {release_path}")
    return f"{release_path} exists and is writable"


CHECKS = [
    ("python_version", check_python_version),
    ("required_env_vars", check_required_env_vars),
    ("master_key_format", check_master_key_format),
    ("postgres_connectivity", check_postgres_connectivity),
    ("object_storage_config", check_object_storage_config),
    ("temporal_config", check_temporal_config),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-flight validation before switching the active Sanocea release.")
    parser.add_argument("--release-path", required=True, help="the candidate release directory to validate disk space/permissions for")
    args = parser.parse_args()

    failures: list[str] = []
    for name, fn in CHECKS:
        try:
            result = fn()
            print(f"[PASS] {name}: {result}")
        except CheckFailure as exc:
            print(f"[FAIL] {name}: {exc}")
            failures.append(name)

    for name, fn in (
        ("disk_space", lambda: check_disk_space(args.release_path)),
        ("release_path_writable", lambda: check_release_path_writable(args.release_path)),
    ):
        try:
            result = fn()
            print(f"[PASS] {name}: {result}")
        except CheckFailure as exc:
            print(f"[FAIL] {name}: {exc}")
            failures.append(name)

    if failures:
        print(f"PREFLIGHT FAILED: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("PREFLIGHT PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
