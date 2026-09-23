# Production deployment procedure — Step P0.2

This document, together with `production-configuration.md`, `infra/systemd/sanocea-api.service.example`,
`scripts/deploy.sh`, `scripts/rollback.sh`, `scripts/preflight_check.py`, and `scripts/health_check.py`,
is intended to be sufficiently exact that a competent operator can deploy Sanocea to a fresh Ubuntu host
without asking anyone what command comes next. It documents a procedure this repository's own conventions
already point at — it does not invent a new one. **P0.2 is documentation, scripting, and locally-safe
testing only.** No step here has been run against a real production Ubuntu host. Every claim about actual
Linux/systemd behavior is labeled **UNVERIFIED UNTIL P0.3** at the point it is made; P0.3 is the step that
runs this procedure, for real, against a real host, and confirms or corrects those claims.

## Part A — actual runtime topology (as discovered, not invented)

- The application is a single FastAPI app (`sanocea.apps.api.app:app`), served by `uvicorn`, listening on
  `0.0.0.0:8010` (matching `infra/docker/sanocea.Dockerfile`'s existing convention — kept, not chosen
  fresh).
- Two infrastructure dependencies are load-bearing at startup: Postgres (`SANOCEA_PG_DSN`) and the
  credential-encryption master key (`SANOCEA_CRED_MASTER_KEY_CURRENT`/`_<VERSION>`, P0.1). Both are
  REQUIRED — `_build_store()` (`apps/api/app.py`) raises before the app can serve a single request if
  either is missing or invalid.
- Two more are OPTIONAL and independently probed by `/health` but never block startup or fail a request:
  Temporal (`SANOCEA_TEMPORAL_TARGET`) and S3-compatible object storage (`SANOCEA_S3_*`).
- `infra/docker/` (Postgres 17 + Temporal + Temporal UI + MinIO + imgproxy + API + worker, via
  `docker-compose.phase05.yml`) already exists in this repository, and its own `infra/docker/README.md`
  states it is **local-dev-only** — it is not offered, here or anywhere in this repo, as the production
  topology, so P0.2 does not adopt it as one.
- `infra/systemd/sanocea-recovery-worker.service.example` (+ `.timer.example` +
  `-oneshot.service.example`) already exists in this repository (Phase 4.6, predates this step) and
  already establishes a real production convention: `/opt/sanocea` as `WorkingDirectory`, a dedicated
  `sanocea` OS user, and a `.venv` inside that same tree. This is direct repository evidence for a
  systemd + venv production model — P0.2 follows it rather than introducing a second, conflicting scheme.
  Only the recovery worker's own scheduling (turning that example into an actually-installed,
  actually-enabled unit/timer) is P0.4's job, explicitly out of scope here.
- No CI/CD platform, no Kubernetes manifest, no Terraform/Nomad/Ansible exists anywhere in this
  repository. Nothing in the actual code requires one.

## Part B — chosen deployment model and justification

**Chosen model: systemd-managed process running inside a Python virtualenv, on a single Ubuntu host.**

Rejected alternatives and why:
- **Docker Compose** — `infra/docker/` already exists and already documents itself as local-dev-only
  (Temporal, Temporal UI, MinIO, imgproxy are dev-convenience containers, not a production topology
  choice this repository has made). Repurposing it for production would mean overriding its own stated
  purpose, not following existing evidence.
- **Kubernetes / Nomad / Terraform / Swarm** — nothing in this repository operates at a scale or
  multi-host topology that requires this. The mandate is explicit that these are excluded "unless the
  repository already genuinely requires it," and it does not.
- **Bare venv with no process manager** — fails "startup-after-reboot" and "restart-on-failure" outright;
  rejected on the mandate's own required properties.

systemd + venv satisfies every required property directly:
- **Startup-after-reboot**: `WantedBy=multi-user.target` + `systemctl enable`.
- **Restart-on-failure**: `Restart=on-failure`, `RestartSec=5`, bounded by `StartLimitIntervalSec`/`Burst`
  so a permanently-broken config fails loudly instead of crash-looping forever.
- **Controlled shutdown**: `systemctl stop` sends `SIGTERM`; uvicorn drains in-flight requests;
  `TimeoutStopSec=30` bounds the wait.
- **Logs**: `journalctl -u sanocea-api`, no separate log-shipping infrastructure required for this step.
- **Env injection**: `EnvironmentFile=`, one file, never interactive-shell-dependent.
- **Dependency ordering**: `After=network-online.target postgresql.service` (deliberately NOT Temporal —
  see Part I).
- **Health verification / operator restart / rollback**: `scripts/deploy.sh` / `scripts/rollback.sh` /
  `scripts/health_check.py` below.

This is "boring, inspectable, recoverable infrastructure": one process, one unit file, one environment
file, plain-text systemd status/journal output, no orchestration layer to reason about.

## Part C — production configuration contract

See `docs/operations/production-configuration.md` (already produced, Step P0.2 Part C deliverable) —
full REQUIRED/OPTIONAL/DEVELOPMENT ONLY/CHANNEL-SPECIFIC/EXTERNAL SECRET classification of every
variable, and the explicit rule that merchant/channel credentials never belong in this file because P0.1
already gives them durable, encrypted, tenant-isolated storage.

## Part D — secret handling

- **Not committed to Git**: `/opt/sanocea/shared/env/sanocea.env` lives only on the host, outside the
  release tree entirely (see Part F) — it is never inside a `releases/<id>/` checkout and therefore is
  never a file `git clone`/`git pull` could ever touch or overwrite.
- **Not embedded in the unit file**: `infra/systemd/sanocea-api.service.example` references
  `EnvironmentFile=/opt/sanocea/shared/env/sanocea.env` by path; no secret value appears in the unit file
  itself, so the unit file is safe to keep in version control (it already is, as the `.example` copy).
- **Filesystem permissions**: `sanocea.env` must be `chmod 600`, owned by the `sanocea` service user
  (root-created, then `chown sanocea:sanocea`) — `scripts/deploy.sh`'s pre-flight step checks this and
  fails rather than silently proceeding with an over-permissive file (see Part L/P).
- **Master key location**: the AES-256-GCM master key (`SANOCEA_CRED_MASTER_KEY_CURRENT`/`_<VERSION>`,
  P0.1) lives ONLY in `sanocea.env` on the host — never in Postgres (P0.1's own design), never in the
  release tree, never logged. `scripts/preflight_check.py`'s `master_key_format` check reports only the
  key *version* and count, never the key bytes.
- **Backup procedure must not publish the key**: whatever backs up `/opt/sanocea/shared/data` (the
  application's own state — see Part F) must NOT be configured to also back up
  `/opt/sanocea/shared/env/`. The master key needs its own, separate, operator-controlled backup channel
  (P0.1's `credential-storage.md` already states this) — a database backup of `encrypted_credentials`
  without the master key backed up separately is not a usable backup.
- **Deployment logs must not print secrets**: `scripts/deploy.sh` and `scripts/preflight_check.py` only
  ever print variable *names*, pass/fail status, and non-secret derived facts (key version, connection
  success/failure) — never a value read from `sanocea.env`. This is enforced by construction (the scripts
  simply never `print()` a secret-holding variable), not by a redaction filter.
- No Vault/KMS is introduced in P0.2, per the mandate's explicit scope control. P0.1's
  `credential-storage.md` already documents the future KMS/Vault migration path for the encrypted-
  credential master key specifically; this document does not duplicate that.

## Part E — deterministic host preparation

Target: **Ubuntu 22.04 LTS** (or 24.04 LTS) x86_64, a clean host with no other production workload.

```bash
# 1. Dedicated, unprivileged service user + group (no login shell, no home-dir surprises)
sudo useradd --system --create-home --home-dir /opt/sanocea --shell /usr/sbin/nologin sanocea

# 2. Base OS packages actually required by this application and this procedure
# P0.3 finding (real Ubuntu 24.04 VPS): the default system Python is already 3.12, which satisfies
# pyproject.toml's real constraint (>=3.11) - `python3.11` itself is NOT in Ubuntu 24.04's own apt cache
# and would require adding a third-party PPA (deadsnakes) for zero actual benefit. Do NOT add that PPA on
# a shared host merely to match a literal binary name - install whichever of python3.12/python3.11 is
# already available. `scripts/deploy.sh` discovers the right interpreter itself (any 3.11+); adjust the
# package name below only if a target host's own default Python is genuinely older than 3.11.
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip postgresql-client git rsync
# If the host's default python3 is < 3.11 (check `python3 --version` first), install a specific newer
# version from Ubuntu's own repos if one exists there (e.g. `python3.12` on 22.04 via backports) before
# reaching for a third-party PPA.

# 3. Directory skeleton (see Part F for the full release layout)
sudo mkdir -p /opt/sanocea/releases /opt/sanocea/shared/env /opt/sanocea/shared/data /opt/sanocea/shared/logs
sudo chown -R sanocea:sanocea /opt/sanocea
sudo chmod 700 /opt/sanocea/shared/env
```

Notes, so nothing here is invented beyond what the repository actually requires:
- **Python version**: `pyproject.toml` declares `requires-python = ">=3.11"` — 3.11 is the deliberate
  floor, not an arbitrary choice.
- **No global `pip install`**: every Python dependency (`fastapi`, `pydantic>=2`, `uvicorn`,
  `psycopg2-binary`, `cryptography`, `temporalio`, `boto3`, `docling`, `pillow` — the exact list in
  `pyproject.toml`) is installed into the RELEASE's own `.venv` (Part F, Part K) — never into system
  Python. This is why `python3.11-venv` is the only Python-side OS package needed, and why no dependency
  version can leak between releases.
- **Postgres/Temporal/object storage are NOT installed by this host-prep step** — they are external
  infrastructure this host connects to (a managed Postgres instance, an S3-compatible endpoint; Temporal
  deliberately not required at all — Part I). Only the `postgresql-client` package (for `pg_isready`/
  connectivity diagnostics) is installed locally; the database server itself is provisioned separately,
  as its own infrastructure decision, outside this document's scope.
- **Firewall assumption**: this host is assumed to sit behind a network boundary (security group / VPC
  firewall / reverse proxy not yet built — tracked as P0.6) that does not expose port 8010 directly to
  the public Internet. Public exposure/TLS/rate-limiting is explicitly P0.6, out of scope here; P0.2
  assumes a controlled-access network for the pilot deployment this procedure targets.
- **Checkout/release location**: `/opt/sanocea` (see Part F) — chosen because it exactly matches the
  `WorkingDirectory` already hardcoded into the pre-existing `infra/systemd/sanocea-recovery-worker.*`
  example units; changing it would require touching files this step does not need to touch.
- Every step above is idempotent (`useradd --system` fails harmlessly if the user exists;
  `apt-get install` on an already-installed package is a no-op; `mkdir -p`/`chown -R` are naturally
  idempotent) — safe to re-run.
- **UNVERIFIED UNTIL P0.3**: this has not been run against a real Ubuntu host in this step. Package names
  (`python3.11-venv` etc.) are correct for Ubuntu 22.04/24.04's own repositories as of this writing but
  have not been executed here.

## Part F — release layout (rollback-safe)

```
/opt/sanocea/
├── releases/
│   ├── 2026-09-12T14-30-00Z/     # one directory per deployment, named by UTC timestamp
│   │   ├── sanocea/              # the checked-out repository (this repo's own `sanocea/` root package)
│   │   └── .venv/                # this release's OWN virtualenv, built fresh for this release
│   └── 2026-09-10T09-15-00Z/     # a previous release, kept until pruned (see rollback, Part O)
├── sanocea -> releases/2026-09-12T14-30-00Z/sanocea   # symlink, atomically re-pointed by deploy/rollback
├── .venv   -> releases/2026-09-12T14-30-00Z/.venv      # symlink, same
└── shared/
    ├── env/
    │   └── sanocea.env           # EnvironmentFile - outside every release, chmod 600
    ├── data/                     # ReadWritePaths target in the unit file - anything the app writes locally
    └── logs/                     # reserved; journald is the actual log sink today (Part C)
```

- `sanocea-api.service`'s `WorkingDirectory=/opt/sanocea` and `ExecStart=/opt/sanocea/.venv/bin/python
  -m uvicorn sanocea.apps.api.app:app ...` never change between deployments — only what the `sanocea` and
  `.venv` symlinks point to changes. **A deployment never overwrites the only known-good application
  copy**: the previous release's directory under `releases/` is left completely untouched until an
  operator explicitly prunes it (Part O).
- Switching releases is one atomic operation per symlink: `ln -sfn releases/<new-id>/sanocea
  /opt/sanocea/sanocea.tmp && mv -T /opt/sanocea/sanocea.tmp /opt/sanocea/sanocea` (same for `.venv`) —
  `mv -T` on the same filesystem is atomic, so there is no window where the symlink is missing or
  half-written.
- `shared/env`, `shared/data` persist across every release and every rollback by construction (they live
  outside `releases/` entirely).

## Part G — database migration procedure

- **Command**: `PostgresStore(dsn).migrate()`, which executes
  `packages/domain_contract/migrations/0001_phase05.sql` in full, every time.
- **When it runs today**: this is the most important thing to disclose honestly — migration is not
  currently a separate deployment step. `apps/api/app.py::_build_store()` calls `store.migrate()`
  unconditionally on **every application startup**, against whichever database `SANOCEA_PG_DSN` on that
  host names. `scripts/deploy.sh` does not need to invoke migration as its own script action — it already
  happens the moment the new release's process starts (Part K's "run migration" step is, concretely, "the
  new release's first successful start").
- **DB identity targeted**: whatever `SANOCEA_PG_DSN` resolves to in `sanocea.env` at the time — there is
  exactly one production database in this topology; this document does not introduce a migration-specific
  connection string distinct from the application's own.
- **Success verification**: the migration file is idempotent by construction (every statement is
  `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` — confirmed by direct inspection, no
  destructive or non-idempotent statement exists in it). Success is simply "the process started without
  raising" — `scripts/health_check.py`'s post-restart check is the practical success signal.
- **Failure behavior**: a SQL error during `migrate()` raises inside `_build_store()`, which prevents
  `create_app()` from completing, which prevents uvicorn from ever binding its port — the new release's
  process never becomes healthy, `scripts/health_check.py` times out, and `scripts/deploy.sh` reports FAIL
  without having switched traffic to it (see Part K/P — the release symlink switch happens BEFORE the
  restart+health-check step specifically so a migration/startup failure is caught while the *previous*
  release's process is still the one systemd is running... see the explicit ordering note in Part K about
  why this still requires `scripts/rollback.sh` as the recovery path, not an automatic revert).
- **Backward-compatibility with rollback — explicitly NOT automatic**: rolling the *application* code
  back (Part O) does **not** roll the *database schema* back. Because every statement in
  `0001_phase05.sql` is purely additive (new tables/indexes, never `DROP`/`ALTER ... TYPE`/column
  removal), an OLDER application release remains compatible with a NEWER (already-migrated) database
  today — this is a real, current property of this schema, not a guarantee this procedure enforces going
  forward. **When a future migration is no longer purely additive (a column type change, a `NOT NULL`
  backfill, a rename), the operator must STOP and not roll the application back** without first
  confirming the older code can actually run against the migrated schema — this document does not, and
  cannot, verify that automatically, because no migration-versioning/down-migration mechanism exists in
  this codebase today (a disclosed gap, not something P0.2 is scoped to build).
- **UNVERIFIED UNTIL P0.3**: idempotency has been exercised repeatedly against real ephemeral Postgres
  instances throughout this project's own test suite (P0.1's integration tests, this step's Part R), but
  never against a real persistent production database that already has prior production data in it.

## Part H — object storage production treatment

- **Current implementation**: `packages/object_storage/s3.py::S3ObjectStorage` — a thin `boto3` S3 client
  wrapper (`put`/`get`/`health`), tenant-scoped by key prefix (`merchants/<merchant_id>/...`).
- **Production configuration**: `SANOCEA_S3_ENDPOINT` (omit for real AWS S3), `SANOCEA_S3_ACCESS_KEY`,
  `SANOCEA_S3_SECRET_KEY`, `SANOCEA_S3_BUCKET` — see `production-configuration.md`. Provider selection
  (AWS S3 vs. a self-hosted S3-compatible service) is an external/config decision this procedure remains
  neutral to; **this repository does not stand up an object-storage server itself in production** — only
  `infra/docker/`'s MinIO container does, and that is local-dev-only (Part A).
- **Bucket creation**: `S3ObjectStorage.ensure_bucket()` exists (`head_bucket`, `create_bucket` on miss)
  but is not called automatically by the application at startup — the operator (or a one-time setup
  script, out of this step's scope) must ensure the bucket exists before first use, exactly the same way
  Postgres itself must already exist before `SANOCEA_PG_DSN` can point at it.
- **Credentials**: `SANOCEA_S3_ACCESS_KEY`/`SANOCEA_S3_SECRET_KEY` — EXTERNAL SECRET, sourced from
  whichever provider is chosen, stored in `sanocea.env` (Part D) like every other bootstrap secret.
- **Persistence expectations**: durability is entirely delegated to the external provider — this
  procedure does not add its own backup/replication for object storage.
- **Health verification**: `/health`'s `object_storage` key — only present if `SANOCEA_S3_BUCKET` is set;
  `scripts/health_check.py` treats a configured-but-failing object store as an INFRASTRUCTURE HEALTH
  failure, and an unconfigured one as simply absent from the response (not a failure).
- **Unavailability behavior**: object storage is used for media assets (product images, per
  `packages/product_onboarding`) — its absence/failure does not prevent order/finance/procurement paths
  from functioning; only media-asset upload/retrieval calls fail. It is intentionally NOT wired as a
  startup dependency in `_build_store()`, matching the mandate's instruction that this may remain an
  EXTERNAL/config dependency without becoming a hard requirement of this deployment procedure.

## Part I — Temporal production treatment

**This topology does not deploy a production Temporal server, and `scripts/deploy.sh` does not require
one.** Direct inspection of `apps/api/app.py`'s `/health` route (Part A) and of
`workers/workflow/temporal_runtime.py`'s own docstring confirms: Temporal connectivity is probed only if
`SANOCEA_TEMPORAL_TARGET` is set, the probe is best-effort (`try`/`except`, converted to a status string,
never raised), and — most importantly — **no order, support, finance, or procurement path in this
codebase currently routes through Temporal at all**. `infra/temporal/README.md` (pre-existing, Phase-
whatever-it-was) already states real-Temporal wiring is acknowledged future work, not present today.

Consequences documented here explicitly, per the mandate's instruction not to solve this beyond what is
necessary:
- `sanocea-api.service` deliberately does NOT declare `After=temporal.service` / `Requires=temporal.
  service` — there is no such unit in this procedure, and the API must start and serve traffic whether or
  not any Temporal server exists anywhere in this deployment.
- No worker startup, task queue, or ordering semantics are documented here for a production Temporal
  server, because none of this procedure's scope requires standing one up.
- **If a future phase makes real Temporal load-bearing for any business path, this becomes a real
  production gap**: the development `temporal server start-dev` CLI is explicitly not production-safe
  (no durable persistence beyond a local SQLite file, no HA, not intended for real traffic) and this
  procedure does not attempt to solve production-grade Temporal persistence/availability. **Flagged, not
  solved, per the mandate.**
- `SANOCEA_TEMPORAL_TARGET` remains OPTIONAL and, for this pilot topology, is deliberately left UNSET.

## Part J — service definitions

Exactly **one** systemd service is in scope for P0.2: `sanocea-api.service` (already created —
`infra/systemd/sanocea-api.service.example`). No second service is created for the recovery worker
(`scripts/run_recovery_worker.py` + the pre-existing `sanocea-recovery-worker.*.example` units) — its
actual scheduling is P0.4, out of scope here; those example units already exist and are unaffected by
this step.

| Property | Value |
|---|---|
| Command | `/opt/sanocea/.venv/bin/python -m uvicorn sanocea.apps.api.app:app --host 0.0.0.0 --port 8010` |
| Working directory | `/opt/sanocea` (required — see the unit file's own comment on why) |
| User / Group | `sanocea` / `sanocea` |
| Environment source | `/opt/sanocea/shared/env/sanocea.env` (`EnvironmentFile=`) |
| Restart policy | `Restart=on-failure`, `RestartSec=5`, bounded by `StartLimitIntervalSec=60`/`StartLimitBurst=5` |
| Dependencies | `After=network-online.target postgresql.service` (Temporal deliberately excluded — Part I) |
| Logs | `journalctl -u sanocea-api` (stdout/stderr → journald) |
| Graceful shutdown | `KillSignal=SIGTERM`, `TimeoutStopSec=30` — uvicorn drains in-flight requests |
| Health expectations | `GET /health` returns `{"api": "ok", ...}` within a few seconds of process start (no cold-start dependency heavier than opening a Postgres connection) |

## Part K — deployment entry point

`scripts/deploy.sh` — see the script itself for the exact implementation. It performs, in order:

1. Validate host prerequisites (required executables: `python3.11`, `rsync`, `systemctl`; correct Python
   version).
2. Validate config presence (`sanocea.env` exists, is `600`, owned by `sanocea`).
3. Create the new release directory (`releases/<UTC-timestamp>/`), `rsync` the repository into
   `releases/<id>/sanocea/`, build a fresh `.venv` inside it, then install dependencies. **Not**
   `pip install -e sanocea/`: verified directly (Part R) that this repository's `pyproject.toml` has no
   `[build-system]`/package configuration and setuptools refuses the build outright ("Multiple top-level
   packages discovered in a flat-layout: ['apps', 'infra', 'sanocea', 'workers', 'packages',
   'connectors']") — this repository has never been an installable Python package, and does not need to
   be one (Part A/F). Instead, `deploy.sh` parses `[project.dependencies]` straight out of
   `pyproject.toml` (via stdlib `tomllib`) and `pip install -r`s exactly that list. `sanocea.*` itself
   becomes importable purely by virtue of the checked-out `sanocea/` directory sitting directly under
   `WorkingDirectory` — confirmed directly by simulating this exact layout with only dependencies
   installed and successfully importing `sanocea.apps.api.app`.
4. **Run `scripts/preflight_check.py`** against the new release's own `.venv` and `sanocea.env` — this is
   the Part L pre-flight gate, and it runs BEFORE any symlink is touched, so a failure here leaves the
   currently-active release completely untouched (Part P). Invoked as
   `python -m sanocea.scripts.preflight_check --release-path <dir>` with cwd set to the release directory
   (the parent of `sanocea/`) — **not** by direct file path. Verified directly: running the identical file
   by path instead only puts its own `scripts/` directory on `sys.path`, so `import sanocea....` fails
   with `No module named 'sanocea'` even though nothing in the script itself is wrong — this matches
   CLAUDE.md's own stated convention that every standalone script in this repository runs as
   `python -m sanocea.scripts.X` from the parent directory, and `deploy.sh` now follows it exactly.
   `health_check.py` has no such requirement (pure stdlib/`urllib`, no `sanocea` import) and is invoked by
   direct path in both `deploy.sh` and `rollback.sh`.

**A real, previously-undeclared dependency gap was also found and fixed during this testing**:
`pyproject.toml` was missing `python-multipart`, which FastAPI requires at import time the moment any
route declares a `File`/`UploadFile` parameter (this application's product-onboarding media-upload
routes do) — without it, the apparently-successful `import sanocea.apps.api.app` line itself raises
`RuntimeError: Form data requires "python-multipart" to be installed`, and the API never starts, on any
host, Windows or Linux. Added to `pyproject.toml`'s `[project.dependencies]`; re-verified end-to-end
after the fix (full real run below).
5. Switch the `sanocea`/`.venv` symlinks at `/opt/sanocea` to point at the new release (atomic, Part F).
   Migration happens implicitly the moment the new process starts (Part G) — there is no separate
   migration invocation.
6. `systemctl restart sanocea-api`.
7. **Run `scripts/health_check.py`** — bounded retry loop against `GET /health` (Part M).
8. Print a single PASS/FAIL line and exit `0`/`1` accordingly. On FAIL after the symlink switch, it prints
   the exact `scripts/rollback.sh` invocation the operator needs — it does not roll back automatically
   (Part O explains why automatic DB-aware rollback is not attempted).

No secret is ever passed as a command-line argument anywhere in this script — every secret-bearing value
is read from `sanocea.env` by the child process itself (`EnvironmentFile=` for the systemd-managed
process; `preflight_check.py` reads `os.environ` after the script sources the same file for its own
subprocess invocation). The script owns every wait internally (bounded, not manual/interactive) and exits
nonzero on any failure — no stage requires a human to watch and manually decide when to proceed.

## Part L — pre-flight validation

`scripts/preflight_check.py` (already created). Checks, in order, each reported individually (name +
pass/fail + non-secret detail, never a secret value):

1. Python version (`>=3.11`).
2. Required env vars present (`SANOCEA_PG_DSN`, `SANOCEA_CRED_MASTER_KEY_CURRENT`) and
   `SANOCEA_USE_IN_MEMORY_STORE` NOT set.
3. Master key format/version validity — via `build_production_credential_provider()` itself (P0.1's own
   fail-closed factory; this script does not reimplement that validation, it reuses it).
4. Postgres connectivity (`psycopg2.connect(..., connect_timeout=5)`).
5. Object storage config, if `SANOCEA_S3_BUCKET` is set (`S3ObjectStorage.health()`); skipped, not
   failed, if unset.
6. Temporal config — reports whether `SANOCEA_TEMPORAL_TARGET` is set; never fails on it either way
   (Part I).
7. Disk space at the candidate release path (≥500MB).
8. Release path exists and is writable.

Exits `1` naming every failing check if any REQUIRED check fails; `0` only if all pass. `scripts/
deploy.sh` calls this before step 5 (the symlink switch) — **failure here occurs before the active
release changes, by construction of the script's own ordering**, satisfying Part L/P's "failure must
occur before switching the active release wherever possible."

## Part M — post-deployment health verification

`scripts/health_check.py` (already created) — see its own docstring for the full APPLICATION /
INFRASTRUCTURE / CONNECTOR HEALTH distinction. In summary: polls `GET /health` on a bounded
interval/deadline; requires `api == "ok"` (APPLICATION HEALTH) and every *present* infra key to be
`"ok"` (INFRASTRUCTURE HEALTH: Postgres, and Temporal/object-storage only if configured at all). It never
queries, and never will query, per-merchant channel-connector credential state — **a missing Flipkart/
Amazon/Meesho merchant credential cannot fail this check**, because `/health` itself has no such notion
and this script does not add one.

## Part N — restart / reboot readiness

- `systemctl enable sanocea-api` (`WantedBy=multi-user.target`) makes the service start automatically on
  boot without any interactive shell or manually-exported environment variable — `EnvironmentFile=`
  supplies every variable the process needs, read by systemd itself before it execs the process.
- `systemctl restart sanocea-api` / `systemctl stop sanocea-api` exercise the same restart-on-failure and
  graceful-shutdown behavior documented in Part J.
- What this step can and cannot verify locally: the unit file's syntax and the restart-policy/graceful-
  shutdown *logic* are inspectable and match the pre-existing, already-in-repo recovery-worker unit's
  conventions exactly (Part A). **A real reboot of a real systemd host has not happened in this step —
  UNVERIFIED UNTIL P0.3**, which is explicitly the step assigned to prove this for real.

## Part O — controlled rollback procedure

`scripts/rollback.sh` (already created) — selects the previous release, re-points the symlinks, restarts
the service, and runs the same bounded health check.

- **How the previous release is selected**: `/opt/sanocea/releases/` directories are named by UTC
  deployment timestamp, so they sort lexicographically = chronologically. `scripts/rollback.sh` defaults
  to the second-most-recent release directory (the one before whatever `sanocea` currently symlinks to);
  an operator may instead pass an explicit release id to roll back further.
- **How services are restarted**: identical to deploy — re-point both symlinks atomically, `systemctl
  restart sanocea-api`.
- **How health is checked**: the same `scripts/health_check.py`, same PASS/FAIL semantics.
- **What happens if the release being rolled back FROM already ran a DB migration**: nothing automatic.
  `scripts/rollback.sh` never touches the database. Because `0001_phase05.sql` has so far only ever added
  tables/indexes (Part G), the older application code remains compatible with the already-migrated
  schema TODAY — but this script does not, and cannot, verify that in general. **This script does not
  promise automatic database rollback, and never will** — that is a explicit, permanent property of this
  procedure, not a gap it plans to close.
- **When rollback is unsafe**: if the migration that shipped with the release being rolled back away from
  was NOT purely additive (Part G's STOP condition) — in that case the operator must stop and assess
  schema/code compatibility manually before rolling the application back; `scripts/rollback.sh` has no
  way to detect this on its own today (no migration-version ledger exists) and this document does not
  claim otherwise.
- **How the operator identifies the last known-good release**: `ls -la /opt/sanocea/releases/` (sorted by
  name = chronological) plus `scripts/deploy.sh`'s own PASS/FAIL output from when each release was
  deployed (a deploy log — see Part R for what is/isn't captured today); a release that never reported
  a deploy-time `HEALTH CHECK PASSED` should not be treated as known-good.

## Part P — failure-class behavior

See Part R below for what was actually exercised locally versus what is UNVERIFIED UNTIL P0.3. Summary of
the intended (and, where marked, tested) behavior — every case below produces a nonzero exit and a
specific printed reason, never a silent success, and every case that occurs before step 5 of Part K
leaves the currently-active release symlinks untouched:

| Failure | Where it is caught | Active release affected? |
|---|---|---|
| Missing/invalid master key | `preflight_check.py` (`master_key_format`) | No |
| Missing `SANOCEA_PG_DSN` / invalid config | `preflight_check.py` (`required_env_vars`) | No |
| Postgres unavailable | `preflight_check.py` (`postgres_connectivity`) | No |
| Temporal unavailable | Never fails anything (Part I) — reported informationally only | N/A |
| Object storage unavailable (when configured) | `preflight_check.py` (`object_storage_config`) | No |
| `sanocea.env` missing / wrong permissions | `deploy.sh` step 2 | No |
| Dependency install failure (`pip install -e`) | `deploy.sh` step 3, before preflight even runs | No |
| Migration failure | Manifests as the new process failing to start → `health_check.py` timeout AFTER the symlink switch (Part G explains why this one case cannot be caught pre-switch: migration only runs as part of process startup, and process startup only happens against the real release layout) | **Yes — this is the one documented exception; recovery is `scripts/rollback.sh`, not an automatic revert** |
| API fails to start for any other reason | `health_check.py` timeout after `systemctl restart` | Yes — same recovery path |
| Health check timeout | `health_check.py` exits 1, `deploy.sh` reports FAIL and prints the rollback command | Yes — same recovery path |

## Part Q — files produced by this step

- `docs/operations/production-deployment.md` (this file)
- `docs/operations/production-configuration.md`
- `infra/systemd/sanocea-api.service.example`
- `scripts/deploy.sh`
- `scripts/rollback.sh`
- `scripts/preflight_check.py`
- `scripts/health_check.py`

No `deploy/systemd/*` or `compose.production.yml` was created — Docker Compose was rejected in Part B,
and this repository's existing convention is `infra/systemd/`, not `deploy/systemd/`, so that convention
is followed rather than introducing a new one.
