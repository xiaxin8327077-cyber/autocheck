param(
  [string]$HostAddress = "",
  [int]$Port = 0,
  [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$exe = Join-Path $root "dist\auto-check.exe"

if (-not (Test-Path $exe)) {
  throw "Executable not found: $exe. Run scripts\package-windows.ps1 first."
}

if (-not $HostAddress) {
  $HostAddress = if ($env:AUTO_CHECK_HOST) { $env:AUTO_CHECK_HOST } else { "0.0.0.0" }
}

if ($Port -le 0) {
  $Port = if ($env:AUTO_CHECK_PORT) { [int]$env:AUTO_CHECK_PORT } else { 8765 }
}

if ($Port -lt 1 -or $Port -gt 65535) {
  throw "Port must be between 1 and 65535."
}

if (-not $ConfigPath -and $env:AUTO_CHECK_CONFIG) {
  $ConfigPath = $env:AUTO_CHECK_CONFIG
}

$argsList = @("--host", $HostAddress, "--port", "$Port", "--no-browser")
if ($ConfigPath) {
  $argsList += @("--config", $ConfigPath)
}

Write-Host "Starting Auto Check on http://$HostAddress`:$Port"
Write-Host "Use http://<server-ip>:$Port from another machine on the same network."
& $exe @argsList
