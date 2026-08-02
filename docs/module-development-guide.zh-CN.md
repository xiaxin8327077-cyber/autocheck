# Auto Check 内置模块开发指南

本文面向新增 Auto Check 业务模块的开发人员。模块是随项目源码和安装包发布的**可信内置扩展**，共享应用进程和受控平台服务；它不是第三方插件沙箱，不提供在线上传、下载或执行 Python/JavaScript 插件的入口。本指南不实现也不预留自定义报表功能。

开始前必须阅读仓库 `AGENTS.md`、`docs/ai-modular-development-rules.zh-CN.md` 和本模块的设计/实施计划。普通模块仅可新增 `src/auto_check/modules/<module_id>/` 与 `tests/modules/<module_id>/`；正式模块目录不得保留 demo、示例业务或未接入的模板代码。需要修改 `server.py`、`app.js`、`module_system`、公共打包脚本或全局数据库协议时，先提交独立平台变更方案并经评审，不能夹带在模块业务提交中。

## 1. 清单与命名空间

每个模块必须在包根目录提供 `manifest.json`，至少声明：

```json
{
  "id": "example_module",
  "name": "示例模块",
  "version": "1.0.0",
  "platform_api": 1,
  "required": false,
  "backend_entry": "auto_check.modules.example_module.module:create_module",
  "api_prefix": "/api/modules/example-module",
  "frontend_entry": "/module-assets/example_module/index.js",
  "frontend_style": "/module-assets/example_module/styles.css",
  "navigation": [
    {
      "id": "example_module",
      "label": "示例模块",
      "route": "example-module",
      "order": 100,
      "permission": "example_module.view"
    }
  ],
  "permissions": ["example_module.view"],
  "dependencies": [],
  "service_dependencies": [
    {
      "name": "platform.user_directory",
      "minimum_version": 1
    }
  ],
  "services": [
    {
      "name": "example_module.lookup",
      "version": 1
    }
  ],
  "release_notes": {
    "version": "1.0.0",
    "items": ["新增示例模块功能"]
  },
  "table_prefix": "example_module_",
  "schema_version": 0
}
```

模块 ID 以小写字母开始，只包含小写字母、数字和下划线。API 必须使用模块独占的 `/api/modules/` 前缀，API 前缀之间也不得形成父子嵌套；权限使用 `<module_id>.<action>`；表名、静态资源、事件和 DOM 根节点分别使用模块前缀，例如 `example_module_items`、`/module-assets/example_module/`、`example_module:item_created`、`data-module="example_module"`。前端资源 URL 不得包含编码字符、查询、片段、反斜杠、空路径段或 `.`/`..`，导航路由不得占用 `report-navigation`、`home`、`auto-check`、`history`、`tools`、`settings`、`users` 等既有页面。`table_prefix` 默认是 `<module_id>_`，仅名称以 `s` 结尾的模块可显式选择对应单数前缀。清单 ID、API、导航 ID/路由、权限、表前缀和公开服务均须全局唯一，表前缀也不得互相包含；冲突模块会在导入工厂和执行迁移前停止加载。

新业务模块默认 `required=false`：包资源、清单读取/解析/校验、依赖规划、迁移或启动失败只隔离该模块及其依赖方，不能阻止核心系统及无关健康模块启动；管理员状态中仅展示固定脱敏原因。只有清单中可可靠识别的 `required=true` 问题才按必选模块阻止启动。只有发布包中的可信代码可被发现和加载。

`release_notes` 为可选的版本化发布说明。旧清单缺少该字段时按无发布说明处理；声明时只允许 `version` 和 `items`，版本必须为 `MAJOR.MINOR.PATCH` 且与模块 `version` 一致。`items` 为 1 至 20 条去首尾空格后的非空、无重复纯文本，每条最多 200 字符。当前启用且不在生命周期切换中的模块会由平台独立聚合到“关于 → 更新日志”，不受当前用户导航权限或模块是否声明导航影响；禁用、失败和不兼容模块不会展示。新增功能写具体功能；界面布局、美化、体验优化和问题修复统一写“系统优化及BUG修复。”，不得展开细节。模块不得修改 `app.js` 静态更新日志，也不得把 HTML 或脚本写入发布说明。

## 2. 推荐目录和职责

```text
src/auto_check/modules/<module_id>/
├── __init__.py
├── manifest.json
├── module.py
├── api.py
├── contracts.py
├── service.py
├── storage.py
├── migrations/
│   └── 001_initial.sql
└── web/
    ├── index.js
    ├── styles.css
    ├── pages/
    └── components/
```

可按职责增加 `validator.py`、`executor.py`、`permissions.py` 或 `export_jobs.py`。`module.py` 负责接入协议，`api.py` 只做请求/响应与状态码映射，业务规则留在 `service.py`，持久化留在 `storage.py`；不得将所有业务逻辑重新堆入单一文件。

## 3. 后端、API、权限和服务

模块工厂返回的对象必须实现平台生命周期：`register_routes()` 注册相对路由，`register_schema()` 声明模块结构，`start()` 启动模块服务，`stop()` 停止后台工作并释放资源，`health()` 返回脱敏状态。路由必须通过模块上下文注册；宿主统一执行登录、CSRF、声明权限、请求体大小和静态资源路径穿越校验，模块路由处理器仍必须依据 `current_user` 校验业务资源所有权、可见范围和下载任务归属。隐藏导航或按钮不能代替鉴权。

路由处理器从 `ModuleRequest.current_user` 取得已鉴权的当前用户。`ModuleContext` 不携带当前用户；它只提供 `application_database`、`config_path`、当前模块独占的 `temp_root`、`now`、`services`、`events`、`logger` 和 `background_executor`。SQL 参数化，标识符来自白名单；API 和日志不返回密码、令牌、连接串、SQL、驱动堆栈或本地绝对路径。模块间不得导入对方 `service.py`、`storage.py` 或私有对象，只能使用版本化公开服务或可序列化的命名空间事件。

三类清单字段职责严格分离：`dependencies` 只声明模块生命周期依赖，`services` 只声明当前模块提供的 `<module_id>.<service>` 服务，`service_dependencies` 只声明模块消费的精确 `platform.<service>` 名称和最小版本，不能用 `dependencies: ["platform"]` 或模块自有 `services` 借用整个平台命名空间。旧清单缺少 `service_dependencies` 时按空列表处理。模块只能注册 `services` 中声明且版本精确匹配的服务；只能解析自身服务、`dependencies` 中依赖模块的公开服务，以及 `service_dependencies` 中逐项授权的平台服务。未声明、未注册或版本不足会分别返回固定的访问、不可用或版本错误；同一模块的同一平台服务只绑定一次，模块停止后 facade 被撤销，继续调用会返回固定生命周期错误。依赖模块未启用时不得启动当前模块，提供方仍有已启用依赖方时不得停用。事件订阅者失败只返回固定脱敏原因，不暴露异常消息且不阻断其他订阅者；模块关闭会排空正在执行的订阅回调，关闭后不能再发布、订阅或注册服务。

平台当前提供 `platform.user_directory` v1。它只读返回已启用用户的 `id`、`username`、`display_name` 和恒为 `true` 的 `active`，保持平台用户管理器的稳定排序；按 ID 查询不存在或停用用户返回 `None`。该 facade 不提供创建、更新、删除、密码、角色、时间或登录信息。

平台同时提供 `platform.report_navigation` v1。需要向报送导航贡献统计卡的模块必须在 `service_dependencies` 精确声明该服务，并在 `start()` 中解析 facade、注册提供方，在 `stop()` 中关闭返回的 handle（facade 随模块停止也会自动关闭仍存活的 handle）。`list_report_processes()` 返回只读的 `ReportProcess(code, name, order, active)` 元组；`register_card_provider(card_code=..., provider=..., semantics_version=...)` 的 `card_code` 只能使用小写字母、数字和下划线且必须以小写字母开头，`semantics_version` 必须是正整数。

提供方是接收一个 `CardStatisticsRequest` 并返回 `CardStatisticsResult` 的可调用对象。宿主会按 `week`、`month`、`quarter`、`year` 四个自然周期依次调用；请求中的当前周期、上一周期、`as_of` 均为 `Asia/Shanghai` 时区感知时间。返回的 `total`、`completed`、`incomplete`、`previous_completed` 必须是非负整数，且 `total == completed + incomplete`；`generated_at` 必须是时区感知时间，返回口径版本必须与注册值一致。完成率和环比变化由平台计算，模块不得写报送导航平台表。

统计卡认领会持久绑定模块 ID：同一卡片只能由一个模块认领，数据库使用单条条件写原子决定 owner，多个进程并发注册时不会发生后写覆盖；模块正常停止后认领仍保留但标记为 inactive/stale，同一模块重启可重新激活，其他模块不能接管。每次成功注册都会持久化新的不可复用 token，停用、成功和失败写入均同时校验 card、owner、token；旧进程的 handle 或迟到回调不能改变新实例状态和快照。`semantics_version` 升级会立即隔离旧口径快照，在新版本首次成功前保持 stale/unavailable，不能把旧版本数值标记成新版本。提供方异常或返回非法结果只产生固定脱敏错误；已有同口径成功快照继续以 stale 展示，首次失败显示 unavailable，不伪造零值。回调执行期间不持有注册锁，允许调用其他平台只读能力；回调返回后平台会复核注册 token。被提供方认领的治理卡（即使当前 inactive）不再接受管理员手工维护。

模块 API 的有请求体方法必须声明 `max_body_bytes`。宿主执行总读取时限和请求大小限制，短读、慢速分段超时或非法 JSON 均不会进入处理器。模块响应只允许 JSON 映射或字节，最大 50 MiB；JSON 在校验时固化为发送快照，后续修改原对象不会改变响应。响应头仅允许 `Allow`、`Content-Disposition`、`ETag`、`Last-Modified`、`Location` 和 `Retry-After`，连接、长度、安全响应头及 `Cache-Control: private, no-store` 由宿主统一生成。模块导入、工厂构造、路由/表结构注册和迁移共享一个启动前有界等待，全部成功前不会向宿主发布模块实例、路由或上下文。后台任务和 `start()`、`stop()`、`health()` 都必须自行支持快速退出；宿主还会执行并发限制、有界等待和故障隔离，但同进程 Python 不能强制终止任意模块代码，超时模块的迟到结果不会发布，未结束前不得重复启用。

## 4. 数据库迁移与运维

应用库先由运维在备份后人工执行 `sql/app_storage/mysql/012_module_system.sql`，再执行 `013_report_navigation_provider_states.sql`，平台应用表共 43 张，`app_schema_version` 仍为 `1`。前者建立模块注册、模块 schema 版本和迁移历史，后者建立带注册 token 的报送导航统计提供方持久状态并为统计运行记录补充 `failed_providers`；生产环境禁止由应用自动执行。模块业务表**不加入**全局 `EXPECTED_APP_SCHEMA`，而由模块自己的 `migrations/` 和清单 `schema_version` 管理。

每个模块从 `001` 起顺序编号迁移。发布后的迁移文件不可修改；后续调整必须新增迁移。模块宿主会校验 checksum，并以同模块串行执行和迁移锁防止并发；checksum 不匹配或迁移失败时禁用当前可选模块并记录脱敏错误。迁移只允许受控的 `CREATE/ALTER/DROP TABLE` 和 `CREATE/DROP INDEX` DDL，所有目标表、引用表和多表语句中的每个表都必须属于清单 `table_prefix`；禁止 DML、查询、跨 schema、动态 SQL、存储过程、视图、触发器及改名绕过。为避免依赖 MySQL `sql_mode` 产生不同解析结果，迁移字符串字面量禁止反斜杠转义；字符串内的引号只能写成连续两个同类引号。禁止用运行时 `CREATE TABLE IF NOT EXISTS` 绕开登记迁移。

单个 SQL 文件中需要分段时，使用独占一行的分隔符：

```sql
-- module-statement-break
```

MySQL DDL 往往无法安全回滚。上线前备份，人工执行，记录版本和 checksum；停用或卸载模块不得自动删除业务表和历史数据。

## 5. 前端生命周期、资源与样式

前端入口由清单和宿主动态加载，必须导出 `mount(context)`、`activate(route)`、`deactivate()` 与 `unmount()`。宿主 `src/auto_check/web/module_host.js` 的 `createContext` 为每个模块创建并以 `Object.freeze` 冻结普通对象；该对象提供 `root`、`api`、`user`、`notify`、`confirm`、`navigate`、`events`。只能在宿主分配的模块根节点内读写 DOM；`deactivate()` 停止轮询和可取消任务，`unmount()` 清理监听器、定时器、轮询、AbortController 和临时 DOM。样式必须加载成功后才会导入和挂载脚本；脚本导入和单次前端生命周期回调最长等待 10 秒，超时只隔离当前模块。连续导航采用最后一次意图，旧模块的迟到跳转不能覆盖更新页面。

全部模块 CSS 必须以 `.auto-check-module[data-module="<module_id>"]` 为顶层作用域，不得编写无作用域 `button`、`input`、`table` 或 `.card`。通过上述冻结对象调用请求、用户信息、消息、确认框、路由和事件；不得读取 `app.js` 的非公开变量。沿用亮色活力主题、`--ui-radius` 和既有语义色；主操作可使用固定 `#3466D9` 到 `#6AA4FF` 渐变，不建立新主题，且悬浮不使用主题光晕。资源必须位于模块资源命名空间，单个静态资源最大 5 MiB，响应使用私有重新验证缓存；JS/CSS 加载失败时只显示本模块错误状态。

## 6. 测试、打包和提交

每个模块至少覆盖清单/命名空间、登录/CSRF/权限/脱敏、服务、存储/迁移、前端生命周期/DOM/CSS、启停与故障隔离、资源释放和验收场景。建议顺序为：

```powershell
python -m pytest tests/modules/<module_id> -q
python -m pytest tests/modules -q
python -m pytest -q
git diff --check
```

需要交付可执行文件时，再按仓库规则打包并验证产物；本次文档更新仅确认包收集规则已适配，未实际打包。提交只包含模块目录、对应测试和文档；不得提交构建产物、缓存或生产数据。

## 7. 明确禁止事项

禁止在线插件、第三方代码执行、跨模块私有依赖、全局 CSS 污染、手工修改 `index.html`/`app.js` 增加模块页面或发布说明、把模块业务表加入全局 schema、修改已发布迁移、在正式模块目录留下 demo，或为了单个模块临时修改打包规则。平台能力不足时，停止业务实现，说明跨模块复用价值、兼容性、安全、迁移、测试和回滚影响，并单独评审平台变更。
