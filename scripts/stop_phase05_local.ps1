$ErrorActionPreference = "Continue"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Local = Join-Path $Root ".local"
$PgData = Join-Path $Local "postgres-data"
$pgCtl = "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe"

Get-Process minio -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process temporal -ErrorAction SilentlyContinue | Stop-Process -Force

if ((Test-Path $pgCtl) -and (Test-Path $PgData)) {
  & $pgCtl -D $PgData stop -m fast
}

Write-Host "Local Phase 0.5 services stopped."

