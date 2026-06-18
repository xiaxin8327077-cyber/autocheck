from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DETAIL_JS = ROOT / "src" / "auto_check" / "web" / "export_detail.js"


def run_export_detail(item: dict) -> str:
    return run_export_function("buildExportDetailText", item)


def run_export_function(function_name: str, item: dict) -> str:
    script = f"""
const {{ {function_name} }} = require({json.dumps(str(EXPORT_DETAIL_JS))});
const item = {json.dumps(item, ensure_ascii=False)};
process.stdout.write({function_name}(item));
"""
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    return result.stdout


def test_stock_mismatch_processing_script_uses_fa_am_and_contract_codes():
    text = run_export_function(
        "buildProcessingScript",
        {
            "difference_reason": "资产缺失",
            "display_details": [
                {
                    "title": "标的代码核对",
                    "rows": [
                        {"label": "FA 科目尾段代码", "value": "244733"},
                        {"label": "AM 标的代码", "value": "244978"},
                        {"label": "AM 合同代码", "value": "PACT001"},
                    ],
                }
            ],
        },
    )

    assert text == (
        "insert\n"
        "\tinto\n"
        "\tdata_mangement.data_mangement_dwd(updatekey,\n"
        "\tupdatetable,\n"
        "\tupdatecol,\n"
        "\tupdatevalue_befor,\n"
        "\tupdatevalue_after,\n"
        "\tupdatekeyvalue,\n"
        "\tlogsql,\n"
        "\tupdatesql,\n"
        "\tstatus)\n"
        "values('c_pactid', 'dwd_am_am_pactasset_dwd', 'c_stockcode', '244978', '244733', 'PACT001',\n"
        "'', 'update dwd.am_am_pactasset_dwd set c_stockcode = ''244733'' where c_pactid = ''PACT001'' and c_stockcode = ''244978''', '1');"
    )


def test_processing_script_generates_multiple_fa_am_scripts_from_asset_missing_refinement():
    text = run_export_function(
        "buildProcessingScript",
        {
            "difference_reason": "资产缺失",
            "display_details": [
                {
                    "title": "资产缺失细分",
                    "table": {
                        "headers": [
                            "序号",
                            "资产类型",
                            "资产名称",
                            "FA科目编码",
                            "科目尾段",
                            "FA估值金额",
                            "核查表",
                            "核查结果",
                            "关键字段",
                            "AM标的代码",
                            "AM合同代码",
                            "原因",
                        ],
                        "rows": [
                            [
                                "①",
                                "特定目的载体",
                                "银行理财A",
                                "1101.05.04.01.0001",
                                "0001",
                                "100",
                                "am_pactasset_dws",
                                "FA和AM标的不一致",
                                "c_stockcode",
                                "9999",
                                "PACT_A",
                                "FA和AM标的不一致",
                            ],
                            [
                                "②",
                                "特定目的载体",
                                "保险理财B",
                                "1101.05.05.01.0002",
                                "0002",
                                "100",
                                "am_pactasset_dws",
                                "FA和AM标的不一致",
                                "c_stockcode",
                                "8888",
                                "PACT_B",
                                "FA和AM标的不一致",
                            ],
                        ],
                    },
                }
            ],
        },
    )

    assert text.count("insert\n\tinto\n\tdata_mangement.data_mangement_dwd") == 2
    assert "'9999', '0001', 'PACT_A'" in text
    assert "c_pactid = ''PACT_A'' and c_stockcode = ''9999''" in text
    assert "'8888', '0002', 'PACT_B'" in text
    assert "c_pactid = ''PACT_B'' and c_stockcode = ''8888''" in text


def test_processing_script_is_blank_without_stock_mismatch_detail():
    assert run_export_function(
        "buildProcessingScript",
        {
            "difference_reason": "资产缺失",
            "display_details": [],
        },
    ) == ""


def test_asset_gap_export_detail_includes_asset_and_stock_mismatch():
    text = run_export_detail(
        {
            "difference_reason": "资产缺失",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "资负报表资产合计", "value": "1171320069.10"},
                        {"label": "估值表资产合计", "value": "1172266385.70"},
                        {"label": "资产差异金额", "value": "946316.60"},
                        {"label": "具体原因", "value": "FA与AM标的不一致"},
                    ],
                },
                {
                    "title": "具体差异明细",
                    "table": {
                        "rows": [
                            ["1101.02.15.01.244733", "G26资控1", "244733", "946316.60"],
                        ]
                    },
                },
                {
                    "title": "标的代码核对",
                    "rows": [
                        {"label": "FA 估值科目名称", "value": "G26资控1"},
                        {"label": "FA 科目尾段代码", "value": "244733"},
                        {"label": "AM 标的代码", "value": "244978"},
                    ],
                },
            ],
        }
    )

    assert text.splitlines() == [
        "差异类型：资产缺失",
        "具体原因：FA与AM标的不一致",
        "资产核对：资负报表资产=1,171,320,069.1，估值表资产=1,172,266,385.7，差异=946,316.6",
        "命中科目：",
        "① 科目代码：1101.02.15.01.244733；科目名称：G26资控1；科目尾段：244733；金额：946,316.6",
        "标的核对：FA估值科目名称：G26资控1；FA科目尾段代码：244733；AM标的代码：244978；核查结果：不一致",
    ]


def test_asset_gap_export_detail_includes_am_confirmed_candidate_message():
    text = run_export_detail(
        {
            "difference_reason": "资产缺失",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "具体原因", "value": "①特定目的载体缺失：太保安盈6号保险理财；原因：FA和AM标的不一致"},
                        {"label": "资负报表资产合计", "value": "199000000"},
                        {"label": "估值表资产合计", "value": "200000000"},
                        {"label": "资产差异金额", "value": "1000000"},
                        {"label": "命中方式", "value": "多个科目组合命中"},
                        {"label": "匹配说明", "value": "候选不唯一，经AM复核确认：候选组合2"},
                    ],
                },
            ],
        }
    )

    assert "匹配说明：候选不唯一，经AM复核确认：候选组合2" in text


def test_asset_gap_export_detail_supports_legacy_zf_detail_asset_label():
    text = run_export_detail(
        {
            "difference_reason": "资产缺失",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "zf_detail 资产合计", "value": "900"},
                        {"label": "估值表资产合计", "value": "1000"},
                        {"label": "资产差异金额", "value": "100"},
                    ],
                },
            ],
        }
    )

    assert "资产核对：资负报表资产=900，估值表资产=1,000，差异=100" in text
    assert "zf_detail资产" not in text


def test_asset_missing_refinement_export_detail_keeps_numbered_specific_reason():
    text = run_export_detail(
        {
            "difference_reason": "资产缺失",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "具体原因", "value": "①债券缺失：23苏城投MTN004；原因：资负数据子系统-债务证券明细表无数据\n②贷款缺失：贷款合同DK20260531001"},
                        {"label": "资负报表资产合计", "value": "800"},
                        {"label": "估值表资产合计", "value": "1000"},
                        {"label": "资产差异金额", "value": "200"},
                    ],
                },
                {
                    "title": "具体差异明细",
                    "table": {
                        "rows": [
                            ["1501.01.01.01.102381204", "23苏城投MTN004", "102381204", "100"],
                            ["1303.01.01.DK20260531001", "贷款合同DK20260531001", "DK20260531001", "100"],
                        ]
                    },
                },
            ],
        }
    )

    assert text.splitlines() == [
        "差异类型：资产缺失",
        "具体原因：",
        "①债券缺失：23苏城投MTN004；原因：资负数据子系统-债务证券明细表无数据",
        "②贷款缺失：贷款合同DK20260531001",
        "资产核对：资负报表资产=800，估值表资产=1,000，差异=200",
        "命中科目：",
        "① 科目代码：1501.01.01.01.102381204；科目名称：23苏城投MTN004；科目尾段：102381204；金额：100",
        "② 科目代码：1303.01.01.DK20260531001；科目名称：贷款合同DK20260531001；科目尾段：DK20260531001；金额：100",
    ]


def test_received_trust_export_detail_includes_c1000_and_fa4001():
    text = run_export_detail(
        {
            "difference_reason": "实收本金差异",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "c1000 实收本金余额", "value": "250000000.00"},
                        {"label": "FA 4001 科目余额", "value": "250117177.50"},
                        {"label": "4001-c1000 差异", "value": "117177.50"},
                        {"label": "具体原因", "value": "①实收本金差异：FA 4001与c1000存在差异，差异值117177.50"},
                    ],
                },
            ],
        }
    )

    assert text.splitlines() == [
        "差异类型：实收本金差异",
        "具体原因：",
        "①实收本金差异：FA 4001与c1000存在差异，差异值117177.50",
        "实收核对：c1000实收本金余额=250,000,000，FA 4001科目余额=250,117,177.5，差异=117,177.5",
    ]


def test_received_trust_export_detail_does_not_append_judgement_basis():
    text = run_export_detail(
        {
            "difference_reason": "实收本金差异",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "c1000 实收本金余额", "value": "250000000.00"},
                        {"label": "FA 4001 科目余额", "value": "250117177.50"},
                        {"label": "4001-c1000 差异", "value": "117177.50"},
                        {"label": "判断依据", "value": "FA 4001 - c1000 等于 a0001-d0000。"},
                    ],
                },
            ],
        }
    )

    assert "判断依据" not in text


def test_ta_total_mismatch_export_detail_includes_dm_and_dws_totals():
    text = run_export_detail(
        {
            "difference_reason": "实收本金差异",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "c1000 实收本金余额", "value": "400"},
                        {"label": "FA 4001 科目余额", "value": "500"},
                        {"label": "4001-c1000 差异", "value": "100"},
                        {"label": "具体原因", "value": "①实收本金差异：FA 4001与c1000存在差异，差异值100；原因：DM表TA份额余额错误"},
                    ],
                },
                {
                    "title": "TA汇总核对",
                    "rows": [
                        {"label": "DM TA 份额余额+待结转收益", "value": "480"},
                        {"label": "DWS TA 份额余额+待结转收益", "value": "500"},
                        {"label": "DM-DWS 差异", "value": "-20"},
                    ],
                },
            ],
        }
    )

    assert text.splitlines() == [
        "差异类型：实收本金差异",
        "具体原因：",
        "①实收本金差异：FA 4001与c1000存在差异，差异值100；原因：DM表TA份额余额错误",
        "实收核对：c1000实收本金余额=400，FA 4001科目余额=500，差异=100",
        "TA汇总核对：DM=480，DWS=500，差异=-20",
    ]


def test_ta_blank_client_type_export_detail_includes_contract_rows():
    text = run_export_detail(
        {
            "difference_reason": "实收本金差异",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "c1000 实收本金余额", "value": "400"},
                        {"label": "FA 4001 科目余额", "value": "500"},
                        {"label": "4001-c1000 差异", "value": "100"},
                        {"label": "具体原因", "value": "①实收本金差异：FA 4001与c1000存在差异，差异值100；原因：dm.ta_pact_survamt_day_zgxg_dm表中客户类型为空导致实收信托有误"},
                    ],
                },
                {
                    "title": "DM TA客户类型为空",
                    "rows": [
                        {"label": "客户类型为空金额合计", "value": "100"},
                    ],
                    "table": {
                        "rows": [
                            ["PACT1", "客户A", "4", "", "SPV", "30", "70", "100"],
                        ]
                    },
                },
            ],
        }
    )

    assert text.splitlines() == [
        "差异类型：实收本金差异",
        "具体原因：",
        "①实收本金差异：FA 4001与c1000存在差异，差异值100；原因：dm.ta_pact_survamt_day_zgxg_dm表中客户类型为空导致实收信托有误",
        "实收核对：c1000实收本金余额=400，FA 4001科目余额=500，差异=100",
        "客户类型为空：合计=100",
        "客户类型明细：",
        "① 合同编号：PACT1；客户名称：客户A；客户类型：4；客户类型明细：-；SPV类型：SPV；金额：100",
    ]


def test_am_missing_export_detail_includes_fa_subject():
    text = run_export_detail(
        {
            "difference_reason": "资产缺失",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "资负报表资产合计", "value": "900"},
                        {"label": "估值表资产合计", "value": "1000"},
                        {"label": "资产差异金额", "value": "100"},
                        {"label": "具体原因", "value": "AM标的缺失"},
                    ],
                },
                {
                    "title": "具体差异明细",
                    "table": {
                        "rows": [["1101.05.03.01.0002", "Asset A", "0002", "100"]],
                    },
                },
                {
                    "title": "AM标的缺失",
                    "rows": [
                        {"label": "FA 估值科目代码", "value": "1101.05.03.01.0002"},
                        {"label": "FA 估值科目名称", "value": "Asset A"},
                        {"label": "FA 科目尾段代码", "value": "0002"},
                    ],
                },
            ],
        }
    )

    assert "差异类型：资产缺失" in text
    assert "具体原因：AM标的缺失" in text
    assert "AM标的缺失：FA估值科目代码：1101.05.03.01.0002；FA估值科目名称：Asset A；FA科目尾段代码：0002；核查结果：未匹配到AM资产信息" in text


def test_project_invest_export_detail_includes_contract_balance():
    text = run_export_detail(
        {
            "difference_reason": "资产缺失",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "资负报表资产合计", "value": "900"},
                        {"label": "估值表资产合计", "value": "1000"},
                        {"label": "资产差异金额", "value": "100"},
                        {"label": "具体原因", "value": "合同投融资余额为0但FA科目余额不为0"},
                    ],
                },
                {
                    "title": "合同投融资余额核对",
                    "rows": [
                        {"label": "AM 资产名称", "value": "Asset A"},
                        {"label": "AM 标的代码", "value": "0002"},
                        {"label": "AM 合同代码", "value": "PACT1"},
                        {"label": "合同投融资余额", "value": "0"},
                    ],
                },
            ],
        }
    )

    assert "差异类型：资产缺失" in text
    assert "具体原因：合同投融资余额为0但FA科目余额不为0" in text
    assert "合同投融资核对：AM资产名称：Asset A；AM标的代码：0002；AM合同代码：PACT1；合同投融资余额：0" in text


def test_liability_equity_export_detail_includes_scope_and_accounts():
    text = run_export_detail(
        {
            "difference_reason": "负债及权益科目差异",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "核对范围", "value": "非1开头科目"},
                        {"label": "命中方式", "value": "多个科目组合命中"},
                        {"label": "命中金额", "value": "231610.00"},
                    ],
                },
                {
                    "title": "具体差异明细",
                    "table": {
                        "rows": [
                            ["2001.01", "应付管理费", "01", "100000.00"],
                            ["2203.01", "应付托管费", "01", "131610.00"],
                        ]
                    },
                },
            ],
        }
    )

    assert text.splitlines() == [
        "差异类型：负债及权益科目差异",
        "权益核对：范围=非1开头科目，命中方式=多个科目组合命中，命中金额=231,610",
        "命中科目：",
        "① 科目代码：2001.01；科目名称：应付管理费；科目尾段：01；金额：100,000",
        "② 科目代码：2203.01；科目名称：应付托管费；科目尾段：01；金额：131,610",
    ]


def test_liability_equity_export_detail_includes_received_trust_residual_gap():
    text = run_export_detail(
        {
            "difference_reason": "负债及权益科目重复",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "具体原因", "value": "①实收本金差异：FA 4001与c1000存在差异，差异值100\n②负债及权益科目重复：其他收益"},
                        {"label": "4001-c1000 差异", "value": "100"},
                        {"label": "主差异", "value": "50"},
                        {"label": "实收差额", "value": "100"},
                        {"label": "剩余差额", "value": "-50"},
                        {"label": "核对范围", "value": "非1开头科目"},
                        {"label": "命中方式", "value": "单行金额命中"},
                        {"label": "命中金额", "value": "50"},
                    ],
                },
                {
                    "title": "具体差异明细",
                    "table": {
                        "rows": [
                            ["4002", "其他收益", "4002", "50"],
                        ]
                    },
                },
            ],
        }
    )

    assert text.splitlines() == [
        "差异类型：负债及权益科目重复",
        "具体原因：",
        "①实收本金差异：FA 4001与c1000存在差异，差异值100",
        "②负债及权益科目重复：其他收益",
        "剩余差额核对：主差异=50，实收差额=100，剩余差额=-50",
        "权益核对：范围=非1开头科目，命中方式=单行金额命中，命中金额=50",
        "命中科目：",
        "① 科目代码：4002；科目名称：其他收益；科目尾段：4002；金额：50",
    ]


def test_liability_equity_export_detail_does_not_append_judgement_basis():
    text = run_export_detail(
        {
            "difference_reason": "负债及权益科目差异",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "核对范围", "value": "非1开头科目"},
                        {"label": "命中方式", "value": "单行金额命中"},
                        {"label": "命中金额", "value": "-200000.00"},
                        {"label": "判断依据", "value": "非1开头估值科目金额命中主差异。"},
                    ],
                },
            ],
        }
    )

    assert "判断依据" not in text


def test_unknown_export_detail_is_blank_without_judgement_basis():
    assert run_export_detail({"difference_reason": "暂无法确定", "match_status": "未解释"}) == ""


def test_unknown_export_detail_includes_judgement_basis():
    text = run_export_detail(
        {
            "difference_reason": "暂无法确定",
            "match_status": "未解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "判断依据", "value": "资产合计与估值表0004不一致，但估值表1开头科目和1541合同差异均未命中。"},
                    ],
                }
            ],
        }
    )

    assert text == "判断依据：资产合计与估值表0004不一致，但估值表1开头科目和1541合同差异均未命中。"


def test_unknown_candidate_ambiguous_export_detail_lists_candidate_groups():
    text = run_export_detail(
        {
            "difference_reason": "负债及权益科目缺失 + 暂无法确定",
            "match_status": "候选不唯一",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "具体原因", "value": "候选不唯一"},
                        {"label": "命中方式", "value": "候选不唯一"},
                        {"label": "命中金额", "value": "50"},
                    ],
                },
                {
                    "title": "候选组合明细",
                    "table": {
                        "headers": ["候选组合", "组内合计", "科目代码", "科目名称", "科目尾段", "金额"],
                        "rows": [
                            ["候选组合1", "50", "2209.01.01.01.A", "应付管理费A", "A", "20"],
                            ["候选组合1", "50", "2209.01.01.01.B", "应付托管费B", "B", "30"],
                            ["候选组合2", "50", "2221.01.01.01.C", "应交税费C", "C", "10"],
                            ["候选组合2", "50", "2221.01.01.01.D", "其他应付款D", "D", "40"],
                        ],
                    },
                },
            ],
        }
    )

    assert text == "\n".join(
        [
            "差异类型：负债及权益科目缺失 + 暂无法确定",
            "具体原因：候选不唯一",
            "权益核对：范围=，命中方式=候选不唯一，命中金额=50",
            "候选组合1：合计金额 50",
            "① 科目代码：2209.01.01.01.A；科目名称：应付管理费A；科目尾段：A；金额：20",
            "② 科目代码：2209.01.01.01.B；科目名称：应付托管费B；科目尾段：B；金额：30",
            "候选组合2：合计金额 50",
            "① 科目代码：2221.01.01.01.C；科目名称：应交税费C；科目尾段：C；金额：10",
            "② 科目代码：2221.01.01.01.D；科目名称：其他应付款D；科目尾段：D；金额：40",
        ]
    )


def test_asset_gap_candidate_ambiguous_export_detail_lists_candidate_groups():
    text = run_export_detail(
        {
            "difference_reason": "资产缺失 + 暂无法确定",
            "match_status": "候选不唯一",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "具体原因", "value": "候选不唯一"},
                        {"label": "资负报表资产合计", "value": "900"},
                        {"label": "估值表资产合计", "value": "950"},
                        {"label": "资产差异金额", "value": "50"},
                        {"label": "命中方式", "value": "候选不唯一"},
                    ],
                },
                {
                    "title": "候选组合明细",
                    "table": {
                        "headers": ["候选组合", "组内合计", "科目代码", "科目名称", "科目尾段", "金额"],
                        "rows": [
                            ["候选组合1", "50", "1001.01.01.01.0001", "资产A", "0001", "20"],
                            ["候选组合1", "50", "1002.01.01.01.0002", "资产B", "0002", "30"],
                            ["候选组合2", "50", "1003.01.01.01.0003", "资产C", "0003", "10"],
                            ["候选组合2", "50", "1004.01.01.01.0004", "资产D", "0004", "40"],
                        ],
                    },
                },
            ],
        }
    )

    assert text == "\n".join(
        [
            "差异类型：资产缺失 + 暂无法确定",
            "具体原因：候选不唯一",
            "资产核对：资负报表资产=900，估值表资产=950，差异=50",
            "候选组合1：合计金额 50",
            "① 科目代码：1001.01.01.01.0001；科目名称：资产A；科目尾段：0001；金额：20",
            "② 科目代码：1002.01.01.01.0002；科目名称：资产B；科目尾段：0002；金额：30",
            "候选组合2：合计金额 50",
            "① 科目代码：1003.01.01.01.0003；科目名称：资产C；科目尾段：0003；金额：10",
            "② 科目代码：1004.01.01.01.0004；科目名称：资产D；科目尾段：0004；金额：40",
        ]
    )


def test_property_right_invest_export_detail_includes_contract_rows_and_basis():
    text = run_export_detail(
        {
            "difference_reason": "资产差异",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "估值1541科目金额合计", "value": "10000000"},
                        {"label": "AM合同投融资余额合计", "value": "20000000"},
                        {"label": "投融资-估值差异合计", "value": "10000000"},
                        {"label": "具体原因", "value": "财产权合同投融资金额比估值金额多"},
                        {"label": "判断依据", "value": "1541最末级科目尾段作为合同代码。"},
                    ],
                },
                {
                    "title": "财产权合同投融资核对",
                    "table": {
                        "rows": [
                            ["1541.01.PACTA", "财产权A", "PACTA", "5000000", "10000000", "5000000"],
                            ["1541.01.PACTB", "财产权B", "PACTB", "5000000", "10000000", "5000000"],
                        ]
                    },
                },
            ],
        }
    )

    assert "1541财产权核对：估值金额合计=10,000,000，AM合同投融资余额合计=20,000,000，差异=10,000,000" in text
    assert "合同明细：" in text
    assert "① 科目代码：1541.01.PACTA；科目名称：财产权A；合同代码：PACTA；估值金额：5,000,000；AM合同投融资余额：10,000,000；差异值：5,000,000" in text
    assert "② 科目代码：1541.01.PACTB；科目名称：财产权B；合同代码：PACTB；估值金额：5,000,000；AM合同投融资余额：10,000,000；差异值：5,000,000" in text
    assert "判断依据" not in text


def test_asset_difference_refinement_export_detail_includes_contract_rows():
    text = run_export_detail(
        {
            "difference_reason": "资产差异",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "资产差异FA科目余额合计", "value": "300"},
                        {"label": "资产差异AM/业务表金额合计", "value": "200"},
                        {"label": "资产差异金额合计", "value": "-100"},
                        {"label": "具体原因", "value": "①流动资金贷款一号贷款合同：FA科目余额与AM投融资余额有差异，差异值-100"},
                    ],
                },
                {
                    "title": "资产差异细分",
                    "table": {
                        "rows": [
                            ["①", "贷款合同", "流动资金贷款一号", "1501.04.05.01.DK20260531001", "DK20260531001", "300", "200", "-100", "dm.am_projinvest_zgxg_dm", "流动资金贷款一号贷款合同：FA科目余额与AM投融资余额有差异，差异值-100"],
                        ]
                    },
                },
            ],
        }
    )

    assert "具体原因：\n①流动资金贷款一号贷款合同：FA科目余额与AM投融资余额有差异，差异值-100" in text
    assert "资产差异细分核对：FA科目余额合计=300，DM证券余额/AM投融资余额/存续回购业务表金额合计=200，差异=-100" in text
    assert "资产差异明细：" in text
    assert "① 资产类型：贷款合同；资产名称：流动资金贷款一号；合同代码：DK20260531001；FA科目余额：300；AM投融资余额：200；差异值：-100" in text


def test_asset_difference_refinement_export_detail_includes_bond_security_code():
    text = run_export_detail(
        {
            "difference_reason": "资产差异",
            "match_status": "组合候选过多",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {"label": "资产差异FA科目余额合计", "value": "200"},
                        {"label": "资产差异DM证券余额/AM投融资余额/存续回购业务表金额合计", "value": "170"},
                        {"label": "资产差异金额合计", "value": "-30"},
                        {"label": "具体原因", "value": "暂不明确具体资产差异，但多个债券，FA债券本金科目余额与DM证券余额有差异，差异值-30"},
                    ],
                },
                {
                    "title": "资产差异细分",
                    "table": {
                        "rows": [
                            ["①", "债券", "23苏城投MTN002", "1101.02.01.01.ZQ002", "ZQ002", "100", "85", "-15", "dm.fa_security_balance_zgxg_dm", "23苏城投MTN002债券：FA债券本金科目余额与DM证券余额有差异，债券代码ZQ002，差异值-15"],
                            ["②", "债券", "23苏城投MTN003", "1101.02.01.01.ZQ003", "ZQ003", "100", "85", "-15", "dm.fa_security_balance_zgxg_dm", "23苏城投MTN003债券：FA债券本金科目余额与DM证券余额有差异，债券代码ZQ003，差异值-15"],
                        ]
                    },
                },
            ],
        }
    )

    assert "资产差异细分核对：FA科目余额合计=200，DM证券余额/AM投融资余额/存续回购业务表金额合计=170，差异=-30" in text
    assert "资产差异明细：" in text
    assert "① 资产类型：债券；资产名称：23苏城投MTN002；证券代码：ZQ002；FA科目余额：100；DM证券余额：85；差异值：-15" in text
    assert "② 资产类型：债券；资产名称：23苏城投MTN003；证券代码：ZQ003；FA科目余额：100；DM证券余额：85；差异值：-15" in text


def test_combined_asset_and_liability_export_detail_includes_both_parts():
    text = run_export_detail(
        {
            "difference_reason": "资产差异 + 负债及权益科目差异",
            "match_status": "已解释",
            "display_details": [
                {
                    "title": "最终判断结果",
                    "rows": [
                        {
                            "label": "具体原因",
                            "value": (
                                "①逆回购：FA科目余额与存续回购业务表逆回购金额有差异，差异值100\n"
                                "②正回购：FA科目余额与存续回购业务表正回购金额有差异，差异值50"
                            ),
                        },
                        {"label": "资负报表资产合计", "value": "1000"},
                        {"label": "估值表资产合计", "value": "900"},
                        {"label": "资产差异金额", "value": "100"},
                        {"label": "资产差异FA科目余额合计", "value": "300"},
                        {"label": "资产差异AM/业务表金额合计", "value": "400"},
                        {"label": "资产差异金额合计", "value": "100"},
                        {"label": "资产端解释后剩余差额", "value": "50"},
                        {"label": "核对范围", "value": "非1开头科目"},
                        {"label": "命中方式", "value": "未命中"},
                        {"label": "命中金额", "value": "0"},
                    ],
                },
                {
                    "title": "资产差异细分",
                    "table": {
                        "rows": [
                            ["①", "逆回购", "逆回购", "1111.12.34.01", "", "300", "400", "100", "assman_reg.ex_pledge_back", "逆回购：FA科目余额与存续回购业务表逆回购金额有差异，差异值100"],
                        ]
                    },
                },
            ],
        }
    )

    assert text.splitlines() == [
        "差异类型：资产差异 + 负债及权益科目差异",
        "具体原因：",
        "①逆回购：FA科目余额与存续回购业务表逆回购金额有差异，差异值100",
        "②正回购：FA科目余额与存续回购业务表正回购金额有差异，差异值50",
        "资产核对：资负报表资产=1,000，估值表资产=900，差异=100",
        "资产差异细分核对：FA科目余额合计=300，DM证券余额/AM投融资余额/存续回购业务表金额合计=400，差异=100",
        "资产差异明细：",
        "① 资产类型：逆回购；资产名称：逆回购；合同代码：无；FA科目余额：300；存续回购业务表金额：400；差异值：100",
        "剩余差额核对：主差异=，实收差额=，剩余差额=50",
        "权益核对：范围=非1开头科目，命中方式=未命中，命中金额=0",
    ]
