# 看板管理外部只读接口

本文定义 AutoCheck 向外部系统提供的两个监管看板数据接口，以及对方系统的推荐接入方式。接口版本为 `v1`，响应编码为 UTF-8。

- 文档更新时间：2026-09-16
- 默认示例地址：`http://127.0.0.1:8765`
- 生产 Base URL：由部署方提供，例如 `https://autocheck.example.internal`

## 1. 接口概览

| 看板 | `board_code` | 方法与路径 |
|---|---|---|
| 金融监管报表报送大屏 | `report_submission` | `GET /api/external/v1/dashboard-management/boards/report_submission/preview` |
| 金融监管报送流程大屏 | `reporting_process` | `GET /api/external/v1/dashboard-management/boards/reporting_process/preview` |

完整请求地址由 Base URL 与上表路径直接拼接。接口只接受 `GET`，使用 UTF-8 JSON，不开放 CORS。调用方应通过自己的后端适配接口访问 AutoCheck，不能让大屏浏览器直接调用，也不能把 Token 写入 JavaScript、HTML、日志或 URL。

## 2. 启用与认证

管理员应在“系统管理 → 看板管理 → 接口监控”中生成或更新这两个固定接口专用的 Token。数据库尚无管理 Token 时，才兼容读取环境变量：

```text
AUTO_CHECK_EXTERNAL_API_TOKEN=<高强度随机 Token>
```

数据库管理 Token 与环境变量回退均未配置时，这两个固定接口关闭并返回 HTTP 503。数据库管理 Token 一旦生成便立即生效并完全取代环境变量回退。配置后，请求必须携带：

```http
Authorization: Bearer <token>
```

请求必须携带一个且仅一个 `Authorization` 头。Token 缺失、重复携带 Authorization、认证方案或格式错误、Token 值错误时均返回 HTTP 401，并带有：

```http
WWW-Authenticate: Bearer
Cache-Control: no-store
```

数据库管理 Token 以 SHA-256 摘要保存并使用 `secrets.compare_digest` 比较；环境变量回退通过平台只读认证服务进行常量时间校验。`Bearer` 认证方案大小写不敏感，但 Token 值区分大小写。外部接口的所有响应都带 `Cache-Control: no-store`。Token 与网页登录 Session 相互独立；外部请求不需要 Cookie 或 CSRF Token，也不能访问普通内部模块路由。

## 3. 请求约束

| 项目 | 约束 |
|---|---|
| HTTP 方法 | 仅 `GET` |
| 路径参数 | `board_code` 只能是 `report_submission` 或 `reporting_process`，大小写敏感 |
| 查询参数 | v1 不定义查询参数；调用方不得依赖未声明参数当前可能被忽略的行为 |
| 请求体 | 不允许请求体；不要发送 `Content-Length` 大于 0 或 `Transfer-Encoding` |
| 必需请求头 | `Authorization: Bearer <token>` |
| 推荐请求头 | `Accept: application/json` |
| Cookie / CSRF | 不需要，也不能替代 Bearer Token |
| CORS | 不开放；浏览器跨域直连不是受支持的接入方式 |

调用方必须完整匹配固定路径，不能把内部路径 `/api/modules/dashboard-management/...` 改造成外部调用，也不能枚举其他模块路径。GET 请求携带实体、Content-Length 冲突或不支持的传输编码时，会在业务处理前返回 HTTP 400。

## 4. curl 示例

以下示例中的地址和 Token 都是占位值：

```bash
curl --fail-with-body \
  --connect-timeout 3 \
  --max-time 10 \
  -H "Accept: application/json" \
  -H "Authorization: Bearer ${AUTO_CHECK_EXTERNAL_API_TOKEN}" \
  "http://127.0.0.1:8765/api/external/v1/dashboard-management/boards/report_submission/preview"
```

```bash
curl --fail-with-body \
  --connect-timeout 3 \
  --max-time 10 \
  -H "Accept: application/json" \
  -H "Authorization: Bearer ${AUTO_CHECK_EXTERNAL_API_TOKEN}" \
  "http://127.0.0.1:8765/api/external/v1/dashboard-management/boards/reporting_process/preview"
```

生产接入应使用内网 HTTPS 反向代理或其他受控传输链路，不应在不可信网络中明文发送 Bearer Token。

## 5. 响应结构

成功或区域级部分失败都返回 HTTP 200：

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | 全部区域成功时为 `success`；至少一个区域失败时为 `partial` |
| `generated_at` | string | 本次数据生成时间，ISO 8601 |
| `data.data_year` | integer | 本次响应的业务年度；v1 不接收年度查询参数，以请求发生时 Asia/Shanghai 业务时区的当前自然年为准 |
| `data.board.code` | string | 固定看板编码 |
| `data.board.name` | string | 固定看板名称 |
| `data.regions` | array | 固定内置区域，按模块 catalog 顺序返回 |
| `meta.request_id` | string | 请求追踪编号，排查时双方共同记录 |

区域结构：

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | string | 固定区域编码 |
| `name` | string | 内置区域名称 |
| `shape` | string | `scalar` 或 `list` |
| `fields` | array | 固定字段元数据；含 `alias`、`name`、`value_type` |
| `status` | string | `success` 或 `error` |
| `columns` | array | 仅成功区域出现；返回列别名，顺序与 `fields` 一致 |
| `rows` | array | 仅成功区域出现；标量区域为 0 或 1 行，列表区域可为多行 |
| `has_more` | boolean | 仅成功区域出现；是否仍有未返回行 |
| `returned_count` | integer | 仅成功区域出现；等于本次 `rows` 数量 |
| `error.code` | string | 仅失败区域出现；安全错误编码 |
| `error.message` | string | 仅失败区域出现；脱敏错误说明 |
| `snapshot_status` | string | 仅四个年度快照区域在成功或回退成功时可能出现，为 `fresh` 或 `stale` |
| `snapshot_refreshed_at` | string/null | 与 `snapshot_status` 同时出现；最近快照刷新时间，ISO 8601 |

普通区域没有业务数据不等于接口失败：只要查询正常完成，区域仍为 `status=success`，并可返回空 `rows`。年度快照区域在当前年度没有可用数据时例外，必须返回 `data_not_ready`。只有该区域无法生成有效结果时才返回 `status=error`。失败区域不同时返回 `columns`、`rows`、`has_more` 和 `returned_count`。

用户新增的自定义区域不会进入外部响应；用户向内置区域追加的自定义字段也不会进入外部字段契约。内部“接口数据”预览、内部“看板页面”预览和外部接口统一使用固定 7+3 区域及其固定字段；自定义区域和字段只保留在配置与来源测试中。

## 6. 成功响应示例

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Cache-Control: no-store
```

```json
{
  "status": "success",
  "generated_at": "2026-09-16T09:00:00",
  "data": {
    "data_year": 2026,
    "board": {
      "code": "report_submission",
      "name": "金融监管报表报送大屏"
    },
    "regions": [
      {
        "code": "report_reconciliation_completion_time",
        "name": "报表对账完成时间",
        "shape": "list",
        "fields": [
          {"alias": "month", "name": "月份", "value_type": "string"},
          {"alias": "reconciliation_completed_time", "name": "对账完成时间", "value_type": "string"},
          {"alias": "reconciliation_completed_at", "name": "实际对账完成日期时间", "value_type": "datetime"}
        ],
        "status": "success",
        "columns": ["month", "reconciliation_completed_time", "reconciliation_completed_at"],
        "rows": [
          {
            "month": "2026-01",
            "reconciliation_completed_time": "21:00",
            "reconciliation_completed_at": null
          },
          {
            "month": "2026-08",
            "reconciliation_completed_time": "09:30",
            "reconciliation_completed_at": "2026-09-15T09:30:00"
          }
        ],
        "has_more": false,
        "returned_count": 2
      }
    ]
  },
  "meta": {"request_id": "req-example"}
}
```

示例为节选；正式响应会返回该看板的全部固定内置区域。`reconciliation_completed_at` 为 `null` 表示该历史周期仅有既时分，完整日期未知。

## 7. 部分失败响应示例

单个区域查询失败不影响其他区域。HTTP 状态仍为 200，失败区域使用 `status=error`，顶层为 `partial`：

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Cache-Control: no-store
```

```json
{
  "status": "partial",
  "generated_at": "2026-09-15T09:30:00",
  "data": {
    "data_year": 2026,
    "board": {
      "code": "report_submission",
      "name": "金融监管报表报送大屏"
    },
    "regions": [
      {
        "code": "annual_supplement_completed",
        "name": "本年度完成补录任务",
        "shape": "scalar",
        "fields": [
          {"alias": "completed_supplement_count", "name": "完成补录任务数", "value_type": "integer"}
        ],
        "status": "success",
        "columns": ["completed_supplement_count"],
        "rows": [{"completed_supplement_count": 18}],
        "has_more": false,
        "returned_count": 1
      },
      {
        "code": "monthly_trust_projects",
        "name": "月度信托项目数量",
        "shape": "list",
        "fields": [
          {"alias": "month", "name": "月份", "value_type": "string"},
          {"alias": "single_trust_count", "name": "单一信托项目数量", "value_type": "integer"},
          {"alias": "collective_trust_count", "name": "集合信托项目数量", "value_type": "integer"},
          {"alias": "property_trust_count", "name": "财产权信托项目数量", "value_type": "integer"}
        ],
        "status": "error",
        "error": {
          "code": "internal_error",
          "message": "数据读取失败"
        }
      }
    ]
  },
  "meta": {"request_id": "req-733e03838f2b446a916432537c5b58f0"}
}
```

## 8. HTTP 状态与错误响应

| HTTP 状态 | 含义 | 是否建议重试 |
|---|---|---|
| 200 | 全部区域成功或区域级部分失败；检查顶层 `status` | 不按 HTTP 重试；只有 `success` 才能替换完整缓存，`partial` 保留上一份完整成功响应 |
| 400 | 请求 framing 非法，例如 GET 携带实体或冲突长度 | 否，修正客户端请求 |
| 401 | Bearer Token 缺失、重复、格式错误或值错误 | 否，检查密钥配置 |
| 404 | 外部路由、模块或 `board_code` 不存在 | 否，检查固定路径 |
| 405 | 路径存在但方法不是 GET | 否，改用 GET |
| 500 | 模块发生未预期错误 | 可少量重试，并记录可用的 `request_id`/`error_id` |
| 503 | 外部 Token 未配置，接口关闭 | 可少量重试；持续出现时联系 AutoCheck 运维 |

请求追踪号并非所有平台级错误都会返回：看板业务处理产生的响应通常包含 `meta.request_id`；认证阶段的 401、未配置阶段的 503 以及部分平台路由错误没有 `request_id`。对方系统排查时还应记录本地时间、目标 URL、HTTP 状态和自身追踪号。

### HTTP 401：Token 缺失或错误

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Cache-Control: no-store
Content-Type: application/json; charset=utf-8
```

```json
{
  "error": {
    "code": "authentication_required",
    "message": "Bearer Token 缺失或无效"
  }
}
```

### HTTP 404：接口或看板编码不存在

```http
HTTP/1.1 404 Not Found
Cache-Control: no-store
Content-Type: application/json; charset=utf-8
```

```json
{
  "error": {
    "code": "resource_not_found",
    "message": "外部看板接口不存在",
    "fields": {}
  },
  "meta": {"request_id": "req-584416ece0f34849b11fd57099f9839f"}
}
```

未显式公开的模块路径也返回 404，但响应体可能为 `{"error":"module route not found"}`。调用方不能据此尝试访问数据源、区域配置、SQL、用户或其他管理数据。

### HTTP 405：请求方法不允许

以下响应需要请求已通过 Bearer 认证；未通过认证会先返回 401：

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET
Cache-Control: no-store
Content-Type: application/json; charset=utf-8
```

```json
{
  "error": "method not allowed"
}
```

### HTTP 503：外部接口未配置

```http
HTTP/1.1 503 Service Unavailable
Cache-Control: no-store
Content-Type: application/json; charset=utf-8
```

```json
{
  "error": {
    "code": "external_api_disabled",
    "message": "外部接口未配置"
  }
}
```

## 9. 金融监管报表报送大屏字段映射

| 区域编码 | 区域名称 | 形态 | 字段别名 | 类型与格式 |
|---|---|---|---|---|
| `annual_supplement_completed` | 本年度完成补录任务 | scalar | `completed_supplement_count` | integer |
| `monthly_report_validation_remaining` | 当月报表检验还剩 | scalar | `remaining_validation_count` | integer |
| `monthly_trust_projects` | 月度信托项目数量 | list | `month` | string；`1月～12月`，例如 `8月` |
| `monthly_trust_projects` | 月度信托项目数量 | list | `single_trust_count` | integer |
| `monthly_trust_projects` | 月度信托项目数量 | list | `collective_trust_count` | integer |
| `monthly_trust_projects` | 月度信托项目数量 | list | `property_trust_count` | integer |
| `report_reconciliation_completion_time` | 报表对账完成时间 | list | `month` | string；`YYYY-MM`，例如 `2026-08` |
| `report_reconciliation_completion_time` | 报表对账完成时间 | list | `reconciliation_completed_time` | string；`HH:mm`，例如 `09:30`；页面展示使用的对账完成时分 |
| `report_reconciliation_completion_time` | 报表对账完成时间 | list | `reconciliation_completed_at` | string/null；ISO 8601 `YYYY-MM-DDTHH:mm:ss`，例如 `2026-09-15T09:30:00`；历史初始化数据无真实完整日期时为 `null` |
| `report_validation_issue_handling` | 报表校验问题处理 | list | `month` | string；`YYYY-MM`，例如 `2026-08` |
| `report_validation_issue_handling` | 报表校验问题处理 | list | `validation_issue_count` | integer |
| `quarterly_special_processing` | 季度报表特殊处理 | list | `quarter` | string；`第N季度`，例如 `第3季度` |
| `quarterly_special_processing` | 季度报表特殊处理 | list | `special_processing_count` | integer |
| `monthly_report_submission_time_comparison` | 当月报表报送时间对比 | list | `report_type` | string |
| `monthly_report_submission_time_comparison` | 当月报表报送时间对比 | list | `actual_report_generated_at` | date；`YYYY-MM-DD` |
| `monthly_report_submission_time_comparison` | 当月报表报送时间对比 | list | `required_submission_at` | date；`YYYY-MM-DD` |

## 10. 金融监管报送流程大屏字段映射

| 区域编码 | 区域名称 | 形态 | 字段别名 | 类型与格式 |
|---|---|---|---|---|
| `regulatory_report_count` | 监管报送报表数量 | list | `report_type` | string |
| `regulatory_report_count` | 监管报送报表数量 | list | `report_count` | integer |
| `monthly_regulatory_report_time` | 当月监管报送报表时间 | list | `report_type` | string |
| `monthly_regulatory_report_time` | 当月监管报送报表时间 | list | `reporting_date` | date；`YYYY-MM-DD` |
| `report_validation_statistics` | 报表校验统计 | list | `report_type` | string |
| `report_validation_statistics` | 报表校验统计 | list | `validation_count` | integer |

日期统一为 `YYYY-MM-DD`，完整日期时间统一为 ISO 8601。不同区域的 `month` 格式不能互换：`monthly_trust_projects` 使用中文月份，另两个含 `month` 的区域使用 `YYYY-MM`。

`report_reconciliation_completion_time` 固定返回 `month`、`reconciliation_completed_time`、`reconciliation_completed_at` 三个字段。`month` 是业务所属月份，也是年度归属和排序的唯一依据；`reconciliation_completed_at` 跨月或跨年不改变行的业务归属。例如 `month=2026-12` 且 `reconciliation_completed_at=2027-01-03T01:15:00` 的记录仍属于 2026 年 12 月。

## 11. 年度、跨年与完整性

- `data.data_year` 是 Asia/Shanghai 业务时区的当前自然年整数；v1 不接收年度查询参数。
- 同一次响应中的年度快照行必须全部属于 `data.data_year`，不得把两个年度的数据合并在同一组列表中。
- 每年 1 月，"报表对账完成时间"来源可能返回上一年 12 月的迟到完成记录；该记录按 `month` 写入上一年度快照，但不进入本年度响应。
- 成功列表必须满足 `has_more=false`，且 `returned_count` 等于本次 `rows` 的实际数量。
- 数据来源编辑区测试最多只展示前 10 行，但该限制不得传播到完整看板预览或外部接口；完整看板必须一次返回固定区域的全部业务行。
- 如果某区域无法完整返回，不得把截断结果标记为成功；该区域返回 `status=error`、错误码 `truncated_result`，顶层返回 `status=partial`。截断数据不得写入年度快照，也不得回退为成功区域。
- 新年度没有可用的年度趋势数据时，年度快照区域返回区域错误 `data_not_ready`，顶层状态为 `partial`；不得用空列表或 `0` 伪装完整成功。
- 调用方不得使用 `partial` 响应覆盖最近一次完整成功快照，也不得按区域拼接出一份跨年度"成功"结果。

区域错误码示例：

```json
{
  "code": "data_not_ready",
  "message": "当前年度数据尚未准备完成"
}
```

```json
{
  "code": "truncated_result",
  "message": "数据来源未返回完整结果"
}
```

跨年示例：`month=2026-12` 且 `reconciliation_completed_at=2027-01-03T01:15:00` 的记录仍属于 2026 年 12 月，写入 2026 年度快照；2027 年响应不得混入该行。

## 12. 对方系统推荐对接方案

推荐调用链：

```text
浏览器大屏
  -> 对方系统后端适配接口
  -> AutoCheck 外部接口
```

对方系统后端适配层负责：

1. 在服务端密钥配置中保存 AutoCheck 地址和 Token，不回传给浏览器。
2. 分别请求两个固定 `board_code`，将 `regions` 按 `code` 转换成原大屏的数据结构。
3. 顶层 `status=partial` 时保留最近一次完整 `success` 响应，不用本次成功区域和旧失败区域拼接新的“成功”结果。
4. 设置连接 3 秒、总超时 10 秒；根据实际网络基线再做小幅调整。
5. 只对连接失败、超时、HTTP 502 和 HTTP 503 做少量、带退避的重试；不对 401 重试，应立即告警并检查 Token 配置。
6. 记录 `meta.request_id`、目标 `board_code`、HTTP 状态和调用耗时，但不记录 Token 或完整 Authorization 头。
7. 缓存最近一次成功的完整响应；AutoCheck 短暂不可用时优先返回缓存，避免整个大屏空白。
8. 对 `status=partial` 不更新完整缓存；有缓存时继续展示最近一次完整 `success`，没有缓存时按对方大屏约定显示“暂无数据/暂不可用”，不要伪造 0，也不要跨年度拼接区域。

## 13. 兼容性与运维

- `/api/modules/dashboard-management/...` 是网页登录内部接口，不能作为外部系统对接地址。
- 外部接口只公开两个固定看板的预览；数据源列表、区域/字段维护、SQL 测试与保存、页面资源和用户信息均不公开。
- 页面生成或更新的数据库管理 Token 写入成功后立即生效，不需要重启 AutoCheck；旧 Token 同时失效。仅在数据库尚无管理 Token、继续使用环境变量兼容回退时，部署配置变更通常需要重启进程。不要在聊天、工单或源码中传递真实 Token。
- `generated_at` 表示 AutoCheck 本次生成响应的时间，不代表每个来源数据的业务时间；年度快照区域可结合 `snapshot_status` 和 `snapshot_refreshed_at` 判断新鲜度。
- 对方解析时必须按区域 `code` 和字段 `alias`，不要依赖数组下标或中文显示名称。
- AutoCheck 预览（含"接口数据"预览与"看板页面"预览）与外部接口使用同一份固定 7+3 区域、固定字段、年度快照及错误规则，是外部接口的本地验收入口。自定义区域和自定义字段仅保留在配置和来源测试能力中，不进入固定完整看板。

## 14. AutoCheck 端调用监控说明

AutoCheck 已在“系统管理 → 看板管理”中提供接口监控页面和调用记录存储。该能力用于 AutoCheck 管理员排查外部 v1 接口状态，不替代调用方自己的服务端调用日志。

监控只记录“Bearer 认证通过且命中看板预览路由”的调用，记录 TCP 对端 IP 并滚动保留 30 天；401、503、错误方法及未命中路由不会进入调用记录。AutoCheck 默认不信任 `X-Forwarded-For` 或 `Forwarded`，部署在反向代理之后时看到的 TCP 对端 IP 可能是代理地址。该监控规则不改变本文件定义的外部响应结构。

## 15. 联调检查清单

1. 确认使用外部 `/api/external/v1/...` 路径，而不是网页登录 `/api/modules/...` 路径。
2. 确认请求由对方系统后端发起，浏览器代码和网络响应中没有 Token。
3. 确认只发送一个 `Authorization: Bearer <token>`，且请求方法为 GET、没有请求体。
4. 先分别验证无 Token 为 401、错误 Token 为 401，再使用正确 Token 调用两个固定看板。
5. 确认 200 响应同时检查 HTTP 状态与顶层 `status`，并能处理 `partial`。
6. 确认按区域 `code`、字段 `alias` 解析，不依赖顺序、中文名或示例中的行数。
7. 确认连接 3 秒、总超时 10 秒，只对允许场景少量退避重试，不重试 401/404/405。
8. 确认缓存最近一次完整成功响应；`partial` 响应不得覆盖最近一次完整成功快照，也不得按区域拼接跨年度结果。
9. 确认日志记录本地时间、目标看板、HTTP 状态、耗时、`request_id`（存在时）和自身追踪号，但不记录 Token 或完整 Authorization。
10. 完成联调后执行一次 Token 更新演练，确认旧 Token 失效、新 Token 生效且大屏不直接感知密钥。

## 16. 接口监控（AutoCheck 内部）

AutoCheck"系统管理 → 看板管理"内提供"接口监控"子页面，供管理员查看外部接口调用情况。

### 16.1 记录范围

仅**认证通过并命中路由才记录**，具体分类如下：

- HTTP 200 且顶层 `status=success`：记为成功。
- HTTP 200 且顶层 `status=partial`：记为部分成功，并记录 `region.status=error` 的区域数量。
- 认证通过但产生 4xx/5xx（如非法看板 404、处理器异常 500）：记为失败。

以下请求**不记录**（401/503 不记录）：

- Token 缺失或错误产生的 **401**。
- 未配置外部 Token 时产生的 **503**。
- 错误请求方法（405）、未命中看板预览路由的路径或其他模块接口。
- 内部 `/api/modules/...` 预览请求。

### 16.2 调用方 IP

调用方 IP 取规范化的 **TCP 对端地址**（IPv4 或 IPv6），用于精确筛选和展示。

不信任 `X-Forwarded-For`、`Forwarded` 等可由客户端伪造的请求头，即使请求携带这些头也不会覆盖 TCP 对端 IP。

### 16.3 留存与隐私

调用记录滚动保留 **30 天**，写入和查看时自动清理过期记录。

记录中**不保存或展示** Token、Token 摘要、Authorization 请求头、SQL、数据源配置或响应数据。

### 16.4 监控页行为

- 展示接口启用状态、Token 来源、系统生成 Token 的最近生成时间和两个固定接口地址；顶部不再展示最近调用或最近成功时间，相关明细仍可从下方调用记录查看。页面不单独显示“Token 已配置”标签。`token_source=managed` 显示为“系统生成”并同时展示 `token_generated_at`，`environment` 显示为“环境变量兼容”且不显示生成时间，`none` 表示未配置；桌面端两个接口地址在同一行并列展示。
- 展示近 24 小时调用、成功、部分成功、失败、平均耗时。
- 分页查看调用记录，支持按看板、结果状态、调用方 IP、日期范围筛选；开始/结束日期复用系统日期选择组件，分别覆盖所选日期的起始和结束时刻，“查询”和“重置”均使用统一空心按钮。
- 调用记录表头与内容统一居中，底部分页复用系统标准左右箭头按钮。
- 从监控页**返回看板管理**时，恢复进入前的当前看板、区域和未保存草稿。

### 16.5 权限

监控入口和内部 API 受 `dashboard_management.external_api_monitor` / `sys.dashboard_management.external_api_monitor` 能力控制，默认仅管理员开启。

## 17. Token 管理

两个固定看板接口使用专属 Bearer Token，由 AutoCheck 管理员在"系统管理 → 看板管理 → 接口监控"页面生成或更新。

### 17.1 生成与更新

- 管理员登录 AutoCheck，进入"接口监控"页面，点击"生成 Token"或"更新 Token"按钮。
- 生成算法使用 `secrets.token_urlsafe(32)`，提供至少 256 位随机熵。
- 更新前页面明确提示"旧 Token 将立即失效"，旧 Token 在数据库写入成功后立即被替换。
- 生成成功后，页面以一次性弹窗展示明文 Token，提供"复制"和"我已保存"操作。
- 明文 Token 仅在本次成功响应和当前一次性弹窗中存在；关闭弹窗、切换页面、退出模块或刷新浏览器后，前端立即清除所有引用。

### 17.2 权限控制

- Token 管理受 `dashboard_management.external_api_token_manage` / `sys.dashboard_management.external_api_token_manage` 能力控制。
- 默认仅管理员拥有。只有接口监控查看权限的用户不能生成或更新 Token。
- 后端生成接口执行登录、CSRF、能力码和请求体校验；请求体必须严格为 `{}`。

### 17.3 存储与校验

- 数据库仅保存 SHA-256 摘要和非敏感短指纹，禁止保存明文 Token。
- 摘要比较使用 `secrets.compare_digest`，恒定时间完成。
- 数据库管理 Token 一旦存在，立即优先并完全取代环境变量 `AUTO_CHECK_EXTERNAL_API_TOKEN`。
- 数据库尚无 Token 时，可将 `AUTO_CHECK_EXTERNAL_API_TOKEN` 作为兼容回退，但也只能用于这两个固定接口。

### 17.4 接口权限边界

该 Token 仅适用于以下两个精确 GET 接口：

- `/api/external/v1/dashboard-management/boards/report_submission/preview`
- `/api/external/v1/dashboard-management/boards/reporting_process/preview`

不得访问：第三个或其他看板、其他外部接口、AutoCheck 内部模块接口、登录/用户/配置/SQL/监控查询/Token 管理接口、任何非 GET 请求。

### 17.5 生产部署

- 启动 AutoCheck → 管理员登录 → 在接口监控页面生成 Token → 将一次性明文安全提供给 Kanban → 配置并验证两个接口。
- 生产环境上线后由生产管理员重新生成生产 Token，不复用开发 Token。
- 不提供"录入已有 Token"功能。

### 17.6 安全约束

- Token 不进入 URL、日志、调用记录、`localStorage`、`sessionStorage` 或普通页面状态。
- 生成操作记录管理员标识和时间，但不记录明文、摘要或候选 Token。
- 页面不显示摘要、环境变量值、数据库字段或内部错误。
