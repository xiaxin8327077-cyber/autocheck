# 人行逐笔报文、三页面与总验收实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以“资管产品模板逐笔”交付首个个性化 16 文件报文生成器，并完成报表生成、报表校验、配置管理三个模块页面及端到端验收。

**Architecture:** 公共报文框架锁定 profile 和 mapping snapshot，流式读取报送库，调用内置格式器在临时区生成并校验文件，然后原子保存到永久 artifact storage。前端按模块生命周期加载，所有页面共享左侧报送选择和查询状态，但生成、校验、报文历史仍是独立 API 与独立记录。

**Tech Stack:** Python 3.12、openpyxl、BIFF8 `.xls` 纯 Python 写入库、zipfile、原生 JavaScript/CSS、pytest。

## Global Constraints

- 必须先完成平台、模块基础和 SQL 校验三份计划。
- `docs/superpowers/specs/2026-09-03-db-validation-message-export-design.md` 只作为“资管产品模板逐笔”的 16 文件结构、命名、数据类型和样式契约；其中旧的核心工具接线、映射表复用、API 命名和 UI 位置被当前独立模块设计取代。
- 不修改现有 `src/auto_check/db_validation/` 的逐笔校验行为，不把新功能接回旧弹窗。
- 报文生成读取执行时当前数据库数据，不声称对应某次生成或校验的数据版本。
- 校验失败、异常或未执行均不拦截报文生成和下载。
- 每次生成新版本，不覆盖旧文件；全部文件成功且结构校验通过后才登记成功。
- 只有“资管产品模板逐笔”安装格式器；其他六类不能通过 API 绕过页面生成报文。
- 历史报送期只查看和下载；当前报送期可重新生成最新报文。
- 前端不使用图片作为主要 UI，不新增主题切换、暗色模式或硬编码第二套圆角/颜色。
- 可见 UI 完成后更新 README 和当前系统更新日志，不修改展示大版本。
- 不自动打包、不提交、不推送。

---

## 文件结构

### 报文后端

- `src/auto_check/modules/regulatory_reporting/message_export/contracts.py`
- `src/auto_check/modules/regulatory_reporting/message_export/registry.py`
- `src/auto_check/modules/regulatory_reporting/message_export/source.py`
- `src/auto_check/modules/regulatory_reporting/message_export/xlsx_writer.py`
- `src/auto_check/modules/regulatory_reporting/message_export/xls_writer.py`
- `src/auto_check/modules/regulatory_reporting/message_export/validator.py`
- `src/auto_check/modules/regulatory_reporting/message_export/service.py`
- `src/auto_check/modules/regulatory_reporting/message_export/coordinator.py`
- `src/auto_check/modules/regulatory_reporting/message_export/resources/`
- `src/auto_check/modules/regulatory_reporting/migrations/007_message_history.sql`

### 前端

- `src/auto_check/modules/regulatory_reporting/web/index.js`
- `src/auto_check/modules/regulatory_reporting/web/api.js`
- `src/auto_check/modules/regulatory_reporting/web/state.js`
- `src/auto_check/modules/regulatory_reporting/web/styles.css`
- `src/auto_check/modules/regulatory_reporting/web/components/report_selector.js`
- `src/auto_check/modules/regulatory_reporting/web/components/run_log.js`
- `src/auto_check/modules/regulatory_reporting/web/components/history_table.js`
- `src/auto_check/modules/regulatory_reporting/web/components/modal.js`
- `src/auto_check/modules/regulatory_reporting/web/components/audit_drawer.js`
- `src/auto_check/modules/regulatory_reporting/web/pages/generation.js`
- `src/auto_check/modules/regulatory_reporting/web/pages/validation.js`
- `src/auto_check/modules/regulatory_reporting/web/pages/configuration.js`
- `src/auto_check/modules/regulatory_reporting/web/pages/config/report_profile.js`
- `src/auto_check/modules/regulatory_reporting/web/pages/config/workflow.js`
- `src/auto_check/modules/regulatory_reporting/web/pages/config/rules.js`

### 测试与文档

- `tests/modules/regulatory_reporting/test_message_contracts.py`
- `tests/modules/regulatory_reporting/test_message_source.py`
- `tests/modules/regulatory_reporting/test_message_xlsx.py`
- `tests/modules/regulatory_reporting/test_message_xls.py`
- `tests/modules/regulatory_reporting/test_message_service.py`
- `tests/modules/regulatory_reporting/test_message_api.py`
- `tests/modules/regulatory_reporting/test_frontend_static.py`
- `tests/modules/regulatory_reporting/test_end_to_end.py`
- `src/auto_check/modules/regulatory_reporting/README.md`
- `README.md`
- `src/auto_check/modules/regulatory_reporting/manifest.json`（通过 `release_notes` 提供模块更新条目）

## 报文接口冻结

```python
# message_export/contracts.py
@dataclass(frozen=True)
class MessageGenerationRequest:
    report_code: str
    report_period: str
    actor_id: str
    actor_name: str

@dataclass(frozen=True)
class MessageFile:
    relative_path: str
    filename: str
    artifact_id: str
    content_type: str
    size: int
    sha256: str

class MessageFormatter(Protocol):
    report_code: str
    def build(self, context: "MessageBuildContext") -> tuple[Path, ...]: ...
    def validate(self, context: "MessageBuildContext", files: tuple[Path, ...]) -> None: ...

@dataclass(frozen=True)
class MessageBuildContext:
    report_period: str
    profile: ReportProfile
    mapping_snapshot_id: str
    temporary_directory: Path
    data_sources: DataSourcesFacade
```

报送编码不能在代码中猜测。安装 pilot formatter 时，从 `platform.report_navigation` 返回项中按稳定编码配置选择；首次环境启动若找不到唯一“资管产品模板逐笔”编码，模块健康状态返回 degraded 并要求管理员绑定一次 `pilot_formatter_report_code`。

## Task 1：通用格式器注册、历史和原子文件版本

**Files:**
- Create: `message_export/contracts.py`
- Create: `message_export/registry.py`
- Create: `message_export/service.py`
- Create: `message_export/coordinator.py`
- Create: `migrations/007_message_history.sql`
- Modify: `manifest.json`（`schema_version=7`）
- Modify: `module.py`
- Modify: `api.py`
- Test: `test_message_service.py`
- Test: `test_message_api.py`

**Interfaces:**
- Consumes: 当前 profile、活动 mapping snapshot、`DataSourcesFacade`、`ArtifactStorageFacade`。
- Produces: formatter registry、message run/history/file API。

- [ ] **Step 1: 写“未安装格式器”和不拦截失败测试**

```python
def test_only_pilot_report_has_formatter(service):
    assert service.capability("pbc_detail").available is True
    assert service.capability("1104").message == "该报送的报文格式尚未接入"

def test_validation_failure_does_not_block_message_generation(service):
    validation_store.latest_state = "failed"
    run = service.start(MessageGenerationRequest("pbc_detail", "2026-08-31", "1", "张三"))
    assert run.id
```

- [ ] **Step 2: 写新版本不覆盖失败测试**

同一报送期执行两次，断言两个 message_run_id、两个 bundle artifact_id、两组 file records 均不同，第一次仍可 stat/download。

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_message_service.py tests/modules/regulatory_reporting/test_message_api.py -q`

Expected: FAIL。

- [ ] **Step 4: 创建消息历史表**

`007_message_history.sql` 创建 message_runs 和 message_files。run 保存 report/name snapshot、report_period、profile_version、mapping_snapshot_id、formatter_id/version、状态、actor、日志和 bundle_artifact_id；file 保存 relative_path、artifact_id、size、sha256、content_type。

- [ ] **Step 5: 实现原子服务**

formatter 输出到模块 temp 目录；validate 全通过后，逐文件和 ZIP 写入 artifact storage；最后在一个数据库事务中登记成功 run/files。任一步失败，run 标 failed，不提供 bundle/file 下载地址，不覆盖旧记录。

- [ ] **Step 6: 实现 API 与权限**

固定路由：

- `GET /message-capability?report_code=...`
- `POST /message-runs`
- `GET /message-runs?report_code=&report_period=&page=&page_size=`
- `GET /message-runs/{run_id}`
- `GET /message-runs/{run_id}/download`
- `GET /message-files/{file_id}/download`

启动需要 generate_message；整包和单文件下载需要 download_message。后端再次校验历史期只读规则：历史期不允许 POST，新生成只能使用当前可操作报送期；GET/download 不限当前期。

- [ ] **Step 7: 运行专项测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_message_service.py tests/modules/regulatory_reporting/test_message_api.py -q`

Expected: PASS。

## Task 2：资管产品模板逐笔数据源投影与 14 个 `.xlsx`

**Files:**
- Create: `message_export/source.py`
- Create: `message_export/xlsx_writer.py`
- Create: `message_export/resources/pbc_detail_contract.json`
- Test: `test_message_contracts.py`
- Test: `test_message_source.py`
- Test: `test_message_xlsx.py`

**Interfaces:**
- Consumes: 总体模块 mapping snapshot；旧设计中的 14 个逐笔文件结构契约。
- Produces: `PbcDetailSource.iter_rows(role, period)`、`PbcDetailXlsxWriter.write(role, rows, path)`。

- [ ] **Step 1: 从参考包生成脱敏结构契约**

读取旧设计指定参考 ZIP，只提取文件名模式、工作表名、完整有序中文列、类型、数字格式、列宽、冻结窗格和关键样式；不得复制生产明细。将结果固定写入 `pbc_detail_contract.json` 并记录源 ZIP SHA-256 `c0883d9533829f8504f2151c1994df63fa9607df855b0e6caae80c9ceed29d17`。

- [ ] **Step 2: 写 14 文件契约失败测试**

断言 ZG01 新增与变更加 ZG02-ZG13 正好 14 文件，列数固定为 `42,42,9,8,19,156,38,34,8,50,52,103,29,23`，完整有序中文列逐项相等而非只比列数。

- [ ] **Step 3: 写双表和标识符安全失败测试**

ZG01 新增使用 mapping role `detail:ZG01`，变更使用 `detail:ZG01_CHANGE`；两者不能指向同一物理表；变更文件日期为报告日前一自然日。所有 SELECT 列由已验证映射逐列引用，禁止 `SELECT *`。

- [ ] **Step 4: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_message_contracts.py tests/modules/regulatory_reporting/test_message_source.py tests/modules/regulatory_reporting/test_message_xlsx.py -q`

Expected: FAIL。

- [ ] **Step 5: 实现流式投影**

按结构契约的中文字段顺序解析 mapping snapshot 最终物理列，任何缺失/冲突都指出 ZG 号和中文字段后整体失败。数据流按 1,000 行块读取，代码类和含前导零值保持文本，日期/Decimal/空值遵守契约。

- [ ] **Step 6: 实现 `.xlsx` 写入**

使用 write-only workbook 或等价流式模式，空表也写完整表头/样式/列宽/冻结窗格。工作表名称严格使用旧设计的 14 个名称；不允许自动截断或替换。

- [ ] **Step 7: 运行专项测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_message_contracts.py tests/modules/regulatory_reporting/test_message_source.py tests/modules/regulatory_reporting/test_message_xlsx.py -q`

Expected: PASS。

## Task 3：两份 BIFF8 `.xls` 模板与 16 文件结构校验

**Files:**
- Create: `message_export/xls_writer.py`
- Create: `message_export/validator.py`
- Create: `message_export/resources/template_2_skeleton.xls`
- Create: `message_export/resources/template_2a_skeleton.xls`
- Modify: `pyproject.toml`（加入经最小原型验证可保存 BIFF8 样式的纯 Python 写入依赖）
- Test: `test_message_xls.py`
- Test: `test_message_service.py`

**Interfaces:**
- Consumes: 脱敏后的两个 `.xls` 骨架、模板数据投影、旧设计 16 工作表契约。
- Produces: `PbcTemplateXlsWriter.write(kind, rows_by_sheet, path)`、`PbcDetailValidator.validate()`。

- [ ] **Step 1: 先做 BIFF8 能力证明测试**

用候选库打开骨架、修改一个指定数据单元格、保存并重新读取；逐项断言 OLE/BIFF8 签名、16 工作表顺序、合并区域、隐藏行列、行高、列宽、关键样式和静态文字不变。候选库不满足则停止实现并向用户报告依赖方案，不能把 `.xls` 改成 `.xlsx`。

- [ ] **Step 2: 写两个模板完整契约失败测试**

文件名分别为 `{YYYYMMDD}-2-{机构代码}-{机构名称}.xls` 与 `{YYYYMMDD}-2a-{机构代码}-{机构名称}.xls`；产品类型分别为 `02-信托公司信托产品` 和 `02a-资产管理信托`；16 工作表名称和顺序与旧设计完全一致。

- [ ] **Step 3: 写整包原子性失败测试**

任一文件缺失、列错序、工作表错误、机构信息不唯一或 writer 异常时，message run failed 且没有可下载 ZIP；正常时 ZIP 只有一级目录 `逐笔当期/`、14 xlsx、2 xls。

- [ ] **Step 4: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_message_xls.py tests/modules/regulatory_reporting/test_message_service.py -q`

Expected: FAIL。

- [ ] **Step 5: 生成脱敏骨架并实现写入**

骨架只保留结构、公式和静态说明，清除所有业务数据；测试扫描非静态数据区域确保没有参考包明细残留。写入后重新打开自检，再交给通用 service 封装。

- [ ] **Step 6: 实现机构信息交叉校验**

从逐笔和模板元数据提取机构代码/名称，去空白后必须各自唯一且互相一致；缺失或多值时失败，不猜默认机构。

- [ ] **Step 7: 运行专项测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_message_xls.py tests/modules/regulatory_reporting/test_message_service.py -q`

Expected: PASS。

## Task 4：模块前端壳、三主页签和左侧七报送

**Files:**
- Create: `web/index.js`, `web/api.js`, `web/state.js`, `web/styles.css`
- Create: `web/components/report_selector.js`, `web/components/modal.js`
- Create: `web/pages/generation.js`, `web/pages/validation.js`, `web/pages/configuration.js`
- Test: `test_frontend_static.py`

**Interfaces:**
- Consumes: 模块 host 的 `mount/activate/deactivate/unmount` context、`GET /catalog`。
- Produces: 一个模块根节点和三个主页签。

- [ ] **Step 1: 写生命周期与结构失败测试**

静态测试断言 export 的生命周期齐全；根节点有 `auto-check-module` 和 `data-module="regulatory_reporting"`；只出现三个主页签；不存在独立“报文下载”和“执行历史”主页签。

- [ ] **Step 2: 写主题与作用域失败测试**

所有 CSS 规则以模块作用域开头；实心主按钮可用 Logo 蓝渐变，空心/文字/危险按钮按语义色；不存在 dark/theme toggle、box-shadow 光晕或图片背景。

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_frontend_static.py -q`

Expected: FAIL。

- [ ] **Step 4: 实现共享状态**

state 只保存 activeTab、reportCode、reportPeriod、catalog、capabilities 和页面级缓存；切换报送时取消旧页面轮询并重新加载；配置页不显示也不请求 reportPeriod。

- [ ] **Step 5: 实现页面框架**

按已确认原型复刻真实导航密度和布局，不嵌入原型截图。顶部页签、左侧报送类型、内容区响应式布局统一复用组件；宽度不足时左侧选择变为下拉，但仍保持报送类型选择语义。

- [ ] **Step 6: 运行静态测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_frontend_static.py -q`

Expected: PASS。

## Task 5：报表生成页面和内嵌历史/下载

**Files:**
- Create: `web/components/run_log.js`
- Create: `web/components/history_table.js`
- Modify: `web/pages/generation.js`
- Modify: `web/api.js`
- Test: `test_frontend_static.py`
- Test: `test_end_to_end.py`

**Interfaces:**
- Consumes: generation API、message capability/history/download API。
- Produces: 当前任务步骤/日志、生成记录、报文版本和下载操作。

- [ ] **Step 1: 写行为失败测试**

断言 checkbox 默认 false；“生成报表”请求带 auto_validate；实时日志按 after_log_id 增量轮询；生成记录行内提供查看日志和报文操作；有成功报文时文案为“重新生成报文”。

- [ ] **Step 2: 写历史期只读失败测试**

历史期隐藏/禁用生成报表和生成/重新生成报文，只保留查看日志、查看文件、单文件下载和整包下载。校验状态不得控制报文按钮。

- [ ] **Step 3: 实现并运行测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_frontend_static.py tests/modules/regulatory_reporting/test_end_to_end.py -q`

Expected: PASS；页面关闭重开后从 API 恢复当前运行状态。

## Task 6：校验页面、动态明细和配置三个子页签

**Files:**
- Create: `web/components/audit_drawer.js`
- Modify: `web/pages/validation.js`
- Create: `web/pages/config/report_profile.js`
- Create: `web/pages/config/workflow.js`
- Create: `web/pages/config/rules.js`
- Modify: `web/pages/configuration.js`
- Test: `test_frontend_static.py`
- Test: `test_end_to_end.py`

**Interfaces:**
- Consumes: validation/config/mapping/workflow API。
- Produces: 校验执行与历史、动态明细弹窗、报送数据/流程编排/校验配置。

- [ ] **Step 1: 写校验页面失败测试**

顶部只有报送期、分组多选和开始校验；统计卡分别显示规则总数、已完成、通过、不通过、异常、错误明细行；同报送期多次记录按时间倒序，不与生成历史合并。

- [ ] **Step 2: 写动态明细失败测试**

服务返回 columns=a,b,c,d 且 visible=a,b,d 时表格只渲染 a,b,d；分页每次调用后端；“下载完整明细”不受 visible 过滤。

- [ ] **Step 3: 写配置页失败测试**

内部只显示“报送数据配置、流程编排、校验配置”三个子页签。报送数据表单无 table ID 手填框；流程可拖排 kjb/ktr/spider；规则表单无定位字段、权重、有效期、自定义 SQL 开关，展示字段由检测结果带出并可取消显示。

- [ ] **Step 4: 实现审计抽屉**

交互参照 `report_special_processing/web/components/record_drawer.js` 的操作记录：时间、操作者、动作，展开显示字段/修改前/修改后；不直接导入其他业务模块文件。

- [ ] **Step 5: 实现并运行测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_frontend_static.py tests/modules/regulatory_reporting/test_end_to_end.py -q`

Expected: PASS。

## Task 7：文档、全量回归和浏览器验收

**Files:**
- Modify: `src/auto_check/modules/regulatory_reporting/README.md`
- Modify: `README.md`
- Modify: `src/auto_check/modules/regulatory_reporting/manifest.json`（模块 `release_notes`）
- Modify Test: `tests/test_web_static.py`

- [ ] **Step 1: 更新文档**

模块 README 记录架构、三类独立任务、API、并发、永久存储、外部 Kettle 配置、恢复和运维备份。根 README 详细列出七类报送、三页面、SQL 动态明细和 pilot 16 文件输出。

- [ ] **Step 2: 更新系统日志**

在模块 manifest 的当前模块版本 `release_notes.items` 中加入：`新增报表生成、SQL校验、配置管理及资管产品模板逐笔报文生成`；平台会自动显示为“报送管理模块：…”。模块 release notes 不写“系统优化及BUG修复”，不直接修改全局 `app.js`，不修改展示大版本。

- [ ] **Step 3: 运行专项测试**

Run: `python -m pytest tests/modules/regulatory_reporting -q`

Expected: PASS。

- [ ] **Step 4: 运行全部测试**

Run: `python -m pytest -q`

Expected: PASS，退出码 0。

- [ ] **Step 5: 运行差异检查**

Run: `git diff --check`

Expected: 无实际 whitespace error。

- [ ] **Step 6: 启动源码应用做浏览器验收**

使用临时测试配置和测试数据库启动源码服务，不占用生产 `8765`。按总路线图第 4 节的 11 步人工验收剧本逐项截图/记录；不得用静态原型代替真实页面验收。

- [ ] **Step 7: 检查敏感信息和永久文件**

在 API 响应、日志、数据库快照和 artifact manifest 中搜索生产 host/password/token/绝对路径；预期均不存在。备份说明必须同时包含应用数据库和 `module-artifacts/regulatory_reporting/`。

- [ ] **Step 8: 用户授权后提交检查点**

```powershell
git add src/auto_check/modules/regulatory_reporting README.md pyproject.toml tests/modules/regulatory_reporting tests/test_web_static.py
git commit -m "交付报送管理页面和人行逐笔报文"
```

- [ ] **Step 9: 仅在用户明确要求时打包或推送**

用户要求打包时，先确认没有运行中的 `dist/auto-check.exe`，再执行 `pwsh -NoLogo -NoProfile -File scripts/package-windows.ps1`。用户要求推送时，按仓库规则推送当前分支；否则不执行这两步。
