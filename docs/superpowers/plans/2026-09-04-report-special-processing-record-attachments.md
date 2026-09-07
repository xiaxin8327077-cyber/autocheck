# Report Special Processing Record Attachments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为报表特殊处理记录增加可粘贴或上传的图片、Excel、Word、ZIP 附件，并在每次修改审计中查看修改前后的附件快照。

**Architecture:** 附件以不可变 LONGBLOB 行保存在模块自有表中，当前移除使用 removed_at 软删除，记录整体删除时物理清理。新文件随 POST/PUT JSON 以 Base64 原子提交，保留文件只提交 ID；审计保存 old/new ID 集合并在查询时批量补全不可变元数据。

**Tech Stack:** Python 3.12、SQLAlchemy Core、MySQL 模块迁移、原生 JavaScript ES modules、HTML/CSS、pytest、Node.js 前端场景测试。

## Global Constraints

- 开发前完整阅读 `AGENTS.md`、`docs/ai-modular-development-rules.zh-CN.md`、本计划和 `docs/superpowers/specs/2026-09-04-report-special-processing-record-attachments-design.md`。
- 如与登录恢复一同开发，还必须阅读并执行 `docs/superpowers/specs/2026-09-04-session-expiry-reauthentication-design.md` 和对应计划。
- 修改前保存 `git status --short` 基线，不覆盖、清理或提交用户已有无关修改。
- 附件功能必须留在 `report_special_processing` 模块；不得把业务校验或附件存储写入平台文件。
- 现有确认说明图片附件表和最多 3 张图片的行为保持不变。
- 当前附件上限：10 个；单个：10 MiB；原始字节总计：30 MiB；POST/PUT 路由 JSON 上限：45 MiB；平台硬上限保持 50 MiB。
- 允许：PNG、JPEG、WebP、XLS、XLSX、DOC、DOCX、ZIP；拒绝 SVG、XLSM、DOCM、RAR、7Z 和可执行文件。
- 不新增依赖、菜单、权限码、平台接口版本、临时文件或外部对象存储。
- 模块版本升至 `1.2.13`，schema version 升至 6；应用展示大版本保持 `V1.2`，与登录恢复共同进入 `v1.2.23`。
- 测试和验证优先交给 `gpt-5.6-luna` high 子代理，主会话审阅实际输出。
- 除非用户另行明确要求，不打包、不刷新 `dist/auto-check.exe`、不提交、不推送、不创建 PR。

---

### Task 1: 定义附件输入契约与文件校验器

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/contracts.py`
- Modify: `src/auto_check/modules/report_special_processing/validator.py`
- Modify: `tests/modules/report_special_processing/test_validator_and_permissions.py`

**Interfaces:**
- Consumes: 记录请求 Mapping、Base64 文本、Python `zipfile` 和 `hashlib` 标准库。
- Produces: `RecordAttachmentFile`、`RecordAttachmentChange`、`validate_record_attachment_change(payload, *, creating)`。

- [ ] **Step 1: 写附件契约和允许类型的失败测试**

在 `test_validator_and_permissions.py` 增加构造有效 PNG、JPEG、WebP、OLE、XLSX、DOCX 和 ZIP 字节的测试助手。至少锁定以下公开契约：

```python
def test_record_attachment_change_accepts_supported_files():
    payload = {
        "record_attachments": {
            "retained_ids": [],
            "new_files": [
                {
                    "client_id": "local-1",
                    "file_name": "证据.png",
                    "content_type": "image/png",
                    "data_base64": base64.b64encode(valid_png()).decode("ascii"),
                }
            ],
        }
    }
    change = validate_record_attachment_change(payload, creating=True)
    assert change.retained_ids == ()
    assert change.new_files[0].file_name == "证据.png"
    assert change.new_files[0].content_type == "image/png"
    assert change.new_files[0].content == valid_png()
    assert len(change.new_files[0].content_sha256) == 64
```

再写参数化测试覆盖 `.jpg/.jpeg/.webp/.xls/.xlsx/.doc/.docx/.zip`。OLE 的服务端 `content_type` 必须是 `application/x-ole-storage`。

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest -q tests/modules/report_special_processing/test_validator_and_permissions.py -k "record_attachment"`

Expected: FAIL，因为契约和校验器尚不存在。

- [ ] **Step 3: 增加精确常量与不可变数据类**

在 `contracts.py` 增加：

```python
@dataclass(frozen=True)
class RecordAttachmentFile:
    client_id: str
    file_name: str
    file_extension: str
    content_type: str
    content: bytes
    content_sha256: str

    @property
    def byte_size(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class RecordAttachmentChange:
    retained_ids: tuple[int, ...]
    new_files: tuple[RecordAttachmentFile, ...]
```

在 `validator.py` 增加且只在附件 POST/PUT 路由使用：

```python
MAX_RECORD_ATTACHMENTS = 10
MAX_RECORD_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_RECORD_ATTACHMENTS_TOTAL_BYTES = 30 * 1024 * 1024
MAX_RECORD_ATTACHMENT_REQUEST_BYTES = 45 * 1024 * 1024
MAX_RECORD_ATTACHMENT_FILE_NAME_CHARS = 255
MAX_OOXML_ENTRIES = 5000
MAX_OOXML_CONTENT_TYPES_BYTES = 1024 * 1024
```

- [ ] **Step 4: 实现请求结构、文件名、Base64、魔数和容器校验**

实现：

```python
def validate_record_attachment_change(
    payload: Mapping[str, Any], *, creating: bool
) -> RecordAttachmentChange | None:
    if "record_attachments" not in payload:
        return None
    raw = payload["record_attachments"]
    if not isinstance(raw, Mapping) or set(raw) != {"retained_ids", "new_files"}:
        raise ValidationError(fields={"record_attachments": "附件参数不完整"})
    retained_ids = _validate_retained_attachment_ids(raw["retained_ids"])
    if creating and retained_ids:
        raise ValidationError(fields={"record_attachments": "新建记录不能引用已有附件"})
    new_files = tuple(_validate_record_attachment_file(item) for item in raw["new_files"])
    if len(retained_ids) + len(new_files) > MAX_RECORD_ATTACHMENTS:
        raise ValidationError(fields={"record_attachments": "每条记录最多 10 个附件"})
    return RecordAttachmentChange(retained_ids, new_files)
```

具体要求：

- `retained_ids` 必须是无重复正整数数组。
- `new_files` 必须是数组；每项必须且只能包含 `client_id/file_name/content_type/data_base64`。
- 文件名使用 basename 语义去掉路径、NUL 和控制字符，trim 后 1–255 字符。
- Base64 使用 `base64.b64decode(..., validate=True)`；空文件和单文件超过 10 MiB 拒绝。
- PNG/JPEG/WebP 校验魔数。
- OLE 文件只接受 `.xls/.doc`，服务端 MIME 固定为 `application/x-ole-storage`。
- OOXML 用 `zipfile.ZipFile(BytesIO(content))` 读取中央目录；条目不超过 5000，只读取不超过 1 MiB 的 `[Content_Types].xml`，分别验证 `xl/` 或 `word/`，拒绝 `vbaProject.bin` 和宏启用 content type。
- `.zip` 只验证可读取中央目录，不解压成员正文。
- 服务端忽略客户端 MIME 的分类结论，按验证结果写入规范化 MIME。
- 计算 SHA-256，并拒绝同批新文件内容重复；错误字段使用 `record_attachments.<client_id>`。

- [ ] **Step 5: 增加非法与边界测试**

覆盖：字段省略返回 None；新建空集合；空对象/缺数组/多字段；重复 retained ID；非法 ID；路径文件名；非法 Base64；空文件；扩展名/魔数不匹配；SVG、XLSM、DOCM、RAR、7Z、EXE；畸形 ZIP；OOXML 错目录；宏内容；同批哈希重复；10 MiB 和超过 1 字节边界。

- [ ] **Step 6: 运行校验测试**

Run: `python -m pytest -q tests/modules/report_special_processing/test_validator_and_permissions.py`

Expected: PASS。

---

### Task 2: 增加迁移、SQLAlchemy 表和附件读取方法

**Files:**
- Create: `src/auto_check/modules/report_special_processing/migrations/006_record_attachments.sql`
- Modify: `src/auto_check/modules/report_special_processing/manifest.json`
- Modify: `src/auto_check/modules/report_special_processing/storage.py`
- Modify: `tests/modules/report_special_processing/test_manifest_and_migrations.py`
- Modify: `tests/modules/report_special_processing/test_storage.py`

**Interfaces:**
- Consumes: Task 1 的 `RecordAttachmentFile`。
- Produces: `RECORD_ATTACHMENTS` 表定义、`list_record_attachments()`、`get_record_attachment()` 和稳定的元数据序列化。

- [ ] **Step 1: 写迁移契约失败测试**

断言 manifest 的 schema version 为 6、迁移 006 被发现，且表包含设计中的全部中文注释列和索引：

```python
def test_migration_006_adds_record_attachments_table():
    sql = migration_sql("006_record_attachments.sql")
    assert "CREATE TABLE report_special_processing_record_attachments" in sql
    for column in (
        "record_id", "original_file_name", "file_extension", "content_type",
        "byte_size", "content_sha256", "content", "created_by_user_id",
        "created_by_username_snapshot", "created_at", "removed_by_user_id",
        "removed_by_username_snapshot", "removed_at",
    ):
        assert re.search(rf"\b{column}\b.+COMMENT '[^']+'", sql)
```

- [ ] **Step 2: 运行迁移测试并确认失败**

Run: `python -m pytest -q tests/modules/report_special_processing/test_manifest_and_migrations.py -k "006 or schema_version or migration"`

Expected: FAIL，因为迁移 006 不存在且 schema version 仍为 5。

- [ ] **Step 3: 创建迁移并注册表定义**

迁移严格使用设计表名和列，加入：

```sql
PRIMARY KEY (id),
KEY ix_rsp_record_att_current (record_id, removed_at, created_at, id),
KEY ix_rsp_record_att_hash (record_id, content_sha256)
```

在 `storage.py` 定义 `RECORD_ATTACHMENTS`，类型与 SQL 一致；保留现有确认附件 `ATTACHMENTS` 名称或将其仅在模块内部安全重命名为 `CONFIRM_ATTACHMENTS`，但不得混表。

- [ ] **Step 4: 写读取与稳定顺序失败测试**

测试同一 `created_at` 下多个 ID 按 `created_at, id` 返回；默认只返回 `removed_at IS NULL`，指定 IDs 时可读取历史行；记录 ID 必须同时匹配。

- [ ] **Step 5: 实现元数据与读取方法**

公开存储接口固定为 `list_record_attachments(self, record_id: int, *, include_removed: bool = False, attachment_ids: Sequence[int] | None = None) -> list[dict[str, Any]]` 和 `get_record_attachment(self, record_id: int, attachment_id: int) -> dict[str, Any] | None`。

列表按 `created_at.asc(), id.asc()`；元数据序列化输出 `id/file_name/file_extension/content_type/byte_size/content_sha256/created_by/created_at/removed`，仅 `get_record_attachment` 返回 `content`。

- [ ] **Step 6: 运行迁移和读取测试**

Run: `python -m pytest -q tests/modules/report_special_processing/test_manifest_and_migrations.py tests/modules/report_special_processing/test_storage.py -k "attachment or migration or schema"`

Expected: PASS。

---

### Task 3: 把附件创建、修改和删除纳入现有事务

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/storage.py`
- Modify: `tests/modules/report_special_processing/test_storage.py`

**Interfaces:**
- Consumes: `RecordAttachmentChange | None`、操作者快照、现有 `create/update/delete_record` 事务。
- Produces: 原子附件写入、`record_attachments` 当前元数据，以及含附件 ID 集合的审计 JSON。

- [ ] **Step 1: 写创建原子性失败测试**

扩展存储 fixture，传入两个附件创建记录，断言主记录、附件和创建审计同事务出现；让第二个附件插入抛错，断言三者均不存在。

```python
created = storage.create(
    record,
    reports,
    processes,
    audit,
    record_attachment_change=RecordAttachmentChange((), (first, second)),
    attachment_actor=actor,
)
assert [item["file_name"] for item in created["record_attachments"]] == ["a.png", "b.xlsx"]
assert audit_changed_fields(created["id"])["record_attachments"]["count"] == 2
```

- [ ] **Step 2: 运行创建测试并确认失败**

Run: `python -m pytest -q tests/modules/report_special_processing/test_storage.py -k "record_attachment and create"`

Expected: FAIL，因为 create 尚不接受附件变化。

- [ ] **Step 3: 实现创建附件 helper**

新增私有 helper `_insert_record_attachments(connection: Any, record_id: int, files: Sequence[RecordAttachmentFile], actor: Mapping[str, str], created_at: datetime) -> list[int]`。

使用服务端已验证的元数据和字节插入，返回自增 ID。`create()` 在写审计前解析 `audit["changed_fields_json"]`，加入 `record_attachments: {count, ids}` 后用 `ensure_ascii=False` 和紧凑分隔符重新序列化，再读取带当前附件的记录。任何异常由外层 transaction 回滚。

`create` 的完整兼容签名为 `create(self, record, reports, processes, audit, *, record_attachment_change: RecordAttachmentChange | None = None, attachment_actor: Mapping[str, str] | None = None) -> dict[str, Any]`。`None` 表示请求省略附件且不插入；`RecordAttachmentChange((), ())` 表示显式无附件，结果与 None 相同；只要 `new_files` 非空就必须提供包含 `user_id/username` 的 attachment_actor。

- [ ] **Step 4: 写修改集合与乐观锁失败测试**

覆盖初始 `[A,B]` 更新为 `[B,C]`：A 设置 removed 信息，B 不更新，C 新增；审计记录 `old_ids/new_ids/added_ids/removed_ids`；返回顺序 B 后 C；row_version 只增加 1。再覆盖版本冲突、错误 retained ID 和数据库异常无部分变化。

- [ ] **Step 5: 实现更新附件集合**

扩展 `update(self, record_id, row_version, changes, reports, processes, audit, *, record_attachment_change: RecordAttachmentChange | None = None, attachment_actor: Mapping[str, str] | None = None) -> dict[str, Any]`，保持现有位置参数兼容。

先执行现有带 row_version 的原子主记录 update；成功取得行锁后再读取当前附件。若 change 非 None：

- retained ID 集合必须是当前 ID 的子集，重复已由 validator 拒绝。
- retained 顺序按数据库当前 `created_at,id`，不接受客户端重排。
- 未保留的当前行一次性写 removed 人和时间，只允许从 NULL 变为非 NULL。
- 插入新附件并得到 ID。
- 解析 `audit["changed_fields_json"]`，把 old/new/added/removed IDs 合入 `record_attachments` 后重新序列化，再写审计。

- [ ] **Step 6: 扩展删除并运行存储测试**

`delete_record()` 在删除审计和主记录前，同时删除 `RECORD_ATTACHMENTS` 和现有确认附件。运行：

`python -m pytest -q tests/modules/report_special_processing/test_storage.py`

Expected: PASS。

---

### Task 4: 在服务层完成权限、总量、去重和审计摘要

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/service.py`
- Modify: `tests/modules/report_special_processing/test_service.py`

**Interfaces:**
- Consumes: Task 1 validator、Task 3 storage 扩展、现有 create/edit 权限和 row_version。
- Produces: 支持 `record_attachments` 的 `create()`、`update()`、`get_record_attachment()` 和附件审计摘要。

- [ ] **Step 1: 写服务创建和更新失败测试**

在 FakeStorage 中实现 Task 3 的参数签名。测试：

- 创建省略字段等同无附件。
- 创建附件使用 create 权限。
- 更新省略字段保持不变。
- 显式空集合移除全部。
- 只改附件形成 update 审计并递增版本。
- 已完成/作废和非创建人按现有 can_edit 拒绝。
- retained ID 跨记录或已移除时返回 400。

- [ ] **Step 2: 运行服务测试并确认失败**

Run: `python -m pytest -q tests/modules/report_special_processing/test_service.py -k "record_attachment"`

Expected: FAIL，因为服务尚未解析和传递附件变化。

- [ ] **Step 3: 实现最终集合校验**

新增服务 helper `_validated_record_attachment_change(self, payload: Mapping[str, Any], *, creating: bool, current: Sequence[Mapping[str, Any]] = ()) -> RecordAttachmentChange | None`。

规则：

- 调用 Task 1 validator。
- 更新时校验 retained IDs 全部属于 current active rows。
- 合并 retained 元数据和 new files 后重新验证最多 10 个、总原始字节最多 30 MiB。
- 对 retained 哈希和新哈希统一去重；同名不同哈希允许。
- 集合级错误统一为 `ValidationError(fields={"record_attachments": "附件数量、大小或引用无效"})`；单文件错误使用 `record_attachments.<client_id>` 字段。

- [ ] **Step 4: 接入 create/update 和审计摘要**

`create()` 调用 helper 后把 change 与 actor 快照传给 storage。`update()` 先取当前附件，再验证 change；`catalog()` 的 `limits.record_attachments` 返回 `max_count/max_file_bytes/max_total_bytes/allowed_extensions`。附件集合变化时把动作摘要补成：

- 仅附件变化：`修改附件（新增 N 个，移除 M 个）`
- 同时有字段变化：保留现有摘要并追加 `；附件新增 N 个、移除 M 个`

不把附件内容、Base64 或完整文件名写入应用日志。

- [ ] **Step 5: 增加历史读取权限测试并实现**

新增：

```python
def get_record_attachment(
    self,
    record_id: int,
    attachment_id: int,
    current_user: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    self.get(record_id, current_user)
    item = self.storage.get_record_attachment(record_id, attachment_id)
    if item is None:
        raise RecordNotFoundError()
    return item
```

测试当前和 removed 历史附件都可读取，跨记录 ID 返回统一 not found，避免泄露。

- [ ] **Step 6: 运行服务测试**

Run: `python -m pytest -q tests/modules/report_special_processing/test_service.py`

Expected: PASS，现有确认附件测试仍通过。

---

### Task 5: 扩展详情、审计和文件下载 API

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/storage.py`
- Modify: `src/auto_check/modules/report_special_processing/service.py`
- Modify: `src/auto_check/modules/report_special_processing/api.py`
- Modify: `tests/modules/report_special_processing/test_api.py`
- Modify: `tests/modules/report_special_processing/test_history.py`
- Modify: `tests/modules/report_special_processing/test_storage.py`

**Interfaces:**
- Consumes: 当前/历史附件存储行和审计 `old_ids/new_ids`。
- Produces: 详情 `record_attachments`、列表 `record_attachment_count`、审计双栏元数据、下载路由。

- [ ] **Step 1: 写详情和列表契约失败测试**

断言 GET detail 返回完整当前元数据但无 content；list 每项只返回 `record_attachment_count`，不返回附件数组或字节。

- [ ] **Step 2: 实现批量附件计数与详情附加**

在 storage 列表查询后，对当前页记录 ID 一次 group-by 查询 `removed_at IS NULL` 计数。`_get_with_connection()` 附加按 `created_at,id` 排序的当前元数据。导出和历史 provider 不应装载文件字节。

- [ ] **Step 3: 写审计水化失败测试**

构造三次附件变化：`[] -> [A,B] -> [B,C] -> [C]`，然后把 B、C 的 removed_at 改为后续状态。断言第二次审计仍按自身集合返回：

```python
field = audit_items[1]["changed_fields"]["record_attachments"]
assert [(x["id"], x["change"]) for x in field["old"]] == [(A, "removed"), (B, "retained")]
assert [(x["id"], x["change"]) for x in field["new"]] == [(B, "retained"), (C, "added")]
```

并用 SQL 事件计数断言附件元数据只执行一次批量查询，不随附件数量增长。

- [ ] **Step 4: 实现审计批量水化**

`storage.audit()` 在同一个 connection 中解析当前页 changed_fields，收集全部 old/new IDs，一次查询不可变元数据。输出：

```python
record_field["old"] = [
    {**metadata[id], "change": "retained" if id in new_ids else "removed"}
    for id in old_ids
]
record_field["new"] = [
    {**metadata[id], "change": "retained" if id in old_ids else "added"}
    for id in new_ids
]
```

不得使用附件行当前 removed_at 推断某条历史审计的 change。

- [ ] **Step 5: 写下载 API 失败测试**

覆盖当前和历史附件下载、UTF-8 文件名、正确长度、`nosniff`、跨记录、无详情权限。模块响应至少包含：

```python
return ModuleHttpResponse.bytes(
    200,
    bytes(payload["content"]),
    content_type=str(payload["content_type"]),
    headers=(("Content-Disposition", encoded_attachment_filename(payload["file_name"])),),
)
```

- [ ] **Step 6: 注册路由和独立请求上限**

新增 `GET /records/{id}/attachments/{attachment_id}`，权限使用 detail，`max_body_bytes=0`。POST `/records` 和 PUT `/records/{id}` 单独使用 `MAX_RECORD_ATTACHMENT_REQUEST_BYTES`；status、void、reopen、delete 保持当前各自上限。

增加边界测试：45 MiB 内进入模块处理，超过 45 MiB 被模块路由拒绝；平台 `MAX_UPLOAD_BYTES` 仍为 50 MiB；非附件路由没有被扩容。

- [ ] **Step 7: 运行后端 API、历史和存储测试**

Run:

```powershell
python -m pytest -q tests/modules/report_special_processing/test_api.py
python -m pytest -q tests/modules/report_special_processing/test_history.py
python -m pytest -q tests/modules/report_special_processing/test_storage.py
python -m pytest -q tests/module_system/test_server_integration.py -k "body or limit or module"
```

Expected: 全部 PASS。

---

### Task 6: 新建独立前端附件编辑器

**Files:**
- Create: `src/auto_check/modules/report_special_processing/web/components/record_attachments.js`
- Modify: `tests/modules/report_special_processing/test_frontend_static.py`
- Create: `tests/modules/report_special_processing/test_record_attachments_frontend.py`

**Interfaces:**
- Consumes: File、FileReader、SubtleCrypto、clipboardData、catalog attachment limits、附件下载回调。
- Produces: `createRecordAttachmentSection(documentRef, options)` 和 `renderRecordAttachmentSnapshot(documentRef, options)`。

- [ ] **Step 1: 写 Node 状态场景失败测试**

用最小 DOM/FileReader/crypto stub 覆盖上传与粘贴进入同一状态：

```javascript
const section = createRecordAttachmentSection(documentRef, {
  recordId: 7,
  initialAttachments: [{ id: 12, file_name: "old.xlsx", byte_size: 10 }],
  editable: true,
  limits: { max_count: 10, max_file_bytes: 10485760, max_total_bytes: 31457280 },
  notify,
  fetchAttachment,
});
await section.addFiles([new File([pngBytes], "new.png", { type: "image/png" })]);
assert.deepEqual((await section.buildChangePayload()).retained_ids, [12]);
assert.equal((await section.buildChangePayload()).new_files[0].file_name, "new.png");
```

测试移除现有附件、移除未保存附件、同哈希拒绝、同名不同内容允许、纯文字 paste 不 preventDefault、文件 paste preventDefault。

- [ ] **Step 2: 运行前端状态测试并确认失败**

Run: `python -m pytest -q tests/modules/report_special_processing/test_record_attachments_frontend.py`

Expected: FAIL，因为组件不存在。

- [ ] **Step 3: 实现组件公开接口**

实现并导出两个明确接口：`createRecordAttachmentSection(documentRef, options)` 返回冻结对象 `{element, addFiles, buildChangePayload, hasPendingWork, destroy}`；`renderRecordAttachmentSnapshot(documentRef, {recordId, attachments, fetchAttachment, previewImage, notify})` 返回只读附件卡片容器。

内部状态区分 persisted metadata 与 local File，不把 Base64 写入 DOM 属性或 storage。图片本地预览使用 object URL；上传 input 允许 multiple。

- [ ] **Step 4: 实现粘贴、前端限制和序列化**

- drawer 内 paste 只有在 `clipboardData.files/items` 含文件时处理；纯文字不拦截。
- 按扩展名和 MIME 做快速过滤；最终信任后端。
- 计算 SHA-256 用 `crypto.subtle.digest`；API 不可用时跳过前端去重但不阻止添加。
- 每次添加后校验当前数量 10、单个 10 MiB、总量 30 MiB。
- 无名图片按 MIME 生成 `粘贴图片-YYYYMMDD-HHmmss-N.<ext>`。
- `buildChangePayload()` 没变化返回 null；有变化返回两个显式数组，File 转 Base64 时只保留纯 Base64 数据。
- destroy 撤销全部 object URL、移除 paste/change 监听器并使未完成 FileReader 结果失效。

- [ ] **Step 5: 增加展示和可访问性测试**

断言图片卡、Office/ZIP 图标、文件名、大小、上传按钮、危险删除按钮、aria-label、只读无增删、全局圆角变量和无光晕样式约束。

- [ ] **Step 6: 运行组件测试**

Run: `python -m pytest -q tests/modules/report_special_processing/test_record_attachments_frontend.py tests/modules/report_special_processing/test_frontend_static.py -k "attachment or paste or upload"`

Expected: PASS。

---

### Task 7: 接入记录抽屉的保存、详情、预览和下载

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/web/api.js`
- Modify: `src/auto_check/modules/report_special_processing/web/components/record_drawer.js`
- Modify: `src/auto_check/modules/report_special_processing/web/styles.css`
- Modify: `tests/modules/report_special_processing/test_frontend_static.py`
- Modify: `tests/modules/report_special_processing/test_record_attachments_frontend.py`

**Interfaces:**
- Consumes: Task 5 下载路由、Task 6 组件、登录恢复计划提供的 `context.api(..., {responseType: "raw"})`。
- Produces: `fetchRecordAttachment(recordId, attachmentId)`、带 `authPreflight` 的附件 create/update payload 和详情附件区。

- [ ] **Step 1: 写 raw 下载失败测试**

在 API 场景中断言附件请求使用平台 raw 模式而不是原生 fetch：

```javascript
const result = await api.fetchRecordAttachment(7, 14);
assert.equal(contextCalls[0].path, "/api/modules/report-special-processing/records/7/attachments/14");
assert.equal(contextCalls[0].options.responseType, "raw");
assert.equal(result.filename, "处理依据.xlsx");
assert.equal(result.blob.size, expectedBytes.length);
```

- [ ] **Step 2: 实现附件下载 API**

复用 `filenameFromDisposition()` 和统一 raw 响应解析。无专用认证标识的非 2xx 仍进入现有 normalizeError；空 Blob 报“附件内容为空”。公开方法名固定为 `fetchRecordAttachment`。

- [ ] **Step 3: 写保存抽屉失败测试**

覆盖 create、save draft、update：等待附件 build 完成，把非 null 结果写入 `payload.record_attachments`，只点击一次保存。附件字段存在时 API options 必须包含 `authPreflight: true`，字段省略时不增加预检。普通无认证标识的 409、400、网络失败时不销毁附件组件；带 account-mismatch 的 409 由平台接管且不进入模块错误链；成功后只调用一次 onSaved。

- [ ] **Step 4: 接入附件区域和异步保存**

在 `createRecordDrawer()` 构建一次 attachment section：

```javascript
const recordAttachments = createRecordAttachmentSection(documentRef, {
  recordId: current.id || null,
  initialAttachments: current.record_attachments || [],
  editable: canEdit,
  limits: catalog?.limits?.record_attachments,
  notify: options.notify,
  fetchAttachment: actions.fetchRecordAttachment,
});

async function buildSavePayload(saveMode) {
  const payload = draftPayload(fields, saveMode, creating ? null : current.row_version, resolveHandlingAt());
  const attachmentChange = await recordAttachments.buildChangePayload();
  if (attachmentChange) payload.record_attachments = attachmentChange;
  return payload;
}
```

saveDraft/saveRecord 在现有 run 回调内 await buildSavePayload，避免 Base64 读取期间重复提交。关闭抽屉时调用 destroy。

`web/api.js` 的 `createRecord/updateRecord` 在 payload 自有属性 `record_attachments` 存在时，为 `context.api` options 增加 `authPreflight: true`；该逻辑只声明大 body 发送前需要平台会话预检，不在模块中请求认证端点、显示登录 UI 或保存密码。

- [ ] **Step 5: 实现详情预览与下载**

图片点击时调用 `fetchRecordAttachment` 得到 Blob，再创建预览 URL；Office/ZIP 点击下载。下载临时 URL 点击后立即撤销；预览 URL 在关闭大图时撤销。现有确认图片预览逻辑保持不变。

- [ ] **Step 6: 运行抽屉与 API 测试**

Run: `python -m pytest -q tests/modules/report_special_processing/test_frontend_static.py tests/modules/report_special_processing/test_record_attachments_frontend.py`

Expected: PASS。

---

### Task 8: 在操作记录渲染修改前后附件快照

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/web/components/record_drawer.js`
- Modify: `src/auto_check/modules/report_special_processing/web/components/record_attachments.js`
- Modify: `src/auto_check/modules/report_special_processing/web/styles.css`
- Modify: `tests/modules/report_special_processing/test_record_attachments_frontend.py`
- Modify: `tests/modules/report_special_processing/test_frontend_static.py`

**Interfaces:**
- Consumes: Task 5 审计字段 `record_attachments.old/new`，每项带 `change=added|removed|retained`。
- Produces: 双栏附件快照、附件变更摘要和历史预览/下载。

- [ ] **Step 1: 写双栏渲染失败测试**

给 `describeAuditEntry` 输入 old `[A removed, B retained]`、new `[B retained, C added]`，断言附件字段不计入普通字符串 pair，而生成专用 attachmentDiff。DOM 必须包含“修改前”“修改后”“新增”“移除”“保留”。

- [ ] **Step 2: 实现审计描述模型**

在处理 changedFields 时识别 `record_attachments`：

```javascript
if (key === "record_attachments") {
  attachmentDiff = {
    old: Array.isArray(meta.old) ? meta.old : [],
    new: Array.isArray(meta.new) ? meta.new : [],
  };
  return;
}
```

只附件变化时摘要使用服务端 action_summary；不把附件对象 JSON.stringify 到普通单元格。

- [ ] **Step 3: 实现双栏和响应式样式**

使用 `renderRecordAttachmentSnapshot` 分别渲染 old/new；附件卡显示变化 badge。宽屏两列，窄屏上下排列。历史图片和文件仍通过 `fetchRecordAttachment(recordId,id)` 获取。

- [ ] **Step 4: 覆盖后续软删除不污染历史**

Node 测试向元数据加入 `removed: true`，但 change 给 `retained`，断言 UI 显示“保留”而不是依据 removed 字段改成“移除”。

- [ ] **Step 5: 运行审计前端测试**

Run: `python -m pytest -q tests/modules/report_special_processing/test_record_attachments_frontend.py tests/modules/report_special_processing/test_frontend_static.py -k "audit or attachment or history"`

Expected: PASS。

---

### Task 9: 验证登录超时带附件保存只执行一次

**Files:**
- Modify: `tests/test_auth_recovery_frontend.py`
- Modify: `tests/modules/report_special_processing/test_record_attachments_frontend.py`
- Modify: `tests/modules/report_special_processing/test_api.py`

**Interfaces:**
- Consumes: 登录恢复计划实现的专用 401 响应头、可重放字符串 body 和最新 CSRF Token。
- Produces: 带附件 POST/PUT 在会话恢复后的端到端回归证据。

- [ ] **Step 1: 写带附件 POST 恢复场景**

构造已序列化的保存 body，第一次 fetch 返回带 `X-Auto-Check-Auth-Recovery: required` 的 401，重新认证后第二次返回 201。断言：

- 两次 body 字符串逐字节相同。
- 第二次使用新 CSRF Token。
- 每次业务请求携带与当时 authState 一致的 X-Auto-Check-Expected-User-Id。
- 表单文本、本地 File 和缩略图保持。
- createRecord 最终 resolve 一次，onSaved 一次。
- 模块后端处理计数为 1，附件插入数为预期值。

另用超过 64 KiB 的附件 JSON 测试点击保存时会话已经过期：authPreflight 的 status 检查先发现未认证，业务 body 在重新认证成功前发送次数为 0，成功后只发送 1 次。状态检查发现其他账号或网络失败时，业务 body 始终发送 0 次。

再模拟预检返回原用户后、业务请求发送前 Cookie 被另一个标签页切换：后端根据 expected user header 在处理器前返回 account-mismatch，模块处理计数和附件插入数均为 0。

- [ ] **Step 2: 写不自动重放场景**

覆盖无专用头业务 401、400、普通 409、500、网络失败均只发一次；附件和表单仍保留。带 account-mismatch 的 409 由平台进入 discarding 并注销，不交给模块且不重试。AbortSignal 在遮罩期间取消时不发第二次。

- [ ] **Step 3: 运行组合测试**

Run:

```powershell
python -m pytest -q tests/test_auth_recovery_frontend.py
python -m pytest -q tests/modules/report_special_processing/test_record_attachments_frontend.py
python -m pytest -q tests/modules/report_special_processing/test_api.py
```

Expected: 全部 PASS；若前置 401 时模块处理计数不为 0，停止实施并报告安全前提失效。

---

### Task 10: 同步模块说明、版本和完整验证

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/README.md`
- Modify: `docs/report-special-processing-module.zh-CN.md`
- Modify: `src/auto_check/modules/report_special_processing/manifest.json`
- Modify: `README.md`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_package_smoke.py`
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Consumes: Tasks 1–9 完成行为和登录恢复 `v1.2.23` 条目。
- Produces: 模块 1.2.13、schema 6、应用 v1.2.23 的一致文档与验证证据。

- [ ] **Step 1: 写版本和迁移清单失败测试**

断言：

- manifest `version == "1.2.13"`、`schema_version == 6`。
- release_notes 只含“支持为报表特殊处理记录粘贴或上传图片、Excel、Word、ZIP 附件，并在修改记录中查看新旧附件”。
- 应用内存在一个 `v1.2.23` 条目，不重复；平台登录恢复功能明确列出，模块条目按现有注入规则出现；“系统优化及BUG修复”最多一条。
- `DEFAULT_VERSION` 仍为 `V1.2`。
- 打包迁移清单包含 006。

- [ ] **Step 2: 更新模块和正式文档**

模块 README 与正式说明写清：

- 模块现有表从五张变为六张。
- 记录附件与确认附件的差异。
- 类型、数量、大小、历史保留、权限和删除规则。
- 粘贴依赖浏览器暴露 clipboard file，上传为稳定兜底。
- Office/ZIP 只下载不在线预览，旧 OLE 类型与无恶意软件扫描限制。

- [ ] **Step 3: 合并根 README 和应用更新日志**

根 README 的 v1.2.23 同时详细记录登录超时恢复和记录附件。应用日志不新增第二个 v1.2.23 块；模块 release_notes 不写通用 BUG 修复条目。

- [ ] **Step 4: 运行直接相关后端测试**

Run:

```powershell
python -m pytest -q tests/modules/report_special_processing/test_validator_and_permissions.py
python -m pytest -q tests/modules/report_special_processing/test_manifest_and_migrations.py
python -m pytest -q tests/modules/report_special_processing/test_storage.py
python -m pytest -q tests/modules/report_special_processing/test_service.py
python -m pytest -q tests/modules/report_special_processing/test_api.py
python -m pytest -q tests/modules/report_special_processing/test_history.py
```

Expected: 全部 PASS。

- [ ] **Step 5: 运行直接相关前端和平台测试**

Run:

```powershell
python -m pytest -q tests/modules/report_special_processing/test_frontend_static.py
python -m pytest -q tests/modules/report_special_processing/test_record_attachments_frontend.py
python -m pytest -q tests/test_auth_recovery_frontend.py
python -m pytest -q tests/test_web_static.py
python -m pytest -q tests/test_package_smoke.py
python -m pytest -q tests/test_security.py
python -m pytest -q tests/module_system/test_server_integration.py
```

Expected: 全部 PASS。

- [ ] **Step 6: 由验证子代理运行全量检查**

Run:

```powershell
python -m pytest -q
git diff --check
git status --short
```

Expected: 全量 pytest PASS；`git diff --check` 无真实 whitespace error；相对开发前基线只出现两项已批准需求涉及的文件，用户原有修改保持不变。

- [ ] **Step 7: 人工验收**

按以下顺序实际操作：

1. 新建记录，粘贴图片，上传 XLS/XLSX、DOC/DOCX、ZIP，保存并逐项预览或下载。
2. 编辑该记录，移除旧图片，添加同名不同内容的新图片，只改附件并保存。
3. 展开修改记录，验证修改前/后双栏、变化标签和历史文件读取。
4. 验证 10 个、10 MiB、30 MiB 边界以及重复内容、非法类型和跨记录访问。
5. 验证完成/作废只读，重开后可编辑附件。
6. 验证现有确认说明的 3 张粘贴图片不受影响。
7. 在带附件保存前使会话过期，验证原账号重登后只创建一条记录和一组附件。

- [ ] **Step 8: 交付说明**

按“代码内容、数据库迁移、界面与行为、文档与版本、测试证据、未执行事项”报告。明确列出未打包、未提交、未推送。
