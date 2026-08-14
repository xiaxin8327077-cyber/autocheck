#!/usr/bin/env bash
set -euo pipefail

ROOT="/opt/auto_check"
OUTPUT_DIR="/tmp/dist-new"

mkdir -p "$OUTPUT_DIR" /tmp/build-new

export PATH="/opt/python/cp312/bin:$PATH"

cd "$ROOT"
python3.12 -m pip install --quiet -e ".[dev]"

python3.12 -m PyInstaller \
  --noconfirm \
  --onefile \
  --name auto-check \
  --paths src \
  --add-data "$ROOT/src/auto_check/web:auto_check/web" \
  --add-data "$ROOT/src/auto_check/resources:auto_check/resources" \
  --collect-submodules auto_check.modules \
  --collect-data auto_check.modules \
  --hidden-import py7zr \
  --hidden-import rarfile \
  --hidden-import psycopg \
  --hidden-import psycopg_binary \
  --hidden-import psycopg.pq \
  --hidden-import pymysql \
  --hidden-import sqlalchemy.dialects.mysql \
  --hidden-import sqlalchemy.dialects.mysql.pymysql \
  --hidden-import auto_check.resources \
  --hidden-import auto_check.resources.data \
  --distpath "$OUTPUT_DIR" \
  --workpath /tmp/build-new \
  --specpath /tmp/build-new \
  src/auto_check/__main__.py

"$OUTPUT_DIR/auto-check" --package-smoke-test

echo ""
echo "Package created: $OUTPUT_DIR/auto-check"
sha256sum "$OUTPUT_DIR/auto-check"
du -h "$OUTPUT_DIR/auto-check"
