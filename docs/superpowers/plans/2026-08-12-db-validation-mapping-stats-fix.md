# 人行逐笔映射统计与必需字段口径修正

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已确认口径修正映射刷新、统计与弹窗，使「表 / 字段 / 必需缺失」分清，数字可信。

**Architecture:** 刷新时按逻辑表独立构建字段映射；必需中文字段改为「按表（及模板/公开信息）」集合；统计以物理业务列为基准；前端直接展示后端四类计数，弹窗默认优先异常项。

**Tech Stack:** Python（`mapping_service` / `mapping_storage` / `rules/basic`）、现有 app DB 快照表、前端 `app.js` 映射弹窗。

## Global Constraints

- 表：ZG01～ZG13 从源端认出物理表；模板/公开信息用固定表名（017 种子 + 人工覆盖）。
- 字段：只做「这张表的中文业务名 → 这张表的英文字段」。
- 必需缺失：只检查「这张表、这次规则真正用到的中文字段」能不能映射到。
- 统计分开：已映射 / 物理列无中文（未映射） / 规则要用但找不到（必需缺失） / 配置了英文但表里没有（配置不存在）。
- 不兜底旧英文业务字段；不提交/推送/打包除非用户要求。
- 改代码前本方案需用户认可。

### 工作区约定（必须遵守）

- **正式主仓**：`D:\xiaxin\auto_check` —— 日常主工作区，本次修 bug **不得**在此目录改代码、写方案附件或跑会污染主仓状态的操作。
- **本次临时工作区**：`D:\cherry\autocheck_jmxkf\autocheck` —— 为避免污染主仓而临时拉出的副本，**本方案及全部实现、测试、本地验证只允许在此路径进行**。
- 不得 `reset` / `checkout` 覆盖本临时仓中与本次无关的已有本地改动。
- 未获用户明确授权前：不向远程推送；不把改动同步/合并回 `D:\xiaxin\auto_check`。

---

## 口径定义（实现准绳）

### 表映射

| 类型 | automatic 来源 |
|------|----------------|
| detail ZG01～ZG13 | 源端 baseinfo `table_name_en` |
| template / public_info | 固定种子表名，不从源端刷表名 |

人工 override 优先，刷新保留。

### 字段映射（每张逻辑表独立）

以该表**物理业务列**为基准（排除技术字段清单）：

| 状态 | 含义 |
|------|------|
| `mapped` | 物理列能对应到有效中文业务名 |
| `unmapped` | 物理列找不到中文业务名 |
| `missing_physical` | 字段信息里有中文→英文，但物理表无该英文列 |

`field_count` = 上述三类之和（= 物理业务列数；`missing_physical` 单独展示时仍可计入明细，但**汇总「业务字段总数」以物理列为准**：`mapped + unmapped`）。
`required_missing` **不计入**业务字段总数，只作为规则缺口计数与明细行。

### 必需缺失（按表）

为每个逻辑范围维护中文必需集合：

- `detail:ZG01` … `detail:ZG13`：仅该 ZG 规则实际读取的中文字段
- `template`：模板交叉规则实际用到的中文（若无可为空集）
- `public_info`：公开信息规则实际用到的中文

仅当「该表必需中文」无法解析到当前有效英文字段时，记 `required_missing`。
**禁止**把全局 92 个中文字段套到每一张逐笔表。

任务启动预检：只对**本次勾选**的表/模板/公开信息检查对应必需集合。

---

## 文件职责

| 文件 | 职责 |
|------|------|
| `rules/basic.py` | 将 `REQUIRED_CHINESE_FIELDS` 改为按 `ZGXX` / template / public_info 的字典或函数 |
| `mapping_service.py` | 按表取必需集合；修正字段构建与统计口径 |
| `mapping_storage.py` | 快照计数与 `status_payload` 与上口径一致（如已正确则只补测试） |
| `server.py` | 刷新传入按表必需集合；启动预检按所选表取集合 |
| `web/app.js` | 状态文案用后端四类计数；弹窗展示异常优先、显示 scope、取消错误去重 |
| `tests/test_db_validation_mapping_*.py` 等 | 锁定口径与回归 |

---

## Task 1: 按表必需中文字段

**Files:** `src/auto_check/db_validation/rules/basic.py`, `tests/...`

- [ ] 新增 `REQUIRED_CHINESE_FIELDS_BY_SCOPE: dict[str, frozenset[str]]`（key 如 `ZG01`…`ZG13`、`TEMPLATE`、`PUBLIC_INFO`），从各 ZG 规则函数源码提取中文参数；删除或降级全局扁平集合的误用。
- [ ] 单测：ZG01 集合含「产品代码」等本表字段；不含明显仅属其他表的字段（抽样断言）。
- [ ] `mapping_service._build_fields_for_table` 只传入**当前表**的必需集合；表不可读时也只标记该表必需字段，不灌全局清单。

## Task 2: 刷新统计口径

**Files:** `mapping_service.py`, `mapping_storage.py`, tests

- [ ] `field_count` / `mapped` / `unmapped` / `missing_physical` / `required_missing` 按上文准绳写入快照。
- [ ] 红绿测试：一张表 10 物理列、8 有中文、2 无中文、1 条配置英文字段不存在、3 条本表必需中文缺失 → 计数分别为 mapped=8, unmapped=2, missing_physical=1, required_missing=3；业务字段总数=10（或明确文档化为 mapped+unmapped）。
- [ ] 禁止再出现「每张 detail 表 required_missing ≈ 全局集合大小」的结果。

## Task 3: 启动预检

**Files:** `server.py`, `mapping_storage.required_missing_for_tables`, tests

- [ ] 预检只返回所选逻辑表范围内的 `required_missing`。
- [ ] 仅有 `unmapped` 不拦截；所选表存在 `required_missing` 才拦截。

## Task 4: 前端状态与弹窗

**Files:** `web/app.js`, `index.html`（若需列头/筛选）, `tests/test_web_static.py`

- [ ] 状态文案使用 `mapped_field_count`、`unmapped_field_count`、`required_missing_count`、`missing_physical_count`，禁止 `fieldCount - unmappedCount`。
- [ ] 弹窗：逻辑表展示含 template `scope`（如 ZG09/口径1）；默认或一键优先异常状态；「未映射」视图包含 `unmapped`+`required_missing`+`missing_physical`，**取消**按 `automatic_field_name` 跨表去重。
- [ ] 摘要同步真实四类数字。

## Task 5: 验证

- [ ] 专项映射测试 + `python -m pytest -q`
- [ ] 本地刷新后目视：状态数字与弹窗一致；ZG01 不再出现成片「别的表字段缺失」

---

## 非目标（本次不做）

- 不改 ZG09/ZG10 模板指标编码匹配逻辑
- 不自动从源端刷新模板/公开信息物理表名
- 不提交、不推送、不打包（除非另有指示）

---

## 交接备注（2026-08-12）

**用户已确认口径，并同意开改；同时指出人工修改映射也有问题。代码尚未落地（本会话只写了方案、完成了问题定位）。**

### 已确认真实数据（快照 id=18）

- 显示 `1815/1838 已映射，23 未映射` 是假象
- 实际：`mapped=645`，`unmapped=23`，`required_missing=1170`，`missing_physical=0`
- 根因：全局 92 个必需中文 × 每张 detail/不可读表；前端用 `fieldCount - unmapped`

### 人工修改已知缺陷（需一并修）

1. 覆盖/恢复后**不重算**快照 `unmapped/required_missing/mapped` 计数
2. **恢复**只清 override，不回写正确的 `mapping_status`
3. **无中文名的 unmapped 行**：`chinese_name` 为空，覆盖 UPDATE 匹配不到；唯一键也按中文名
4. 未映射行「修改」语义应是：绑定中文业务名 → 该物理英文列（不是只改英文名）
5. 表覆盖后字段快照可能过期，应提示重新刷新（或覆盖后触发刷新）
6. 前端覆盖成功后未刷新设置页状态文案

### 建议下一模型直接执行

工作目录必须是：`D:\cherry\autocheck_jmxkf\autocheck`（临时仓）；禁止改 `D:\xiaxin\auto_check`。
方案文件：`docs/superpowers/plans/2026-08-12-db-validation-mapping-stats-fix.md`
任务顺序：按表必需字段 → 刷新统计 → 启动预检 → **人工覆盖/恢复** → 前端状态/弹窗 → `pytest -q`
不要 reset 无关本地改动；不要提交/推送/打包/同步回主仓，除非用户要求。
