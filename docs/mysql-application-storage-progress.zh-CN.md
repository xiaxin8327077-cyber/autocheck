# MySQL 应用存储改造进度与后续实施方案

> 更新日期：2026-07-14
> 开发分支：`codex/mysql-app-storage`
> 基线分支：`feature/auto-check`（基线提交 `be8503f`）
> 完整设计：`docs/superpowers/specs/2026-07-14-mysql-application-storage-design.md`
> 完整任务计划：`docs/superpowers/plans/2026-07-14-mysql-application-storage.md`

## 1. 本次改造的确认范围

- Auto Check 自身运行数据只支持 MySQL，暂不支持 PostgreSQL。
- MySQL 连接信息继续放在现有 `config.json` 的 `app_database` 节点中。
- 继续使用现有 `--config` 和 `AUTO_CHECK_CONFIG` 定位配置文件，不新增启动参数。
- 采用单实例部署，一个 Auto Check 服务供所有用户访问；登录会话仍保存在进程内存中。
- 应用启动时只连接和校验 MySQL，不自动建库、建表、升级表结构或迁移 SQLite 数据。
- SQLite 到 MySQL 的迁移由运维人员手工执行 SQL。
- 日期、日期时间、时间和金额字段在本次迁移中直接使用 MySQL 原生类型，不继续按字符串保存。
- MySQL 建表 SQL需要包含中文表注释和中文字段注释。
- “本地数据查询”页面及入口需要隐藏，不提供新的 MySQL 管理页面。

## 2. 总体进度结论

按完整实施计划的 8 个任务统计：

| 状态 | 内容 |
| --- | --- |
| 已完成 | Task 1 MySQL 应用数据库基础；Task 2 应用配置存储迁移 |
| 开发中 | Task 3 用户与认证存储迁移；Task 5 中的数据库启动、校验、关闭及配置存储注入部分 |
| 未完成 | Task 4 历史记录迁移；Task 5 页面隐藏和 SQLite 管理接口停用；Task 6 仓库内通用建表与导出工具；Task 7 文档和更新日志；Task 8 全量验证与 Windows 打包 |

当前代码还不能作为最终版本交付。主要原因是历史记录仍走 SQLite，“本地数据查询”仍可见，认证改动尚未提交且定向测试还有 1 个旧断言失败。

## 3. 已完成部分

### 3.1 方案和实施计划

已完成 MySQL 单库、单实例、人工迁移、启动只读校验、原生字段类型和页面隐藏等边界设计，并形成设计和实施计划。

对应提交：

- `398badb docs: plan mysql application storage`

### 3.2 MySQL 应用数据库基础

已新增 `src/auto_check/app/app_database.py`，完成以下能力：

- 从现有 `config.json` 读取 `app_database`。
- 只接受 `backend=mysql`。
- 使用 SQLAlchemy Core 和 PyMySQL 创建连接池。
- 使用 SQLAlchemy URL 对象构造连接地址，避免密码被直接拼接进 URL 或错误信息。
- 支持连接测试、显式连接、显式事务和连接池关闭。
- 启动时只读校验 `app_schema_version`、目标表和关键字段。
- 校验过程不执行 DDL，不创建 SQLite 文件，也不自动回退到 SQLite/JSON。
- Windows、Linux 打包脚本已加入 SQLAlchemy MySQL 方言隐藏依赖。

对应提交：

- `d78cc06 feat: add mysql application database foundation`
- `659f1be fix: secure mysql application database config`

### 3.3 应用配置存储迁移

应用配置的运行时读写已改为 MySQL，覆盖：

- `data_sources`：DWS 和报表数据源配置。
- `app_settings`：系统默认设置。
- `config_snapshots`：配置快照。
- 数据源密码仍按现有加密方式保存，不以明文落库。
- 动态配置保存时不再重写 `config.json`；`config.json` 仅保留 MySQL 启动连接信息。
- 服务端配置相关路由已注入同一个 `ApplicationDatabase` 实例。

对应提交：

- `6d193a1 feat: store application config in mysql`
- `2d595c4 fix: wire mysql config storage into server`

定向验证结果：

```text
python -m pytest -q tests/test_app_database.py tests/test_config.py
39 passed in 0.50s
```

### 3.4 生产 SQLite 数据转换产物

已读取生产源文件 `D:\xiaxin\download\auto-check (1).db` 并生成一次性迁移产物：

- `D:\xiaxin\download\auto_check_mysql_schema.sql`
- `D:\xiaxin\download\auto_check_mysql_data.sql`
- `D:\xiaxin\download\auto_check_mysql_migration_report.json`

已核对的转换结果：

| 项目 | 结果 |
| --- | ---: |
| SQLite 完整性检查 | `ok` |
| SQLite 外键异常 | 0 |
| 目标表 | 20 张（19 张业务表 + `app_schema_version`） |
| 导出源数据 | 3036 行 |
| 中文表注释 | 20 个 |
| 中文字段注释 | 155 个 |
| 日期字段 | `DATE` |
| 日期时间字段 | `DATETIME(6)` |
| 时间字段 | `TIME(6)` |
| 金额字段 | `DECIMAL(38,12)` |

转换报告确认所有生产值均完成类型转换，没有截断或降级为字符串。数据 SQL 包含密码哈希和已加密的下游数据库凭据，属于敏感生产数据，不进入 Git 仓库。

注意：以上是针对当前生产 DB 生成的一次性外部文件；仓库内可复用的通用建表 SQL和离线导出脚本尚未完成。

## 4. 开发中部分

### 4.1 用户与认证存储迁移

工作区已新增 `src/auto_check/app/storage_users.py`，并修改 `security.py` 和服务启动逻辑，当前实现方向为：

- 用户只从 MySQL `users` 表读取和保存。
- 初始化管理员、新建用户、修改用户、重置密码和登录时间写回 MySQL。
- 运行时不自动从 JSON 或 SQLite 导入用户。
- `AuthManager` 使用服务启动时创建的 `ApplicationDatabase`。
- 登录会话继续保存在单实例进程内存中。

这些文件目前仍是未提交改动：

- `src/auto_check/app/storage_users.py`
- `src/auto_check/app/security.py`
- `src/auto_check/app/server.py`
- `tests/mysql_config_test_support.py`
- `tests/test_security.py`

当前定向测试结果：

```text
python -m pytest -q tests/test_security.py
25 passed, 1 failed in 27.65s
```

剩余失败不是 MySQL 用户写入失败，而是一个密码传输测试仍尝试读取已不再生成的动态 `config.json`。需要将该断言改为检查 MySQL 中保存的是密文，并补齐其他测试替身的数据库注入后才能提交。

### 4.2 服务启动生命周期

服务启动已经能够：

1. 从配置文件创建 `ApplicationDatabase`。
2. 执行 `SELECT 1` 连接测试。
3. 校验 schema 版本、表和字段。
4. 把数据库实例注入配置路由和认证管理器。
5. 服务退出时关闭连接池。

但历史仓储仍在 `ApiRouter` 中创建 `SqliteHistoryStore`，因此当前只能算“部分完成”，还没有达到运行时彻底脱离 SQLite 的目标。

## 5. 未完成部分

### 5.1 三类历史记录迁移

以下运行历史仍使用 SQLite：

- 自动对数历史。
- 人行逐笔校验历史。
- 流程链执行历史、步骤、日志和明细。

待修改文件主要包括：

- `src/auto_check/app/storage_history.py`
- `src/auto_check/app/history.py`
- `src/auto_check/app/history_migration.py`
- `src/auto_check/app/server.py`
- `tests/test_history.py`

必须覆盖保存、列表、详情、删除、排序、级联删除、子表替换、事务回滚，以及 `Decimal/date/datetime/time` 与现有 API JSON 格式之间的转换。

### 5.2 “本地数据查询”页面和 SQLite 管理接口

当前页面、菜单、JavaScript 自动加载逻辑、样式和测试仍然存在，服务端也仍导入 SQLite 管理模块。

待处理内容：

- 隐藏侧边栏、顶部导航和页面主体入口。
- 页面不再自动调用本地存储查询接口。
- 停用运行时 SQLite 表查询、导出和备份接口，确保接口不会再访问 SQLite。
- 同步默认太空主题和暗色模式下的静态测试。
- 更新 README 和应用内更新日志。

### 5.3 仓库内通用迁移资产

以下计划文件尚不存在：

- `sql/app_storage/mysql/001_init_schema.sql`
- `scripts/export_sqlite_to_mysql.py`
- `tests/test_sqlite_to_mysql_export.py`

需要把已验证的一次性 schema 整理为不含生产数据和凭据的通用建表脚本，并提供只读打开 SQLite、校验数据类型、输出 SQL 和报告的通用离线导出命令。

### 5.4 文档、示例配置和发布说明

以下内容尚未按 MySQL 新架构统一更新：

- `README.md`
- `docs/deployment.zh-CN.md`
- `docs/intranet-production-deployment.zh-CN.md`
- `docs/check-history-design.zh-CN.md`
- `docs/flow-bg-execution-design.zh-CN.md`
- SQLite 相关旧设计文档的“历史/回滚参考”标记。
- `src/auto_check/web/app.js` 中的精简更新日志。

### 5.5 全量验证、真实 MySQL 验证和打包

尚未完成：

- `python -m pytest -q` 全量测试。
- 对目标 MySQL 的真实连接和只读 schema 校验。
- 运行时 SQLite 引用扫描。
- `git diff --check`。
- Windows 可执行文件重新打包和启动冒烟检查。

用户已确认 `auto_check` 数据库已经创建；但当前没有证据证明建表 SQL、数据 SQL 已在目标库执行，也没有完成真实 MySQL 验证，因此不能写成“生产库迁移已完成”。

## 6. 后续实施顺序

后续按以下顺序推进，每一阶段先跑定向测试并形成独立提交，避免把问题积压到最后一次全量测试。

### 阶段一：收尾用户与认证迁移

1. 修改密码传输测试，改为检查 MySQL 中的密文，不再读取动态 `config.json`。
2. 更新 `tests/test_crypto_fallback.py` 和 `tests/test_server.py` 中的 `AuthManager` 测试替身，统一注入数据库。
3. 为用户增删改、密码重置和登录时间写回增加线程内互斥保护，适配 `ThreadingHTTPServer`。
4. 运行：

```powershell
python -m pytest -q tests/test_security.py tests/test_crypto_fallback.py tests/test_server.py
```

5. 测试通过后提交：`feat: store users and authentication in mysql`。

### 阶段二：迁移三类历史记录

1. 先把 `tests/test_history.py` 改为 MySQL 仓储合约测试。
2. 使用 SQLAlchemy Core 重写三类历史的主表和子表读写。
3. 每次保存在一个事务内完成主表更新和子表替换。
4. 移除服务运行时的历史自动迁移扫描和 `SqliteHistoryStore` 创建。
5. 运行：

```powershell
python -m pytest -q tests/test_history.py tests/test_server.py
```

6. 通过后形成独立历史迁移提交。

### 阶段三：隐藏页面并停用 SQLite 管理接口

1. 修改 `index.html`、`app.js` 和 `styles.css`，隐藏所有“本地数据查询”入口并停止自动请求。
2. 服务端相关接口返回稳定的停用结果或 404，不读取本地 DB 文件。
3. 反向修改当前仍要求页面可见的静态测试。
4. 运行：

```powershell
python -m pytest -q tests/test_storage_admin.py tests/test_web_static.py tests/test_server.py
```

5. 通过后形成独立 UI/接口停用提交。

### 阶段四：补齐通用建表 SQL 和离线导出工具

1. 从已验证的外部 schema 提取通用 DDL，保留原生类型、索引、外键、20 个表注释和 155 个字段注释。
2. 通用 DDL 不包含 `CREATE DATABASE`、`DROP`、`TRUNCATE`、生产数据或任何凭据。
3. 导出脚本以 SQLite 只读模式工作，只生成文件，不连接 MySQL。
4. 对临时 SQLite 样本验证行数、类型转换、敏感信息不输出到控制台和版本号最后写入。
5. 运行：

```powershell
python -m pytest -q tests/test_sqlite_to_mysql_export.py
```

6. 通过后形成独立迁移工具提交。

### 阶段五：更新文档和发布说明

1. 更新部署、备份、回滚、人工执行 SQL 顺序和 `config.json` 示例。
2. README 详细记录关键行为变化。
3. 应用内更新日志按仓库约定只写“系统优化及BUG修复”。
4. 把 SQLite 设计文档标成历史迁移和回滚参考。
5. 运行相关静态与部署资产测试。

### 阶段六：真实 MySQL 验证、全量回归和打包

1. 使用本地忽略提交的配置文件连接目标 MySQL，密码不写入 Git、日志或本文档。
2. 先做 `SELECT 1`、schema 版本、表、字段和迁移数据行数的只读检查。
3. 除非有隔离测试库或明确授权，不在已有 `auto_check` 库执行破坏性或清空数据的测试。
4. 扫描活动运行路径中的 SQLite 引用并清理。
5. 运行：

```powershell
python -m pytest -q
git diff --check
rg -n "sqlite3|auto-check\.db|SqliteHistoryStore|PRAGMA|sqlite_master" src/auto_check/app src/auto_check/web
```

6. 确认 `dist\auto-check.exe` 未运行后重新打包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1
```

7. 对打包产物执行启动冒烟检查，确认缺少或错误 MySQL 配置时明确报错，且不会创建 SQLite 文件。

## 7. 最终验收标准

只有同时满足以下条件，才能宣布本次改造完成：

- 配置、用户、自动对数历史、人行逐笔历史和流程链历史全部从 MySQL 读写。
- 应用运行时不创建、不读取、不迁移 `auto-check.db`。
- `config.json` 只承载 `app_database` 等启动信息，动态配置不写回文件。
- 启动时只读校验 MySQL；缺配置、连接失败或 schema 不匹配时拒绝启动并给出明确原因。
- “本地数据查询”所有可见入口已隐藏，前端不再自动调用相关接口。
- 通用建表 SQL 包含中文表/字段注释和原生日期、时间、金额类型。
- 生产迁移行数和关键表抽样核对一致。
- 全量测试通过，`git diff --check` 无实际空白错误。
- Windows 安装包已刷新并通过启动冒烟检查。

## 8. 当前主要风险

- 历史记录涉及多张父子表和大体量逐笔校验明细，是剩余改动中风险最高的部分，必须保证事务原子性和现有 API 返回结构不变。
- 已生成的数据 SQL约 9 MB，包含敏感生产数据，只能受控传递和执行，不能提交仓库。
- 目标 MySQL 已建库不等于已完成 schema/data 导入；上线前必须执行只读核对并留存行数结果。
- 当前工作区认证改动尚未提交，继续开发前应先将 1 个失败测试修复并形成独立提交，避免与历史迁移交叉。
