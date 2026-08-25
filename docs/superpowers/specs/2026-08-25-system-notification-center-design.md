# 系统通知中心设计

状态：已确认，可进入实施计划

日期：2026-08-25

## 1. 背景

Auto Check 当前已经存在“我的待办”等业务入口，但缺少跨页面、跨模块的统一通知能力。用户只有进入对应页面并主动刷新后，才能发现新事项。

本次建设一个平台级“系统通知中心”。报表特殊处理待办是首个通知来源，但通知中心不得被实现成待办专用功能。后续任务完成、任务失败、导入结果、系统公告、权限变化等场景都应复用同一套发布、存储、未读和实时推送协议。

生产环境约束：

- 应用以 Linux x86_64 单文件可执行程序运行，由 systemd 管理。
- 用户通过内网浏览器访问 `http://服务器IP:8765`。
- 生产环境不能连接外网。
- 当前服务是单进程 `ThreadingHTTPServer`。
- 并发在线用户少于 50 人。
- 第一阶段只做应用内通知，不申请浏览器或 Windows 桌面通知权限。

## 2. 已确认需求

### 2.1 第一阶段范围

- 顶栏增加通知铃铛。
- 铃铛显示未读条数，而不只是红点。
- 未读数为 `1` 至 `99` 时显示准确数字，超过 `99` 显示 `99+`，为 `0` 时隐藏角标。
- 点击铃铛展开通知列表。
- 新通知到达时在页面右上角弹出一次。
- 通知记录持久化到 MySQL。
- 通过 SSE 实时推送在线通知。
- 通知保留 30 天，即使对应待办已经完成，也不提前删除。
- 点击单条通知后标记该条已读。
- 提供“全部已读”。
- 仅打开通知面板不会清除未读。
- 上线前已经存在的历史待办不补通知；只处理功能上线后产生的新待办事件。

### 2.2 非目标

- 不实现浏览器 Notification API。
- 不实现 Windows 原生通知。
- 不依赖互联网、外部推送平台、Redis、Kafka 或其他消息中间件。
- 不建设管理员人工发布公告页面。
- 不建设通知模板管理页面。
- 不建设短信、邮件、企业微信等外部渠道。
- 不把通知历史作为永久审计日志使用。
- 不自动把“待办完成”解释为“通知已读”。

## 3. 设计原则与模块边界

### 3.1 平台能力，不是待办模块

通知中心属于跨模块复用的平台协议能力，必须分为两个层次实施：

1. 通用通知平台：负责协议、存储、查询、已读状态、清理、SSE 和核心顶栏界面。
2. 首个业务接入：报表特殊处理模块在业务提交后调用通用平台服务。

通用通知平台不得：

- 导入 `report_special_processing` 的内部类型或存储。
- 查询报表特殊处理业务表。
- 判断 `pending`、`completed`、`voided` 等业务状态。
- 内置“特殊处理”“待确认”等业务文案。

报表特殊处理模块不得：

- 直接写通知平台的数据表。
- 直接操作 SSE 连接。
- 在全局 `server.py`、`app.js` 或 `styles.css` 中加入模块专用逻辑。

### 3.2 平台变更与模块变更分离

本功能需要新增 `platform.notification` 版本化共享服务，也需要修改核心顶栏，因此属于经过确认的平台协议变更。实施时必须先完成并验证通用通知平台，再在独立任务中修改 `report_special_processing` 模块。

### 3.3 一致性边界

业务模块必须在自身业务事务成功提交后调用通知服务，避免业务回滚但通知已经生成。通知写入是独立的短事务，并通过去重键实现幂等。

当前模块数据库事务与平台通知事务没有公共事务编排协议，因此第一阶段不承诺分布式原子性。通知写入失败时：

- 原业务结果保持成功，不做反向回滚。
- 模块记录脱敏错误、来源模块、事件类型和请求号。
- 模块可以对同一去重键进行有限重试，重复调用不会生成重复通知。
- 不在第一阶段引入通用事务外盒或消息队列。

## 4. 总体架构

```text
报表特殊处理及后续业务模块
        │
        │ platform.notification v1
        ▼
通知发布门面（自动绑定来源模块）
        │
        ▼
通知服务
├── 参数校验与幂等去重
├── MySQL 通知主体与收件状态
├── 未读计数与 30 天清理
└── 提交后发布实时事件
        │
        ▼
进程内 SSE Hub
        │
        ▼
当前登录用户的浏览器
├── 顶栏铃铛未读数
├── 全部/未读通知列表
└── 右上角即时弹窗
```

## 5. 平台通知发布协议

### 5.1 服务名称与版本

- 服务名称：`platform.notification`
- 首版协议：`1`
- 来源模块：由平台为每个模块绑定门面时自动注入，调用者不能伪造。

### 5.2 数据契约

建议后端契约：

```python
NotificationLevel = Literal["info", "success", "warning", "error"]
NotificationActionType = Literal["navigate"]

@dataclass(frozen=True)
class NotificationAction:
    type: NotificationActionType
    route: str
    query: Mapping[str, str]

@dataclass(frozen=True)
class NotificationPublishRequest:
    event_type: str
    dedupe_key: str
    recipient_user_ids: tuple[str, ...]
    category: str
    level: NotificationLevel
    title: str
    content: str
    action: NotificationAction | None = None

@dataclass(frozen=True)
class NotificationPublishResult:
    notification_id: str
    created: bool
    recipient_count: int
```

### 5.3 校验规则

- `event_type`、`category` 使用小写命名空间标识，匹配 `[a-z][a-z0-9_.-]{0,63}`。
- `dedupe_key` 必填，UTF-8 长度不超过 191 个字符。
- 接收人去空、去重后必须至少有 1 个，单次最多 100 个。
- 用户 ID 长度不超过 64，且必须是当前启用用户。
- `title` 去除首尾空白后必填，最多 191 个字符。
- `content` 最多 2,000 个字符，允许为空字符串。
- `route` 必须匹配应用内部路由格式 `[a-z][a-z0-9-]{0,63}`，不接受协议、域名、斜杠开头地址或任意 URL；点击时再由现有核心页面或模块宿主解析，未知路由显示错误且不导航。
- `query` 最多 20 个键，每个键和值最多 191 个字符，只保存字符串。
- 平台以北京时间生成 `created_at`，调用模块不能覆盖创建时间或过期时间。
- `expires_at = created_at + 30 天`。

### 5.4 幂等规则

平台根据以下组合判断同一业务事件：

```text
source_module + event_type + SHA-256(dedupe_key)
```

重复发布返回已有通知 ID，`created=false`，不会重复插入收件人，也不会再次触发 SSE 和右上角弹窗。

## 6. 数据模型

### 6.1 `system_notifications`

保存一条通用通知的公共内容。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | `CHAR(32)` | UUID hex，主键 |
| `source_module` | `VARCHAR(64)` | 来源模块，平台自动填写 |
| `event_type` | `VARCHAR(64)` | 来源内事件类型 |
| `category` | `VARCHAR(64)` | 展示分类，如 `todo`、`task`、`import`、`system` |
| `level` | `VARCHAR(16)` | `info/success/warning/error` |
| `title` | `VARCHAR(191)` | 通知标题 |
| `content` | `TEXT` | 通知正文 |
| `action_json` | `JSON NULL` | 受控内部跳转描述 |
| `dedupe_key` | `VARCHAR(191)` | 原始业务去重键，便于排障 |
| `dedupe_hash` | `CHAR(64)` | 去重键 SHA-256 |
| `created_at` | `DATETIME(6)` | 创建时间 |
| `expires_at` | `DATETIME(6)` | 30 天过期时间 |

索引：

- 主键：`id`
- 唯一键：`(source_module, event_type, dedupe_hash)`
- 清理索引：`(expires_at, id)`

`source_module`、`event_type`、`dedupe_hash` 使用 ASCII 字符集，避免旧版 MySQL 的复合索引字节数问题。

### 6.2 `system_notification_recipients`

保存每个用户独立的收件和已读状态。

| 字段 | 类型 | 说明 |
|---|---|---|
| `notification_id` | `CHAR(32)` | 通知 ID |
| `user_id` | `VARCHAR(64)` | 接收用户 ID |
| `received_at` | `DATETIME(6)` | 收件时间，等于通知创建时间 |
| `read_at` | `DATETIME(6) NULL` | 为空表示未读 |

索引：

- 主键：`(notification_id, user_id)`
- 用户列表索引：`(user_id, received_at, notification_id)`
- 用户未读索引：`(user_id, read_at, received_at)`
- `notification_id` 外键指向通知主体并 `ON DELETE CASCADE`。
- 不对 `user_id` 建用户表外键，避免删除用户时破坏通知清理和历史兼容；所有读写仍必须通过当前用户 ID 隔离。

### 6.3 数据保留

- 应用启动成功后执行一次过期清理。
- 后台每 6 小时清理一次 `expires_at <= now` 的通知主体，收件记录级联删除。
- 清理每批最多 1,000 条并循环，避免长事务。
- 应用停止时停止清理线程并释放资源。
- 待办完成、作废、重开或改派不会提前删除旧通知，也不会自动设为已读。

## 7. 查询与已读 API

所有接口都要求现有登录会话，只允许访问当前用户自己的收件记录。

### 7.1 查询列表

```http
GET /api/notifications?filter=all&limit=20&cursor=<opaque>
```

- `filter`：`all` 或 `unread`，默认 `all`。
- `limit`：默认 20，最小 1，最大 50。
- 使用不透明游标按 `received_at DESC, notification_id DESC` 翻页，不使用大偏移量。
- 只返回未过期通知。

响应：

```json
{
  "items": [
    {
      "id": "0123456789abcdef0123456789abcdef",
      "source_module": "report_special_processing",
      "event_type": "pending_confirmation_created",
      "category": "todo",
      "level": "info",
      "title": "报表特殊处理待确认",
      "content": "项目端 · 处理字段名",
      "action": {
        "type": "navigate",
        "route": "report-special-processing",
        "query": {"record_id": "12", "highlight": "1", "open": "confirm"}
      },
      "created_at": "2026-08-25T10:30:00+08:00",
      "read_at": null,
      "is_read": false
    }
  ],
  "unread_count": 3,
  "next_cursor": "opaque-or-null"
}
```

### 7.2 单条已读

```http
POST /api/notifications/{notification_id}/read
X-CSRF-Token: <current token>
```

- 仅更新当前用户对应的收件记录。
- 已读通知重复调用仍返回成功。
- 不存在或不属于当前用户统一返回 404，避免泄露其他用户通知是否存在。
- 响应返回该条 `read_at` 和最新准确 `unread_count`。

### 7.3 全部已读

```http
POST /api/notifications/read-all
X-CSRF-Token: <current token>
```

- 只更新当前用户、未过期且当前未读的通知。
- 返回 `updated_count` 和 `unread_count=0`。
- 不需要二次确认。

## 8. SSE 实时推送

### 8.1 连接

```http
GET /api/notifications/stream
Accept: text/event-stream
```

响应头至少包含：

```text
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache, no-store
Connection: keep-alive
X-Accel-Buffering: no
```

SSE 使用同源会话 Cookie 鉴权，不在 URL 中携带令牌。当前内网 HTTP 可以使用同源 SSE，不需要访问互联网。

### 8.2 事件

新通知在 MySQL 事务提交成功后才进入 SSE Hub：

```text
id: 0123456789abcdef0123456789abcdef
event: notification
data: {"notification":{...},"unread_count":3}

```

每 20 秒发送注释心跳：

```text
: ping

```

如连接队列溢出，服务端发送 `resync` 事件或关闭连接；浏览器重新查询列表与未读数，不尝试在内存中补发所有事件。

### 8.3 连接容量与资源限制

- 每个浏览器标签页一条 SSE 连接。
- 每个用户最多 5 条并发连接。
- 整个进程最多 200 条连接。
- 超限返回 429，不创建后台线程或队列。
- 每条连接使用容量 100 的有界队列。
- 用户注销、会话失效、客户端断开、应用关闭时必须注销订阅。
- 每次心跳前重新确认会话仍有效，使已注销会话的旧连接及时关闭。

### 8.4 断线与降级

- 浏览器依赖 `EventSource` 自动重连。
- 每次连接成功或重连后重新查询第一页和准确未读数。
- 断线期间产生的通知从 MySQL 列表中恢复，不会丢失。
- 重连时恢复的旧通知不补弹右上角提示。
- SSE 连续失败后，前端每 60 秒轮询通知列表第一页；SSE 恢复后停止轮询。
- 服务端不依赖 `Last-Event-ID` 完成可靠补偿，MySQL 查询是最终依据。

## 9. 前端界面

### 9.1 顶栏铃铛

- 放在 `.top-nav-actions` 内、顶部用户菜单之前。
- 按钮具有 `aria-label="通知，3条未读"` 和 `aria-expanded`。
- 铃铛使用纯主题蓝和系统圆角变量，不使用渐变或主题光晕。
- 角标使用危险红色，显示准确未读数量；`99+` 为视觉上限，辅助文本仍保留准确数。
- 未读数为 0 时隐藏角标。

### 9.2 通知面板

- 锚定铃铛右侧展开，桌面宽度约 400px，小屏幕限制在视口内。
- 最大高度约 520px，列表内部纵向滚动。
- 标题栏包含“通知”、准确未读数和“全部已读”。
- 提供“全部”和“未读”筛选。
- 每页 20 条，接近底部时按游标加载下一页。
- 打开面板不修改已读状态。
- 点击面板外、按 Esc 或再次点击铃铛关闭。

通知项包含：

- 分类图标与分类文字。
- 标题。
- 最多两行正文摘要。
- 创建时间。
- 未读点和“未读”辅助文本。
- 有跳转动作时显示“查看”。

未读使用浅蓝背景、圆点和文字共同表达；已读使用白色背景和弱化文字。空列表显示“暂无通知”，接口失败显示可重试状态。

### 9.3 点击行为

- 点击通知时先请求单条已读，再更新铃铛和列表状态。
- 标记已读失败时保留未读状态并显示错误提示，但不阻止用户查看目标业务。
- `action.type=navigate` 复用现有受控模块导航能力。
- 无动作的通知在面板内展开完整正文。
- 目标模块仍执行自己的页面与接口权限检查，通知不能绕过权限。

### 9.4 右上角即时弹窗

- 只对当前 SSE 连接实时收到的 `notification` 事件弹出。
- 展示分类图标、标题、两行正文、“查看”和关闭按钮。
- 6 秒后自动关闭，悬浮或键盘聚焦时暂停计时。
- 同时最多展示 3 条；更多通知只更新角标和列表。
- 手动关闭不标记已读。
- 点击“查看”执行单条已读并跳转。
- 当前标签页使用通知 ID 集合去重，SSE 重连、列表刷新和登录初始化不重复弹出。

### 9.5 语义色与可访问性

- `info`、待办、系统：主题蓝。
- `success`：绿色。
- `warning`：橙色。
- `error`：红色。
- 状态同时使用图标和文字，不只依赖颜色。
- 铃铛、筛选、全部已读、通知项和关闭按钮支持键盘操作及可见焦点。
- 弹窗容器使用适当的 `aria-live="polite"`，错误通知使用 `role="alert"`。

## 10. 报表特殊处理首个接入

### 10.1 当前待办语义

当前 `PendingConfirmTodoProvider` 查询分配给当前数据治理负责人的 `pending` 记录，并生成：

- 标题：`报表特殊处理待确认`
- 摘要：`维度名称 · 字段名称`
- 跳转：`report-special-processing`
- 查询参数：`record_id`、`highlight=1`、`open=confirm`

通知沿用相同标题、摘要和受控跳转，不重新发明另一套待办语义。

### 10.2 触发场景

只在业务操作提交成功并真正产生一个新的待确认关系时发布：

1. 新建正式记录，状态直接进入 `pending`。
2. 草稿提交，状态由 `draft` 进入 `pending`。
3. 已完成或已作废记录重开，状态重新进入 `pending`。
4. 记录处于 `pending` 时，数据治理负责人改派给另一个用户。

以下场景不发布：

- 保存草稿。
- `pending` 状态下只修改正文、脚本、摘要等普通字段且负责人未变化。
- 完成、作废或删除记录。
- 查询或刷新“我的待办”。
- 应用启动时扫描既有待办。
- 功能上线前已经存在的历史待办。

### 10.3 收件人与去重

- 收件人是提交后记录的 `governance_owner_user_id`。
- 无有效、启用的负责人时不发布；正式提交本身应由现有验证拒绝无负责人数据。
- 去重键格式：`rsp-pending:{record_id}:{row_version}:{recipient_user_id}`。
- 重开和改派会增加 `row_version`，因此会生成新的通知。
- 重试相同业务结果时仍使用相同版本和收件人，不重复通知。
- 旧负责人已经收到的历史通知继续保留 30 天，不因改派自动删除或改为已读。

### 10.4 通知内容

```python
NotificationPublishRequest(
    event_type="pending_confirmation_created",
    dedupe_key=f"rsp-pending:{record_id}:{row_version}:{owner_id}",
    recipient_user_ids=(owner_id,),
    category="todo",
    level="info",
    title="报表特殊处理待确认",
    content=f"{dimension_label} · {field_name}",
    action=NotificationAction(
        type="navigate",
        route="report-special-processing",
        query={"record_id": str(record_id), "highlight": "1", "open": "confirm"},
    ),
)
```

模块清单增加 `platform.notification` 最低版本 1 的服务依赖。模块启动时解析通知服务并注入业务服务，停用模块后绑定门面自动失效。

## 11. 安全与隐私

- 所有通知 HTTP 接口要求登录。
- 修改类接口要求现有 CSRF 校验。
- 通知 ID 不作为授权依据，所有查询与更新都附加当前用户 ID 条件。
- 404 响应不区分“不存在”和“不属于当前用户”。
- SSE 不在 URL、日志或事件数据中传递会话令牌。
- 模块不能指定 `source_module`。
- 动作只允许应用内部路由和字符串查询参数。
- 通知正文不得包含密码、连接串、SQL、驱动错误栈或未脱敏敏感数据。
- 日志记录事件类型、来源、通知 ID、请求号和错误编号，不记录完整通知正文。

## 12. 生命周期与故障隔离

- 通知平台初始化失败属于平台启动失败，不能以“无通知”状态静默运行。
- 可选业务模块未声明通知服务依赖时不能解析服务。
- 单个业务模块发布失败不影响其他模块和现有 SSE 连接。
- 单个 SSE 客户端写入失败只移除该连接。
- 浏览器脚本加载失败不影响现有页面和业务模块，只隐藏通知入口并记录前端错误。
- 关闭服务时依次停止接受新 SSE、关闭订阅、停止清理线程，再关闭 HTTP Server 和数据库资源。

## 13. 部署与兼容性

- 不新增第三方 Python 或前端依赖。
- 不改变当前端口 8765。
- 不要求 HTTPS 即可实现应用内通知和 SSE。
- 不要求生产环境访问外网。
- 数据库升级前备份 `auto_check` 数据库并执行新增 SQL。
- Linux 单文件打包需要包含新增前端 JS/CSS 资源；只有用户明确要求打包时才构建或刷新产物。
- 不提升展示用大版本号；应用内更新日志并入当前系统版本。

## 14. 测试范围

### 14.1 数据库与服务

- SQL 建表、索引、字符集和外键契约。
- 发布参数校验。
- 相同去重键幂等。
- 多收件人独立已读。
- 用户隔离。
- 游标分页稳定性。
- 30 天过期过滤与分批清理。
- 不存在或无权通知统一 404。

### 14.2 平台协议

- 模块必须声明 `platform.notification` 才能解析。
- 来源模块由绑定门面注入且不可伪造。
- 门面关闭后拒绝发布。
- 无效内部路由和过大负载被拒绝。

### 14.3 SSE

- 只向目标用户连接推送。
- 多连接接收同一实时事件。
- 心跳格式正确。
- 队列溢出触发重同步而不是无界增长。
- 超过用户或全局连接限制时拒绝。
- 断开、注销和服务停止后清理订阅。
- 通知事务提交前不推送，重复发布不推送。

### 14.4 前端

- 顶栏铃铛结构和可访问属性。
- `0` 隐藏、`1..99` 准确显示、`100+` 显示 `99+`。
- 打开列表不标记已读。
- 单条已读和全部已读更新准确数量。
- 全部/未读筛选和游标加载。
- SSE 新事件插入列表并只弹一次。
- 重连只同步列表，不补弹旧通知。
- 最多同时显示 3 个弹窗。
- 销毁时关闭 EventSource 和降级轮询。
- JS 语法检查与 CSS 作用域检查。

### 14.5 首个待办接入

- 新建正式记录发布一次。
- 草稿保存不发布，草稿提交发布一次。
- 重开发布一次。
- `pending` 改派给新负责人发布一次。
- 普通编辑、完成、作废、删除和查询待办不发布。
- 相同业务结果重试不重复发布。
- 启动时不扫描和补发历史待办。

## 15. 验收标准

1. 登录用户在任意页面都能看到顶栏铃铛。
2. 铃铛显示准确未读数，超过 99 显示 `99+`。
3. 新待办提交成功后，在线接收人 1 秒内看到数量变化和一次右上角弹窗。
4. 非接收人不看到该通知，也不能通过通知 ID 读取或标记。
5. 刷新页面、切换页面、SSE 重连不会重复弹出同一旧通知。
6. 浏览器断线期间的新通知在恢复后出现在列表和未读数中。
7. 打开面板不清除未读；单击通知和“全部已读”行为符合约定。
8. 通知对应待办完成后仍保留，直到创建满 30 天。
9. 上线前历史待办不生成通知。
10. 生产内网无需外网、HTTPS、Redis 或消息队列即可运行。
11. 通知平台与报表特殊处理模块边界清晰，通用层不包含待办专用代码。
12. 相关测试、全量测试、JS 语法检查及 `git diff --check` 通过。

## 16. 回滚方案

### 16.1 代码回滚

- 先移除报表特殊处理模块对 `platform.notification` 的依赖和发布调用。
- 再移除核心通知 API、SSE、前端入口和平台服务注册。
- 回滚不会影响报表特殊处理原业务数据和现有待办查询。

### 16.2 数据回滚

- 默认保留两张通知表，代码回滚后它们不会被访问。
- 如确认不再需要且已备份，可人工删除 `system_notification_recipients`，再删除 `system_notifications`。
- 不在应用启动或模块停用时自动删表。

## 17. 后续扩展方向

后续业务模块通过 `platform.notification` 接入，不改变通知中心核心：

- 后台任务完成或失败。
- 文件导入成功或失败。
- 数据校验结果。
- 系统维护公告。
- 权限或账号状态变化。
- 将来在 HTTPS 或浏览器策略允许时，增加浏览器桌面通知渠道。

新增管理员公告、通知偏好、外部渠道或可靠事务外盒时，应分别形成新设计，不在第一阶段预埋复杂实现。
