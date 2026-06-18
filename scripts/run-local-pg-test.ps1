$ErrorActionPreference = "Stop"

$exe = Join-Path $PSScriptRoot "..\dist\auto-check.exe"
$config = Join-Path $PSScriptRoot "..\config\local-pg-test-config.json"

if (-not (Test-Path $exe)) {
  throw "Executable not found: $exe"
}

if (-not (Test-Path $config)) {
  throw "Test config not found: $config"
}

& $exe --config $config
