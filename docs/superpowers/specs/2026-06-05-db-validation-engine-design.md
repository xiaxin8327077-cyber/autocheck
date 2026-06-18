# 资管逐笔数据库校验引擎设计

状态：已确认，待实施计划。

日期：2026-06-05

## 目标

在 `auto_check` 中新增“资管逐笔数据库校验”能力。校验数据从数据库读取，规则按已反编译的旧审核程序复刻，结果继续输出 Excel，并保持旧程序结果文件的结构和命名格式一致。

本期只做逐笔数据校验和跨期校验。不做模板校验，不做公开信息校验。

## 已确认约束

- 数据库类型同时支持 MySQL 和 PostgreSQL。
- 数据库连接复用 `auto_check` 现有配置，不新增独立连接模型。
- 校验运行时由用户从现有配置中选择逐笔数据源。
- 字段匹配元数据源独立放在系统设置中，运行时自动使用。
- 逐笔当期数据不按 `caldate` 过滤，按表名区分。
- 当期表使用无后缀原表名。
- 上期表使用原表名追加 `_YYYY_MM` 后缀，例如 `zgxgzh_projholdinfo_zg04_2026_04`。
- 报告期默认上月底，可由用户重新输入。
- 系统根据报告期自动推导上期日期和上期表后缀。
- 输出文件固定显示 `模板校验（否）-公开信息校验（否）`。

## 表名映射

逐笔逻辑表固定为 13 张：

| ZG 编号 | 当期表名 |
| --- | --- |
| ZG01 | `zgxgzh_baseinfo_zg01_26` |
| ZG02 | `zgxgzh_begraiseinfo_zg02_26` |
| ZG03 | `zgxgzh_projendinfo_zg03_26` |
| ZG04 | `zgxgzh_projholdinfo_zg04` |
| ZG05 | `zgxgzh_projdebt_zg05_2024` |
| ZG06 | `zgxgzh_beneficial_zg06` |
| ZG07 | `zgxgzh_ioudetail_zg07` |
| ZG08 | `zgxgzh_spvdetail_zg08` |
| ZG09 | `zgxgzh_debtordate_zg09` |
| ZG10 | `zgxgzh_surecinfo_zg10` |
| ZG11 | `zgxgzh_industinfo_zg11` |
| ZG12 | `zgzgzh_zg12` |
| ZG13 | `zgzgzh_zg13` |

上期表名由当期表名加报告期上一个月的后缀生成。报告期为 `2026-05-31` 时，上期表后缀为 `_2026_04`。

## 字段匹配元数据

字段映射不靠代码猜测，也不靠逐笔表 DDL 的注释。引擎启动时从元数据表读取字段字典。

元数据表：

- `xt_reg_table_baseinfo`
- `xt_reg_table_field_info`

匹配关系：

- `xt_reg_table_baseinfo.table_name_en` = 逐笔英文表名。
- `xt_reg_table_baseinfo.id` = `xt_reg_table_field_info.table_id`。
- `xt_reg_table_field_info.field_propert` = 逐笔表英文字段名。
- `xt_reg_table_field_info.field_name` = 中文字段名，对应旧校验程序中的列名。

系统设置新增“字段匹配数据源”：

- 选择一个现有配置。
- 选择配置中的 `dws` 或 `business` 来源。
- 配置 `baseinfo` 表引用，默认 `test.xt_reg_table_baseinfo`。
- 配置 `field_info` 表引用，默认 `test.xt_reg_table_field_info`。

这样逐笔数据表和字段映射表可以在同一个数据库连接中，也可以位于不同库或不同 schema。

## 架构

采用方案 A：Python 规则引擎 + 数据库适配层。

新增模块建议放在 `src/auto_check/db_validation/`：

- `config.py`：校验专用设置、报告期计算、表引用配置。
- `metadata.py`：加载字段匹配元数据，生成中文列名到英文列名的映射。
- `tables.py`：维护 13 张 ZG 表映射、当期表名和上期表名生成。
- `reader.py`：通过现有 `DatabaseClient` 读取 MySQL/PostgreSQL 数据。
- `engine.py`：编排校验流程，生成统一结果行。
- `rules/`：按 ZG 表拆分规则，例如 `zg01.py`、`zg04.py`。
- `excel.py`：输出旧程序格式的 Excel。
- `jobs.py`：后台任务状态、进度、结果文件路径。

规则层只使用字段逻辑名和 Python 数据结构，不直接写 MySQL 或 PostgreSQL 方言。数据库差异只在读取层处理。

## 数据流

1. 用户进入“资管逐笔数据库校验”页面。
2. 用户选择现有数据源配置和来源。
3. 页面默认填入上月底报告期，允许手动修改。
4. 后端根据报告期计算上期日期和上期表后缀。
5. 后端从系统设置里的字段匹配数据源加载元数据。
6. 后端校验 13 张当期表是否存在，并检查规则所需字段。
7. 后端读取当期表和可用的上期表数据。
8. Python 规则引擎执行表内规则和跨期规则。
9. 每条错误统一转换成 12 列结果行。
10. Excel writer 生成旧程序格式 `.xlsx`。
11. 页面显示完成状态并提供下载。

## Excel 输出

输出为单个 `.xlsx` 文件，只有一个 sheet：

- sheet 名称：`Sheet1`
- 无冻结窗格
- 无自动筛选
- 表头样式和列宽按旧结果样例复刻

表头固定 12 列：

1. `数据日期`
2. `金融机构编码`
3. `法人金融机构名称`
4. `数据管理机构`
5. `明细数据相关信息`
6. `校验表单`
7. `数据值1`
8. `数据值2`
9. `校验标识`
10. `校验规则`
11. `错误描述`
12. `情况说明`

文件名格式：

```text
YYYYMMDD-资管产品数据审核结果-模板校验（否）-公开信息校验（否）(Ver.20260202).xlsx
```

例如：

```text
20260531-资管产品数据审核结果-模板校验（否）-公开信息校验（否）(Ver.20260202).xlsx
```

## API 和页面入口

新增工具入口名称：资管逐笔数据库校验。

建议新增接口：

- `GET /api/db-validation/configs`：列出现有数据库配置和可选来源。
- `GET /api/db-validation/settings`：读取字段匹配数据源设置。
- `POST /api/db-validation/settings`：保存字段匹配数据源设置。
- `POST /api/db-validation/jobs`：创建校验任务。
- `GET /api/db-validation/jobs/{job_id}`：查询任务状态、进度、错误数量和日志。
- `GET /api/db-validation/jobs/{job_id}/download`：下载 Excel 结果。

校验任务在后台线程中运行，不阻塞 HTTP 请求。页面展示当前 ZG 表、规则进度、错误数量、耗时和最终下载入口。

## 错误处理

- 字段匹配元数据源连接失败：任务失败，提示连接或库/模式配置错误。
- `baseinfo` 找不到逐笔表：对应 ZG 表失败，提示缺少 `table_name_en` 元数据。
- `field_info` 找不到规则所需字段：对应规则失败，记录缺失字段名，不做盲猜。
- 当期表缺失：任务失败。
- 上期表缺失：跨期规则跳过并记录缺失表；表内规则继续执行。
- 单条规则异常：记录规则名和异常，继续执行其他规则；最终状态显示“完成但有规则异常”。
- 无错误结果：仍生成只有 12 列表头的 Excel。
- 结果文件命名冲突：覆盖任务临时目录中的同名文件，下载文件名仍使用旧程序格式。

## 验证方式

验证分为四类：

- 元数据验证：确认 13 张逐笔表都能通过 `table_name_en -> id -> table_id` 找到字段映射。
- 表名验证：报告期 `2026-05-31` 时，上期表后缀为 `_2026_04`。
- Excel 验证：sheet 名、12 列表头、列顺序、文件名格式与旧结果样例一致。
- 数据库验证：MySQL 和 PostgreSQL 各跑最小用例，确认同一规则输出一致。

实现完成后按项目偏好执行测试，并重新打包 `dist/auto-check.exe`。

## 本地种子数据

已按当前设计把本地 PostgreSQL 测试库准备好：

- 数据库：`auto_check_test`
- 数据 schema：`dws`
- 元数据 schema：`test`
- 元数据表：
  - `test.xt_reg_table_baseinfo`：27 行
  - `test.xt_reg_table_field_info`：784 行
- 当期逐笔表：13 张，使用无后缀原表名。
- 上期逐笔表：13 张，使用 `_2026_04` 后缀。

导入来源：

- 当期：`D:\xiaxin\rhexe\逐笔当期`
- 上期：`D:\xiaxin\rhexe\逐笔上期`
- 元数据：`D:\xiaxin\rhexe\xt_reg_table_baseinfo_202606051016.sql`
- 元数据：`D:\xiaxin\rhexe\xt_reg_table_field_info_202606051016.sql`

已导入主要行数：

| 表 | 当期行数 | 上期行数 |
| --- | ---: | ---: |
| `zgxgzh_baseinfo_zg01_26` | 66 | 118 |
| `zgxgzh_begraiseinfo_zg02_26` | 388 | 700 |
| `zgxgzh_projendinfo_zg03_26` | 18 | 30 |
| `zgxgzh_projholdinfo_zg04` | 29653 | 29279 |
| `zgxgzh_projdebt_zg05_2024` | 8523 | 8349 |
| `zgxgzh_beneficial_zg06` | 1813 | 1717 |
| `zgxgzh_ioudetail_zg07` | 291 | 289 |
| `zgxgzh_spvdetail_zg08` | 13665 | 13226 |
| `zgxgzh_debtordate_zg09` | 2 | 2 |
| `zgxgzh_surecinfo_zg10` | 2 | 2 |
| `zgxgzh_industinfo_zg11` | 2 | 2 |
| `zgzgzh_zg12` | 0 | 0 |
| `zgzgzh_zg13` | 1485 | 1363 |

## 非目标

本期不实现：

- 模板校验。
- 公开信息校验。
- 把规则配置成可视化编辑。
- 把所有规则改写成 SQL。
- 历史结果持久化查询页面。
