$ErrorActionPreference = "Stop"

$psql = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
$seed = Join-Path $PSScriptRoot "..\sql\seed_auto_check_test.postgres.sql"
$perf = Join-Path $PSScriptRoot "..\sql\append_perf_test_data.postgres.sql"

if (-not (Test-Path $psql)) {
  throw "psql not found: $psql"
}

$env:PGPASSWORD = "postgres"

& $psql -h 127.0.0.1 -p 5432 -U postgres -d auto_check_test -f $seed
& $psql -h 127.0.0.1 -p 5432 -U postgres -d auto_check_test -f $perf
