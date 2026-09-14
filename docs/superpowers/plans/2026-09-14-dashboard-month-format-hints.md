# Dashboard Month Format Hints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在输出字段区域按数据区域标注 `month` 字段格式。

**Architecture:** 直接更新三个内置 `month` 字段的目录说明，服务启动时由现有种子同步机制写入数据库。提示仅影响字段说明，不参与字段和 SQL 处理。

**Tech Stack:** 原生 JavaScript、模块作用域 CSS、pytest 静态契约测试。

## Global Constraints

- 仅修改 `dashboard_management` 模块、对应测试和文档。
- 不改变 SQL、接口和看板解析逻辑。
- 不打包、不提交、不推送。

---

### Task 1: 月份格式提示

**Files:**
- Modify: `tests/modules/dashboard_management/test_catalog.py`
- Modify: `src/auto_check/modules/dashboard_management/catalog.py`
- Modify: `src/auto_check/modules/dashboard_management/README.md`

**Interfaces:**
- Consumes: `BUILTIN_FIELD_SEEDS`
- Produces: 三个内置 `month` 字段的格式化说明。

- [x] **Step 1: 写入失败的静态测试**

断言三个区域编码及两种格式文案存在于内置字段目录。

- [x] **Step 2: 运行测试并确认因提示尚不存在而失败**

Run: `python -m pytest -q tests/modules/dashboard_management/test_frontend_static.py`

- [x] **Step 3: 实现最小展示逻辑与样式**

更新三个内置 `month` 字段的说明，由现有种子同步机制更新数据库记录。

- [x] **Step 4: 同步模块说明并运行模块测试**

Run: `python -m pytest -q tests/modules/dashboard_management`

- [x] **Step 5: 检查差异**

Run: `git diff --check`
