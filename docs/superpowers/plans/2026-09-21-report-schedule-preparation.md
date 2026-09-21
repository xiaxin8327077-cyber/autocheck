# 报送日期提前准备实施方案

> **For agentic workers:** 使用 superpowers:executing-plans 按任务实施，测试可委派；本方案已获用户认可，通知需求由用户追加授权。

**Goal:** 月初前准备报送日期，对无法自动准备的日期向管理员发站内通知。

**Architecture:** 由原生报送导航拥有独立日期准备服务，统一定时任务仅负责调度。复用现有月份日期表、通知中心、用户目录，不改变看板外部接口或 kanban。

**Tech Stack:** Python、SQLAlchemy Core、MySQL、现有统一调度器和通知平台。

## 约束与行为

- 新任务 `report_navigation_schedule_prepare`，名称“报送日期预生成”，默认北京时间每天 15:00；启动时在调度线程运行前补查一次。保留管理页的配置、停用、删除和恢复能力，不自动恢复已删除任务。
- 每次补查当月和下月，12 月同时准备次年 1 月。只处理已启用且在目标月份需要报送的流程，不执行报送数据统计或 DWS SQL。
- 有日期则保留；月末前只检查下月并提醒维护，到本月最后一天仍缺失才沿用上年同月日号。错过月底运行时，当月缺失可立即补漏。闰年 2 月 29 日在非闰年收敛为 28 日。保留原有人行集中报送默认每月 1 日规则，同样仅在月末或当月补漏时写入。
- 写入采用主键冲突时不更新，防止并发人工维护被覆盖；人工维护 API 仍可正常更新。
- 尚未维护、缺少历史配置、日期月份异常、读取或继承失败时逐项记录，继续其他流程。通知所有启用的管理员，包含目标月份、流程、原因和报送导航入口。相同月份/流程/原因/收件人复用通知平台持久去重（保留 30 天），不把原始异常或连接信息写入通知。
- 异常写入任务失败状态，启动继续；通知发送失败也记录任务失败，后续运行重试。
- 新增 `023_report_navigation_schedule_prepare.sql` 只幂等预置任务，已有配置不覆盖；无需新增表、修改 schema 版本或对外返回字段。

## Task 1：日期准备与管理员通知

文件：`app/report_navigation_schedule_preparation.py`、`app/report_navigation.py`、`app/storage_report_navigation.py`，测试 `tests/test_report_navigation_schedule_preparation.py`（上述 app 路径均在 `src/auto_check/` 下）。

接口：`ReportNavigationService.prepare_schedules(*, now=None)` 返回 `SchedulePreparationResult(months, checked_count, ready_count, issues)`；问题为 `SchedulePreparationIssue(report_month, process_code, process_name, reason)`。独立函数 `run_schedule_preparation(service, notification_service, user_directory, *, now)` 处理通知和脱敏失败汇总。

- [x] 先运行新用例确认缺失接口产生预期失败。
- [x] 实现当月/下月枚举、启用月份过滤、按流程异常隔离。
- [x] `upsert_schedule(..., only_if_missing=True)` 使用 `ON DUPLICATE KEY UPDATE process_code=VALUES(process_code)`；`ensure_schedule` 使用此模式并校验日期归属月份。
- [x] 通知使用 `NotificationPublishRequest`，source 为 `report_navigation`，通过 `list_active_users()` 选择 active 的 admin；成功无通知，问题存在则写失败概要。
- [x] 运行 `python -m pytest -q tests/test_report_navigation_schedule_preparation.py tests/test_report_navigation.py`。

## Task 2：接入调度与交付

文件：`app/scheduled_tasks.py`、`app/server.py`、新升级 SQL、README、部署文档、`web/app.js` 更新日志；测试现有定时任务和部署说明。

- [x] 注册新模板并由 server 注入现有只读 user directory。启动时执行启用的新任务，复用执行状态和下次时间计算；之后启动串行线程。
- [x] 新 SQL 重复执行保留任务配置；更新部署步骤至 023，完整表数仍为 56。
- [x] 同步 v1.2.31 功能说明与精简应用内日志，不变更 V1.2 大版本。
- [x] 运行直接相关测试后运行 `python -m pytest -q`，区分已知文档基线失败，执行 `git diff --check`。
- [x] 在开发库应用 023 并重启已核实身份的源码进程，验证任务规则、启动状态、日期与 LAN HTTP；不修改原有其他任务配置。不打包、不提交、不推送。

回滚：停用或删除新任务，必要时回退相应源码；保留已生成日期供人工核对，不批量删除业务数据。

验证记录：服务入口缺失的测试先失败（1 failed）；随后通过内存应用库构造 12 月 1 日提前继承场景，断言下月不得写入也先失败，再实现月末限制。通知跳转沿用现有导航，只传递完整 action 对象，不新增页面。

交付验证（2026-09-21）：相关集合 202 passed；全量 2350 passed、11 skipped、2 failed。两项失败均为已有 tests/module_system/test_documentation.py 文档字符串断言，与本次改动无关；未修改该基线。SQL 023 在开发库连续执行两次验证幂等，原任务配置保留。源码服务已重启，任务启动补查 success，下次执行 2026-09-21 15:00；9/10 月各 7 个流程日期完整，未生成待维护通知。本机与局域网 8765 页面均返回 200。通知过期去重已使用真实 SQLite 通知仓储验证，git diff --check 无实际空白错误。未打包；提交和推送按用户后续明确要求执行。
