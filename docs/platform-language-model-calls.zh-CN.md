# 共享模型调用协议

`platform.language_models` 当前提供版本 2。服务按最低版本解析：已有依赖版本 1 的模块继续调用原方法，新调用控制接口需声明最低版本 2。注册器仍只注册一个同名服务，不增加业务专用路由。

## 原有接口

`complete(model_id, messages, *, timeout_seconds, cancel_event=None) -> str`

请求仅发送模型与消息，沿用供应商默认设置，返回正文字符串。模型选择、关闭与协作取消行为保持兼容。

## 调用控制与诊断

`complete_with_options(model_id, messages, *, timeout_seconds, cancel_event=None, options=None) -> dict`

允许的控制项：

| 参数 | 允许值 |
| --- | --- |
| `thinking` | `{"type":"enabled"}` 或 `{"type":"disabled"}` |
| `reasoning_effort` | `none`、`low`、`high`、`max` |
| `response_format` | `{"type":"json_object"}` |
| `max_tokens` | 正整数，布尔值和字符串不被接受 |
| `temperature` | 闭区间 [0, 2] 内的有限 JSON 数值，包括 0。布尔值、字符串、NaN 及无穷值会在发出请求前被拒绝。 |

只传调用方明确提供的白名单选项。平台不猜测供应商默认行为，不允许覆盖模型名、接口地址、访问密钥或任意 HTTP 参数。网关不拒绝参数不等于采用了参数，消费模块须根据其线路能力和实测决定启用项。

数据校验的结构化生成在现有版本 2 接口上显式传入 `temperature: 0`，以减少多次分析同一需求时的采样差异。当前配置的网关已通过该值的请求验证。其他调用方省略该项时沿用各自供应商的采样策略，无需改动模型配置。相同温度下的输出仍可能有差异。

`none` 可用于支持该参数的线路请求关闭推理，参见 [DeepSeek Chat Completions 官方协议](https://api-docs.deepseek.com/api/create-chat-completion/)。私有网关是否采用该设置仍须单独验证。

返回：

- `content`：纯文本正文；空正文为空字符串。非字符串结构块被拒绝，不将思考块转换成正文。
- `finish_reason`：供应商给出的字符串终止原因，缺失时为空。调用方应拒绝把截断或过滤后的不完整结果视为成功。
- `usage`：白名单内的非负整数输入、输出、总用量及缓存/推理用量；供应商未提供的值不估算、不补零。
- `model`：供应商实际返回的模型标识；未提供或类型无效时为空，不用请求别名代替。
- `duration_ms`：当前调用的本地耗时，包含配置读取和上游请求，不代表首字耗时。

接口不返回思考正文、密钥、地址、HTTP 响应头或其他任意上游元数据。JSON 格式、业务结构完整性和真实文档依据由消费模块分别验证。

数据库配置结构与持久数据不变。整体回滚时先使使用新方法的模块退回版本 1 调用，再回滚平台；不改变旧消费者的行为。
