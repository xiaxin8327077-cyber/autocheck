from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LegacyRule:
    rule_id: str
    rule_text: str
    enabled: bool = True
    disabled_reason: str = ""

    @property
    def zg_code(self) -> str:
        return f"ZG{self.rule_id[2:4]}"

    @property
    def is_template_rule(self) -> bool:
        return "模板交叉校验" in self.rule_text

    @property
    def is_public_info_rule(self) -> bool:
        return "公开信息交叉校验" in self.rule_text

    @property
    def category(self) -> str:
        if self.is_template_rule:
            return "模板校验"
        if self.is_public_info_rule:
            return "公开数据校验"
        return "逐笔数据校验"


ACTIVE_LEGACY_RULES: tuple[LegacyRule, ...] = (
    LegacyRule("Zg01_Rule1", "Zg01_Rule1:无固定期限产品，发行机构提前终止权标识填“1-有”，需核实"),
    LegacyRule("Zg01_Rule3", "Zg01_Rule3:资管产品增信形式与增信机构类型不对应，需核实"),
    LegacyRule("Zg01_Rule4", "Zg01_Rule4:开放式产品客户赎回权标识填报“1-有”，需核实"),
    LegacyRule("Zg01_Rule5", "Zg01_Rule5:产品代码第8-9位，与产品募集起始日期年份不一致，需核实"),
    LegacyRule("Zg01_Rule6", "Zg01_Rule6:产品名称长度小于等于5个字，有特殊符号，需核实"),
    LegacyRule("Zg01_Rule7", "Zg01_Rule7:分级产品的管理方式为单独管理，需核实"),
    LegacyRule("Zg01_Rule8", "Zg01_Rule8:托管机构名称未填报法人机构名称，需核实"),
    LegacyRule("Zg01_Rule9", "Zg01_Rule9:托管机构名称与代码未同时有数，需核实"),
    LegacyRule("Zg02_Rule1", "Zg02_Rule1:初始募集信息指标人民币合计与人民币金额不相等，需核实"),
    LegacyRule("Zg02_Rule2", "Zg02_Rule2:客户类型与地区代码不对应，需核实"),
    LegacyRule("Zg03_Rule1", "Zg03_Rule1:兑付客户收益金额较大，超过5亿元；兑付客户收益率过高，大于10%，需核实"),
    LegacyRule("Zg03_Rule2", "Zg03_Rule2:终止信息指标人民币合计与人民币金额不相等，需核实"),
    LegacyRule("Zg04_Rule1", "Zg04_Rule1:分产品分客户类型存续募集信息（ZG04）份额与资产负债信息（ZG05）实收本金不一致，需核实"),
    LegacyRule("Zg04_Rule2", "Zg04_Rule2:产品份额比对不符合校验公式（当期期末产品份额=上期期末产品份额+当期申购份额-当期兑付份额），需核实"),
    LegacyRule("Zg04_Rule3", "Zg04_Rule3:产品金额比对不符合校验公式（当期期末产品金额≈上期期末产品金额+当期申购金额-当期兑付金额），需核实"),
    LegacyRule("Zg04_Rule4", "Zg04_Rule4:净值型产品报送期末净值跨期变动过大（超过20%），需核实"),
    LegacyRule("Zg04_Rule6", "Zg04_Rule6：净值型产品期末累计净值小于期末净值，需核实"),
    LegacyRule("Zg04_Rule7", "Zg04_Rule7：期末产品份额为0的净值型产品期末净值与上期不一致且为1，需核实"),
    LegacyRule("Zg04_Rule8", "Zg04_Rule8:存续期募集信息指标人民币合计与人民币金额不相等，需核实"),
    LegacyRule("Zg04_Rule9", "Zg04_Rule9:客户类型与地区代码不对应，需核实"),
    LegacyRule("Zg04_Rule10", "Zg04_Rule10:当期申购金额与份额未同时有数，需核实"),
    LegacyRule("Zg04_Rule11", "Zg04_Rule11:当期募集金额与份额变动过大（超过20%），需核实"),
    LegacyRule("Zg04_Rule13", "Zg04_Rule13:当期兑付/赎回金额与份额变动过大（超过20%），需核实"),
    LegacyRule("Zg04_Rule12", "Zg04_Rule12:当期兑付/赎回金额与份额未同时有数，需核实"),
    LegacyRule("Zg04_Rule14", "Zg04_Rule14：存续期募集信息净值型产品期末净值和期末产品份额之积与期末产品金额的差值较大，需核实"),
    LegacyRule("Zg04_Rule15", "Zg04_Rule15：当月年化收益率跨期变动过大（超过200%），需核实"),
    LegacyRule("Zg04_Rule16", "Zg04_rule16:净值型产品期末产品金额有数，期末产品份额为0，需核实"),
    LegacyRule("Zg04_Rule17", "Zg04_Rule17：当月年化收益率为0，需核实"),
    LegacyRule("Zg04_Rule18", "Zg04_Rule18：净值型产品期末净值或累计净值为0，需核实"),
    LegacyRule("Zg04_Rule19", "Zg04_Rule19：期末产品金额折人民币为0时，当月年化收益率比上期波动超过20%，需核实"),
    LegacyRule("Zg05_Rule1", "Zg05_Rule1:资产负债指标人民币合计与人民币金额不相等，需核实"),
    LegacyRule("Zg05_Rule2", "Zg05_Rule2:资产负债指标人民币合计与折人民币金额不相等，需核实"),
    LegacyRule("Zg05_Rule3", "Zg05_Rule3:ZG05除回购和拆借外贷款与ZG07明细数据汇总金额不相等，需核实"),
    LegacyRule("Zg05_Rule4", "Zg05_Rule4:ZG05指标与ZG08明细数据汇总金额不相等，需核实"),
    LegacyRule("Zg06_Rule1", "Zg06_Rule1:资产负债项目与基础资产类型不对应，需核实"),
    LegacyRule("Zg06_Rule2", "Zg06_Rule2:基础资产出让机构代码不符合编码规则，需核实"),
    LegacyRule("Zg06_Rule3", "Zg06_Rule3:基础资产出让机构类型与行业不对应，需核实"),
    LegacyRule("Zg06_Rule4", "Zg06_Rule4:基础资产出让机构注册地区未填报到区县一级，需核实"),
    LegacyRule("Zg06_Rule5", "Zg06_Rule5:基础资产出让机构类型与规模不对应，需核实"),
    LegacyRule("Zg06_Rule6", "Zg06_Rule6:利率水平大于等于10或小于等于1，需核实"),
    LegacyRule("Zg06_Rule7", "Zg06_Rule7:金融机构实体基础资产出让机构代码不等于14位，需核实"),
    LegacyRule("Zg06_Rule8", "Zg06_Rule8:数据跨期不一致"),
    LegacyRule("Zg06_Rule9", "Zg06_Rule9:转让预计终止日期，转让展期到期日期大于、等于2090，需核实"),
    LegacyRule("Zg06_Rule10", "Zg06_Rule10:同一基础资产出让机构相关信息不一致，需核实"),
    LegacyRule("Zg06_Rule11", "Zg06_Rule11:公开信息交叉校验-资产转让起始日期早于产品起始日期，需核实"),
    LegacyRule("Zg06_Rule12", "Zg06_Rule12:公开信息交叉校验-转让预计终止日期晚于产品预计终止日期，需核实"),
    LegacyRule("Zg06_Rule13", "Zg06_Rule13:“五篇大文章”相关字段标识未填报，需核实"),
    LegacyRule("Zg06_Rule14", "Zg06_Rule14:“五篇大文章”相关字段标识不应填报"),
    LegacyRule("Zg06_Rule15", "Zg06_Rule15:出让机构出表标识为1-是，需核实"),
    LegacyRule("Zg06_Rule16", "Zg06_Rule16:出让机构回购标识为1-是，需核实"),
    LegacyRule("Zg07_Rule1", "Zg07_Rule1:贷款合同原始发放机构所在地代码未填报到区县一级，需核实"),
    LegacyRule("Zg07_Rule2", "Zg07_Rule2:借款人类型与地区代码不对应，需核实"),
    LegacyRule("Zg07_Rule3", "Zg07_Rule3:地区代码未填报到区县一级，需核实"),
    LegacyRule("Zg07_Rule4", "Zg07_Rule4:借款人类型与借款人代码不对应，需核实"),
    LegacyRule("Zg07_Rule5", "Zg07_Rule5:借款人代码不符合编码规则，需核实"),
    LegacyRule("Zg07_Rule6", "Zg07_Rule6:借款人类型与行业不对应，需核实"),
    LegacyRule("Zg07_Rule7", "Zg07_Rule7:借款人类型与企业规模不对应，需核实"),
    LegacyRule("Zg07_Rule8", "Zg07_Rule8:利率水平大于等于10或小于等于1，需核实"),
    LegacyRule("Zg07_Rule9", "Zg07_Rule9:除回购和拆借外贷款明细信息跨期校验"),
    LegacyRule("Zg07_Rule11", "Zg07_Rule11:展期贷款（贷款状态FS03）与贷款展期到期日期不对应，需核实"),
    LegacyRule("Zg07_Rule12", "Zg07_Rule12:同一借款人字段信息不一致，需核实"),
    LegacyRule("Zg07_Rule13", "Zg07_Rule13:公开信息交叉校验-贷款到期日期或展期到期日期大于产品预计终止日期，需核实"),
    LegacyRule("Zg07_Rule14", "Zg07_Rule14:借款人代码为空，需核实。"),
    LegacyRule("Zg07_Rule15", "Zg07_Rule15:借款人类型与贷款产品类别不对应，需核实"),
    LegacyRule("Zg07_Rule16", "Zg07_Rule16:贷款产品类别不为F02，需核实"),
    LegacyRule("Zg07_Rule17", "Zg07_Rule17:贷款到期日期或贷款展期到期日期大于、等于2090，需核实"),
    LegacyRule("Zg07_Rule18", "Zg07_Rule18:转让贷款的贷款转让机构代码、贷款合同原始发放机构代码为空，需核实。"),
    LegacyRule("Zg08_Rule1", "Zg08_Rule1:公开信息交叉校验-所投资资管产品已终止，需核实"),
    LegacyRule("Zg08_Rule2", "Zg08_Rule2:公开信息交叉校验-当期及上期所投资资管产品均不在平台名录库中，需核实"),
    LegacyRule("Zg08_Rule3", "Zg08_Rule3:银行非保本理财产品的交易对手为理财产品，需核实"),
    LegacyRule("Zg08_Rule4", "Zg08_Rule4:公开信息交叉校验-回购业务交易对手方未填报相关数据，需核实"),
    LegacyRule("Zg08_Rule8", "Zg08_Rule8:公开信息交叉校验-回购业务交易对手方填报相关数据，本机构未填写，需核实"),
    LegacyRule("Zg08_Rule5", "Zg08_Rule5:公开信息交叉校验-特定目的载体投资交易对手实收本金方未填报相关数据，需核实"),
    LegacyRule("Zg08_Rule9", "Zg08_Rule9:公开信息交叉校验-特定目的载体投资交易实收本金方填报相关数据，本机构未填写，需核实"),
    LegacyRule("Zg08_Rule6", "Zg08_Rule6:公开信息交叉校验-实收本金方交易对手特定目的载体投资未填报相关数据，需核实"),
    LegacyRule("Zg08_Rule10", "Zg08_Rule10:公开信息交叉校验-实收本金方交易对手特定目的载体投资填报相关数据，本机构未填写，需核实"),
    LegacyRule("Zg08_Rule7", "Zg08_Rule7:公开信息交叉校验-拆借业务交易对手方未填报相关数据，需核实"),
    LegacyRule("Zg08_Rule11", "Zg08_Rule11:公开信息交叉校验-拆借业务交易对手方填报相关数据，本机构未填写，需核实"),
    LegacyRule("Zg08_Rule12", "Zg08_Rule12:交易对手代码为自身产品代码，需核实"),
    LegacyRule("Zg08_Rule13", "Zg08_Rule13:交易对手机构编码与交易对手产品代码前6位不一致，需核实"),
    LegacyRule("Zg09_Rule3", "Zg09_Rule3:模板交叉校验-表内（金融）资产与模板数据不一致，需核实", enabled=False, disabled_reason="模板校验暂未接入，当前版本不执行"),
    LegacyRule("Zg10_Rule1", "Zg10_Rule1:模板交叉校验-数据平台指标与模板数据不一致，需核实", enabled=False, disabled_reason="模板校验暂未接入，当前版本不执行"),
    LegacyRule("Zg12_Rule1", "Zg12_Rule1:地区代码未填报到区县一级，需核实"),
    LegacyRule("Zg12_Rule2", "Zg12_Rule2:借款人类型与地区代码不对应，需核实"),
    LegacyRule("Zg12_Rule3", "Zg12_Rule3:借款人代码为空，需核实。"),
    LegacyRule("Zg12_Rule4", "Zg12_Rule4:借款人类型与借款人代码不对应，需核实"),
    LegacyRule("Zg12_Rule5", "Zg12_Rule5:借款人代码不符合编码规则，需核实"),
    LegacyRule("Zg12_Rule6", "Zg12_Rule6:借款人类型与行业不对应，需核实"),
    LegacyRule("Zg12_Rule7", "Zg12_Rule7:借款人类型与企业规模不对应，需核实"),
    LegacyRule("Zg12_Rule8", "Zg12_Rule8:利率水平大于等于10或小于等于1，需核实"),
    LegacyRule("Zg12_Rule9", "Zg12_Rule9:除资产收益权外其他债权明细信息跨期校验"),
    LegacyRule("Zg12_Rule10", "Zg12_Rule10:登记交易场所代码不符合编码规则，需核实"),
    LegacyRule("Zg12_Rule11", "Zg12_Rule11:除资产收益权外其他债权预计到期日期大于、等于2090，需核实"),
    LegacyRule("Zg12_Rule12", "Zg12_Rule12:同一借款人字段信息不一致，需核实"),
    LegacyRule("Zg12_Rule13", "Zg12_Rule13:公开信息交叉校验-除资产收益权外其他债权预计到期日期大于产品预计终止日期，需核实"),
    LegacyRule("Zg12_Rule14", "Zg12_Rule14:债权类型与登记交易场所不对应，需核实"),
    LegacyRule("Zg12_Rule16", "Zg12_Rule16:ZG05除资产收益权外其他债权与ZG12明细数据汇总金额不相等，需核实"),
    LegacyRule("Zg12_Rule17", "Zg12_Rule17:登记交易场所为其他，代码未填报18个0；或者填18个0，类型未填其他，需核实"),
    LegacyRule("Zg12_Rule18", "Zg12_Rule18:担保方式为其他，需核实"),
    LegacyRule("Zg13_Rule1", "Zg13_Rule1:地区代码未填报到区县一级，需核实"),
    LegacyRule("Zg13_Rule2", "Zg13_Rule2:标的企业代码不符合编码规则，需核实"),
    LegacyRule("Zg13_Rule3", "Zg13_Rule3:标的企业代码为空，需核实。"),
    LegacyRule("Zg13_Rule4", "Zg13_Rule4:其他股权投资明细信息跨期校验"),
    LegacyRule("Zg13_Rule5", "Zg13_Rule5:股权出让方代码不符合编码规则，需核实"),
    LegacyRule("Zg13_Rule6", "Zg13_Rule6:股权出让方代码为空，需核实。"),
    LegacyRule("Zg13_Rule8", "Zg13_Rule8:同一标的企业字段信息不一致，需核实"),
    LegacyRule("Zg13_Rule9", "Zg13_Rule9:公开信息交叉校验-合同预计终止日期大于产品预计终止日期，需核实"),
    LegacyRule("Zg13_Rule10", "Zg13_Rule10:ZG05除资产收益权外其他债权与ZG13-A7310明细数据汇总金额不相等，需核实"),
    LegacyRule("Zg13_Rule11", "Zg13_Rule11:ZG05除资产收益权外其他债权与ZG13-A7320明细数据汇总金额不相等，需核实"),
    LegacyRule("Zg13_Rule12", "Zg13_Rule12:股性永续债合同预计终止日期与持股比例填报不符合要求，需核实"),
    LegacyRule("Zg13_Rule13", "Zg13_Rule13:资产负债项目与行业信息不对应，需核实"),
    LegacyRule("Zg13_Rule15", "Zg13_Rule15:境内金融机构标的企业代码未填报金融机构编码，需核实。"),
    LegacyRule("Zg13_Rule16", "Zg13_Rule16:境内金融机构标的股权出让方代码未填报金融机构编码，需核实。"),
)


LEGACY_RULE_IDS: frozenset[str] = frozenset(rule.rule_id for rule in ACTIVE_LEGACY_RULES)
EXECUTABLE_LEGACY_RULE_IDS: frozenset[str] = frozenset(rule.rule_id for rule in ACTIVE_LEGACY_RULES if rule.enabled)
DISABLED_LEGACY_RULE_IDS: frozenset[str] = frozenset(rule.rule_id for rule in ACTIVE_LEGACY_RULES if not rule.enabled)
