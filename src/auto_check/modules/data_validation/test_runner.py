"""配置型规则在进程内用样本行计算，不连接业务库。

旧扁平样本与求值语义由 ``query_samples`` 保留；新 filters/join 规格使用嵌套
关系样本。本模块保留历史导出名，供 service 与测试继续使用。
"""

from __future__ import annotations

from typing import Any

from .query_samples import default_cases, evaluate_case as _evaluate_case

__all__ = ["default_field_compare_cases", "evaluate_case"]


def default_field_compare_cases(
    definition: dict[str, Any],
    columns: list[dict[str, Any]] | None = None,
    related_columns: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """兼容旧调用；新规格自动改用嵌套关系样本。"""
    return default_cases(definition, columns, related_columns)


def evaluate_case(definition: dict[str, Any], row: dict[str, Any]) -> int:
    return _evaluate_case(definition, row)
