# 资产缺失细分链路确认稿

## 状态

本文件用于确认“资产缺失”细分链路和“具体原因”列的新展示格式。当前仅整理方案，不代表已经实现。

## 适用范围

- 只处理 `资产缺失`。
- `资产重复` 暂不进入本方案。
- 只有已命中具体估值表缺失资产明细时，才继续做资产类型细分。
- 未命中具体资产明细时，仍按现有逻辑归为 `资产差异`。

## 一级判断链路

1. 主表 `zf_detail_2024.a0001` 小于估值表 `fa_valuationreport_dws` 的 `0004` 资产合计。
2. 计算资产缺失差额：`0004 - a0001`。
3. 取估值表中 `1` 开头的实际末级科目。
4. 用实际末级科目的 `f_marketvalue` 匹配资产缺失差额。
5. 如果能命中具体科目，差异类型为 `资产缺失`。
6. 如果不能命中具体科目，差异类型为 `资产差异`。

“实际末级科目”指当前项目估值表中没有下级科目的科目，不按固定点数判断。

## 具体原因列格式

`具体原因` 列直接展示格式化后的逐条原因：

```text
①债券缺失：XX债券；原因：XXX
②股票缺失：XX股票
③贷款缺失：XX贷款；原因：XXX
```

规则：

- 单个资产也使用 `①` 开头。
- 多个资产按 `①②③` 顺序拼接。
- 能定位最终原因时，追加 `；原因：XXX`。
- 暂时不能定位最终原因时，只展示 `①资产类型缺失：资产名称`，不展示 `原因`。
- 资产名称优先使用 FA 估值表科目名称 `c_accountname`。
- 其他资产无法分类时，资产名称使用 `科目代码 + 科目名称`。

## 资产类型识别

按以下规则识别缺失资产类型：

| 资产类型 | 识别规则 |
| --- | --- |
| 特定目的载体 | FA 科目前四段为 `1101.05.01.01`、`1101.05.02.01`、`1101.05.03.01`、`1101.05.04.01`、`1101.05.05.01`、`1101.05.07.01` |
| 债券 | 科目编码以 `1501.01` 开头 |
| 股票 | 科目编码以 `1101.01` 开头 |
| 公募基金 | 科目编码以 `1101.04` 开头 |
| 私募基金 | 科目编码以 `1101.05.06` 开头 |
| 逆回购 | 科目前四段满足 `1111.xx.xx.01`，后续可带尾段 |
| 贷款 | 科目编码以 `1303.01.01` 或 `1501.04.05.01` 开头 |
| 股权投资 | 科目编码以 `1511.01.01` 开头 |
| 信托计划收益权 | 科目编码 `LIKE '1541.01%'`，且科目名称 `LIKE '江苏信托%信托产品%'` 或 `LIKE '江苏信托%资金信托计划%'` |
| 资产收益权 | 科目编码 `LIKE '1541.01%'`，且科目名称不满足信托计划收益权名称条件 |
| 其他资产 | 不做分类，使用 `科目代码 + 科目名称` 作为缺失资产名称 |

## 特定目的载体缺失

触发前提：

1. 已判定为 `资产缺失`。
2. 资产缺失金额能命中估值表 `1` 开头实际末级科目。
3. 命中的 FA 科目前四段属于特定目的载体范围：`1101.05.01.01`、`1101.05.02.01`、`1101.05.03.01`、`1101.05.04.01`、`1101.05.05.01`、`1101.05.07.01`，其中 `1101.05.06.01` 仍归为私募基金。

核查链路：

1. 使用 FA 估值表科目名称 `c_accountname` 匹配 AM 标的信息表资产名称。
2. 如果匹配不到 AM 标的，原因：
   `AM标的缺失`
3. 如果 FA 科目尾段代码不等于 AM 标的代码，原因：
   `FA和AM标的不一致`
4. 如果 FA 科目尾段代码等于 AM 标的代码，用 AM 标的信息表中匹配到的合同代码，继续查 `am_projinvest_dws`。
5. 如果 `am_projinvest_dws` 查不到合同投融资余额，或 `f_acbalance = 0`，原因：
   `合同投融资余额为0但FA科目余额不为0`
6. 如果 `am_projinvest_dws.f_acbalance <> 0`，继续查 DWS 数据源固定表 `dm.am_projinvest_spv_zgxg_dm`。

`dm.am_projinvest_spv_zgxg_dm` 查询条件：

- `svd_projcode = 项目编号`
- `svd_cldate = 核对日期`
- `svd_mpactid = AM标的信息表中匹配到的合同代码`
- `COALESCE(svd_balamoney_cost,0) + COALESCE(svd_balamoney_inte,0) + COALESCE(svd_balamoney_fair,0) <> 0`

后续判断：

1. 如果查不到 SPV 数据，原因：
   `该特定目的载体在dm.am_projinvest_spv_zgxg_dm不存在或余额为0`
2. 如果 AM 标的信息表资产名称 `c_udlyasset LIKE '%收益凭证%'`，不判断 `svd_assettype`，直接进入收益凭证报表核查。
3. 如果 AM 标的信息表资产名称 `c_udlyasset NOT LIKE '%收益凭证%'`，且查到的 SPV 数据中 `svd_assettype` 为空，或不在 `31、32、34、35、37、33、38` 中，原因：
   `该特定目的载体资产类型为空或资产类型有误`
4. 如果 AM 标的信息表资产名称 `c_udlyasset LIKE '%收益凭证%'`，且已在 `dm.am_projinvest_spv_zgxg_dm` 查到对应合同余额非 0 的数据，查业务报表数据源：
   `currency_report_24.currency_detail_project_2_1_9`
   只按 `caldate` 过滤。
   若无数据，原因：
   `该收益凭证在资负数据子系统-其他债权明细表无数据`
5. 如果 `svd_assettype` 正常，且 AM 标的信息表资产名称 `c_udlyasset NOT LIKE '%收益凭证%'`，查业务报表数据源：
   `currency_report_24.currency_detail_project_2_1_6`
   只按 `caldate` 过滤。
   若无数据，原因：
   `资负数据子系统-特定目的载体明细表无数据`
6. 如果以上检查都无异常，原因留空。

具体原因示例：

```text
①特定目的载体缺失：XX信托计划；原因：FA和AM标的不一致
①特定目的载体缺失：XX信托计划；原因：合同投融资余额为0但FA科目余额不为0
①特定目的载体缺失：XX信托计划；原因：资负数据子系统-特定目的载体明细表无数据
①特定目的载体缺失：XX信托计划
```

其中 `XX信托计划` 使用 FA 估值表科目名称 `c_accountname`。

## 债券缺失

触发条件：

- FA 科目编码以 `1501.01` 开头。

核查链路：

1. 取 FA 科目最后一个点后的值作为证券代码。
2. 到 DWS 数据源固定查询 `dm.fa_security_balance_zgxg_dm`。
3. 查询条件：
   - `sbm_projcode = 项目编号`
   - `sbm_cacldate = 核对日期`
   - `sbm_stockcode = FA科目尾段证券代码`
   - `sbm_sename = FA估值表科目名称`
   - `COALESCE(sbm_balamoney_cost,0) + COALESCE(sbm_balamoney_fair,0) + COALESCE(sbm_balamoney_inte,0) <> 0`
4. 若查不到数据，原因：
   `该债券在dm.fa_security_balance_zgxg_dm中不存在或金额为0`
5. 若查到数据但 `sbm_seclas_h2024` 为空，原因：
   `该债券债券类别_人行字段（sbm_seclas_h2024）为空`
6. 若 `sbm_seclas_h2024` 不为空，到业务报表数据源查询：
   `currency_report_24.currency_detail_project_2_1_4`
   只按 `caldate` 过滤。
7. 若报表明细表无数据，原因：
   `资负数据子系统-债务证券明细表无数据`
8. 若报表明细表有数据，原因留空。

具体原因示例：

```text
①债券缺失：XX债券；原因：该债券债券类别_人行字段（sbm_seclas_h2024）为空
①债券缺失：XX债券
```

## 股票缺失

触发条件：

- FA 科目编码以 `1101.01` 开头。

核查链路：

1. 取 FA 科目最后一个点后的值作为证券代码。
2. 到 DWS 数据源固定查询 `dm.fa_security_balance_zgxg_dm`。
3. 查询条件：
   - `sbm_projcode = 项目编号`
   - `sbm_cacldate = 核对日期`
   - `sbm_stockcode = FA科目尾段证券代码`
   - `sbm_sename = FA估值表科目名称`
   - `COALESCE(sbm_balamoney_cost,0) + COALESCE(sbm_balamoney_fair,0) + COALESCE(sbm_balamoney_inte,0) <> 0`
4. 若查不到数据，原因：
   `该股票在dm.fa_security_balance_zgxg_dm中不存在或金额为0`
5. 若查到数据但 `sbm_gpgqtype_h` 为空，原因：
   `该股票股票股权类别_人行字段（sbm_gpgqtype_h）为空`
6. 若 `sbm_gpgqtype_h` 不为空，到业务报表数据源查询：
   `currency_report_24.currency_detail_project_2_1_5`
   只按 `caldate` 过滤。
7. 若报表明细表无数据，原因：
   `资负数据子系统-股票股权明细表无数据`
8. 若报表明细表有数据，原因留空。

## 公募基金缺失

触发条件：

- FA 科目编码以 `1101.04` 开头。

核查链路：

1. 取 FA 科目最后一个点后的值作为证券代码。
2. 到 DWS 数据源固定查询 `dm.fa_security_balance_zgxg_dm`。
3. 查询条件：
   - `sbm_projcode = 项目编号`
   - `sbm_cacldate = 核对日期`
   - `sbm_stockcode = FA科目尾段证券代码`
   - `sbm_sename = FA估值表科目名称`
   - `COALESCE(sbm_balamoney_cost,0) + COALESCE(sbm_balamoney_fair,0) + COALESCE(sbm_balamoney_inte,0) <> 0`
4. 若查不到数据，原因：
   `该公募基金在dm.fa_security_balance_zgxg_dm中不存在或金额为0`
5. 若查到数据但 `sbm_fundtype` 为空，原因：
   `该公募基金公募私募_人行字段（sbm_fundtype）为空`
6. 若 `sbm_fundtype` 不为空，到业务报表数据源查询：
   `currency_report_24.currency_detail_project_2_1_6`
   只按 `caldate` 过滤。
7. 若报表明细表无数据，原因：
   `资负数据子系统-特定目的载体明细表无数据`
8. 若报表明细表有数据，原因留空。

## 私募基金缺失

触发条件：

- FA 科目编码以 `1101.05.06` 开头。

核查链路与公募基金一致，但原因文案使用“私募基金”：

- 查不到数据：
  `该私募基金在dm.fa_security_balance_zgxg_dm中不存在或金额为0`
- `sbm_fundtype` 为空：
  `该私募基金公募私募_人行字段（sbm_fundtype）为空`
- 报表明细表无数据：
  `资负数据子系统-特定目的载体明细表无数据`

## 逆回购缺失

触发条件：

- FA 科目前四段满足 `1111.xx.xx.01`，后续可带尾段。

核查链路：

1. 到业务报表数据源固定查询 `ass_man_reg.ex_pledge_back`。
2. 按 `project_code = 项目编号` 过滤。
3. 只过滤 `subcode` 以 `7` 开头的数据。
4. 只查询空值问题：`buyback_money` 为空或 `expenses` 为空。
5. 若存在空值数据，原因：
   `存续回购业务表回购金额或佣金存在空数据`
6. 若不存在空值数据，原因留空。

注意：当前口径按项目过滤，但不按日期过滤。

## 贷款缺失

触发条件：

- FA 科目编码以 `1303.01.01` 或 `1501.04.05.01` 开头。

核查链路：

1. 取 FA 科目最后一个点后的值作为合同编号，可能以 `DK` 或 `ZQ` 开头。
2. 到 DWS 数据源固定查询 `dm.am_projinvest_zgxg_dm`。
3. 查询条件：
   - `pin_projcode = 项目编号`
   - `pin_cldate = 核对日期`
   - `pin_mpactid = FA科目尾段合同编号`
   - `pin_acbalance <> 0`
4. 若查不到数据，原因：
   `该贷款在dm.am_projinvest_zgxg_dm不存在或投融资余额为0`
5. 若查到数据，到业务报表数据源查询：
   `currency_report_24.currency_detail_project_2_1_2`
   只按 `caldate` 过滤。
6. 若报表明细表无数据，原因：
   `资负数据子系统-除回购和拆借外贷款明细表无数据`
7. 若报表明细表有数据，原因留空。

## 股权投资缺失

触发条件：

- FA 科目编码以 `1511.01.01` 开头。

核查链路：

1. 取 FA 科目最后一个点后的值作为合同编号，通常以 `GQ` 开头。
2. 到 DWS 数据源固定查询 `dm.am_projinvest_zgxg_dm`。
3. 查询条件：
   - `pin_projcode = 项目编号`
   - `pin_cldate = 核对日期`
   - `pin_mpactid = FA科目尾段合同编号`
   - `pin_acbalance <> 0`
4. 若查不到数据，原因：
   `该股权投资在dm.am_projinvest_zgxg_dm不存在或投融资余额为0`
5. 若查到数据但 `pin_gqtype_h` 为空，原因：
   `该股权投资股权投资类别字段（pin_gqtype_h）为空`
6. 若 `pin_gqtype_h` 不为空，到业务报表数据源查询：
   `currency_report_24.currency_detail_project_2_1_5_2`
   只按 `caldate` 过滤。
7. 若报表明细表无数据，原因：
   `资负数据子系统-股权明细表无数据`
8. 若报表明细表有数据，原因留空。

## 信托计划收益权缺失

触发条件：

```sql
c_accountcode LIKE '1541.01%'
AND (
  c_accountname LIKE '江苏信托%信托产品%'
  OR c_accountname LIKE '江苏信托%资金信托计划%'
)
```

核查链路：

1. 取 FA 科目最后一个点后的值作为合同编号，通常以 `CC` 开头。
2. 到 DWS 数据源固定查询 `dm.am_projinvest_spv_zgxg_dm`。
3. 查询条件：
   - `svd_projcode = 项目编号`
   - `svd_cldate = 核对日期`
   - `svd_mpactid = FA科目尾段合同编号`
   - `COALESCE(svd_balamoney_cost,0) + COALESCE(svd_balamoney_inte,0) + COALESCE(svd_balamoney_fair,0) <> 0`
4. 若查不到数据，原因：
   `该信托计划收益权在dm.am_projinvest_spv_zgxg_dm不存在或余额为0`
5. 若查到数据，到业务报表数据源查询：
   `currency_report_24.currency_detail_project_2_1_6`
   只按 `caldate` 过滤。
6. 若报表明细表无数据，原因：
   `资负数据子系统-特定目的载体明细表无数据`
7. 若报表明细表有数据，原因留空。

## 资产收益权缺失

触发条件：

```sql
c_accountcode LIKE '1541.01%'
AND c_accountname NOT LIKE '江苏信托%信托产品%'
AND c_accountname NOT LIKE '江苏信托%资金信托计划%'
```

核查链路：

1. 取 FA 科目最后一个点后的值作为合同编号，通常以 `CC` 开头。
2. 到 DWS 数据源固定查询 `zgxg_zhbs.ccqxx`。
3. 查询条件：
   - `pjdw_projcode = 项目编号`
   - `pin_mpactid = FA科目尾段合同编号`
   - `pin_acbalance <> 0`
   - 不加日期条件
4. 若查不到数据，原因：
   `该财产权在zgxg_zhbs.ccqxx不存在或投融资余额为0`
5. 若查到数据，到业务报表数据源查询：
   `currency_report_24.currency_detail_project_2_1_9`
   只按 `caldate` 过滤。
6. 若报表明细表无数据，原因：
   `资负数据子系统-其他债权明细表无数据`
7. 若报表明细表有数据，原因留空。

## 其他资产缺失

触发条件：

- 命中资产缺失明细，但不属于上述任何资产类型。

具体原因格式：

```text
①其他资产缺失：科目代码 科目名称
```

原因留空。

## 多个资产缺失

如果资产缺失金额由多个估值表末级科目共同命中，则每个命中资产生成一条 `具体原因`：

```text
①债券缺失：XX债券；原因：XXX
②特定目的载体缺失：XX信托计划；原因：XXX
③贷款缺失：XX贷款
```

同时建议在展开详情中增加表格区块，区块名为 `资产缺失细分`。

建议表格字段：

| 字段 | 含义 |
| --- | --- |
| 序号 | 与具体原因中的 ①②③ 对应 |
| 资产类型 | 债券、股票、特定目的载体等 |
| 资产名称 | FA 估值表科目名称，或其他资产的科目代码+科目名称 |
| FA科目编码 | 估值表科目编码 |
| 科目尾段 | 证券代码、标的代码或合同编号 |
| FA估值金额 | 估值表 `f_marketvalue` |
| 核查表 | 本次细分实际查询的表 |
| 核查结果 | 缺少数据、字段为空、报表无数据、无异常等 |
| 关键字段 | 为空或不符合要求的字段 |
| 原因 | 具体原因列中 `；原因：` 后的内容 |

## 表和数据源

| 表 | 数据源 |
| --- | --- |
| `dm.fa_security_balance_zgxg_dm` | DWS 数据源 |
| `dm.am_projinvest_zgxg_dm` | DWS 数据源 |
| `dm.am_projinvest_spv_zgxg_dm` | DWS 数据源 |
| `zgxg_zhbs.ccqxx` | DWS 数据源 |
| `currency_report_24.currency_detail_project_2_1_2` | 业务报表数据源 |
| `currency_report_24.currency_detail_project_2_1_4` | 业务报表数据源 |
| `currency_report_24.currency_detail_project_2_1_5` | 业务报表数据源 |
| `currency_report_24.currency_detail_project_2_1_5_2` | 业务报表数据源 |
| `currency_report_24.currency_detail_project_2_1_6` | 业务报表数据源 |
| `currency_report_24.currency_detail_project_2_1_9` | 业务报表数据源 |
| `ass_man_reg.ex_pledge_back` | 业务报表数据源 |

## 待确认点

1. 具体原因多条拼接时，是否使用换行分隔；建议使用换行，便于 Excel 单元格和页面详情阅读。
2. 报表明细表目前均只按 `caldate` 过滤，是否全部保持该口径。

## 已确认口径

- `资产收益权` 查询 `zgxg_zhbs.ccqxx` 不加日期条件。
- `逆回购` 当前按 `project_code` 过滤项目，只按 `subcode` 以 `7` 开头并检查空值，不按日期过滤。
