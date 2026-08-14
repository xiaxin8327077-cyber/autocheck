import os
import re
import subprocess
import sys
from pathlib import Path

from auto_check.db_validation.rules import basic
from auto_check.package_smoke import run_package_smoke


ROOT = Path(__file__).resolve().parents[1]


def test_package_smoke_loads_dynamic_module_assets_migrations_and_resources() -> None:
    result = run_package_smoke()

    assert result["module_id"] == "report_special_processing"
    assert result["schema_version"] == 3
    assert result["migration_versions"] == [1, 2, 3]
    assert result["frontend_entry"] == "web/index.js"
    assert result["resource_files"] == ["FileName.xlsx", "RefInfo.xlsx"]
    assert result["status"] == "ok"


def test_basic_rules_import_does_not_require_runtime_source_code() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import inspect; "
            "inspect.getsource=lambda *args, **kwargs: (_ for _ in ()).throw(OSError('no source')); "
            "import auto_check.db_validation.rules.basic",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_required_chinese_field_snapshot_matches_rule_source() -> None:
    source = Path(basic.__file__).read_text(encoding="utf-8")
    field_pattern = re.compile(
        r'(?:_row_text|_row_value|_row_has_any|_first_text)\('
        r'[^)]*?"([\u4e00-\u9fff][\u4e00-\u9fff\w（）()]{1,20})"'
    )
    extracted = frozenset(
        match.group(1)
        for match in field_pattern.finditer(source)
        if "_" not in match.group(1) and match.group(1) not in {"中文名", "指标名称"}
    )

    assert basic.REQUIRED_CHINESE_FIELDS == extracted
