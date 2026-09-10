# 监管报送平台公共服务实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为独立业务模块提供受控的数据源查询、Kettle 执行、Spider 流程执行和永久文件存储能力，不暴露核心内部对象或敏感配置。

**Architecture:** 四个服务均按现有 `PlatformServiceSpec`/`BoundService` 模式提供每模块独立且可撤销的 facade。数据源服务通过只读会话执行有限查询；Kettle 服务在平台层保管加密 Basic Auth 并适配生产 HTTP API；Spider 服务把 `server.py` 中的流程任务管理抽成可复用核心服务；文件服务把稳定 artifact ID 映射到模块隔离的持久目录。

**Tech Stack:** Python 3.12、dataclasses、PostgreSQL/MySQL 驱动、现有 ModuleRuntime、pytest。

## Global Constraints

- 这是平台兼容层，不包含监管报送业务表、页面或业务判断。
- 服务名和版本固定为 `platform.data_sources` v1、`platform.kettle_execution` v1、`platform.flow_execution` v1、`platform.artifact_storage` v1。
- 所有 facade 均绑定调用模块 owner，模块停止后必须撤销访问。
- 不返回 `DataSourceConfig`、密码、Token、绝对路径、原始驱动连接或可变核心配置对象。
- 查询只允许单条只读语句；超时、最大行数和取消不可由调用模块关闭。
- Spider 取消只停止本地等待和后续提交，不强杀已提交的 `sp_task`。
- 持久文件目录位于应用配置目录下的 `module-artifacts/<module_id>/`，不是 `ModuleContext.temp_root`。
- 不自动打包、不提交、不推送；提交步骤仅作为用户授权后的检查点。

---

## 文件结构

### 新增

- `src/auto_check/app/data_sources_platform.py`：公开数据类型、只读查询验证、方言包装和 facade。
- `src/auto_check/app/kettle_execution_platform.py`：Kettle KJB/KTR 请求、状态、日志、取消和脱敏 facade。
- `src/auto_check/app/storage_kettle_execution.py`：Kettle 基础地址、用户名和加密密码配置存储。
- `src/auto_check/app/flow_execution_service.py`：从 HTTP 路由解耦的 Spider 任务管理服务。
- `src/auto_check/app/flow_execution_platform.py`：Spider 服务的模块 facade。
- `src/auto_check/app/artifact_storage.py`：模块隔离的永久文件存储核心。
- `src/auto_check/app/artifact_storage_platform.py`：永久文件服务的模块 facade。
- `tests/test_data_sources_platform.py`
- `tests/test_kettle_execution_platform.py`
- `tests/test_flow_execution_platform.py`
- `tests/test_artifact_storage_platform.py`

### 修改

- `src/auto_check/app/db.py`：增加驱动无关的只读游标执行原语，不改变现有 `fetch_all` 行为。
- `src/auto_check/app/config.py`：增加 Kettle 平台配置的加密序列化，不向模块公开。
- `src/auto_check/app/server.py`：实例化公共服务、让既有 Spider 接口委托新服务、传入 `ModuleRuntime.build()`。
- `tests/test_db.py`：只读会话、超时、流式读取和取消回归。
- `tests/test_config.py`：Kettle 密码加密、脱敏读取和兼容性回归。
- `tests/test_flow_tool.py`、`tests/test_server.py`：既有 Spider 接口兼容性。
- `tests/test_platform_services.py`：注册、版本、撤销和依赖声明。

## 公开接口冻结

在写实现前，先把以下类型作为测试中的唯一公共契约；后续模块只能依赖这些名字：

```python
# src/auto_check/app/data_sources_platform.py
@dataclass(frozen=True)
class PublicDataSource:
    id: str
    name: str
    db_type: Literal["postgresql", "mysql"]
    default_namespace: str

@dataclass(frozen=True)
class ReadOnlyQuery:
    source_id: str
    sql: str
    parameters: tuple[object, ...] = ()
    timeout_seconds: int = 30
    maximum_rows: int = 1000

@dataclass(frozen=True)
class QueryColumn:
    name: str
    database_type: str

@dataclass(frozen=True)
class QueryPage:
    columns: tuple[QueryColumn, ...]
    rows: tuple[dict[str, object], ...]
    truncated: bool

class DataSourcesFacade(Protocol):
    def list_sources(self) -> tuple[PublicDataSource, ...]: ...
    def inspect(self, request: ReadOnlyQuery) -> tuple[QueryColumn, ...]: ...
    def fetch(self, request: ReadOnlyQuery) -> QueryPage: ...
    def stream(self, request: ReadOnlyQuery, consumer: Callable[[tuple[QueryColumn, ...], tuple[dict[str, object], ...]], None], cancel_event: Event, *, chunk_rows: int = 1000) -> int: ...
    def quote_identifier(self, source_id: str, parts: tuple[str, ...]) -> str: ...
```

```python
# src/auto_check/app/kettle_execution_platform.py
KettleKind = Literal["kjb", "ktr"]

@dataclass(frozen=True)
class KettleStartRequest:
    kind: KettleKind
    remote_path: str
    parameters: Mapping[str, str]
    timeout_seconds: int
    actor_name: str

@dataclass(frozen=True)
class KettleReference:
    run_id: str

@dataclass(frozen=True)
class KettleStatus:
    run_id: str
    state: Literal["queued", "running", "succeeded", "failed", "cancelled", "unknown"]
    progress: int
    external_id: str | None
    log_cursor: int
    error: str

class KettleExecutionFacade(Protocol):
    def start(self, request: KettleStartRequest) -> KettleReference: ...
    def status(self, run_id: str) -> KettleStatus: ...
    def logs(self, run_id: str, after: int = 0, limit: int = 500) -> tuple[dict[str, object], ...]: ...
    def cancel(self, run_id: str) -> KettleStatus: ...
```

```python
# src/auto_check/app/flow_execution_platform.py
@dataclass(frozen=True)
class SpiderFlow:
    id: str
    name: str
    enabled: bool

@dataclass(frozen=True)
class SpiderStartRequest:
    flow_id: str
    trigger_type: str
    executor_name: str
    timeout_seconds: int

@dataclass(frozen=True)
class ExternalFlowReference:
    job_id: str

@dataclass(frozen=True)
class ExternalFlowStatus:
    job_id: str
    state: Literal["queued", "running", "succeeded", "failed", "cancelled", "unknown"]
    progress: int
    external_task_id: str | None
    log_cursor: int
    error: str

class FlowExecutionFacade(Protocol):
    def list_flows(self, keyword: str = "", limit: int = 500) -> tuple[SpiderFlow, ...]: ...
    def start(self, request: SpiderStartRequest) -> ExternalFlowReference: ...
    def status(self, job_id: str) -> ExternalFlowStatus: ...
    def logs(self, job_id: str, after: int = 0, limit: int = 500) -> tuple[dict[str, object], ...]: ...
    def cancel(self, job_id: str) -> ExternalFlowStatus: ...
```

```python
# src/auto_check/app/artifact_storage_platform.py
@dataclass(frozen=True)
class ArtifactInfo:
    id: str
    business_key: str
    filename: str
    content_type: str
    size: int
    sha256: str
    created_at: str

class ArtifactWriter(Protocol):
    def write(self, data: bytes) -> None: ...
    def commit(self) -> ArtifactInfo: ...
    def abort(self) -> None: ...

class ArtifactStorageFacade(Protocol):
    def begin_write(self, *, business_key: str, filename: str, content_type: str) -> ArtifactWriter: ...
    def stat(self, artifact_id: str) -> ArtifactInfo: ...
    def read_range(self, artifact_id: str, start: int, end_exclusive: int) -> bytes: ...
    def iter_bytes(self, artifact_id: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]: ...
    def verify(self, artifact_id: str) -> bool: ...
    def usage(self) -> tuple[int, int]: ...
```

## Task 1：数据源只读服务

**Files:**
- Create: `src/auto_check/app/data_sources_platform.py`
- Modify: `src/auto_check/app/db.py`
- Test: `tests/test_data_sources_platform.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `load_store(config_path, database=application_database)`、`resolve_data_source_entry()`、`DatabaseClient`。
- Produces: `create_data_sources_platform_service(config_path, application_database) -> PlatformServiceSpec` 和“公开接口冻结”中的全部数据源类型。

- [ ] **Step 1: 写脱敏目录失败测试**

```python
def test_catalog_never_exposes_credentials(service):
    source = service.list_sources()[0]
    assert source.id == "source-a"
    assert source.name == "报表库"
    assert source.db_type == "postgresql"
    assert not hasattr(source, "password")
    assert "host" not in source.__dict__
```

- [ ] **Step 2: 写只读边界失败测试**

```python
@pytest.mark.parametrize("sql", [
    "DELETE FROM t", "UPDATE t SET a=1", "SELECT 1; SELECT 2",
    "SET statement_timeout=0", "COPY t TO '/tmp/a'",
])
def test_query_rejects_unsafe_sql(service, sql):
    with pytest.raises(ValueError, match="只读"):
        service.fetch(ReadOnlyQuery("source-a", sql))
```

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest tests/test_data_sources_platform.py tests/test_db.py -q`

Expected: FAIL，原因是服务类型和只读执行原语尚不存在。

- [ ] **Step 4: 实现数据库只读执行原语**

在 `DatabaseClient` 增加内部方法，强制驱动事务只读、查询超时、逐批读取并在 `cancel_event` 置位时中止；PostgreSQL 使用 `SET TRANSACTION READ ONLY` 与本地 `statement_timeout`，MySQL 使用只读事务和驱动读超时。保留现有 `fetch_all/fetch_one` 签名。

```python
def stream_read_only(
    self,
    sql: str,
    params: tuple[object, ...],
    *,
    timeout_seconds: int,
    maximum_rows: int,
    chunk_rows: int,
    cancel_event: threading.Event,
    consumer: Callable[[tuple[QueryColumn, ...], tuple[dict[str, object], ...]], None],
) -> int:
    ...
```

实现时 `maximum_rows` 必须硬限制在 `1..1_000_000`，`timeout_seconds` 必须硬限制在 `1..300`，`chunk_rows` 必须硬限制在 `1..10_000`；元数据探测由调用者传入最多 5 秒和最多 1 行。

- [ ] **Step 5: 实现 facade 与方言引用**

静态验证忽略字符串和注释后只允许一个顶层语句且首个关键字为 `SELECT` 或 `WITH`；最终安全边界仍由只读数据库会话承担。`quote_identifier()` 只接受 `^[A-Za-z_][A-Za-z0-9_$]*$` 的每段标识符，再按 PostgreSQL 双引号或 MySQL 反引号引用。

- [ ] **Step 6: 运行专项测试**

Run: `python -m pytest tests/test_data_sources_platform.py tests/test_db.py -q`

Expected: PASS；目录响应中不出现 host、port、database、username、password 或连接串。

- [ ] **Step 7: 用户授权后创建平台提交检查点**

```powershell
git add src/auto_check/app/data_sources_platform.py src/auto_check/app/db.py tests/test_data_sources_platform.py tests/test_db.py
git commit -m "新增模块只读数据源平台服务"
```

未获授权时只保留工作区改动并报告差异，不执行提交。

## Task 2：Kettle Basic Auth 执行平台服务

**Files:**
- Create: `src/auto_check/app/kettle_execution_platform.py`
- Create: `src/auto_check/app/storage_kettle_execution.py`
- Modify: `src/auto_check/app/config.py`
- Modify: `src/auto_check/app/server.py`（管理员平台配置 API 与服务实例化）
- Test: `tests/test_kettle_execution_platform.py`
- Test: `tests/test_config.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: 现有 `encrypt_secret/decrypt_secret`、stdlib HTTP client、用户已确认的启动 URL。
- Produces: `create_kettle_execution_platform_service(settings_store, transport) -> PlatformServiceSpec` 和冻结的 `KettleExecutionFacade`。

**Authoritative reference:** `D:/xiaxin/wx/xwechat_files/ccqlove_5f6d/msg/file/2026-09/PDIA_REST_API_10_1_MK-95PDIA010-01 (1).pdf` 的 PDF 页 10-11、29-30、39-40、43-44、56-57、59-60、63-64；所有行为仍需在 Pentaho 11 测试环境验证。

- [ ] **Step 1: 写端点、编码和认证失败测试**

```python
def test_job_and_trans_use_confirmed_paths_and_basic_auth(fake_transport, facade):
    facade.start(KettleStartRequest("kjb", "/home/kettle/filerep/dm/a.kjb", {"inputdate": "2026-08-31"}, 120, "张三"))
    assert fake_transport.last.path == "/kettle/executeJob/"
    assert fake_transport.last.query == {"job": "/home/kettle/filerep/dm/a.kjb", "inputdate": "2026-08-31"}
    assert fake_transport.last.authorization_scheme == "Basic"
```

另测 KTR 使用 `/kettle/executeTrans/` 和 `trans`；远端路径、空参数名、CR/LF、重复保留参数和超长 URL 必须拒绝。测试凭据只用 `test-user/test-password`，不得复制截图值。

- [ ] **Step 2: 写密码加密和脱敏失败测试**

保存后数据库/配置 JSON 只出现 `password_encrypted`，GET 配置只返回 `configured=true` 和脱敏 username，不返回密码或 Authorization；日志、异常和 facade 响应中搜索测试 Base64 值必须无匹配。

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest tests/test_kettle_execution_platform.py tests/test_config.py tests/test_server.py -q`

Expected: FAIL，Kettle 平台服务尚不存在。

- [ ] **Step 4: 实现平台配置**

`KettleExecutionSettings` 保存 `base_url`、`username`、内存态 `password`、connect/read timeout；序列化使用现有 AES-GCM `encrypt_secret()`。管理员接口固定为 `GET/PUT /api/settings/kettle-execution`，需要 `sys.settings`、登录和 CSRF。base URL 只允许 `http/https`，不允许 query、fragment 或内嵌凭据。

- [ ] **Step 5: 实现已确认的启动请求**

KJB 为 `GET {base_url}/kettle/executeJob/?job=<encoded>&...`，KTR 为 `GET {base_url}/kettle/executeTrans/?trans=<encoded>&...`。使用 HTTP Basic Auth 头但永不持久化完整头；响应正文按最大 2 MiB 读取，超过即失败并脱敏。

- [ ] **Step 6: 按 XML 契约实现状态、日志和停止**

`executeJob` 解析 `<webresult><result>OK</result><id>...</id>`；`executeTrans` 同时接受同结构响应和成功空响应。状态调用固定为：

```text
GET /kettle/jobStatus/?name={name}&id={carte_id}&from={next_log_line}&xml=Y
GET /kettle/transStatus/?name={name}&id={carte_id}&from={next_log_line}&xml=Y
```

解析 `status_desc`、`error_desc`、`first_log_line_nr`、`last_log_line_nr`、`result/nr_errors`、`result/result` 和 `logging_string`。`logging_string` 若能安全识别为 Base64+gzip 则解码，否则按原始文本处理；解码上限 8 MiB。`from` 固定取上次 `last_log_line_nr + 1`，避免重复日志。

停止调用固定为：

```text
GET /kettle/stopJob/?name={name}&id={carte_id}&xml=Y
GET /kettle/stopTrans/?name={name}&id={carte_id}&xml=Y
```

只有 `<webresult><result>OK</result>` 才记为停止请求已接受。HTTP 200 但 XML 为 ERROR 仍是失败；禁止把响应中的 Java 堆栈原样传给前端。

- [ ] **Step 7: 处理 `executeTrans` 空成功响应的关联风险**

如果 Pentaho 11 实测的 `executeTrans` 不返回 Carte ID，平台状态先记为 unknown，并对同一规范化 remote_path 加独占锁，禁止第二个同路径 KTR 启动。联调时验证 `/kettle/runTrans` 是否可在保持文件系统语义的前提下返回 ID；只有用户确认切换后才能更改启动端点。不得仅凭 trans name 把“最后一次执行”绑定到并发任务。

- [ ] **Step 8: 运行专项测试**

Run: `python -m pytest tests/test_kettle_execution_platform.py tests/test_config.py tests/test_server.py -q`

Expected: PASS；输出和错误不含 Authorization、用户名密码或完整生产 URL。

- [ ] **Step 9: 用户授权后创建平台提交检查点**

```powershell
git add src/auto_check/app/kettle_execution_platform.py src/auto_check/app/storage_kettle_execution.py src/auto_check/app/config.py src/auto_check/app/server.py tests/test_kettle_execution_platform.py tests/test_config.py tests/test_server.py
git commit -m "新增Kettle执行平台服务"
```

## Task 3：Spider 流程执行服务

**Files:**
- Create: `src/auto_check/app/flow_execution_service.py`
- Create: `src/auto_check/app/flow_execution_platform.py`
- Modify: `src/auto_check/app/server.py`（`ApiRouter` Spider 初始化与既有流程接口委托位置）
- Test: `tests/test_flow_execution_platform.py`
- Test: `tests/test_flow_tool.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `DatabaseFlowGateway`、`run_flow_chain()`、`FlowChainRunContext`。
- Produces: `create_flow_execution_platform_service(service) -> PlatformServiceSpec` 和冻结的 `FlowExecutionFacade`。

- [ ] **Step 1: 写 facade 归属、日志游标和取消测试**

```python
def test_facade_returns_incremental_logs_and_local_cancel(facade):
    ref = facade.start(SpiderStartRequest("flow-1", "reporting", "张三", 120))
    first = facade.logs(ref.job_id, after=0)
    second = facade.logs(ref.job_id, after=len(first))
    assert set(first).isdisjoint(second)
    status = facade.cancel(ref.job_id)
    assert status.state in {"cancelled", "running"}
```

再断言 owner A 的 facade 不能读取 owner B 创建的 job，关闭 facade 后所有方法抛 `RuntimeError`。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/test_flow_execution_platform.py tests/test_flow_tool.py -q`

Expected: FAIL，平台 facade 尚不存在。

- [ ] **Step 3: 抽取任务管理但保持旧接口兼容**

`FlowExecutionService` 负责列表、启动、状态、日志、取消和后台线程；`ApiRouter` 原有流程接口改为委托该服务。状态映射固定为：pending→queued、running/submitted→running、completed→succeeded、failed→failed、cancelled→cancelled；无法确认外部状态时返回 unknown，不猜成功。

- [ ] **Step 4: 实现模块 facade**

绑定 owner 并保存 `owner -> job ids` 访问关系；错误文本经现有运行时脱敏函数处理。取消只设置本地 cancel event，并在日志中写“已提交的 sp_task 不会被强制终止”。

- [ ] **Step 5: 运行专项与回归测试**

Run: `python -m pytest tests/test_flow_execution_platform.py tests/test_flow_tool.py tests/test_server.py -q`

Expected: PASS；既有流程工具请求/响应字段保持不变。

- [ ] **Step 6: 用户授权后创建平台提交检查点**

```powershell
git add src/auto_check/app/flow_execution_service.py src/auto_check/app/flow_execution_platform.py src/auto_check/app/server.py tests/test_flow_execution_platform.py tests/test_flow_tool.py tests/test_server.py
git commit -m "开放可撤销的Spider流程执行服务"
```

## Task 4：永久文件服务

**Files:**
- Create: `src/auto_check/app/artifact_storage.py`
- Create: `src/auto_check/app/artifact_storage_platform.py`
- Test: `tests/test_artifact_storage_platform.py`

**Interfaces:**
- Consumes: application config directory and module owner from `PlatformServiceSpec.binder`。
- Produces: `create_artifact_storage_platform_service(root: Path, now: Callable[[], datetime]) -> PlatformServiceSpec` 和冻结的 `ArtifactStorageFacade`。

- [ ] **Step 1: 写原子写入和目录穿越失败测试**

```python
def test_commit_is_atomic_and_owner_scoped(storage_a, storage_b):
    writer = storage_a.begin_write(business_key="validation/run-1", filename="1.jsonl.gz", content_type="application/gzip")
    writer.write(b"abc")
    info = writer.commit()
    assert storage_a.verify(info.id) is True
    with pytest.raises(FileNotFoundError):
        storage_b.stat(info.id)

@pytest.mark.parametrize("value", ["../x", "..\\x", "/abs", "C:\\abs"])
def test_rejects_traversal(storage_a, value):
    with pytest.raises(ValueError):
        storage_a.begin_write(business_key=value, filename="x", content_type="text/plain")
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/test_artifact_storage_platform.py -q`

Expected: FAIL，存储服务尚不存在。

- [ ] **Step 3: 实现存储布局与 manifest**

物理布局固定为：

```text
module-artifacts/<owner>/<artifact-id-prefix>/<artifact-id>.bin
module-artifacts/<owner>/<artifact-id-prefix>/<artifact-id>.json
module-artifacts/<owner>/.staging/<uuid>.part
```

`commit()` 先 fsync 临时文件，计算 size/sha256，写 manifest，再用同卷原子替换发布；失败调用 `abort()` 清理 `.part`。artifact ID 使用随机 32 位十六进制，不由业务键或文件名组成。

- [ ] **Step 4: 实现范围读取、流式读取和容量统计**

`read_range` 校验 `0 <= start <= end_exclusive <= size`；`iter_bytes` 每次最多 8 MiB；`usage()` 返回 `(artifact_count, total_bytes)`。第一阶段不提供 delete，不注册清理计划。

- [ ] **Step 5: 运行专项测试**

Run: `python -m pytest tests/test_artifact_storage_platform.py -q`

Expected: PASS；中途异常无可见 artifact，跨 owner 访问失败，篡改文件后 `verify()` 返回 false。

- [ ] **Step 6: 用户授权后创建平台提交检查点**

```powershell
git add src/auto_check/app/artifact_storage.py src/auto_check/app/artifact_storage_platform.py tests/test_artifact_storage_platform.py
git commit -m "新增模块永久文件存储服务"
```

## Task 5：注册、生命周期与平台总回归

**Files:**
- Modify: `src/auto_check/app/server.py:4771`（`run_server()` 服务构造和清理）
- Modify: `tests/test_platform_services.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: Tasks 1-4 的四个 `create_*_platform_service()`。
- Produces: `ModuleRuntime.build(..., platform_services=(...))` 中稳定注册的七个既有/新增平台服务。

- [ ] **Step 1: 写注册和关闭顺序失败测试**

断言注册列表包含 user_directory、report_navigation、notification、data_sources、kettle_execution、flow_execution、artifact_storage，名称唯一；启动失败和正常退出均先停止模块 runtime，再停止底层 Kettle/Spider/通知服务。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/test_platform_services.py tests/test_server.py -q`

Expected: FAIL，新增服务尚未注入 runtime。

- [ ] **Step 3: 在 `run_server()` 注入服务**

```python
platform_services=(
    create_user_directory_service(auth_manager),
    create_report_navigation_service(report_navigation_service),
    create_notification_platform_service(notification_service),
    create_data_sources_platform_service(resolved_config_path, application_database),
    create_kettle_execution_platform_service(kettle_settings_store, kettle_transport),
    create_flow_execution_platform_service(flow_execution_service),
    create_artifact_storage_platform_service(resolved_config_path.parent / "module-artifacts", beijing_now),
)
```

所有底层实例在 `finally` 中确定性关闭，清理失败不得掩盖原始异常。

- [ ] **Step 4: 运行平台完整回归**

Run: `python -m pytest tests/test_platform_services.py tests/test_data_sources_platform.py tests/test_flow_execution_platform.py tests/test_artifact_storage_platform.py tests/test_flow_tool.py tests/test_server.py -q`

Expected: PASS。

- [ ] **Step 5: 运行全套验证**

Run: `python -m pytest -q`

Expected: PASS。

Run: `git diff --check`

Expected: 无实际 whitespace error。

- [ ] **Step 6: 用户授权后创建平台总提交**

```powershell
git add src/auto_check/app tests
git commit -m "完善独立模块公共平台能力"
```

只添加本计划相关文件，排除用户已有原型和其他未跟踪文件；未获授权时不提交。
