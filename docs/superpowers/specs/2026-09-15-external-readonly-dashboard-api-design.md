# AutoCheck 外部只读看板接口设计

状态：已确认，待实施

日期：2026-09-15

## 1. 目标与边界

AutoCheck 为“金融监管报表报送大屏”和“金融监管报送流程大屏”提供两个外部只读接口。外部系统通过后端适配层调用 AutoCheck，浏览器不直接访问接口，Bearer Token 不进入前端 JavaScript。

本次只修改 `D:\xiaxin\auto_check`。不修改 `D:\xiaxin\kanban`，不开放 CORS，不打包 `dist\auto-check.exe`，不提交或推送代码。

## 2. 方案比较与结论

可选方案有三种：

1. 在 `server.py` 为两个看板硬编码路由。改动少，但把看板业务写入平台内核，后续扩展会继续堆叠条件分支，违反模块边界。
2. 扩展通用模块路由协议，由模块显式把某个 GET 路由标记为 `external=True`。平台只负责认证、外部命名空间和分发，模块负责业务白名单与响应契约。该方案安全边界清晰，可供其他模块复用。
3. 仅由对方系统抓取现有网页登录接口。该方案依赖 Session/CSRF，难以安全自动化，也无法形成稳定的服务端契约。

采用方案 2。

## 3. 平台协议

`ModuleRouter.add()` 增加默认值为 `False` 的 `external` 参数。只有 `external=True` 的路由才能进入外部分发，且登记时强制方法为 `GET`。原有模块路由的登记、权限和内部访问方式保持不变。

外部模块路径从模块清单的 `/api/modules/<module-prefix>` 映射为 `/api/external/v1/<module-prefix>`。`ModuleRouter` 和 `ModuleRuntime` 分别提供独立的 external preflight/dispatch；外部分发不复用网页登录权限判断，也不会扫描普通内部路由。

平台 HTTP 层只处理以下通用职责：

- 从环境变量 `AUTO_CHECK_EXTERNAL_API_TOKEN` 读取 Token。
- 未配置或只包含空白时返回 HTTP 503。
- 严格解析 `Authorization: Bearer <token>`；缺失、格式错误或值错误时返回 HTTP 401。
- 使用 `secrets.compare_digest()` 比较 Token。
- 401 响应增加 `WWW-Authenticate: Bearer`。
- 所有外部接口响应增加 `Cache-Control: no-store`。
- 只允许模块显式公开的 GET 路由；方法不匹配返回 405，未知或未公开路由返回 404。

平台层不包含任何 board code、区域编码、看板字段或 SQL 业务判断。

## 4. 看板模块契约

`dashboard_management` 只把 `/boards/{board_code}/preview` 标记为 external，并由独立的外部处理器调用 `preview_external_board_data()`。内部 `/api/modules/dashboard-management/boards/{board_code}/preview` 继续调用现有 `preview_board_data()`，因此内部预览仍可展示用户启用的自定义区域。

外部接口只接受：

- `report_submission`
- `reporting_process`

外部服务从 `BUILTIN_REGION_SEEDS` 取得对应看板的固定区域顺序，只查询数据库中 `built_in=true`、已启用且编码属于固定集合的区域。用户新增区域、其他管理数据、数据源、SQL 和用户信息均不进入响应。

固定区域为：

- `report_submission`：`annual_supplement_completed`、`monthly_report_validation_remaining`、`monthly_trust_projects`、`report_reconciliation_completion_time`、`report_validation_issue_handling`、`quarterly_special_processing`、`monthly_report_submission_time_comparison`
- `reporting_process`：`regulatory_report_count`、`monthly_regulatory_report_time`、`report_validation_statistics`

外部接口沿用现有区域执行、日期序列化、快照刷新/回退和区域错误脱敏规则。单个区域失败不阻断其他区域。

## 5. 响应协议

成功与部分失败都返回 HTTP 200：

```json
{
  "status": "success",
  "generated_at": "2026-09-15T09:30:00",
  "data": {
    "board": {"code": "report_submission", "name": "金融监管报表报送大屏"},
    "regions": []
  },
  "meta": {"request_id": "req-..."}
}
```

只要任一区域的 `status` 为 `error`，顶层 `status` 为 `partial`；否则为 `success`。`generated_at` 使用服务本次请求的同一个时间并序列化为 ISO 8601。区域错误保持：

```json
{"status": "error", "error": {"code": "internal_error", "message": "数据读取失败"}}
```

认证失败、路由不存在、board code 非法和 Token 未配置分别使用 401、404、404、503，不伪装为区域级 partial。

## 6. 对方系统推荐架构

调用链固定为：浏览器大屏 → 对方系统后端适配接口 → AutoCheck 外部接口。

对方后端保存 AutoCheck 地址和 Token，把 `regions` 按 `code` 转换为原大屏结构；单区失败保留最近成功数据；连接超时建议 3 秒、总超时 10 秒；只对连接失败、超时、502 和 503 少量重试，不重试 401；记录 `meta.request_id`；缓存最近一次成功响应，避免 AutoCheck 短暂不可用时大屏整体空白。

## 7. 测试与验收

TDD 覆盖：external 标记隔离、只允许 GET、503/401、正确 Token、两个固定看板、非法 board code、排除自定义区域、顶层元数据、部分失败、内部预览兼容。相关测试通过后运行全量 `python -m pytest -q` 和 `git diff --check`。

最后重启当前 AutoCheck 开发环境，确认 8765 端口监听，并实测 401、503 和正确 Token 的成功调用。为避免把正式 Token 写入命令历史，开发验收使用临时测试 Token，重启后按既有运行配置恢复或明确记录当前 Token 状态。
