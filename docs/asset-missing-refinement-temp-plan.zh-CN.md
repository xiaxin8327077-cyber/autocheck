# 资产缺失细分临时方案

## 状态

本方案为已讨论但暂缓实施的临时方案。后续如果继续做“资产缺失”细分，可先从本文恢复上下文，再按实际复杂度拆分实施。

## 背景

- 当前资产缺失逻辑先确认 `a0001 < fa_valuationreport_dws.0004`，再将资产差额匹配到估值表中 `1` 开头的叶子科目明细。
- 特定目的载体逻辑覆盖 `1101.05.01.01`、`1101.05.02.01`、`1101.05.03.01`、`1101.05.04.01`、`1101.05.05.01`、`1101.05.07.01` 相关 AM 标的核查；`1101.05.06.01` 仍归为私募基金。
- 本方案只针对已命中 `资产缺失` 且能匹配到具体估值表缺失明细的情况继续细分。
- `资产重复` 不进入本方案。

## 资产类型识别

| 资产类型 | 识别规则 |
| --- | --- |
| 特定目的载体 | `1101.05.01.01`、`1101.05.02.01`、`1101.05.03.01`、`1101.05.04.01`、`1101.05.05.01`、`1101.05.07.01` 沿用 AM 标的逻辑 |
| 债券 | 科目编码以 `1501.01` 开头 |
| 股票 | 科目编码以 `1101.01` 开头 |
| 公募基金 | 科目编码以 `1101.04` 开头 |
| 私募基金 | 科目编码以 `1101.05.06` 开头 |
| 逆回购 | 科目前四段满足 `1111.__.__.01`，可按 `^1111\.\d{2}\.\d{2}\.01$` 判断 |
| 贷款 | 科目编码以 `1303.01.01`、1501.04.05.01 开头 |
 股权投资 科目编码以1511.01.01 开头
 信托计划收益权 科目编码以1541.01 开头且 (科目名称like '江苏信托%信托产品%' or 科目名称like '江苏信托%资金信托计划%')
 资产收益权 科目编码以1541.01开头且 (科目名称 not like '江苏信托%信托产品%' and 科目名称 not like '江苏信托%资金信托计划%')
| 其他资产 | 不做分类，保留 `科目代码拼接科目名称为缺失的资产名称` |

## 债券细分

1. 取科目最后一个点后的值作为证券代码。
2. 到 DWS 数据源固定查询 `dm.fa_security_balance_zgxg_dm`。
3. 查询条件为：
   - `sbm_projcode = 项目编号`
   - `sbm_cacldate = 对数日期`
   - `sbm_stockcode = 科目尾段证券代码`
   - `sbm_sename = 估值表科目名称`
   sbm_balamoney_cost+sbm_balamoney_fair+sbm_balamoney_inte !=0
4. 若查不到数据，原因：`该债券在dm.fa_security_balance_zgxg_dm中不存在或金额为0`。
5. 若查到数据但 `sbm_seclas_h2024` 为空，原因：`该债券债券类别_人行字段（sbm_seclas_h2024）为空`。
6. 若 `sbm_seclas_h2024` 不为空，到业务报表数据源查询 `currency_report_24.currency_detail_project_2_1_4`，只按 `caldate` 过滤。
7. 若报表明细表无数据，原因：`资负数据子系统-债务证券明细表无数据`。
8. 若报表明细表有数据，原因留空。

## 股票细分

1. 取科目最后一个点后的值作为证券代码。
2. 到 DWS 数据源固定查询 `dm.fa_security_balance_zgxg_dm`。
3. 查询条件为：
   - `sbm_projcode = 项目编号`
   - `sbm_cacldate = 对数日期`
   - `sbm_stockcode = 科目尾段证券代码`
   - `sbm_sename = 估值表科目名称`
   sbm_balamoney_cost+sbm_balamoney_fair+sbm_balamoney_inte !=0
4. 若查不到数据，原因详：`该股票在dm.fa_security_balance_zgxg_dm中不存在或金额为0`。
5. 若查到数据但 `sbm_gpgqtype_h` 为空，原因：`该股票股票股权类别_人行字段（sbm_gpgqtype_h）为空`。
6. 若 `sbm_gpgqtype_h` 不为空，到业务报表数据源查询 `currency_report_24.currency_detail_project_2_1_5`，只按 `caldate` 过滤。
7. 若报表明细表无数据，原因详情为：`资负数据子系统-股票股权明细表无数据`。
8. 若报表明细表有数据，原因留空。

## 公募基金细分

1. 取科目最后一个点后的值作为证券代码。
2. 到 DWS 数据源固定查询 `dm.fa_security_balance_zgxg_dm`。
3. 查询条件为：
   - `sbm_projcode = 项目编号`
   - `sbm_cacldate = 对数日期`
   - `sbm_stockcode = 科目尾段证券代码`
   - `sbm_sename = 估值表科目名称`
    sbm_balamoney_cost+sbm_balamoney_fair+sbm_balamoney_inte !=0
4. 若查不到数据，原因：`该公募基金在dm.fa_security_balance_zgxg_dm中不存在或金额为0`。
5. 若查到数据但 `sbm_fundtype` 为空，原因：`该公募基金公募私募_人行字段（sbm_fundtype）为空`。
6. 若 `sbm_fundtype` 不为空，到业务报表数据源查询 `currency_report_24.currency_detail_project_2_1_6`，只按 `caldate` 过滤。
7. 若报表明细表无数据，原因：`资负数据子系统-特定目的载体明细表无数据`。
8. 若报表明细表有数据，，原因留空。


## 私募基金细分

1. 取科目最后一个点后的值作为证券代码。
2. 到 DWS 数据源固定查询 `dm.fa_security_balance_zgxg_dm`。
3. 查询条件为：
   - `sbm_projcode = 项目编号`
   - `sbm_cacldate = 对数日期`
   - `sbm_stockcode = 科目尾段证券代码`
   - `sbm_sename = 估值表科目名称`
    sbm_balamoney_cost+sbm_balamoney_fair+sbm_balamoney_inte !=0
4. 若查不到数据，原因：`该私募基金在dm.fa_security_balance_zgxg_dm中不存在或金额为0`。
5. 若查到数据但 `sbm_fundtype` 为空，原因：`该私募基金公募私募_人行字段（sbm_fundtype）为空`。
6. 若 `sbm_fundtype` 不为空，到业务报表数据源查询 `currency_report_24.currency_detail_project_2_1_6`，只按 `caldate` 过滤。
7. 若报表明细表无数据，原因：`资负数据子系统-特定目的载体明细表无数据`。
8. 若报表明细表有数据，，原因留空。

## 逆回购细分

1. 当科目前四段满足 `1111.__.__.01` 时，识别为逆回购。
2. 到业务报表数据源固定查询 `assman_reg.ex_pledge_back`。
3. 只过滤 `subcode` 以 `7` 开头的数据，其余暂不过滤。
4. 只查询空值问题：`buyback_money` 为空或 `expenses` 为空。
5. 若存在空值数据，原因：`存续回购业务表回购金额或佣金存在空数据`。
6. 若不存在空值数据，原因留空。

注意：这条规则风险最高，因为目前确认的口径不按项目和日期过滤，后续实施前建议再复核是否会误判其他项目或期间的数据。

## 贷款细分

1. 当科目编码以 `1303.01.01`、1501.04.05.01 开头时，识别为贷款。
2. 取科目最后一个点后的值，也就是 `DK`、'ZQ' 开头的合同编号。
3. 到 DWS 数据源固定查询 `dm.am_projinvest_zgxg_dm`。
4. 查询条件为：
   - `pin_projcode = 项目编号`
   - `pin_cldate = 对数日期`
   - `pin_mpactid = 科目尾段贷款合同编号`
   pin_acbalance !=0
5. 若查不到数据，原因：`该贷款在dm.am_projinvest_zgxg_dm不存在或投融资余额为0`。
8. 若查到数据，到业务报表数据源查询 `currency_report_24.currency_detail_project_2_1_2`，只按 `caldate` 过滤。
9. 若报表明细表无数据，原因详情为：`资负数据子系统-除回购和拆借外贷款明细表无数据`。
10. 若报表明细表有数据，原因留空。

## 股权投资细分

1. 当科目编码以 1511.01.01 开头时，识别为股权投资。
2. 取科目最后一个点后的值，也就是 GQ 开头的合同编号。
3. 到 DWS 数据源固定查询 `dm.am_projinvest_zgxg_dm`。
4. 查询条件为：
   - `pin_projcode = 项目编号`
   - `pin_cldate = 对数日期`
   - `pin_mpactid = 科目尾段贷款合同编号`
   pin_acbalance !=0
5. 若查不到数据，原因：`该股权投资在dm.am_projinvest_zgxg_dm不存在或投融资余额为0`。
8. 若查到数据，查pin_gqtype_h字段是否为空，若为空，原因：“该股权投资股权投资类别字段（pin_gqtype_h）为空”
9.若不为空，到业务报表数据源查询 `currency_report_24.currency_detail_project_2_1_5_2`，只按 `caldate` 过滤。
9. 若报表明细表无数据，原因详情为：`资负数据子系统-股权明细表无数据`。
10. 若报表明细表有数据，原因留空。


 信托计划收益权 科目编码以1541.01 开头且 (科目名称like '江苏信托%信托产品%' or 科目名称like '江苏信托%资金信托计划%')
 
  ##  信托计划收益权细分

1. 当科目编码以 科目编码以1541.01 开头且 (科目名称like '江苏信托%信托产品%' or 科目名称like '江苏信托%资金信托计划%')，识别为信托计划收益权
2. 取科目最后一个点后的值，也就是 CC 开头的合同编号。
3. 到 DWS 数据源固定查询 `dm.am_projinvest_spv_zgxg_dm`。
4. 查询条件为：
   - `svd_projcode = 项目编号`
   - `svd_mpactid = 科目尾段贷款合同编号`
    svd_balamoney_cost+svd_balamoney_inte+svd_balamoney_fair !=0
5. 若查不到数据，原因：`该信托计划收益权在dm.am_projinvest_spv_zgxg_dm不存在或余额为0`。
9.若查到，到业务报表数据源查询 `currency_report_24.currency_detail_project_2_1_6`，只按 `caldate` 过滤。
9. 若报表明细表无数据，原因详情为：`资负数据子系统-特定目的载体明细表无数据`。
10. 若报表明细表有数据，原因留空。
 
   ##  资产收益权细分
   zgxg_zhbs.ccqxx
 1. 当科目编码以 科目编码以科目编码以1541.01开头且 (科目名称 not like '江苏信托%信托产品%' and 科目名称 not like '江苏信托%资金信托计划%')，识别为资产收益权
2. 取科目最后一个点后的值，也就是 CC 开头的合同编号。
3. 到 DWS 数据源固定查询 `zgxg_zhbs.ccqxx`。
4. 查询条件为：
   - `pjdw_projcode = 项目编号`
   - `pin_mpactid = 科目尾段贷款合同编号`
   pin_acbalance !=0
5. 若查不到数据，原因：`该财产权在zgxg_zhbs.ccqxx不存在或投融资余额为0`。
9.若查到，到业务报表数据源查询 `currency_report_24.currency_detail_project_2_1_9`，只按 `caldate` 过滤。
9. 若报表明细表无数据，原因详情为：`资负数据子系统-其他债权明细表无数据`。
10. 若报表明细表有数据，原因留空。

## 多个资产缺失

①②③拼起来

建议表格字段：

| 字段 | 含义 |
| --- | --- |
| 资产类型 | 债券、股票、基金、逆回购、贷款等 |
| FA科目编码 | 估值表科目编码 |
| FA科目名称 | 估值表科目名称 |
| 科目尾段 | 证券代码或贷款合同编号 |
| FA估值金额 | 估值表 `f_marketvalue` |
| 核查表 | 本次细分实际查询的表 |
| 核查结果 | 缺少数据、字段为空、报表未生成、仍需排查等 |
| 关键字段 | 为空或不一致的字段 |
| 建议处理 | 面向业务排查的简要说明 |

## 实施建议

- 表引用使用固定可信表名，并通过 `TableRef(parts=(schema, table)).quoted(db_type)` 生成带 schema 的安全表名。
- `dm.*` 表继续走 DWS 数据源，表名前保留 `dm.`。
- `currency_report_24.*` 和 `assman_reg.*` 走业务报表数据源。
- 金额对比先保持当前精确比较口径。
- 建议分阶段实现：
  1. 先实现单资产债券、股票、基金、贷款细分。
  2. 再实现多个资产缺失的表格详情。
  3. 最后处理逆回购，因为当前过滤口径风险最高。
- 若后续修改源码，需要同步更新后端测试、Repository SQL 测试、服务端详情展示测试、导出详情测试、前端静态字段测试、`README.md`、`docs/reconcile-rules.zh-CN.md`、`docs/reconcile-logic-history.zh-CN.md`，并重新打包 `dist/auto-check.exe`。
