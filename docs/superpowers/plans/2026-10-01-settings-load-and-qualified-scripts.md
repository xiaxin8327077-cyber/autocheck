# 系统设置离页加载与特殊处理脚本限定表名实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement the two independent tasks and review their combined changes. Steps use checkbox syntax for tracking.

**Goal:** 取消离开系统设置后的过期加载与渲染，并在特殊处理自动脚本中使用数据源的 Schema／数据库限定表名和数据库方言引用。

**Architecture:** 设置加载使用独立作用域，包含取消控制、请求代次及会话检查；共享 loader 的普通调用保持既有行为。特殊处理前端预览与后端生成分别使用同一限定规则，数据源元信息由模块接口提供，脚本仅保存和展示，不在系统内执行。

**Tech Stack:** 原生 JavaScript、Python、Node 行为测试、pytest。

## Global Constraints

- 用户已认可设置离页清理方案并授权本次脚本增强；在当前目录和分支开发，不创建分支或 worktree。
- 保留已有未提交改动，特别是 README、app.js、test_web_static.py 和逐笔规则相关文件。
- 暂不使用 Astra；不自动打包、提交、推送或部署。
- 特殊处理业务代码只能修改本模块及对应测试、文档，不混入平台设置清理代码。
- PostgreSQL 使用 Schema，MySQL 使用 database；普通标识符直接输出，仅需引用的模式／库名、表名和字段用双引号或反引号，内部引用符加倍转义。保留物理标识符大小写，不使用数据源展示名当作库名。用户后续明确不为普通名称统一加引号。
- 不覆盖 MANUAL 脚本，不执行生成 SQL，不增加数据库迁移或权限入口。

## Task 1: 设置加载生命周期

**Files:** `src/auto_check/web/app.js`；`tests/test_web_static.py`；新增独立设置导航行为测试。

**Interfaces:** 设置页加载上下文将取消信号和有效性判断传给可复用 loader；省略上下文的工具页、初始化、保存后刷新调用保持原有行为。

- [x] 先补行为测试：设置请求 pending 时切到角色／用户／字典页；旧成功或失败响应不得写状态、DOM 或错误反馈；覆盖快速往返与未启动定时器。
- [x] 运行测试确认旧代码失败，再实现独立取消作用域。
- [x] 在模块宿主停用前处理设置离页；覆盖直接模块导航和认证边界；每个 await 后、catch/finally 及总加载末尾检查有效性。
- [x] 保留界面偏好的超时、草稿与保存保护；导航取消不影响全局流程浮窗轮询或后台任务。
- [x] 运行相关静态、界面偏好、认证恢复和模块宿主测试，复核现有未提交日志改动未被覆盖。

## Task 2: 特殊处理自动脚本限定表名

**Files:** `src/auto_check/modules/report_special_processing/sql_builder.py`、`service.py`、`metadata.py`、`web/components/script_preview.js`、必要的结构化编辑组件；`tests/modules/report_special_processing/`；模块 README 与设计说明。

**Interfaces:** 使用现有数据源 ID 对应的真实 db_type、schema、database；前端和后端处理相同字段并产生相同限定 SQL。已有结构化快照与当前数据源的兼容规则按现有安全校验保留。

- [x] 先补测试：PostgreSQL Schema、MySQL database、数字开头、连字符、空格、保留字、大小写、内部引用符、点号和已有限定表名；覆盖前端预览／后端一致性以及 MANUAL 脚本。
- [x] 运行测试确认失败，再实现分段限定和引用，保留条件与值的现有生成语义。
- [x] 数据源元信息缺失时沿用可证明安全的现有回退；不猜测错误库名／Schema，不把已经限定的名称重复拼接。
- [x] 同步模块说明，说明自动脚本使用的数据源范围与引用规则。
- [x] 运行模块相关测试并交由独立审查复核边界。

## Task 3: 集成与交付验证

- [x] 在现有 v1.3.2 简约日志中同步系统优化与模块脚本功能；模块 release_notes 只写本模块本次功能，保留用户现有更新。
- [x] 独立子代理审查两项差异，修复明确问题。
- [x] 委派运行 `.runtime/dev-venv/Scripts/python.exe -m pytest -q`，运行 `git diff --check`。
- [x] 确认本地服务仍运行并返回可测试链接；如必须重启，先确认原 PID 及配置，不覆盖配置、不打包。
- [x] 汇报代码、文档、行为与实际验证范围；生产的约一秒改善仍需在实际环境验证。

## 验证记录

- 设置生命周期新增测试旧实现 8 项失败；退出失败恢复补测先失败再修复。最终设置、静态页面、认证恢复与模块宿主组合 354 passed。
- 脚本限定首轮新测试旧实现 15 failed / 1 passed；最终专项 34 passed，真实抽屉覆盖元数据加载和旧脚本模式保护。
- 全量 pytest：2787 passed / 11 skipped / 1 warning，退出码 0；末期模块变化补跑 394 passed / 9 skipped，退出码 0。跳过项包含未配置真实数据库的用例；警告为 SQLite datetime adapter 弃用提示。
- 独立审查发现的原始控制字符校验、合法名称空格和元数据范围空格问题已修复并复核。最新四个 JS 文件语法检查及全目录差异检查通过。
- 本地源码曾完成 HTTP 验证；用户随后要求仅提交改动，已停止本次启动的开发服务。
- 本次提交不包含已有逐笔规则改动；未打包、推送或部署。生产环境的切页延迟改善尚需实际验证。

## 后续反馈

- 用户要求普通物理名称不加引号；前后端改为按需引用，保留特殊名称的转义及历史脚本保护。
- 用户反馈从系统设置点击其他菜单后仍停留约一秒，随后才显示目标页。先完成只读排查；用户随后认可控件分批读写、分帧处理、折叠字段按需增强和离页取消方案，详见同日控件性能方案。
- 按需引用修正专项 66 passed、抽屉保护 2 passed，模块组合 411 passed / 9 skipped；最终与控件性能修复统一运行全量测试，2842 passed / 11 skipped / 1 warning，退出码 0。
