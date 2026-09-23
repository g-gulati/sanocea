$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $env:SANOCEA_PG_DSN) {
  $env:SANOCEA_PG_DSN = "postgresql://sanocea@127.0.0.1:55432/sanocea_phase05"
}
$env:SANOCEA_TEMPORAL_TARGET = "127.0.0.1:57233"
$env:SANOCEA_RUN_TEMPORAL_TESTS = "1"
$env:SANOCEA_S3_ENDPOINT = "http://127.0.0.1:59000"
$env:SANOCEA_S3_ACCESS_KEY = "sanocea-dev"
$env:SANOCEA_S3_SECRET_KEY = "sanocea-dev-secret"
$env:SANOCEA_S3_BUCKET = "sanocea-phase05"

$Diagnostics = Join-Path $Root "tests\fixtures\phase11_merchant\generated\integration_bounded_diagnostics.json"
python -m sanocea.scripts.run_pytest_bounded --timeout-seconds 420 --diagnostics-path $Diagnostics -- (Join-Path $Root "tests\integration") -q --durations=10
exit $LASTEXITCODE
