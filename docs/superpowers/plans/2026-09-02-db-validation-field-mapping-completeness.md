# 人行逐笔校验字段映射完整性修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 ZG07“贷款余额折人民币”未进入字段映射导致 `Zg05_Rule3` 将汇总值识别为 0 的问题，并补齐审计确认的其他字段清单遗漏。

**Architecture:** 保持现有按表字段声明和映射快照架构，只补齐规则真实依赖的字段声明。测试覆盖声明、映射生成和跨表规则读取链路，避免仅用中文测试数据绕过映射层。

**Tech Stack:** Python 3、pytest、现有 `DbValidationMappingService` 与 `DbValidationEngine`。

## Global Constraints

- 不修改数据库结构、公共入口、前端、权限或版本号，不写死英文字段名。
- 测试和验证交由子代理执行，主会话检查结果。
- 不自动打包、提交或推送。

---

### Task 1: 建立失败回归测试

**Files:**
- Modify: `tests/test_db_validation_mapping_service.py`
- Modify: `tests/test_db_validation_engine.py`

- [x] 增加 ZG07 必需字段集合包含“贷款余额折人民币”的断言。
- [x] 增加任意运行时物理字段名经字段目录注入后参与 `Zg05_Rule3` 汇总的测试，证明实现不依赖固定英文列名。
- [x] 运行最小测试，确认修复前因字段声明遗漏而失败。

### Task 2: 修复字段声明并审计其他遗漏

**Files:**
- Modify: `src/auto_check/db_validation/rules/basic.py`
- Modify: `src/auto_check/db_validation/tables.py`
- Modify: `src/auto_check/db_validation/engine.py`
- Modify: `src/auto_check/db_validation/mapping_service.py`
- Test: `tests/test_db_validation_mapping_service.py`
- Test: `tests/test_db_validation_engine.py`

- [x] 将“贷款余额折人民币”加入 ZG07 必需字段集合。
- [x] 将“初始募集金额”加入 ZG02 必需字段集合。
- [x] 将“金融机构编码”和“数据管理机构”按实际读取范围加入可选字段集合，缺失时不得阻断运行。
- [x] 对比全部规则读取字段与按表字段集合，确认没有其他高置信遗漏。
- [x] 让执行引擎和启动预检共用逐笔表直接依赖定义，确保选择 ZG05 时同步预检 ZG07、ZG08。
- [x] 运行最小测试，确认修复后通过。

### Task 3: 同步规则说明并完成验证

**Files:**
- Modify: `src/auto_check/db_validation/rules_document.py`
- Modify: `tests/test_db_validation_rules_document.py`

- [x] 在 `Zg05_Rule3` 规则备注中说明 ZG07 字段映射依赖，并增加文档测试。
- [x] 运行逐笔校验相关测试和全量测试。
- [x] 运行 `git diff --check` 并检查最终差异范围。
