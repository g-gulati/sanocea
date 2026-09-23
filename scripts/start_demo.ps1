# SANOCEA Demo Engine Starter - Premium Basket rehearsal / live demo
# One script to bring up every real piece the Shopify order-loop + WhatsApp demo needs:
# Postgres -> Docker Desktop -> WAHA (WhatsApp) container -> ngrok tunnel -> API server ->
# re-sync the real Shopify webhooks + WhatsApp session contact against whatever fresh ngrok
# URL this run got (ngrok's free-tier URL is different every time the tunnel restarts - the
# single biggest thing that silently breaks this demo between sessions).
#
# Real bug found during two live cold-start tests (fixed here): port 55432 can end up in a
# state where postgres.exe specifically fails to bind it ("Permission denied" on both ::1 and
# 127.0.0.1), even though the port is confirmed free by other tools (a plain .NET TcpListener
# binds it fine) and even after a full `wsl --shutdown`. Reordering Postgres before Docker did
# NOT fix it - this is a sticky, Windows/Docker-networking-driver-level reservation on this one
# port, not a simple startup race. The reliable fix is to not depend on 55432 being free: if the
# configured port fails with exactly this error, fall back to a known-good alternate port and
# use THAT port for the rest of this script (API server, sync script) instead - confined to this
# script's own run, never touching any other script's hardcoded default.
#
# Safe to run repeatedly: every step first checks whether that piece is already up and only
# starts what's actually missing.

$ErrorActionPreference = "Continue"
$RepoRoot = "D:\Autonomous E-Commerce ERP"
$SanoceaRoot = "$RepoRoot\sanocea"
$PgBin = "C:\Program Files\PostgreSQL\17\bin"
$PgData = "$SanoceaRoot\.local\postgres-data"

function Write-Step($msg) { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "  $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "  $msg" -ForegroundColor Red }

# Real bug found during live cold-start testing (fixed here): `docker info`/`docker inspect` issued
# while Docker Desktop's backend is still initializing can hang indefinitely on Windows instead of
# erroring out - there is no built-in timeout, so a plain `docker info` call inside the old wait loop
# could block the ENTIRE script forever, well past the loop's intended 90s budget (the budget only
# covered Start-Sleep time between calls, not a hung call itself). Two real runs got stuck this way
# simultaneously during testing.
#
# First fix attempt used Start-Job for the timeout, which turned out to be its own real bug: Start-Job
# spins up a whole new PowerShell host process per call, and under this script's actual invocation
# context (cmd.exe -> powershell -NoProfile -ExecutionPolicy Bypass -File ...) that reliably stalled
# the WHOLE script for 60-90+ seconds with zero visible progress - confirmed live via a clean cold-start
# test. Second fix attempt used .NET Process + pipe redirection, which deadlocks the moment `docker
# info`'s output fills the OS pipe buffer (nothing was draining the redirected stream) - also confirmed
# live (both calls hung to their exact timeout ceiling). The version below - cmd.exe file-redirection +
# Process.WaitForExit(ms) - avoids both: no PowerShell job/runspace overhead, and file-based redirection
# doesn't have the pipe-buffer-deadlock class of bug. Verified standalone under a cold
# -NoProfile -ExecutionPolicy Bypass invocation (matching this script's real launch path): fast
# real-command exits (~300-500ms) and correctly kills+returns at the deadline for a genuinely hung
# command. Every docker CLI call in this script goes through this wrapper.
function Invoke-WithTimeout {
    param([string]$CmdLine, [int]$TimeoutMs = 8000)
    $outFile = [System.IO.Path]::GetTempFileName()
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = "cmd.exe"
        $psi.Arguments = "/c $CmdLine > `"$outFile`" 2>&1"
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        if (-not $proc.WaitForExit($TimeoutMs)) {
            try { $proc.Kill() } catch {}
            return @{ ExitCode = -1; Output = "" }
        }
        return @{ ExitCode = $proc.ExitCode; Output = (Get-Content $outFile -Raw -ErrorAction SilentlyContinue) }
    } finally {
        Remove-Item $outFile -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "=== SANOCEA Demo Engine ===" -ForegroundColor Cyan
Write-Host ""

# 1. Postgres (native, non-Docker)
Write-Step "[1/6] Postgres"
# ROOT CAUSE of the recurring "stuck at step 1" hang (found after several wrong theories - Docker, Start-Job):
# `pg_ctl start *> $null` makes PowerShell wait for the redirected output pipe to CLOSE, but the long-lived
# postgres.exe that pg_ctl spawns inherits that pipe and never closes it - so the script blocked forever
# right after Postgres had already started fine. Fixed by launching pg_ctl with Start-Process (no pipes at
# all, detached), never redirecting a command that spawns a daemon, and polling pg_isready ourselves.
#
# Also: port 55432 intermittently refuses postgres.exe ("Permission denied", a Windows/Docker network-driver
# reservation), so 55199 is now the PRIMARY port - no doomed first attempt, no fallback dance. 55432 is only
# honoured if something is already listening there.
$PgPort = 55199

function Test-PgReady($port) {
    & "$PgBin\pg_isready.exe" -h 127.0.0.1 -p $port *> $null
    return ($LASTEXITCODE -eq 0)
}

function Start-PgAndWait($port, $timeoutSec) {
    $pgArgs = @("-D", "`"$PgData`"", "-l", "`"$PgData\startup.log`"", "-W", "-o", "`"-p $port`"", "start")
    $p = Start-Process -FilePath "$PgBin\pg_ctl.exe" -ArgumentList $pgArgs -WindowStyle Hidden -PassThru
    $null = $p.WaitForExit(20000)
    # Right after a reboot Postgres can take 30-40s (crash recovery + antivirus scanning the data dir), so
    # poll patiently instead of assuming a fixed sleep is enough. Give up early only if the postmaster died.
    $elapsed = 0; $gone = 0
    while ($elapsed -lt $timeoutSec) {
        if (Test-PgReady $port) { return $true }
        Start-Sleep -Seconds 2; $elapsed += 2
        if ($elapsed -ge 6 -and -not (Test-Path "$PgData\postmaster.pid")) { $gone++ } else { $gone = 0 }
        if ($gone -ge 2) { return $false }
    }
    return $false
}

$pgUp = Test-PgReady $PgPort
if (-not $pgUp -and (Test-PgReady 55432)) { $PgPort = 55432; $pgUp = $true }
if ($pgUp) {
    Write-Ok "Postgres already running on port $PgPort."
} else {
    Write-Warn "Starting Postgres on port $PgPort (can take up to ~40s right after a reboot)..."
    $pgUp = Start-PgAndWait $PgPort 90
    if (-not $pgUp) {
        Write-Warn "First attempt didn't come up, retrying once..."
        $pgUp = Start-PgAndWait $PgPort 60
    }
}
if ($pgUp) { Write-Ok "Postgres is ready on port $PgPort." } else { Write-Err "Postgres did not come up - check $PgData\startup.log." }
$PgDsn = "postgresql://sanocea:sanocea@127.0.0.1:$PgPort/sanocea_phase05"

# 2. Docker Desktop (needed for the WAHA WhatsApp container)
Write-Step "[2/6] Docker Desktop"
$dockerUp = ((Invoke-WithTimeout -CmdLine "docker info" -TimeoutMs 8000).ExitCode -eq 0)
if (-not $dockerUp) {
    Write-Warn "Starting Docker Desktop (this can take ~30-60s)..."
    $dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) { Start-Process $dockerExe }
    $waited = 0
    while (-not $dockerUp -and $waited -lt 90) {
        Start-Sleep -Seconds 3; $waited += 3
        $dockerUp = ((Invoke-WithTimeout -CmdLine "docker info" -TimeoutMs 8000).ExitCode -eq 0)
    }
}
if ($dockerUp) { Write-Ok "Docker is running." } else { Write-Err "Docker did not start - WhatsApp will not work until it's up." }

# 3. WAHA (WhatsApp) container
Write-Step "[3/6] WAHA (WhatsApp) container"
$WahaApiKey = "sanocea-demo-local-only-key-not-for-production"
$WahaHeaders = @{ "X-Api-Key" = $WahaApiKey }
if ($dockerUp) {
    $wahaStatus = (Invoke-WithTimeout -CmdLine 'docker inspect sanocea-waha-demo --format="{{.State.Status}}"' -TimeoutMs 8000).Output
    if ($wahaStatus) { $wahaStatus = $wahaStatus.Trim() }
    if ($wahaStatus -ne "running") {
        Invoke-WithTimeout -CmdLine "docker start sanocea-waha-demo" -TimeoutMs 10000 | Out-Null
        Start-Sleep -Seconds 5
    }
    Write-Ok "WAHA container running."
    # Real gap found live: the container being "running" only means the WAHA server process is up - it
    # says nothing about whether the actual WhatsApp session INSIDE it is still connected. A real run
    # showed the container healthy for hours while the session itself had silently dropped to FAILED
    # (a normal WhatsApp Web disconnect, not a container crash), leaving inbound messages completely
    # undelivered with zero trace anywhere - a demo-day-shaped failure. Checked and self-healed here via
    # WAHA's own session API rather than trusting Docker's container-level status alone.
    $sessionStatus = $null
    try { $sessionStatus = (Invoke-RestMethod -Uri "http://127.0.0.1:3000/api/sessions/default" -Headers $WahaHeaders -TimeoutSec 8).status } catch {}
    if ($sessionStatus -ne "WORKING") {
        Write-Warn "WhatsApp session is '$sessionStatus', not WORKING - restarting it..."
        try { Invoke-RestMethod -Uri "http://127.0.0.1:3000/api/sessions/default/restart" -Method Post -Headers $WahaHeaders -TimeoutSec 10 | Out-Null } catch {}
        $waited = 0
        while ($sessionStatus -ne "WORKING" -and $waited -lt 30) {
            Start-Sleep -Seconds 3; $waited += 3
            try { $sessionStatus = (Invoke-RestMethod -Uri "http://127.0.0.1:3000/api/sessions/default" -Headers $WahaHeaders -TimeoutSec 8).status } catch {}
        }
    }
    if ($sessionStatus -eq "WORKING") { Write-Ok "WhatsApp session is WORKING." } else { Write-Err "WhatsApp session is '$sessionStatus', not WORKING - it likely needs a fresh QR scan (open http://127.0.0.1:3000)." }
} else {
    Write-Warn "Skipped - Docker not available."
}

# 4. ngrok tunnel (public HTTPS URL for real Shopify webhook delivery)
Write-Step "[4/6] ngrok tunnel"
$ngrokUrl = $null
try {
    $tunnels = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 3
    $ngrokUrl = ($tunnels.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1).public_url
} catch {}
if (-not $ngrokUrl) {
    Write-Warn "Starting ngrok..."
    Start-Process -WindowStyle Minimized ngrok -ArgumentList "http 8080 --log=stdout"
    $waited = 0
    while (-not $ngrokUrl -and $waited -lt 30) {
        Start-Sleep -Seconds 2; $waited += 2
        try {
            $tunnels = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 3
            $ngrokUrl = ($tunnels.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1).public_url
        } catch {}
    }
}
if ($ngrokUrl) { Write-Ok "Tunnel: $ngrokUrl" } else { Write-Err "ngrok did not start - real Shopify orders will not reach SANOCEA." }

# 5. API server
Write-Step "[5/6] SANOCEA API server"
$apiUp = $false
try { Invoke-RestMethod -Uri "http://127.0.0.1:8080/health" -TimeoutSec 2 | Out-Null; $apiUp = $true } catch {}
if (-not $apiUp) {
    Write-Warn "Starting API server..."
    $env:SANOCEA_PG_DSN = $PgDsn
    $env:SANOCEA_CRED_MASTER_KEY_CURRENT = "v1"
    $env:SANOCEA_CRED_MASTER_KEY_V1 = "KioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKio="
    $env:SANOCEA_WAHA_BASE_URL = "http://127.0.0.1:3000"
    $env:SANOCEA_WAHA_API_KEY = "sanocea-demo-local-only-key-not-for-production"
    $env:SANOCEA_DEMO_TRUSTED_SENDERS = "manpreet.gulati.2000@gmail.com"
    # AI fill for missing description/tags (via the local `agy` CLI). Set to "0" to turn it off - it only
    # ever triggers when a product is missing those two fields, and falls back to asking over WhatsApp.
    $env:SANOCEA_ENABLE_AI_ENRICHMENT = "1"
    Start-Process -WindowStyle Minimized powershell -ArgumentList "-NoExit", "-Command", "cd '$RepoRoot'; python -m uvicorn sanocea.apps.api.app:app --host 0.0.0.0 --port 8080"
    $waited = 0
    while (-not $apiUp -and $waited -lt 30) {
        Start-Sleep -Seconds 2; $waited += 2
        try { Invoke-RestMethod -Uri "http://127.0.0.1:8080/health" -TimeoutSec 2 | Out-Null; $apiUp = $true } catch {}
    }
}
if ($apiUp) { Write-Ok "API server is healthy." } else { Write-Err "API server did not start - check the minimized PowerShell window it opened for the real error." }

# 5.5  Mock Tally ERP server (Shopify -> Tally demo)
Write-Step "[5.5/6] Mock Tally ERP server (Shopify -> Tally demo)"
$tallyUp = $false
try { Invoke-RestMethod -Uri "http://127.0.0.1:9000/" -TimeoutSec 2 | Out-Null; $tallyUp = $true } catch {}
if (-not $tallyUp) {
    Start-Process -WindowStyle Minimized python -ArgumentList "-X", "utf8", "$SanoceaRoot\scripts\mock_tally_server.py"
    Start-Sleep -Seconds 2
    try { Invoke-RestMethod -Uri "http://127.0.0.1:9000/" -TimeoutSec 3 | Out-Null; $tallyUp = $true } catch {}
}
if ($tallyUp) { Write-Ok "Mock Tally server running at http://127.0.0.1:9000/" } else { Write-Warn "Mock Tally server did not start - run manually: python scripts/mock_tally_server.py" }

# 6. Sync real Shopify webhooks + WhatsApp session contact to THIS run's tunnel URL
Write-Step "[6/6] Syncing Shopify webhooks + WhatsApp contact to the live tunnel"
if ($apiUp -and $ngrokUrl) {
    $env:SANOCEA_PG_DSN = $PgDsn
    $env:SANOCEA_CRED_MASTER_KEY_CURRENT = "v1"
    $env:SANOCEA_CRED_MASTER_KEY_V1 = "KioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKio="
    $env:SANOCEA_WAHA_BASE_URL = "http://127.0.0.1:3000"
    $env:SANOCEA_WAHA_API_KEY = "sanocea-demo-local-only-key-not-for-production"
    python "$SanoceaRoot\scripts\sync_demo_endpoints.py" $ngrokUrl
} else {
    Write-Warn "Skipped - API server or ngrok not up."
}

Write-Host ""
Write-Host "=== READY ===" -ForegroundColor Cyan
Write-Host "Command Center:  http://127.0.0.1:8080/ui"
Write-Host "Tally Dashboard: http://127.0.0.1:9000/   (Shopify -> Tally live vouchers)"
Write-Host "Public tunnel:   $ngrokUrl"
Write-Host "Storefront:      https://sanocea-commerce-os-dev.myshopify.com  (password: sanocea)"
Write-Host "Postgres port:   $PgPort"
Write-Host ""
Write-Host "Tally demo trigger:"
Write-Host "  python -X utf8 scripts/demo_shopify_to_tally.py --product makhana"
Write-Host "  python -X utf8 scripts/demo_shopify_to_tally.py --product dates"
Write-Host "  python -X utf8 scripts/demo_shopify_to_tally.py --product nuts"
# Open Command Center automatically (only when the API is actually up - otherwise it would just show an error page).
if ($apiUp) { try { Start-Process "http://127.0.0.1:8080/ui" } catch {} }
if ($tallyUp) { try { Start-Process "http://127.0.0.1:9000/" } catch {} }
Write-Host ""
Write-Host "Everything above keeps running in its own window after you close this one."
Write-Host ""
Write-Host "Press any key to close this window..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
