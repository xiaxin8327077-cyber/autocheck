#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SKIP_TESTS=false
CLEAN=false
PYTHON_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tests) SKIP_TESTS=true; shift ;;
    --clean) CLEAN=true; shift ;;
    --python-path) PYTHON_PATH="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

resolve_python() {
  if [[ -n "$PYTHON_PATH" ]]; then
    if [[ -x "$PYTHON_PATH" ]]; then
      echo "$PYTHON_PATH"
      return
    fi
    echo "PythonPath not found: $PYTHON_PATH" >&2
    exit 1
  fi

  for candidate in python3.12 python3 python; do
    if command -v "$candidate" &>/dev/null; then
      echo "$(command -v "$candidate")"
      return
    fi
  done

  echo "Python not found. Please install Python 3.12 or pass --python-path." >&2
  exit 1
}

PYTHON="$(resolve_python)"
PYTHON_VERSION="$($PYTHON --version 2>&1)"
echo "Using Python: $PYTHON ($PYTHON_VERSION)"

SRC_PATH="$ROOT/src"
WEB_PATH="$ROOT/src/auto_check/web"
RESOURCES_PATH="$ROOT/src/auto_check/resources"
ENTRY="$ROOT/src/auto_check/__main__.py"
DIST_PATH="$ROOT/dist"
BUILD_PATH="$ROOT/build"
OUTPUT="$DIST_PATH/auto-check"
export PYTHONPATH="$SRC_PATH${PYTHONPATH:+:$PYTHONPATH}"

if [[ "$SKIP_TESTS" == false ]]; then
  echo "Running tests before packaging..."
  "$PYTHON" -m pytest -q
fi

PYINSTALLER_ARGS=(
  "-m" "PyInstaller"
  "--noconfirm"
  "--onefile"
  "--name" "auto-check"
  "--paths" "$SRC_PATH"
  "--add-data" "$WEB_PATH:auto_check/web"
  "--add-data" "$RESOURCES_PATH:auto_check/resources"
  "--collect-submodules" "auto_check.modules"
  "--collect-data" "auto_check.modules"
  "--hidden-import" "py7zr"
  "--hidden-import" "rarfile"
  "--hidden-import" "psycopg"
  "--hidden-import" "psycopg_binary"
  "--hidden-import" "psycopg.pq"
  "--hidden-import" "pymysql"
  "--hidden-import" "sqlalchemy.dialects.mysql"
  "--hidden-import" "sqlalchemy.dialects.mysql.pymysql"
  "--hidden-import" "auto_check.resources"
  "--hidden-import" "auto_check.resources.data"
  "--distpath" "$DIST_PATH"
  "--workpath" "$BUILD_PATH"
  "--specpath" "$BUILD_PATH"
)

if [[ "$CLEAN" == true ]]; then
  PYINSTALLER_ARGS+=("--clean")
fi

PYINSTALLER_ARGS+=("$ENTRY")

echo "Packaging Linux executable..."
"$PYTHON" "${PYINSTALLER_ARGS[@]}"

if [[ ! -f "$OUTPUT" ]]; then
  echo "Package failed, executable not found: $OUTPUT" >&2
  exit 1
fi

echo "Running packaged artifact smoke test..."
"$OUTPUT" --package-smoke-test

echo ""
echo "Package created: $OUTPUT"
echo "Size: $(du -h "$OUTPUT" | cut -f1)"
echo ""
echo "To deploy to production server:"
echo "  1. Copy $OUTPUT to the server"
echo "  2. chmod +x auto-check"
echo "  3. AUTO_CHECK_HOST=0.0.0.0 ./auto-check"
