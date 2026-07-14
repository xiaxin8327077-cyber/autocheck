param(
  [string]$PythonPath = "",
  [switch]$SkipTests,
  [switch]$Clean
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Resolve-Python {
  param([string]$Preferred)

  if ($Preferred) {
    if (Test-Path $Preferred) {
      return (Resolve-Path $Preferred).Path
    }
    $preferredCommand = Get-Command $Preferred -ErrorAction SilentlyContinue
    if ($preferredCommand) {
      return $preferredCommand.Source
    }
    throw "PythonPath not found: $Preferred"
  }

  $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  if (Test-Path $codexPython) {
    return (Resolve-Path $codexPython).Path
  }

  foreach ($candidate in @("python", "py")) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($command) {
      return $command.Source
    }
  }

  throw "Python not found. Please install Python 3.12 or pass -PythonPath."
}

$python = Resolve-Python -Preferred $PythonPath
$srcPath = Join-Path $root "src"
$webPath = Join-Path $root "src\auto_check\web"
$resourcesPath = Join-Path $root "src\auto_check\resources"
$entry = Join-Path $root "src\auto_check\__main__.py"
$distPath = Join-Path $root "dist"
$buildPath = Join-Path $root "build"
$exe = Join-Path $root "dist\auto-check.exe"

if (-not $SkipTests) {
  Write-Host "Running tests before packaging..."
  & $python -m pytest -q
  if ($LASTEXITCODE -ne 0) {
    throw "Tests failed, packaging aborted."
  }
}

$pyinstallerArgs = @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--onefile",
  "--name", "auto-check",
  "--paths", $srcPath,
  "--add-data", "$webPath;auto_check/web",
  "--add-data", "$resourcesPath;auto_check/resources",
  "--hidden-import", "py7zr",
  "--hidden-import", "rarfile",
  "--hidden-import", "psycopg",
  "--hidden-import", "psycopg_binary",
  "--hidden-import", "psycopg.pq",
  "--hidden-import", "pymysql",
  "--hidden-import", "sqlalchemy.dialects.mysql",
  "--hidden-import", "sqlalchemy.dialects.mysql.pymysql",
  "--distpath", $distPath,
  "--workpath", $buildPath,
  "--specpath", $buildPath
)

if ($Clean) {
  $pyinstallerArgs += "--clean"
}

$pyinstallerArgs += $entry

Write-Host "Packaging Windows executable..."
& $python @pyinstallerArgs
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller failed."
}

if (-not (Test-Path $exe)) {
  throw "Package failed, executable not found: $exe"
}

Write-Host "Package created: $exe"
