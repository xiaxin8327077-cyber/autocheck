# -*- coding: utf-8 -*-
"""防回退守卫：逐笔校验引擎不得重新引入生产业务物理表名等硬编码。

对应《人行逐笔校验引擎动态表与字段映射改造方案》实施约束：
逐笔、模板、公开信息物理表名只存在于应用数据库初始化 SQL（017_db_validation_mapping.sql）
与测试夹具中，程序运行代码不得直接引用。
"""
from pathlib import Path

import auto_check.db_validation as db_validation_package

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = Path(db_validation_package.__file__).resolve().parent

FORBIDDEN_PRODUCTION_TABLE_TOKENS = (
    "zgxgzh_",
    "zgzgzh_",
    "balance_sheet_info",
    "public_information_rh",
)


def _iter_package_python_sources():
    return sorted(path for path in PACKAGE_DIR.rglob("*.py") if "__pycache__" not in path.parts)


def test_db_validation_package_has_no_production_table_names():
    violations = []
    for path in _iter_package_python_sources():
        content = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_PRODUCTION_TABLE_TOKENS:
            if token in content:
                violations.append(f"{path.relative_to(PROJECT_ROOT)} 包含 {token}")

    assert violations == []


def test_db_validation_engine_has_no_public_info_table_fallback():
    from inspect import signature

    from auto_check.db_validation.engine import DbValidationEngine

    assert "public_info_table" not in signature(DbValidationEngine.__init__).parameters


def test_frontend_settings_do_not_carry_public_info_table_default():
    for relative in ("src/auto_check/web/app.js", "src/auto_check/web/index.html"):
        content = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert "public_information_rh" not in content, f"{relative} 仍包含公开信息物理表名兜底"
        assert "dbValidationPublicInfoTable" not in content, f"{relative} 仍保留公开信息表隐藏输入"
