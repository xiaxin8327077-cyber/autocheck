# 看板管理外部只读接口

本文定义 AutoCheck 向外部系统提供的两个监管看板数据接口，以及对方系统的推荐接入方式。接口版本为 `v1`，响应编码为 UTF-8。

- 文档更新时间：2026-09-15
- 默认示例地址：`http://127.0.0.1:8765`
- 生产 Base URL：由部署方提供，例如 `https://autocheck.example.internal`

## 1. 接口概览

| 看板 | `board_code` | 方法与路径 |
|---|---|---|
| 金融监管报表报送大屏 | `report_submission` | `GET /api/external/v1/dashboard-management/boards/report_submission/preview` |
| 金融监管报送流程大屏 | `reporting_process` | `GET /api/external/v1/dashboard-management/boards/reporting_process/preview` |

完整请求地址由 Base URL 与上表路径直接拼接。接口只接受 `GET`，使用 UTF-8 JSON，不开放 CORS。调用方应通过自己的后端适配接口访问 AutoCheck，不能让大屏浏览器直接调用，也不能把 Token 写入 JavaScript、HTML、日志或 URL。

## 2. 启用与认证

AutoCheck 进程通过环境变量读取 Token：

```text
AUTO_CHECK_EXTERNAL_API_TOKEN=<高强度随机 Token>
```

环境变量未配置、为空或只包含空白时，全部外部模块接口关闭并返回 HTTP 503。配置后，请求必须携带：

```http
Authorization: Bearer <token>
```

请求必须携带一个且仅一个 `Authorization` 头。Token 缺失、重复携带 Authorization、认证方案或格式错误、Token 值错误时均返回 HTTP 401，并带有：

```http
WWW-Authenticate: Bearer
Cache-Control: no-store
```

AutoCheck 使用 `secrets.compare_digest` 进行常量时间比较。`Bearer` 认证方案大小写不敏感，但 Token 值区分大小写。外部接口的所有响应都带 `Cache-Control: no-store`。Token 与网页登录 Session 相互独立；外部请求不需要 Cookie 或 CSRF Token，也不能访问普通内部模块路由。

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

区域没有业务数据不等于接口失败：只要查询正常完成，区域仍为 `status=success`，并可返回空 `rows`。只有该区域无法生成有效结果时才返回 `status=error`。失败区域不同时返回 `columns`、`rows`、`has_more` 和 `returned_count`。

用户新增的自定义区域不会进入外部响应；用户向内置区域追加的自定义字段也不会进入外部字段契约。内部网页登录预览接口仍按其原有规则返回已启用的自定义区域和字段。

## 6. 成功响应示例

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Cache-Control: no-store
```

```json
{
  "status": "success",
  "generated_at": "2026-09-15T09:30:00",
  "data": {
    "board": {
      "code": "reporting_process",
      "name": "金融监管报送流程大屏"
    },
    "regions": [
      {
        "code": "regulatory_report_count",
        "name": "监管报送报表数量",
        "shape": "list",
        "fields": [
          {"alias": "report_type", "name": "报表类型", "value_type": "string"},
          {"alias": "report_count", "name": "报表数量", "value_type": "integer"}
        ],
        "status": "success",
        "columns": ["report_type", "report_count"],
        "rows": [{"report_type": "月报", "report_count": 12}],
        "has_more": false,
        "returned_count": 1
      }
    ]
  },
  "meta": {"request_id": "req-2f2f0f7d6e1843b4a7eb3af6764cbf80"}
}
```

示例为节选；正式响应会返回该看板的全部固定内置区域。

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
| 200 | 全部区域成功或区域级部分失败；检查顶层 `status` | 不按 HTTP 重试；`partial` 按区域使用缓存 |
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
| `report_reconciliation_completion_time` | 报表对账完成时间 | list | `reconciliation_completed_at` | datetime；ISO 8601，例如 `2026-09-15T09:30:00` |
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

当前固定区域没有仅含时间的字段；若未来通过版本化契约新增 `time` 类型，格式使用 `HH:mm`。日期统一为 `YYYY-MM-DD`，完整日期时间统一为 ISO 8601。不同区域的 `month` 格式不能互换：`monthly_trust_projects` 使用中文月份，另两个含 `month` 的区域使用 `YYYY-MM`。

## 11. 对方系统推荐对接方案

推荐调用链：

```text
浏览器大屏
  -> 对方系统后端适配接口
  -> AutoCheck 外部接口
```

对方系统后端适配层负责：

1. 在服务端密钥配置中保存 AutoCheck 地址和 Token，不回传给浏览器。
2. 分别请求两个固定 `board_code`，将 `regions` 按 `code` 转换成原大屏的数据结构。
3. 单个区域 `status=error` 时保留该区域最近一次成功数据，并可在内部标记数据陈旧。
4. 设置连接 3 秒、总超时 10 秒；根据实际网络基线再做小幅调整。
5. 只对连接失败、超时、HTTP 502 和 HTTP 503 做少量、带退避的重试；不对 401 重试，应立即告警并检查 Token 配置。
6. 记录 `meta.request_id`、目标 `board_code`、HTTP 状态和调用耗时，但不记录 Token 或完整 Authorization 头。
7. 缓存最近一次成功的完整响应；AutoCheck 短暂不可用时优先返回缓存，避免整个大屏空白。
8. 对 `status=partial` 做区域级合并：成功区域使用新数据，失败区域沿用缓存。若没有缓存，按对方大屏约定显示“暂无数据/暂不可用”，不要伪造 0。

## 12. 兼容性与运维

- `/api/modules/dashboard-management/...` 是网页登录内部接口，不能作为外部系统对接地址。
- 外部接口只公开两个固定看板的预览；数据源列表、区域/字段维护、SQL 测试与保存、页面资源和用户信息均不公开。
- 修改 `AUTO_CHECK_EXTERNAL_API_TOKEN` 后需要重启 AutoCheck 进程。轮换时应先更新对方后端密钥，再在计划窗口重启并验证；不要在聊天、工单或源码中传递真实 Token。
- `generated_at` 表示 AutoCheck 本次生成响应的时间，不代表每个来源数据的业务时间；年度快照区域可结合 `snapshot_status` 和 `snapshot_refreshed_at` 判断新鲜度。
- 对方解析时必须按区域 `code` 和字段 `alias`，不要依赖数组下标或中文显示名称。

## 13. AutoCheck 端调用监控说明

AutoCheck 已确认后续在“系统管理 → 看板管理”中增加接口监控能力，但该监控页面与调用记录存储尚未包含在当前外部 v1 接口交付中。在监控代码、迁移和测试完成前，调用方不能假设 AutoCheck 已经保存调用历史，仍应保留自己的服务端调用日志。

后续监控按已确认设计只记录“Bearer 认证通过且命中看板预览路由”的调用，记录 TCP 对端 IP 并滚动保留 30 天；401、503、错误方法及未命中路由不会进入调用记录。AutoCheck 默认不信任 `X-Forwarded-For` 或 `Forwarded`，部署在反向代理之后时看到的 TCP 对端 IP 可能是代理地址。该监控规则不改变本文件定义的外部响应结构。

## 14. 联调检查清单

1. 确认使用外部 `/api/external/v1/...` 路径，而不是网页登录 `/api/modules/...` 路径。
2. 确认请求由对方系统后端发起，浏览器代码和网络响应中没有 Token。
3. 确认只发送一个 `Authorization: Bearer <token>`，且请求方法为 GET、没有请求体。
4. 先分别验证无 Token 为 401、错误 Token 为 401，再使用正确 Token 调用两个固定看板。
5. 确认 200 响应同时检查 HTTP 状态与顶层 `status`，并能处理 `partial`。
6. 确认按区域 `code`、字段 `alias` 解析，不依赖顺序、中文名或示例中的行数。
7. 确认连接 3 秒、总超时 10 秒，只对允许场景少量退避重试，不重试 401/404/405。
8. 确认缓存最近一次成功响应，并在区域失败时只回退相应区域，不把失败伪造成数值 0。
9. 确认日志记录本地时间、目标看板、HTTP 状态、耗时、`request_id`（存在时）和自身追踪号，但不记录 Token 或完整 Authorization。
10. 完成联调后执行一次 Token 轮换演练，确认旧 Token 失效、新 Token 生效且大屏不直接感知密钥。
