# Deploy plan: SEO Opportunity UI (worker + API bridge + website) — prepared 2026-10-01, NOT executed

Three production pieces must ship together; order below. Nothing has been run.

## Facts established (read-only)
- **Worker** (`sanocea-seo-worker.service`) runs `/opt/sanocea/repo/packages/seo-stack/dist/src/worker/workerDaemon.js` straight from the repo (no release dir). `dist/` already holds the NEW build; the running process (started 12:08) still has the OLD code in memory, so `systemctl restart` is the deploy. DB: `data/seo_monitoring.sqlite`; all schema changes are additive `CREATE TABLE IF NOT EXISTS`.
- **API** runs from `/opt/sanocea/sanocea` -> `releases/<id>/sanocea` (`scripts/deploy.sh`). The UI needs the bridge's new `opportunities` view, so the API MUST be redeployed or the new section stays empty.
- **Website** is static files from `/var/www/sanocea/current` -> `releases/<id>` (`scripts/deploy_website.sh`). A fresh build differs from live only in `assets/main-*.js`, `demo.html`, `whatsapp-demo.html` (the SEO bundle), so no unrelated website work ships.
- **`scripts/deploy.sh` rsyncs the whole working tree** (excluding .git/.venv/caches), i.e. ~220 uncommitted changes from other work in progress ship with it. Decide before running (see Decisions).
- Free disk 32 GB (floor 20 GB). Control endpoints stay **disabled** (no `SEO_WORKER_CONTROL_TOKEN` in the unit): no approval/transition is possible in production.

## Decisions needed before executing
1. Commit the intended work first (recommended: gives `git revert` as rollback and a clean record), or ship the working tree as-is.
2. Move `gmail_credentials.json` and `gmail_outreach_token.pickle` out of the repo root before `deploy.sh`: rsync would copy them into the release directory.

## Steps (in order)
1. **Backup DB** (WAL-safe): `sqlite3 packages/seo-stack/data/seo_monitoring.sqlite ".backup 'packages/seo-stack/data/backups/pre-opportunity-$(date -u +%Y%m%dT%H%M%S).sqlite'"`
2. **Build check**: `cd packages/seo-stack && npm test` (expect 210 pass).
3. **Worker**: `sudo systemctl restart sanocea-seo-worker` (never `pkill node`). Verify: `curl -s 127.0.0.1:8089/health` healthy; `/opportunities` returns `{count:0,...}` (not 404); then once `curl -s 127.0.0.1:8089/sync-rankcommand >/dev/null` (runs agents; refreshes opportunities). Expect 4 technical opportunities; the Google index item appears when the daily `gsc-position` job next runs (~15:31 UTC) and `/google-search-state` shows CONNECTED.
   Until step 3 completes the new section would say "nothing to review", so do not skip ahead.
4. **API**: after Decisions 1-2, `scripts/deploy.sh` (bounded; preflight + health check; leaves the old release active on failure). Verify a leased demo session's `GET /demo/seo/overview` contains `opportunities` and `gsc_property`, and has no `dbPath`, `.sqlite`, `/opt/`, `/etc/`, credential strings.
5. **Website**: `scripts/deploy_website.sh` (prints the rollback target). Verify the live bundle contains "things need attention", then browser QA on production at 1280 px and 390 px (real session, no request interception): 5 sections intact, real rows, no priority words, `/ui` and `/console.html` 404.

## Rollback (each piece independent)
- **Website**: `ln -sfn /var/www/sanocea/releases/2026-10-01T08-10-45Z /var/www/sanocea/current.tmp && mv -T /var/www/sanocea/current.tmp /var/www/sanocea/current` (previous release; no nginx reload needed).
- **API**: `scripts/rollback.sh` (re-points `/opt/sanocea/sanocea` and `.venv` to the previous release and restarts `sanocea-api`).
- **Worker**: prebuilt previous build (commit cd1c435) is saved at `/opt/sanocea/shared/rollback/seo-stack-dist-cd1c435/dist`. Roll back with: `cd /opt/sanocea/repo/packages/seo-stack && mv dist dist.new && cp -a /opt/sanocea/shared/rollback/seo-stack-dist-cd1c435/dist dist && sudo systemctl restart sanocea-seo-worker`. The new tables/rows are ignored by the old build (additive); restore the step-1 backup only if the DB itself is suspect.
- The new UI degrades safely: if the `opportunities` view is missing the section shows only the existing items.
