$ErrorActionPreference = "Stop"

$psql = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
$scenario = Join-Path $PSScriptRoot "..\sql\append_20260520_scenario_data.postgres.sql"

if (-not (Test-Path $psql)) {
  throw "psql not found: $psql"
}

if (-not (Test-Path $scenario)) {
  throw "Scenario SQL not found: $scenario"
}

$env:PGPASSWORD = "postgres"

& $psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -p 5432 -U postgres -d auto_check_test -f $scenario
