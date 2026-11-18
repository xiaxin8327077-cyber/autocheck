"""提示词默认模板与输出契约的静态验证。

只读取常量与内存存储，不调用模型、不发起任何网络请求。
"""

from __future__ import annotations

import json
import math
import re

import pytest

from auto_check.modules.data_validation.prompt_defaults import (
    DEFAULT_PROMPTS,
    REQUIRED_PLACEHOLDERS,
    RULE_OUTPUT_CONTRACT,
    SELECT_OUTPUT_CONTRACT,
    STAGE_LABELS,
)


def _fenced_json_blocks(text: str) -> list[str]:
    return re.findall(r"```json\s*\n(.*?)\n```", text, re.DOTALL)


def _is_string_array(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def test_default_prompts_keep_required_placeholders() -> None:
    assert set(DEFAULT_PROMPTS) == set(REQUIRED_PLACEHOLDERS) == set(STAGE_LABELS)
    assert REQUIRED_PLACEHOLDERS == {
        "select_table": ("request_text", "source_name", "tables", "categories"),
        "generate_rule": ("request_text", "table", "fields"),
        "generate_sql": ("request_text", "table", "fields"),
    }
    for stage, template in DEFAULT_PROMPTS.items():
        for name in REQUIRED_PLACEHOLDERS[stage]:
            assert "{" + name + "}" in template


def test_select_contract_example_is_parseable_and_matches_service_fields() -> None:
    blocks = _fenced_json_blocks(SELECT_OUTPUT_CONTRACT)
    assert blocks, "SELECT_OUTPUT_CONTRACT 必须包含 JSON 示例"
    example = json.loads(blocks[0])
    # 服务层从 target.table 与顶层 report_category 读取，示例必须与接口字段位置一致。
    assert set(example["target"]) == {"table"}
    assert isinstance(example["target"]["table"], str) and example["target"]["table"]
    assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", example["target"]["table"])
    assert isinstance(example["report_category"], str) and example["report_category"]
    assert "report_category" not in example["target"]
    assert _is_string_array(example["uncertainties"])
    assert _is_string_array(example["unsupported_requirements"])


def test_select_contract_keeps_uncertainty_and_empty_target_handling() -> None:
    text = SELECT_OUTPUT_CONTRACT
    assert "uncertainties" in text and "unsupported_requirements" in text
    assert "字符串数组" in text
    assert "空对象" in text and "不得强行" in text
    assert "交由服务端返回待澄清结果" in text
    assert "空字符串" in text and "不得强行选择分类" in text
    assert "待分析数据" in text
    assert "report_category" in text and "编码" in text
    assert "generate_sql" not in text


def test_rule_contract_examples_cover_violation_condition_mappings() -> None:
    blocks = _fenced_json_blocks(RULE_OUTPUT_CONTRACT)
    assert len(blocks) >= 3, "规则契约应给出常量与字段比较的真实 JSON 示例"
    examples = [json.loads(block) for block in blocks]
    for example in examples:
        assert example["rule_type"] == "field_compare"
        assert set(example["expression"]) == {"left", "op", "right_type", "right"}
        assert isinstance(example["expression"]["left"], str) and example["expression"]["left"]
        assert example["expression"]["op"] in {"lt", "lte", "gt", "gte", "eq", "neq"}
        assert _is_string_array(example["uncertainties"])
        assert _is_string_array(example["unsupported_requirements"])
        assert "sql" not in example
    shapes = {(item["expression"]["op"], item["expression"]["right_type"]): item for item in examples}
    # 违规条件映射：不得为0 -> eq 0；不得小于0 -> lt 0；到期日不得早于发放日 -> lt 字段。
    assert shapes[("eq", "value")]["expression"]["right"] == 0
    assert shapes[("lt", "value")]["expression"]["right"] == 0
    assert shapes[("lt", "field")]["expression"]["right"] == "issue_date"
    for item in examples:
        right = item["expression"]["right"]
        if item["expression"]["right_type"] == "value":
            assert type(right) in (int, float) and math.isfinite(right)
        else:
            assert isinstance(right, str) and right


def test_rule_contract_semantics_cover_unsupported_and_unresolved_policies() -> None:
    text = RULE_OUTPUT_CONTRACT
    assert "field_compare" in text
    assert "right_type=value" in text and "right_type=field" in text
    assert "违规" in text and "正常条件" in text
    for word in ("存续", "一般", "通常", "除外"):
        assert word in text
    assert "unsupported_requirements" in text and "字符串数组" in text
    assert "uncertainties" in text
    # 二元仍只贯通skip；一元完整性检查单独支持violate，不能再把非空判为不支持。
    assert "skip" in text and "unresolved" in text
    assert "violate" in text and "二元比较" in text and "一元" in text
    assert "is_null" in text and "is_not_null" in text
    assert "empty_string_as_null" not in text
    assert "filters" in text and "relationship_confirmed:false" in text
    assert "两表" in SELECT_OUTPUT_CONTRACT and "related_target" in SELECT_OUTPUT_CONTRACT
    assert "null_policy=review" in text and "缺值待核实" in text and "空串视为空值" in text
    # 完全无法形成当前表达式时允许 null + 空 expression，但必须带未解决事项。
    assert "rule_type 必须为 field_compare" not in text
    assert "rule_type 为 null" in text and "expression 为空对象" in text and "非空" in text
    assert "近似替换" in text and "禁止猜单位" in text
    assert "待分析数据" in text
    assert "SQL" in text and "不得" in text
    for word in ("名称", "类型", "含义", "单位", "取数逻辑"):
        assert word in text


def test_contracts_are_appendable_without_placeholder_collision() -> None:
    for contract in (SELECT_OUTPUT_CONTRACT, RULE_OUTPUT_CONTRACT):
        for name in ("request_text", "source_name", "tables", "categories", "table", "fields"):
            assert "{" + name + "}" not in contract


def test_contracts_are_not_baked_into_default_templates() -> None:
    assert SELECT_OUTPUT_CONTRACT not in DEFAULT_PROMPTS["select_table"]
    assert RULE_OUTPUT_CONTRACT not in DEFAULT_PROMPTS["generate_rule"]


def test_old_custom_template_intent_preserved() -> None:
    """旧意图：自定义模板可保存并替换默认模板，缺占位符仍被拒绝，重置恢复默认。"""
    from auto_check.modules.data_validation.contracts import AppError
    from tests.modules.data_validation.support import service, user

    _database, rules = service()
    prompts = rules.list_prompts()
    assert [item["stage"] for item in prompts] == ["select_table", "generate_rule", "generate_sql"]
    assert all(item["is_default"] for item in prompts)

    custom = "需求：{request_text} 数据源：{source_name} 表：{tables} 分类：{categories} 自定义"
    saved = rules.save_prompt(user(), "select_table", custom)
    assert saved["version_no"] == 1
    assert rules.list_prompts()[0]["content"] == custom

    with pytest.raises(AppError):
        rules.save_prompt(user(), "select_table", "缺少变量")

    reset = rules.reset_prompt(user(), "select_table")
    assert reset["version_no"] == 2
    assert rules.list_prompts()[0]["is_default"] is False
    assert rules.list_prompts()[0]["content"] == DEFAULT_PROMPTS["select_table"]
