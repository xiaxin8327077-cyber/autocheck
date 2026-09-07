# 登录超时续操作与记录附件修复复验报告

复验日期：2026-09-07

复验对象：`D:\xiaxin\auto_check` 当前工作区，依据首次验收报告逐项检查 F1–F8 及补充测试缺口。

结论：多数问题已经修复，自动化测试无失败，但仍有 3 个明确问题，因此暂不通过最终验收。当前新增的真实 MySQL 测试具有破坏性门控缺口，修复前不要设置 `AUTO_CHECK_IT_MYSQL_DSN` 运行该测试。

## 1. 测试结果

| 检查 | 结果 |
| --- | --- |
| 登录恢复、报表特殊处理模块、服务端集成和通知定向测试 | 264 passed，5 skipped，59.60s，退出码 0 |
| `python -m pytest -q` | 1692 passed，7 skipped，141.47s，退出码 0 |
| `git diff --check` | 退出码 0，无实际空白错误；仅 LF/CRLF 提示 |
| 首次报告复现脚本 | F1–F6、F8 和 F7 的详情/审计路径得到预期结果 |

5 项定向跳过来自未设置 `AUTO_CHECK_IT_MYSQL_DSN` 的真实 MySQL 测试；另外 2 项是当前环境不支持创建目录符号链接。由于真库测试没有执行，数据库事务结论仍受此限制。

## 2. 已确认修复

- F1：版本冲突改为保留原抽屉、字段和附件，显示“加载最新记录”按钮；只有用户显式点击后才刷新。
- F2：`discarding` 状态不会被新的 `recover()` 覆盖，注销失败后继续保持“重试退出”。
- F3 的正常迟到分支：退出后迟到的登录成功不再应用会话，并会尝试注销新会话；但注销失败分支仍有下述 R1。
- F4：并发 `discardUnexpectedSession()` 共享注销流程，等待者均能结束，重复点击不会并行注销。
- F5：预检会拒绝矛盾状态、缺用户名、用户名不一致等异常结构；业务请求发送次数为 0。
- F6：人行上传第二次收到 `account-mismatch` 时会进入注销流程，不再作为普通上传错误处理。
- F7 的详情和审计查询：显式元数据列已排除 `content LONGBLOB`；附件修改事务仍有下述 R2。
- F8：OOXML 成员读取阶段的 CRC、加密和不支持压缩异常会转换为附件字段校验错误。
- 补充项：Base64 改为严格解码；平台 API 可保留原生 `Headers` 和 tuple-array 请求头；`destroy()` 会取消等待者并解绑事件。

隔离场景的关键输出：

```text
EXIT_DURING_LOGIN ["exit","waiterCancelled","logout"]
DISCARD_AFTER_RECOVER true 重试退出
CONCURRENT_DISCARD_PROMISES cancelled cancelled
MISSING_USERNAME auth_preflight_failed [ '/api/auth/status' ]
CONTRADICTORY_STATUS auth_preflight_failed [ '/api/auth/status' ] recoveries 0
CUSTOM_HEADERS_INSTANCE keep
UPLOAD_RETRY_ACCOUNT_MISMATCH {"requests":2,"discardCalls":1,"error":"authentication recovery cancelled"}
OOXML_CRC_EXCEPTION ValidationError
NONCANONICAL_BASE64 ValidationError
METADATA_COLUMNS_INCLUDE_CONTENT False
```

## 3. 仍需修复

### R1 — 迟到登录会话注销失败后没有阻塞和重试入口

位置：

- `src/auto_check/web/auth_recovery.js:322`
- `src/auto_check/web/auth_recovery.js:333`
- `src/auto_check/web/app.js:1774`
- `src/auto_check/web/app.js:1796`

触发：用户提交重新认证后立即点击退出，登录响应随后成功建立新 Cookie，但注销新会话失败或被页面跳转中断。

当前实现已经进入 `terminal`、隐藏遮罩并跳转登录页；`discardLateSession()` 以 fire-and-forget 方式调用注销并用空 catch 吞掉失败。页面没有保持阻塞，也没有“重试退出”入口。登录页可能再次识别到刚建立的有效会话。

独立复现中令 `discardSession()` 明确抛出 `logout failed`，输出：

```text
LATE_DISCARD_FAILURE {"events":["navigate-login","discard"],"overlayHidden":true,"recovering":false,"exitLabel":"退出系统"}
```

要求：退出、销毁或 applySession 进行中遇到迟到成功时，注销结果必须受状态机管理；失败时保持阻塞并允许重试，成功后才完成退出。不要依赖 `location.href` 中止认证或注销请求。补充“迟到会话注销失败”的失败、重试和最终退出测试。

### R2 — 附件修改事务仍读取全部正文

位置：`src/auto_check/modules/report_special_processing/storage.py:917`。

`_apply_record_attachment_change()` 只需获取当前附件 ID，却仍使用 `select(RECORD_ATTACHMENTS)`，因此会把当前附件的 `content LONGBLOB` 一并读回。每次显式提交 `record_attachments` 的修改仍可能无谓读取最多 30 MiB 正文。

独立查询源码确认：

```text
UPDATE_ATTACHMENT_SELECTS_FULL_TABLE True
CONTENT_COLUMN_SELECTED True
```

要求：该查询显式选择 ID 或必要元数据列，排除 `content`。现有查询断言只覆盖列表和审计路径；应覆盖 `_apply_record_attachment_change()` 产生的 SQL。真实 MySQL 测试应在执行 update 前清空捕获记录，并断言整个 update 路径没有选择正文列。

### R3 — 真实 MySQL 测试可能删除误配置的非测试库

位置：`tests/modules/report_special_processing/test_storage_real_mysql.py:60`、`:70`。

fixture 目前只要求库名匹配小写标识符且不等于精确的 `auto_check`，随后直接执行 `DROP DATABASE IF EXISTS`。如果环境变量误指向 `mysql`、`sys`、`auto_check_prod` 或其他业务库，代码仍会尝试删除。注释中的“必须是独立 scratch schema”没有形成强制保护。

要求：在执行任何 DROP 前，将目标限制为明确、足够严格的测试库命名规则，例如固定前缀与随机后缀；拒绝系统库和所有不符合测试前缀的库；限制允许主机；打印脱敏后的最终目标并进行只读断言。测试代码应生成本轮唯一 scratch 库，而不是直接删除 DSN 中已有库。修复前不要设置该环境变量运行真库测试。

## 4. 再次复验要求

1. 为 R1–R3 先添加能在当前实现上失败的回归测试，再修复。
2. 运行定向测试和 `python -m pytest -q`。
3. R3 修复后，在明确隔离的 MySQL 测试实例运行 5 项真库测试，记录建库、迁移 001–006、事务回滚和清理结果。
4. 完成真实浏览器场景：超时带附件保存只落一条、错误密码保留、退出与迟到响应、版本冲突保留、历史新旧附件预览及下载。
5. 本报告不代表已授权打包、部署、提交或推送。

本次复验仅新增本报告，没有修改业务源码、配置或数据库。
