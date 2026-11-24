# AI 数据校验 51 条原始请求

本清单逐字保留冻结清单中的请求。原 39 条由 23 条历史请求、5 条下午补充、10 条文档提炼及 1 条采纳请求组成。本轮另有 7 条复核、4 条截图和 1 条实际界面采纳请求。两条采纳请求包含界面传入的原方案范围、运算和业务前提。

分组依据为原 39 条运行记录和冻结清单中的案例标识。七条复核使用清单的 `today_` 前缀，四条截图使用 `screenshot_` 前缀。[冻结清单](../outputs/ai-frozen-final51-manifest-20261123.json) · [本轮原始运行记录](../outputs/.runtime/low-history-regression-20261120/final-ordinary51-20261123-summary.json)

## 原历史请求（23 条）

### `nav_current_mode_null`

项目运行方式为净值型时，净值不得为空

### `nav_conversational_null`

净值型的项目，净值不能是空的吧

### `nav_nonnet_bounds`

非净值型项目的净值不得大于1或小于0。

### `paid_terminated_principle`

当期终止的项目的实收原则上不得大于 0

### `paid_terminated_symbol`

当期终止项目的实收不得>0

### `income_gt`

收益转让标识为是的项目，资产收益权余额应大于0

### `income_zero_then`

项目收益转让标识为是，那么它的资产收益权余额不能为0

### `nav_typed_null`

净值型项目的净值不得为空

### `nav_simple_null`

净值不得为空

### `income_should_gt`

收益转让标识为是的项目，资产收益权余额应该大于0

### `income_zero_forbid`

收益转让标识为是的项目，资产收益权余额不得为0

### `income_zero_when`

项目收益转让标识为是时资产收益权余额不能为0

### `income_reverse`

收益转让标识为否的项目，资产收益权余额不应大于0

### `paid_live_forbid`

存续项目的实收不得小于0

### `paid_live_cannot`

存续项目的实收不能小于0

### `paid_end_principle`

当期结束的项目的实收原则上不应该大于 0。

### `paid_consistency`

对比项目和募集表中的实收是否一致

### `nav_original_accum_null`

项目原始运行方式为净值型时，累计净值不得为空

### `nav_original_unit_nonnull_10`

原始运行方式为净值型的项目的单位净值不得为空且一般不大于10

### `nav_original_unit_10_nonnull`

原始运行方式为净值型的项目的单位净值一般不大于10且一定不能为空

### `nav_original_unit_0_nonnull`

原始运行方式为净值型的项目的单位净值一般不大于0且一定不能为空

### `nav_scope_only`

净值型项目

### `nav_metric_only`

净值

## 下午补充请求（5 条）

### `afternoon_paid_trust`

存续项目的实收信托不得小于0

### `afternoon_project_dates`

项目起始日不得大于项目预计结束日

### `afternoon_project_dates_reworded`

项目的起始日不能大于预计结束日

### `afternoon_nav_compare`

净值型项目的单位净值应小于等于累计净值

### `afternoon_project_start_null`

项目起始日不能为空

## 根据文档提炼的请求（10 条）

### `doc_product_name_null`

项目信息表的产品名称不能为空

### `doc_raise_dates`

项目信息表的募集开始日期不得晚于募集结束日期

### `doc_actual_end_start`

项目信息表的产品实际终止日期不得早于产品起始日期

### `doc_acc_nav_positive`

项目信息表的累计净值应大于0

### `doc_unit_nav_bounds`

项目信息表的单位净值应在0到5之间，包含两个边界

### `doc_nav_dates`

项目信息表的累计净值日期不得早于单位净值日期

### `doc_raise_initial_amt`

募集明细表的初始募集金额不得小于0

### `doc_raise_initial_share`

募集明细表的初始募集份额应大于等于0

### `doc_raise_pay_amt`

募集明细表的当期兑付金额不得小于0

### `doc_raise_customer_name`

募集明细表的客户名称不能为空

## 本轮七条复核请求（7 条）

### `today_customer_keywords`

客户名称包含“商会|协会|中心|基金会|学会|物业|委员会”且不包含“有限公司|有限责任公司”时客户类型未归为“广义政府”，请确认

### `today_management_null`

资产管理信托项目产品类型不得为空

### `today_nonmanagement_no_value`

非资产管理信托项目的产品类型不得有值

### `today_contract_date`

贷款合同到期日一般不大于项目预计到期日

### `today_different_dates`

人行项目预计到期日与原始项目预计到期日期有差异，提醒关注

### `today_formula_a`

不满足公式：期末产品份额=上一期期末产品份额+当期申购份额-当期兑付份额，请核实

### `today_formula_b`

募集明细应满足公式：期末产品份额=上一期期末产品份额+当期申购份额-当期兑付份额。

## 四条截图复核请求（4 条）

### `screenshot_ended_paid`

项目已结束，但是实收信托不为0

### `screenshot_active_paid`

存续项目实收信托不得小于0

### `screenshot_performance_signs`

产品期末业绩表现不能包含%或‰

### `screenshot_public_separate`

募集方式为公开募集的项目，管理方式不应为单独管理

## 实际采纳请求（2 条）

### `ui_adopt_paid_consistency`

项目实收信托与募集期末实收份额汇总差异核对
用户已确认存续项目实收存在项目余额与募集合同实收份额两个独立可选方案，且两者按同一项目编号、同一数据日期对应，可另做跨维度差异核对。
建议检查类型：aggregate_consistency
文档字段：proj_info_dtl_pboc.f_equity_total_4001_bal、raise_info_dtl_pboc.f_end_share
原方案报送分类：group:pbc
建议运算：sum
各原方案的适用范围：[{"table":"proj_info_dtl_pboc","filters":[{"table":"proj_info_dtl_pboc","field":"c_projstatus","op":"eq","value":"1"}]}]
原建议所列前提，请结合当前已确认业务知识核实：确认项目4001科目余额与募集合同实收份额的计量口径、单位及允许差额

### `adopted_paid_consistency`

存续项目实收信托项目余额与募集合同实收份额汇总差异核对
知识库已确认按同一c_projinnercode、d_cldate汇总募集明细f_end_share，与项目f_equity_total_4001_bal比较，差额不为0即异常，容差0，用于跨维度一致性核查
建议检查类型：aggregate_consistency
文档字段：proj_info_dtl_pboc.f_equity_total_4001_bal、raise_info_dtl_pboc.f_end_share
原方案报送分类：group:pbc
建议运算：sum
各原方案的适用范围：[{"table":"proj_info_dtl_pboc","filters":[{"table":"proj_info_dtl_pboc","field":"c_projstatus","op":"eq","value":"1"}]}]
原建议所列前提，请结合当前已确认业务知识核实：确认项目实收信托余额与募集合同实收份额的计量单位及换算关系
