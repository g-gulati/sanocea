$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Local = Join-Path $Root ".local"
$Bin = Join-Path $Local "bin"
$Logs = Join-Path $Local "logs"
$PgData = Join-Path $Local "postgres-data"
$MinioData = Join-Path $Local "minio-data"
$TemporalData = Join-Path $Local "temporal"

New-Item -ItemType Directory -Force $Bin, $Logs, $MinioData, $TemporalData | Out-Null

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
  Copy-Item (Join-Path $Root ".env.example") $envFile
}

$pgBin = "C:\Program Files\PostgreSQL\17\bin"
$initdb = Join-Path $pgBin "initdb.exe"
$pgCtl = Join-Path $pgBin "pg_ctl.exe"
$createdb = Join-Path $pgBin "createdb.exe"
$psql = Join-Path $pgBin "psql.exe"

if (-not (Test-Path $initdb)) {
  throw "PostgreSQL initdb.exe not found at $initdb"
}

& (Join-Path $pgBin "pg_isready.exe") -h 127.0.0.1 -p 55432 -U sanocea 2>$null | Out-Null
$pgIsReady = ($LASTEXITCODE -eq 0)
if (-not (Test-Path $PgData)) {
  & $initdb -D $PgData -U sanocea --auth=trust --encoding=UTF8
}

if (-not $pgIsReady) {
  & $pgCtl -D $PgData -l (Join-Path $Logs "postgres.log") -o "-p 55432 -h 127.0.0.1" start
}

try {
  & $createdb -h 127.0.0.1 -p 55432 -U sanocea sanocea_phase05 2>$null
} catch {
  # Database may already exist.
}

$minioExe = Join-Path $Bin "minio.exe"
if (-not (Test-Path $minioExe)) {
  curl.exe -L -o $minioExe "https://dl.min.io/server/minio/release/windows-amd64/minio.exe"
}

$env:MINIO_ROOT_USER = "sanocea-dev"
$env:MINIO_ROOT_PASSWORD = "sanocea-dev-secret"
if (-not (Get-Process minio -ErrorAction SilentlyContinue)) {
  # NOTE (multi-platform connector hardening, closure item 3): Start-Process -ArgumentList joins array
  # elements into a single command-line string WITHOUT quoting elements that contain spaces (unlike
  # System.Diagnostics.ProcessStartInfo.ArgumentList, which does). $MinioData lives under a path
  # containing spaces ("...E-Commerce ERP\sanocea\..."), so the unquoted array element used to get
  # word-split by MinIO's own argv parsing into multiple positional directory arguments - which MinIO
  # interprets as a DISTRIBUTED multi-node deployment, not a single local drive. That wedged the server
  # indefinitely in "Waiting for all other servers to be online" and silently created stray
  # .minio.sys-bearing directories at each split path fragment (relative to whatever the process's cwd
  # happened to be). Fixed by explicitly double-quoting the path so it survives as one token.
  Start-Process -FilePath $minioExe `
    -ArgumentList @("server", "`"$MinioData`"", "--address", "127.0.0.1:59000", "--console-address", "127.0.0.1:59001") `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Logs "minio.out.log") `
    -RedirectStandardError (Join-Path $Logs "minio.err.log")
}

$temporalZip = Join-Path $Bin "temporal.zip"
$temporalDir = Join-Path $Bin "temporal"
$temporalExe = Join-Path $temporalDir "temporal.exe"
if (-not (Test-Path $temporalExe)) {
  curl.exe -L -o $temporalZip "https://temporal.download/cli/archive/latest?platform=windows&arch=amd64"
  New-Item -ItemType Directory -Force $temporalDir | Out-Null
  tar.exe -xf $temporalZip -C $temporalDir
  $found = Get-ChildItem -Path $temporalDir -Recurse -Filter "temporal.exe" | Select-Object -First 1
  if (-not $found) {
    throw "temporal.exe not found after extracting $temporalZip"
  }
  if ($found.FullName -ne $temporalExe) {
    Copy-Item $found.FullName $temporalExe
  }
}

$temporalDb = Join-Path $TemporalData "temporal.db"
if (-not (Get-Process temporal -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath $temporalExe `
    -ArgumentList "server start-dev --ip 127.0.0.1 --port 57233 --db-filename `"$temporalDb`"" `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Logs "temporal.out.log") `
    -RedirectStandardError (Join-Path $Logs "temporal.err.log")
}

Write-Host "Local Phase 0.5 services requested."
Write-Host "Postgres: postgresql://sanocea@127.0.0.1:55432/sanocea_phase05"
Write-Host "Temporal: 127.0.0.1:57233"
Write-Host "MinIO: http://127.0.0.1:59000"
