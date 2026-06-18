$ErrorActionPreference = "Stop"

$psql = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
$scenario = Join-Path $PSScriptRoot "..\sql\append_20260614_16_reconcile_scenarios.postgres.sql"

if (-not (Test-Path $psql)) {
  throw "psql not found: $psql"
}

if (-not (Test-Path $scenario)) {
  throw "Scenario SQL not found: $scenario"
}

$env:PGPASSWORD = "postgres"

Write-Host "Loading local PostgreSQL auto-check scenario data for 2026-06-14 ~ 2026-06-16..."
& $psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -p 5432 -U postgres -d auto_check_test -f $scenario
if ($LASTEXITCODE -ne 0) {
  throw "psql failed with exit code $LASTEXITCODE"
}
Write-Host "Local PostgreSQL auto-check scenario data for 2026-06-14 ~ 2026-06-16 has been loaded."
