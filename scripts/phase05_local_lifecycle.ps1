param(
  [Parameter(Mandatory=$true)]
  [ValidateSet("start", "status", "stop", "restart", "cleanup-stale", "integration-test")]
  [string]$Command
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Local = Join-Path $Root ".local"
$Bin = Join-Path $Local "bin"
$Logs = Join-Path $Local "logs"
$Pids = Join-Path $Local "pids"
$PgBin = "C:\Program Files\PostgreSQL\17\bin"
$PgPort = if ($env:SANOCEA_PG_PORT) { $env:SANOCEA_PG_PORT } else { "55433" }
$TemporalPort = if ($env:SANOCEA_TEMPORAL_PORT) { $env:SANOCEA_TEMPORAL_PORT } else { "57233" }
$MinioPort = if ($env:SANOCEA_MINIO_PORT) { $env:SANOCEA_MINIO_PORT } else { "59000" }
$MinioConsolePort = ([int]$MinioPort + 1).ToString()
$PgData = if ($env:SANOCEA_PG_DATA) { $env:SANOCEA_PG_DATA } else { Join-Path $Local "postgres-$PgPort-data" }
$MinioData = if ($env:SANOCEA_MINIO_DATA) { $env:SANOCEA_MINIO_DATA } else { Join-Path $Local "minio-$MinioPort-data" }
$TemporalData = if ($env:SANOCEA_TEMPORAL_DATA) { $env:SANOCEA_TEMPORAL_DATA } else { Join-Path $Local "temporal-$TemporalPort" }

New-Item -ItemType Directory -Force $Bin, $Logs, $Pids, $MinioData, $TemporalData | Out-Null

function Write-Pid($name, $ProcessId) {
  Set-Content -LiteralPath (Join-Path $Pids "$name-$PgPort-$TemporalPort-$MinioPort.pid") -Value "$ProcessId" -Encoding ASCII
}

function Read-Pid($name) {
  $path = Join-Path $Pids "$name-$PgPort-$TemporalPort-$MinioPort.pid"
  if (Test-Path $path) { return [int](Get-Content -Raw -LiteralPath $path) }
  return $null
}

function Test-Pid($ProcessId) {
  if (-not $ProcessId) { return $false }
  return [bool](Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Stop-Owned($name) {
  $ProcessId = Read-Pid $name
  if ($name -eq "postgres" -and (Test-Path (Join-Path $PgBin "pg_ctl.exe")) -and (Test-Path $PgData)) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & (Join-Path $PgBin "pg_ctl.exe") -D $PgData stop -m fast -w 2>$null | Out-Null
    $ErrorActionPreference = $old
    Start-Sleep -Seconds 2
  }
  if (Test-Pid $ProcessId) {
    Stop-Process -Id $ProcessId -Force -ErrorAction Stop
  }
  Remove-Item -LiteralPath (Join-Path $Pids "$name-$PgPort-$TemporalPort-$MinioPort.pid") -Force -ErrorAction SilentlyContinue
}

function Pg-Ready {
  & (Join-Path $PgBin "pg_isready.exe") -h 127.0.0.1 -p $PgPort -U sanocea 2>$null | Out-Null
  return ($LASTEXITCODE -eq 0)
}

function Temporal-Ready {
  $exe = Join-Path $Bin "temporal\temporal.exe"
  if (-not (Test-Path $exe)) { return $false }
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & $exe operator cluster health --address "127.0.0.1:$TemporalPort" 2>$null | Out-Null
  $ErrorActionPreference = $old
  return ($LASTEXITCODE -eq 0)
}

function Minio-Ready {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$MinioPort/minio/health/live" -TimeoutSec 3
    return ($r.StatusCode -eq 200)
  } catch {
    return $false
  }
}

function Start-Postgres {
  if (-not (Test-Path (Join-Path $PgBin "initdb.exe"))) { throw "PostgreSQL 17 binaries not found at $PgBin" }
  if (-not (Test-Path $PgData)) {
    & (Join-Path $PgBin "initdb.exe") -D $PgData -U sanocea --auth=trust --encoding=UTF8 | Out-Host
  }
  if (-not (Pg-Ready)) {
    $args = '-D "' + $PgData + '" -p ' + $PgPort + ' -h 127.0.0.1'
    $p = Start-Process -FilePath (Join-Path $PgBin "postgres.exe") -ArgumentList $args -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $Logs "postgres-owned.out.log") -RedirectStandardError (Join-Path $Logs "postgres-owned.err.log")
    Write-Pid "postgres" $p.Id
    Start-Sleep -Seconds 4
  }
  if (-not (Pg-Ready)) { throw "Postgres did not become healthy on 127.0.0.1:$PgPort" }
  & (Join-Path $PgBin "createdb.exe") -h 127.0.0.1 -p $PgPort -U sanocea sanocea_phase21 2>$null
}

function Start-Minio {
  $exe = Join-Path $Bin "minio.exe"
  if (-not (Test-Path $exe)) { throw "MinIO binary missing at $exe; run start_phase05_local.ps1 once to download it" }
  if (-not (Minio-Ready)) {
    $env:MINIO_ROOT_USER = "sanocea-dev"
    $env:MINIO_ROOT_PASSWORD = "sanocea-dev-secret"
    $p = Start-Process -FilePath $exe -ArgumentList @("server", $MinioData, "--address", "127.0.0.1:$MinioPort", "--console-address", "127.0.0.1:$MinioConsolePort") -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $Logs "minio-owned.out.log") -RedirectStandardError (Join-Path $Logs "minio-owned.err.log")
    Write-Pid "minio" $p.Id
    Start-Sleep -Seconds 3
  }
  if (-not (Minio-Ready)) { throw "MinIO did not become healthy on 127.0.0.1:$MinioPort" }
}

function Start-Temporal {
  $exe = Join-Path $Bin "temporal\temporal.exe"
  if (-not (Test-Path $exe)) { throw "Temporal binary missing at $exe; run start_phase05_local.ps1 once to download it" }
  if (-not (Temporal-Ready)) {
    $db = Join-Path $TemporalData "temporal.db"
    $p = Start-Process -FilePath $exe -ArgumentList "server start-dev --ip 127.0.0.1 --port $TemporalPort --db-filename `"$db`"" -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $Logs "temporal-owned.out.log") -RedirectStandardError (Join-Path $Logs "temporal-owned.err.log")
    Write-Pid "temporal" $p.Id
    Start-Sleep -Seconds 5
  }
  if (-not (Temporal-Ready)) { throw "Temporal did not become healthy on 127.0.0.1:$TemporalPort" }
}

function Status {
  [ordered]@{
    postgres = if (Pg-Ready) { "healthy" } else { "down" }
    temporal = if (Temporal-Ready) { "healthy" } else { "down" }
    minio = if (Minio-Ready) { "healthy" } else { "down" }
    postgres_pid = Read-Pid "postgres"
    temporal_pid = Read-Pid "temporal"
    minio_pid = Read-Pid "minio"
  } | ConvertTo-Json
}

if ($Command -eq "start") {
  Start-Postgres
  Start-Minio
  Start-Temporal
  Status
} elseif ($Command -eq "status") {
  Status
} elseif ($Command -eq "stop") {
  Stop-Owned "temporal"
  Stop-Owned "minio"
  Stop-Owned "postgres"
  Status
} elseif ($Command -eq "restart") {
  & $PSCommandPath stop | Out-Host
  & $PSCommandPath start | Out-Host
} elseif ($Command -eq "cleanup-stale") {
  foreach ($name in @("postgres", "temporal", "minio")) {
    $ProcessId = Read-Pid $name
    if ($ProcessId -and -not (Test-Pid $ProcessId)) {
      Remove-Item -LiteralPath (Join-Path $Pids "$name-$PgPort-$TemporalPort-$MinioPort.pid") -Force -ErrorAction SilentlyContinue
    }
  }
  Status
} elseif ($Command -eq "integration-test") {
  $env:SANOCEA_PG_DSN = "postgresql://sanocea@127.0.0.1:$PgPort/sanocea_phase21"
  & (Join-Path $PSScriptRoot "run_phase05_integration.ps1")
  exit $LASTEXITCODE
}
