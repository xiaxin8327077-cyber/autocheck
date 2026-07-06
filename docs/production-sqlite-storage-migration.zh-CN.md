# 生产环境 SQLite 存储迁移步骤

本文档用于指导生产环境从旧版本地 SQLite 存储迁移到 V2 结构化本地存储。

迁移目标：

- 保留本地 SQLite `auto-check.db`，不切换到 MySQL/PostgreSQL。
- 将旧 `app_kv`、`history_runs` 和旧 JSON 历史导入结构化表。
- 保留旧表和旧 JSON 作为兼容快照，不在迁移过程中删除旧数据。
- 迁移后应用 API、前端历史列表、详情和下载行为保持兼容。

数据库结构说明见：

- `docs/local-sqlite-database-design.zh-CN.md`

## 一、适用范围

适用于以下生产部署形态：

- Windows 单机 exe 部署。
- Linux 内网服务部署。
- 源码或 Python 服务方式部署。

本次迁移只处理应用自身数据：

- 系统配置、数据源配置、用户账号。
- 自动对数历史。
- 人行逐笔校验历史。
- 流程链执行历史。

不迁移业务库原始数据，不修改 DWS、报表库、申报平台数据库。

## 二、迁移前确认

### 1. 确认新版本代码或程序包

生产环境必须使用包含以下提交之后的版本：

```text
b5798a5 feat: normalize local storage tables
5517935 feat: normalize remaining local history tables
e7b04c5 docs: add local sqlite database design
```

如果使用打包 exe 或 Linux 二进制，需要确认二进制由该分支或合并后的主干重新打包生成。

### 2. 确认密钥环境变量

如果生产环境已经保存过数据库密码，必须保持 `AUTO_CHECK_SECRET_KEY` 不变。

迁移前后不要更换该值，否则旧配置中的加密数据库密码可能无法解密。

### 3. 确认应用已经停止

迁移前先停止正在运行的应用，避免 SQLite 文件被并发写入。

Windows：

```powershell
Get-Process auto-check -ErrorAction SilentlyContinue
Stop-Process -Name auto-check -Force
```

Linux systemd：

```bash
sudo systemctl stop auto-check
sudo systemctl status auto-check
```

### 4. 定位生产数据目录

默认 Windows 数据目录：

```text
%APPDATA%\auto-check
```

默认数据库：

```text
%APPDATA%\auto-check\auto-check.db
```

如果启动时使用了 `--config`：

```text
auto-check.exe --config D:\xxx\config.json
```

则数据库位于：

```text
D:\xxx\auto-check.db
```

Linux 内网部署常见目录：

```text
/home/autocheck/data/config.json
/home/autocheck/data/auto-check.db
```

以实际启动参数中的 `--config` 为准。

## 三、迁移前备份

迁移前必须备份整个应用数据目录。不要只备份 `auto-check.db`。

需要一起备份的典型文件和目录：

- `auto-check.db`
- `config.json`
- `history.json`
- `db-validation-history.json`
- `db-validation-results/`
- `pbc-import-uploads/`
- 其他与生产部署绑定的数据文件

### Windows 备份示例

以下示例假设使用默认数据目录：

```powershell
$dataDir = Join-Path $env:APPDATA "auto-check"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $dataDir "backup-before-storage-v2-$stamp"

New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $dataDir "auto-check.db") -Destination $backupDir -Force

foreach ($name in @("config.json", "history.json", "db-validation-history.json")) {
    $path = Join-Path $dataDir $name
    if (Test-Path -LiteralPath $path) {
        Copy-Item -LiteralPath $path -Destination $backupDir -Force
    }
}

foreach ($name in @("db-validation-results", "pbc-import-uploads")) {
    $path = Join-Path $dataDir $name
    if (Test-Path -LiteralPath $path) {
        Copy-Item -LiteralPath $path -Destination (Join-Path $backupDir $name) -Recurse -Force
    }
}

Get-ChildItem -LiteralPath $backupDir
```

### Linux 备份示例

以下示例假设数据目录为 `/home/autocheck/data`：

```bash
DATA_DIR=/home/autocheck/data
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$DATA_DIR/backup-before-storage-v2-$STAMP"

mkdir -p "$BACKUP_DIR"
cp -a "$DATA_DIR/auto-check.db" "$BACKUP_DIR/"

for name in config.json history.json db-validation-history.json db-validation-results pbc-import-uploads; do
  if [ -e "$DATA_DIR/$name" ]; then
    cp -a "$DATA_DIR/$name" "$BACKUP_DIR/"
  fi
done

ls -lah "$BACKUP_DIR"
```

## 四、迁移前基线统计

迁移前记录旧库数据量，方便迁移后对账。

如果生产服务器有 Python，可执行：

```bash
python - <<'PY'
import sqlite3
from pathlib import Path

db_path = Path("auto-check.db")
con = sqlite3.connect(db_path)
try:
    print("integrity:", con.execute("PRAGMA integrity_check").fetchone()[0])
    tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print("tables:", tables)
    if "history_runs" in tables:
        print("history_runs:")
        for row in con.execute("SELECT kind, COUNT(*) FROM history_runs GROUP BY kind ORDER BY kind"):
            print(" ", row[0], row[1])
    if "app_kv" in tables:
        print("app_kv:", con.execute("SELECT COUNT(*) FROM app_kv").fetchone()[0])
finally:
    con.close()
PY
```

Windows PowerShell 示例：

```powershell
$dbPath = Join-Path $env:APPDATA "auto-check\auto-check.db"
@'
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
con = sqlite3.connect(db_path)
try:
    print("integrity:", con.execute("PRAGMA integrity_check").fetchone()[0])
    tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print("tables:", tables)
    if "history_runs" in tables:
        print("history_runs:")
        for row in con.execute("SELECT kind, COUNT(*) FROM history_runs GROUP BY kind ORDER BY kind"):
            print(" ", row[0], row[1])
    if "app_kv" in tables:
        print("app_kv:", con.execute("SELECT COUNT(*) FROM app_kv").fetchone()[0])
finally:
    con.close()
'@ | python - $dbPath
```

如果生产环境没有 Python，可跳过该步骤，但必须保留完整备份。

## 五、推荐：先在副本上演练

正式迁移前，建议把生产数据目录复制到临时演练目录，用新版本程序指向演练目录启动一次。

Windows 示例：

```powershell
$dataDir = Join-Path $env:APPDATA "auto-check"
$dryRunDir = Join-Path $env:TEMP "auto-check-storage-v2-dry-run"
Remove-Item -LiteralPath $dryRunDir -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item -LiteralPath $dataDir -Destination $dryRunDir -Recurse -Force

# 如果使用 exe 演练，启动时指向副本 config.json。
D:\path\to\auto-check.exe --config "$dryRunDir\config.json" --no-browser
```

Linux 示例：

```bash
DRY_RUN_DIR=/tmp/auto-check-storage-v2-dry-run
rm -rf "$DRY_RUN_DIR"
cp -a /home/autocheck/data "$DRY_RUN_DIR"

/path/to/auto-check --config "$DRY_RUN_DIR/config.json" --host 127.0.0.1 --port 18765 --no-browser
```

演练通过后删除临时目录即可。不要把演练目录替换回生产目录。

## 六、正式迁移方式

### 方式 A：通过新版本首次启动自动迁移

这是生产推荐方式，适合 exe 或 Linux 二进制部署。

步骤：

1. 停止旧版本应用。
2. 完整备份生产数据目录。
3. 替换为新版本 exe 或二进制。
4. 使用原生产启动参数启动新版本。
5. 新版本在读取配置、用户和历史时自动创建 V2 schema 并迁移旧数据。
6. 登录系统，检查数据源、用户、历史列表、人行逐笔校验历史和流程链历史。

Windows 示例：

```powershell
D:\path\to\auto-check.exe --config D:\prod\config.json --no-browser
```

Linux systemd 示例：

```bash
sudo systemctl start auto-check
sudo journalctl -u auto-check -n 200 --no-pager
```

### 方式 B：源码或 Python 服务下手动触发迁移

如果生产环境是源码部署，或可以运行当前 Python 包，可在启动服务前手动执行以下脚本。

脚本会触发：

- schema 初始化。
- 配置迁移。
- 用户迁移。
- 自动对数历史迁移。
- 人行逐笔校验历史迁移。
- 流程链历史迁移。
- 完整性和外键检查。

Windows PowerShell：

```powershell
$env:PYTHONPATH = "D:\path\to\auto_check\src"
$configPath = "D:\prod\config.json"

@'
import sqlite3
import sys
from pathlib import Path

from auto_check.app.config import load_store, save_store
from auto_check.app.history import SqliteHistoryStore
from auto_check.app.local_store import db_path_for_config
from auto_check.app.security import AuthManager
from auto_check.app.storage_schema import get_schema_version

config_path = Path(sys.argv[1])
db_path = db_path_for_config(config_path)

store = load_store(config_path)
save_store(store, config_path)

users = AuthManager(config_path=config_path).list_users()
reconcile_runs = SqliteHistoryStore(config_path, kind="reconcile").list_runs()
db_validation_runs = SqliteHistoryStore(config_path, kind="db_validation").list_runs()
flow_chain_runs = SqliteHistoryStore(config_path, kind="flow_chain").list_runs()

with sqlite3.connect(db_path) as con:
    con.execute("PRAGMA foreign_keys = ON")
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    fk_issues = con.execute("PRAGMA foreign_key_check").fetchall()
    run_headers = dict(con.execute(
        "SELECT kind, COUNT(*) FROM run_headers GROUP BY kind ORDER BY kind"
    ).fetchall())
    history_runs = dict(con.execute(
        "SELECT kind, COUNT(*) FROM history_runs GROUP BY kind ORDER BY kind"
    ).fetchall())

print("db_path:", db_path)
print("schema_version:", get_schema_version(db_path))
print("integrity:", integrity)
print("foreign_key_issues:", len(fk_issues))
print("users:", len(users))
print("run_headers:", run_headers)
print("history_runs:", history_runs)
print("api_counts:", {
    "reconcile": len(reconcile_runs),
    "db_validation": len(db_validation_runs),
    "flow_chain": len(flow_chain_runs),
})

if integrity != "ok" or fk_issues:
    raise SystemExit(1)
'@ | python - $configPath
```

Linux：

```bash
export PYTHONPATH=/path/to/auto_check/src
CONFIG_PATH=/home/autocheck/data/config.json

python - "$CONFIG_PATH" <<'PY'
import sqlite3
import sys
from pathlib import Path

from auto_check.app.config import load_store, save_store
from auto_check.app.history import SqliteHistoryStore
from auto_check.app.local_store import db_path_for_config
from auto_check.app.security import AuthManager
from auto_check.app.storage_schema import get_schema_version

config_path = Path(sys.argv[1])
db_path = db_path_for_config(config_path)

store = load_store(config_path)
save_store(store, config_path)

users = AuthManager(config_path=config_path).list_users()
reconcile_runs = SqliteHistoryStore(config_path, kind="reconcile").list_runs()
db_validation_runs = SqliteHistoryStore(config_path, kind="db_validation").list_runs()
flow_chain_runs = SqliteHistoryStore(config_path, kind="flow_chain").list_runs()

with sqlite3.connect(db_path) as con:
    con.execute("PRAGMA foreign_keys = ON")
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    fk_issues = con.execute("PRAGMA foreign_key_check").fetchall()
    run_headers = dict(con.execute(
        "SELECT kind, COUNT(*) FROM run_headers GROUP BY kind ORDER BY kind"
    ).fetchall())
    history_runs = dict(con.execute(
        "SELECT kind, COUNT(*) FROM history_runs GROUP BY kind ORDER BY kind"
    ).fetchall())

print("db_path:", db_path)
print("schema_version:", get_schema_version(db_path))
print("integrity:", integrity)
print("foreign_key_issues:", len(fk_issues))
print("users:", len(users))
print("run_headers:", run_headers)
print("history_runs:", history_runs)
print("api_counts:", {
    "reconcile": len(reconcile_runs),
    "db_validation": len(db_validation_runs),
    "flow_chain": len(flow_chain_runs),
})

if integrity != "ok" or fk_issues:
    raise SystemExit(1)
PY
```

## 七、迁移后核验

### 1. 数据库结构检查

迁移后应至少包含以下表：

```text
app_kv
app_settings
config_snapshots
data_sources
db_validation_result_rows
db_validation_runs
db_validation_selected_tables
db_validation_warnings
flow_chain_run_details
flow_chain_run_logs
flow_chain_run_steps
flow_chain_runs
history_runs
reconcile_delta_results
reconcile_result_details
reconcile_results
reconcile_run_counts
reconcile_runs
run_headers
schema_migrations
storage_migration_runs
users
```

`sqlite_sequence` 是 SQLite 内部表，存在与否取决于是否已有自增表写入记录。

### 2. SQL 核验

```sql
PRAGMA integrity_check;
PRAGMA foreign_key_check;

SELECT MAX(version) FROM schema_migrations;

SELECT kind, COUNT(*)
FROM run_headers
GROUP BY kind
ORDER BY kind;

SELECT kind, COUNT(*)
FROM history_runs
GROUP BY kind
ORDER BY kind;

SELECT source_type, source_key, migrated_count, skipped_count, status, finished_at
FROM storage_migration_runs
ORDER BY id DESC;
```

期望：

- `PRAGMA integrity_check` 返回 `ok`。
- `PRAGMA foreign_key_check` 返回 0 行。
- `schema_migrations` 最大版本为 `2`。
- `run_headers` 中应有已迁移的历史记录。
- `history_runs` 旧兼容数据仍保留。
- `storage_migration_runs` 中迁移状态为 `completed`。

### 3. 功能核验

登录系统后检查：

- 数据源配置能正常展示。
- 用户列表、登录、权限正常。
- 自动对数历史列表和详情可打开。
- 人行逐笔校验历史列表、详情和下载路径正常。
- 流程链历史列表和详情正常。
- 新执行一次自动对数、人行逐笔校验或流程链后，历史能正常新增。

## 八、回退步骤

如果迁移后发现问题，按以下方式回退。

### 1. 停止新版本应用

Windows：

```powershell
Stop-Process -Name auto-check -Force
```

Linux：

```bash
sudo systemctl stop auto-check
```

### 2. 恢复旧程序和旧数据

恢复迁移前备份的数据目录，至少恢复：

- `auto-check.db`
- `config.json`
- `history.json`
- `db-validation-history.json`
- 相关文件产物目录

Windows 示例：

```powershell
$dataDir = Join-Path $env:APPDATA "auto-check"
$backupDir = Join-Path $dataDir "backup-before-storage-v2-YYYYMMDD-HHMMSS"

Copy-Item -LiteralPath (Join-Path $backupDir "auto-check.db") -Destination $dataDir -Force

foreach ($name in @("config.json", "history.json", "db-validation-history.json")) {
    $path = Join-Path $backupDir $name
    if (Test-Path -LiteralPath $path) {
        Copy-Item -LiteralPath $path -Destination $dataDir -Force
    }
}
```

Linux 示例：

```bash
DATA_DIR=/home/autocheck/data
BACKUP_DIR=/home/autocheck/data/backup-before-storage-v2-YYYYMMDD-HHMMSS

cp -a "$BACKUP_DIR/auto-check.db" "$DATA_DIR/"
for name in config.json history.json db-validation-history.json db-validation-results pbc-import-uploads; do
  if [ -e "$BACKUP_DIR/$name" ]; then
    rm -rf "$DATA_DIR/$name"
    cp -a "$BACKUP_DIR/$name" "$DATA_DIR/"
  fi
done
```

### 3. 启动旧版本应用

不要用旧版本应用打开已经迁移后的新库。回退时必须同时恢复旧程序和备份数据。

## 九、注意事项

- 不要在应用运行中直接复制或替换 `auto-check.db`。
- 不要迁移后立即删除 `app_kv`、`history_runs`、旧 JSON 文件或备份目录。
- 不要更换 `AUTO_CHECK_SECRET_KEY`。
- 不要把生产 `auto-check.db` 提交到 Git。
- 不要把演练副本覆盖回生产目录。
- 如果生产环境有多个实例，不要让多个进程同时写同一个 SQLite 文件。

## 十、交付确认清单

迁移交付前逐项确认：

- [ ] 已停止旧应用。
- [ ] 已备份完整数据目录。
- [ ] 已确认 `AUTO_CHECK_SECRET_KEY` 不变。
- [ ] 已使用新版本程序完成迁移。
- [ ] `PRAGMA integrity_check` 返回 `ok`。
- [ ] `PRAGMA foreign_key_check` 返回 0 行。
- [ ] `schema_migrations` 最大版本为 `2`。
- [ ] 自动对数、人行逐笔校验、流程链历史数量符合预期。
- [ ] 登录、数据源、历史详情、下载路径完成抽样验证。
- [ ] 备份目录已登记并保留。
