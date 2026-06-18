# Db Validation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working version of the asset-management row-level database validation engine in `auto_check`.

**Architecture:** Add an isolated `auto_check.db_validation` package for table metadata, database reading, rule execution, and Excel output. Integrate it into the existing local HTTP server with background jobs and a small tools-page UI, reusing `ConfigStore`, `DatabaseClient`, and current frontend patterns.

**Tech Stack:** Python 3.12, stdlib `dataclasses`/`threading`, `psycopg`, `PyMySQL`, `openpyxl`, existing static HTML/CSS/JS, pytest.

---

## File Structure

- Create `src/auto_check/db_validation/__init__.py`: package marker and version export.
- Create `src/auto_check/db_validation/config.py`: settings dataclasses, default field metadata source, source selection helpers.
- Create `src/auto_check/db_validation/tables.py`: 13 ZG table constants, report-period calculation, previous table suffix generation.
- Create `src/auto_check/db_validation/metadata.py`: field metadata loading from `xt_reg_table_baseinfo` and `xt_reg_table_field_info`.
- Create `src/auto_check/db_validation/reader.py`: database table loading through `DatabaseClient`.
- Create `src/auto_check/db_validation/models.py`: result rows, run summary, rule errors, job payload model helpers.
- Create `src/auto_check/db_validation/excel.py`: old-program-compatible Excel writer.
- Create `src/auto_check/db_validation/rules/common.py`: value normalization, decimal/date helpers, code/area predicates.
- Create `src/auto_check/db_validation/rules/basic.py`: first-pass high-confidence row rules and cross-period rules.
- Create `src/auto_check/db_validation/engine.py`: orchestration from selected sources to Excel output.
- Modify `src/auto_check/app/config.py`: persist `db_validation` settings in `ConfigStore`.
- Modify `src/auto_check/app/server.py`: add DB validation settings, job, status, and download APIs.
- Modify `src/auto_check/web/index.html`: add tools card/modal and settings fields.
- Modify `src/auto_check/web/app.js`: add DB validation modal flow, polling, and download.
- Modify `src/auto_check/web/styles.css`: minimal styling for the new modal and tool card.
- Create tests:
  - `tests/test_db_validation_config.py`
  - `tests/test_db_validation_tables.py`
  - `tests/test_db_validation_metadata.py`
  - `tests/test_db_validation_excel.py`
  - `tests/test_db_validation_engine.py`
  - Extend `tests/test_server.py`
  - Extend `tests/test_web_static.py`

## Task 1: Persist DB Validation Settings

**Files:**
- Modify: `src/auto_check/app/config.py`
- Test: `tests/test_db_validation_config.py`

- [ ] **Step 1: Write failing config persistence tests**

Create `tests/test_db_validation_config.py`:

```python
from auto_check.app.config import (
    ConfigStore,
    DbValidationSettings,
    save_store,
    load_store,
)


def test_store_persists_db_validation_settings(tmp_path):
    path = tmp_path / "config.json"
    store = ConfigStore(
        db_validation=DbValidationSettings(
            metadata_config_name="local",
            metadata_source="business",
            baseinfo_table="meta.xt_reg_table_baseinfo",
            field_info_table="meta.xt_reg_table_field_info",
        )
    )

    save_store(store, path)
    loaded = load_store(path)

    assert loaded.db_validation == store.db_validation


def test_db_validation_settings_defaults_are_usable():
    settings = ConfigStore().db_validation

    assert settings.metadata_config_name == ""
    assert settings.metadata_source == "dws"
    assert settings.baseinfo_table == "test.xt_reg_table_baseinfo"
    assert settings.field_info_table == "test.xt_reg_table_field_info"
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_db_validation_config.py -q
```

Expected: import failure for `DbValidationSettings`.

- [ ] **Step 3: Implement settings dataclass and JSON conversion**

In `src/auto_check/app/config.py`, add:

```python
@dataclass(frozen=True)
class DbValidationSettings:
    metadata_config_name: str = ""
    metadata_source: str = "dws"
    baseinfo_table: str = "test.xt_reg_table_baseinfo"
    field_info_table: str = "test.xt_reg_table_field_info"
```

Extend `ConfigStore`:

```python
@dataclass
class ConfigStore:
    configs: list[NamedConfig] = field(default_factory=list)
    default_name: str = ""
    default_settings: DefaultSettings = field(default_factory=DefaultSettings)
    pbc_import_tool: PbcImportToolSettings = field(default_factory=PbcImportToolSettings)
    db_validation: DbValidationSettings = field(default_factory=DbValidationSettings)
```

Add converters:

```python
def db_validation_settings_from_dict(payload: dict[str, Any]) -> DbValidationSettings:
    payload = payload or {}
    source = str(payload.get("metadata_source", "dws") or "dws").strip()
    if source not in {"dws", "business"}:
        source = "dws"
    return DbValidationSettings(
        metadata_config_name=str(payload.get("metadata_config_name", "") or ""),
        metadata_source=source,
        baseinfo_table=str(payload.get("baseinfo_table", "test.xt_reg_table_baseinfo") or "test.xt_reg_table_baseinfo"),
        field_info_table=str(payload.get("field_info_table", "test.xt_reg_table_field_info") or "test.xt_reg_table_field_info"),
    )


def db_validation_settings_to_dict(settings: DbValidationSettings) -> dict[str, Any]:
    return asdict(settings)
```

Update `load_store()` return value to pass `db_validation=db_validation_settings_from_dict(payload.get("db_validation", {}))`.

Update `save_store()` payload to include `"db_validation": db_validation_settings_to_dict(store.db_validation)`.

- [ ] **Step 4: Run config tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_db_validation_config.py tests/test_config.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/auto_check/app/config.py tests/test_db_validation_config.py
git commit -m "feat: add db validation settings"
```

## Task 2: Table Mapping and Report Period Helpers

**Files:**
- Create: `src/auto_check/db_validation/__init__.py`
- Create: `src/auto_check/db_validation/tables.py`
- Test: `tests/test_db_validation_tables.py`

- [ ] **Step 1: Write failing table helper tests**

Create `tests/test_db_validation_tables.py`:

```python
from datetime import date

from auto_check.db_validation.tables import (
    ZG_TABLES,
    default_report_date,
    previous_period,
    previous_table_name,
    report_date_token,
)


def test_zg_table_mapping_contains_13_tables():
    assert len(ZG_TABLES) == 13
    assert ZG_TABLES["ZG01"] == "zgxgzh_baseinfo_zg01_26"
    assert ZG_TABLES["ZG13"] == "zgzgzh_zg13"


def test_default_report_date_is_previous_month_end():
    assert default_report_date(date(2026, 6, 5)).isoformat() == "2026-05-31"


def test_previous_period_and_table_suffix():
    current = date(2026, 5, 31)

    assert previous_period(current).isoformat() == "2026-04-30"
    assert previous_table_name("zgxgzh_projholdinfo_zg04", current) == "zgxgzh_projholdinfo_zg04_2026_04"
    assert report_date_token(current) == "20260531"
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_db_validation_tables.py -q
```

Expected: import failure for `auto_check.db_validation`.

- [ ] **Step 3: Implement table helpers**

Create `src/auto_check/db_validation/__init__.py`:

```python
VERSION = "Ver.20260202"
```

Create `src/auto_check/db_validation/tables.py`:

```python
from __future__ import annotations

from calendar import monthrange
from datetime import date


ZG_TABLES: dict[str, str] = {
    "ZG01": "zgxgzh_baseinfo_zg01_26",
    "ZG02": "zgxgzh_begraiseinfo_zg02_26",
    "ZG03": "zgxgzh_projendinfo_zg03_26",
    "ZG04": "zgxgzh_projholdinfo_zg04",
    "ZG05": "zgxgzh_projdebt_zg05_2024",
    "ZG06": "zgxgzh_beneficial_zg06",
    "ZG07": "zgxgzh_ioudetail_zg07",
    "ZG08": "zgxgzh_spvdetail_zg08",
    "ZG09": "zgxgzh_debtordate_zg09",
    "ZG10": "zgxgzh_surecinfo_zg10",
    "ZG11": "zgxgzh_industinfo_zg11",
    "ZG12": "zgzgzh_zg12",
    "ZG13": "zgzgzh_zg13",
}


def month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def shift_month(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year = month_index // 12
    month = month_index % 12 + 1
    return month_end(year, month)


def default_report_date(today: date) -> date:
    return shift_month(today.replace(day=1), -1)


def previous_period(report_date: date) -> date:
    return shift_month(report_date.replace(day=1), -1)


def previous_suffix(report_date: date) -> str:
    prev = previous_period(report_date)
    return f"_{prev.year:04d}_{prev.month:02d}"


def previous_table_name(base_table: str, report_date: date) -> str:
    return f"{base_table}{previous_suffix(report_date)}"


def report_date_token(report_date: date) -> str:
    return report_date.strftime("%Y%m%d")
```

- [ ] **Step 4: Run tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_db_validation_tables.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/auto_check/db_validation/__init__.py src/auto_check/db_validation/tables.py tests/test_db_validation_tables.py
git commit -m "feat: add db validation table helpers"
```

## Task 3: Field Metadata Loader

**Files:**
- Create: `src/auto_check/db_validation/metadata.py`
- Test: `tests/test_db_validation_metadata.py`

- [ ] **Step 1: Write failing metadata tests**

Create `tests/test_db_validation_metadata.py`:

```python
from auto_check.db_validation.metadata import FieldMetadataLoader


class FakeClient:
    def __init__(self):
        self.calls = []

    def fetch_all(self, sql, params=()):
        self.calls.append((sql, params))
        if "xt_reg_table_baseinfo" in sql:
            return [{"id": "t1", "table_name_en": "zgxgzh_baseinfo_zg01_26"}]
        if "xt_reg_table_field_info" in sql:
            return [
                {"table_id": "t1", "field_propert": "projcode", "field_name": "产品代码", "sort": "1"},
                {"table_id": "t1", "field_propert": "projname", "field_name": "产品名称", "sort": "2"},
            ]
        return []


def test_metadata_loader_maps_chinese_names_to_english_fields():
    loader = FieldMetadataLoader(FakeClient(), "test.xt_reg_table_baseinfo", "test.xt_reg_table_field_info")

    catalog = loader.load()

    assert catalog.field_for("zgxgzh_baseinfo_zg01_26", "产品代码") == "projcode"
    assert catalog.field_for("zgxgzh_baseinfo_zg01_26", "产品名称") == "projname"


def test_metadata_loader_reports_missing_field():
    loader = FieldMetadataLoader(FakeClient(), "test.xt_reg_table_baseinfo", "test.xt_reg_table_field_info")
    catalog = loader.load()

    try:
        catalog.field_for("zgxgzh_baseinfo_zg01_26", "不存在")
    except KeyError as exc:
        assert "zgxgzh_baseinfo_zg01_26.不存在" in str(exc)
    else:
        raise AssertionError("expected missing field KeyError")
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_db_validation_metadata.py -q
```

Expected: import failure.

- [ ] **Step 3: Implement metadata loader**

Create `src/auto_check/db_validation/metadata.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from auto_check.app.pbc_import import parse_table_ref


@dataclass(frozen=True)
class TableFieldCatalog:
    by_table: dict[str, dict[str, str]]

    def field_for(self, table_name: str, chinese_name: str) -> str:
        try:
            return self.by_table[table_name][chinese_name]
        except KeyError as exc:
            raise KeyError(f"{table_name}.{chinese_name}") from exc

    def fields_for_table(self, table_name: str) -> dict[str, str]:
        if table_name not in self.by_table:
            raise KeyError(table_name)
        return dict(self.by_table[table_name])


class FieldMetadataLoader:
    def __init__(self, client: Any, baseinfo_table: str, field_info_table: str):
        self.client = client
        self.baseinfo_table = parse_table_ref(baseinfo_table)
        self.field_info_table = parse_table_ref(field_info_table)

    def load(self) -> TableFieldCatalog:
        db_type = self.client.config.db_type if hasattr(self.client, "config") else "postgresql"
        baseinfo_sql = (
            f"SELECT id, table_name_en FROM {self.baseinfo_table.quoted(db_type)} "
            "WHERE COALESCE(table_name_en, '') <> ''"
        )
        field_sql = (
            f"SELECT table_id, field_propert, field_name, sort FROM {self.field_info_table.quoted(db_type)} "
            "WHERE COALESCE(field_propert, '') <> '' AND COALESCE(field_name, '') <> '' "
            "ORDER BY table_id, CAST(sort AS INTEGER)"
        )
        base_rows = self.client.fetch_all(baseinfo_sql)
        field_rows = self.client.fetch_all(field_sql)
        id_to_table = {str(row["id"]): str(row["table_name_en"]) for row in base_rows}
        by_table: dict[str, dict[str, str]] = {}
        for row in field_rows:
            table_name = id_to_table.get(str(row.get("table_id", "")))
            if not table_name:
                continue
            by_table.setdefault(table_name, {})[str(row["field_name"])] = str(row["field_propert"])
        return TableFieldCatalog(by_table=by_table)
```

- [ ] **Step 4: Run metadata tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_db_validation_metadata.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/auto_check/db_validation/metadata.py tests/test_db_validation_metadata.py
git commit -m "feat: load db validation field metadata"
```

## Task 4: Models and Excel Writer

**Files:**
- Create: `src/auto_check/db_validation/models.py`
- Create: `src/auto_check/db_validation/excel.py`
- Test: `tests/test_db_validation_excel.py`

- [ ] **Step 1: Write failing Excel tests**

Create `tests/test_db_validation_excel.py`:

```python
from datetime import date

from openpyxl import load_workbook

from auto_check.db_validation.excel import write_result_excel, result_filename
from auto_check.db_validation.models import ValidationResultRow


def test_excel_writer_matches_old_result_structure(tmp_path):
    path = tmp_path / "result.xlsx"
    rows = [
        ValidationResultRow(
            data_date="2026-05-31",
            org_code="D1003632000013",
            org_name="江苏省国际信托有限责任公司",
            manager_org="南京",
            detail="产品代码:P1",
            form="资管产品基本信息校验",
            value1="产品名称:X",
            value2="",
            mark="20260531-D1003632000013-ZG01-Zg01_Rule6",
            rule="Zg01_Rule6:产品名称长度小于等于5个字，有特殊符号，需核实",
            error="产品名称过于简单，含有特殊字符（？、！、^），需核实",
            note="",
        )
    ]

    write_result_excel(path, rows)
    wb = load_workbook(path)
    ws = wb.active

    assert wb.sheetnames == ["Sheet1"]
    assert [ws.cell(1, c).value for c in range(1, 13)] == [
        "数据日期", "金融机构编码", "法人金融机构名称", "数据管理机构", "明细数据相关信息", "校验表单",
        "数据值1", "数据值2", "校验标识", "校验规则", "错误描述", "情况说明",
    ]
    assert ws.cell(2, 9).value == "20260531-D1003632000013-ZG01-Zg01_Rule6"
    assert ws.freeze_panes is None
    assert ws.auto_filter.ref is None


def test_result_filename_uses_old_program_format():
    assert result_filename(date(2026, 5, 31)) == (
        "20260531-资管产品数据审核结果-模板校验（否）-公开信息校验（否）(Ver.20260202).xlsx"
    )
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_db_validation_excel.py -q
```

Expected: import failure.

- [ ] **Step 3: Implement result model and Excel writer**

Create `src/auto_check/db_validation/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class ValidationResultRow:
    data_date: str
    org_code: str
    org_name: str
    manager_org: str
    detail: str
    form: str
    value1: str
    value2: str
    mark: str
    rule: str
    error: str = ""
    note: str = ""

    def to_excel_row(self) -> list[str]:
        return [
            self.data_date,
            self.org_code,
            self.org_name,
            self.manager_org,
            self.detail,
            self.form,
            self.value1,
            self.value2,
            self.mark,
            self.rule,
            self.error,
            self.note,
        ]

    def to_payload(self) -> dict[str, str]:
        return asdict(self)
```

Create `src/auto_check/db_validation/excel.py`:

```python
from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from auto_check.db_validation import VERSION
from auto_check.db_validation.models import ValidationResultRow
from auto_check.db_validation.tables import report_date_token


HEADERS = [
    "数据日期", "金融机构编码", "法人金融机构名称", "数据管理机构", "明细数据相关信息", "校验表单",
    "数据值1", "数据值2", "校验标识", "校验规则", "错误描述", "情况说明",
]


def result_filename(report_date: date) -> str:
    return f"{report_date_token(report_date)}-资管产品数据审核结果-模板校验（否）-公开信息校验（否）({VERSION}).xlsx"


def write_result_excel(path: str | Path, rows: list[ValidationResultRow]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for column in range(1, len(HEADERS) + 1):
        ws.column_dimensions[ws.cell(1, column).column_letter].width = 13
    for row in rows:
        ws.append(row.to_excel_row())
    wb.save(output)
    return output
```

- [ ] **Step 4: Run Excel tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_db_validation_excel.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/auto_check/db_validation/models.py src/auto_check/db_validation/excel.py tests/test_db_validation_excel.py
git commit -m "feat: write db validation excel results"
```

## Task 5: Database Reader and Engine Skeleton

**Files:**
- Create: `src/auto_check/db_validation/reader.py`
- Create: `src/auto_check/db_validation/engine.py`
- Test: `tests/test_db_validation_engine.py`

- [ ] **Step 1: Write failing engine skeleton tests**

Create `tests/test_db_validation_engine.py`:

```python
from datetime import date

from auto_check.db_validation.engine import DbValidationEngine


class FakeClient:
    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table
        self.config = type("Config", (), {"db_type": "postgresql"})()

    def fetch_all(self, sql, params=()):
        if "xt_reg_table_baseinfo" in sql:
            return [{"id": "t1", "table_name_en": "zgxgzh_baseinfo_zg01_26"}]
        if "xt_reg_table_field_info" in sql:
            return [
                {"table_id": "t1", "field_propert": "projcode", "field_name": "产品代码", "sort": "1"},
                {"table_id": "t1", "field_propert": "projname", "field_name": "产品名称", "sort": "2"},
                {"table_id": "t1", "field_propert": "issuername", "field_name": "发行机构名称", "sort": "3"},
            ]
        for table, rows in self.rows_by_table.items():
            if table in sql:
                return rows
        return []


def test_engine_generates_empty_excel_when_no_rows(tmp_path):
    client = FakeClient({})
    engine = DbValidationEngine(
        data_client=client,
        metadata_client=client,
        baseinfo_table="test.xt_reg_table_baseinfo",
        field_info_table="test.xt_reg_table_field_info",
        output_dir=tmp_path,
    )

    result = engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG01"])

    assert result.report_date == "2026-05-31"
    assert result.error_count == 0
    assert result.excel_path.exists()
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_db_validation_engine.py -q
```

Expected: import failure for `DbValidationEngine`.

- [ ] **Step 3: Implement reader and engine skeleton**

Create `src/auto_check/db_validation/reader.py`:

```python
from __future__ import annotations

from typing import Any

from auto_check.app.pbc_import import parse_table_ref


class ValidationTableReader:
    def __init__(self, client: Any):
        self.client = client

    def fetch_table(self, table_name: str) -> list[dict[str, Any]]:
        table = parse_table_ref(table_name)
        db_type = self.client.config.db_type
        return self.client.fetch_all(f"SELECT * FROM {table.quoted(db_type)}")
```

Extend `src/auto_check/db_validation/models.py`:

```python
from pathlib import Path


@dataclass(frozen=True)
class DbValidationRunResult:
    report_date: str
    error_count: int
    excel_path: Path
    rows: list[ValidationResultRow]
    warnings: list[str]
```

Create `src/auto_check/db_validation/engine.py`:

```python
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable, Any

from auto_check.db_validation.excel import result_filename, write_result_excel
from auto_check.db_validation.metadata import FieldMetadataLoader
from auto_check.db_validation.models import DbValidationRunResult, ValidationResultRow
from auto_check.db_validation.reader import ValidationTableReader
from auto_check.db_validation.tables import ZG_TABLES, previous_table_name


ProgressLogger = Callable[[str, int | None, str | None], None]


class DbValidationEngine:
    def __init__(
        self,
        *,
        data_client: Any,
        metadata_client: Any,
        baseinfo_table: str,
        field_info_table: str,
        output_dir: str | Path,
    ):
        self.data_reader = ValidationTableReader(data_client)
        self.metadata_loader = FieldMetadataLoader(metadata_client, baseinfo_table, field_info_table)
        self.output_dir = Path(output_dir)

    def run(
        self,
        *,
        report_date: date,
        selected_tables: list[str] | None = None,
        log: ProgressLogger | None = None,
    ) -> DbValidationRunResult:
        logger = log or (lambda message, progress=None, step=None: None)
        table_codes = selected_tables or list(ZG_TABLES)
        warnings: list[str] = []
        rows: list[ValidationResultRow] = []
        logger("加载字段匹配元数据", 5, "加载元数据")
        self.metadata_loader.load()
        for index, zg_code in enumerate(table_codes, start=1):
            base_table = ZG_TABLES[zg_code]
            prev_table = previous_table_name(base_table, report_date)
            progress = 10 + int(index / max(len(table_codes), 1) * 70)
            logger(f"读取 {zg_code} 当期表 {base_table}", progress, zg_code)
            current_rows = self.data_reader.fetch_table(base_table)
            try:
                self.data_reader.fetch_table(prev_table)
            except Exception:
                warnings.append(f"上期表缺失或不可读：{prev_table}")
            rows.extend([])
            if not current_rows:
                warnings.append(f"{zg_code} 当期表无数据：{base_table}")
        output_path = self.output_dir / result_filename(report_date)
        write_result_excel(output_path, rows)
        logger(f"生成结果文件：{output_path.name}", 100, "完成")
        return DbValidationRunResult(
            report_date=report_date.isoformat(),
            error_count=len(rows),
            excel_path=output_path,
            rows=rows,
            warnings=warnings,
        )
```

- [ ] **Step 4: Run engine skeleton tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_db_validation_engine.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/auto_check/db_validation/reader.py src/auto_check/db_validation/engine.py src/auto_check/db_validation/models.py tests/test_db_validation_engine.py
git commit -m "feat: add db validation engine skeleton"
```

## Task 6: First-Pass High-Confidence Rules

**Files:**
- Create: `src/auto_check/db_validation/rules/common.py`
- Create: `src/auto_check/db_validation/rules/basic.py`
- Modify: `src/auto_check/db_validation/engine.py`
- Test: `tests/test_db_validation_engine.py`

- [ ] **Step 1: Add failing tests for first rules**

Append to `tests/test_db_validation_engine.py`:

```python
def test_engine_runs_zg01_product_name_rule(tmp_path):
    client = FakeClient({
        "zgxgzh_baseinfo_zg01_26": [
            {
                "projcode": "D100362600001",
                "projname": "A?",
                "issuername": "江苏省国际信托有限责任公司",
            }
        ],
    })
    engine = DbValidationEngine(
        data_client=client,
        metadata_client=client,
        baseinfo_table="test.xt_reg_table_baseinfo",
        field_info_table="test.xt_reg_table_field_info",
        output_dir=tmp_path,
    )

    result = engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG01"])

    assert result.error_count == 1
    assert result.rows[0].mark.endswith("ZG01-Zg01_Rule6")
    assert "产品名称长度小于等于5个字" in result.rows[0].rule
```

- [ ] **Step 2: Run failing rule tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_db_validation_engine.py::test_engine_runs_zg01_product_name_rule -q
```

Expected: fails with zero result rows.

- [ ] **Step 3: Implement common helpers**

Create `src/auto_check/db_validation/rules/common.py`:

```python
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def is_blank(value: Any) -> bool:
    return text(value) == ""


def to_decimal(value: Any) -> Decimal:
    raw = text(value)
    if raw == "":
        return Decimal("0")
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return Decimal("0")


def has_value(value: Any) -> bool:
    return not is_blank(value) and to_decimal(value) != Decimal("0")


def percent_change_too_large(a: Any, b: Any, threshold: Decimal) -> bool:
    left = to_decimal(a)
    right = to_decimal(b)
    if right == 0:
        return left != 0
    return abs((left - right) / right) > threshold


def looks_bad_org_code(value: Any) -> bool:
    raw = text(value)
    return bool(raw) and len(raw) not in {14, 18}


def area_not_county_level(value: Any) -> bool:
    raw = text(value)
    return bool(raw) and raw != "000000" and (len(raw) != 6 or raw.endswith("00"))
```

- [ ] **Step 4: Implement basic rule runner**

Create `src/auto_check/db_validation/rules/basic.py`:

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from auto_check.db_validation.models import ValidationResultRow
from auto_check.db_validation.rules.common import area_not_county_level, has_value, is_blank, text, to_decimal
from auto_check.db_validation.tables import report_date_token


ORG_CODE = "D1003632000013"
ORG_NAME = "江苏省国际信托有限责任公司"
MANAGER_ORG = "南京"


def make_row(
    *,
    report_date: date,
    zg_code: str,
    rule_id: str,
    rule: str,
    form: str,
    detail: str,
    value1: str = "",
    value2: str = "",
    error: str = "",
    org_code: str = ORG_CODE,
    org_name: str = ORG_NAME,
    manager_org: str = MANAGER_ORG,
) -> ValidationResultRow:
    return ValidationResultRow(
        data_date=report_date.isoformat(),
        org_code=org_code,
        org_name=org_name,
        manager_org=manager_org,
        detail=detail,
        form=form,
        value1=value1,
        value2=value2,
        mark=f"{report_date_token(report_date)}-{org_code}-{zg_code}-{rule_id}",
        rule=rule,
        error=error,
        note="",
    )


def run_basic_rules(zg_code: str, report_date: date, current_rows: list[dict[str, Any]], previous_rows: list[dict[str, Any]]) -> list[ValidationResultRow]:
    if zg_code == "ZG01":
        return list(_zg01(report_date, current_rows))
    if zg_code == "ZG04":
        return list(_zg04(report_date, current_rows, previous_rows))
    if zg_code in {"ZG06", "ZG07", "ZG12", "ZG13"}:
        return list(_common_detail_rules(zg_code, report_date, current_rows))
    if zg_code == "ZG08":
        return list(_zg08(report_date, current_rows))
    return []


def _zg01(report_date: date, rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    for row in rows:
        projcode = text(row.get("projcode"))
        projname = text(row.get("projname"))
        if len(projname) <= 5 or any(symbol in projname for symbol in ["?", "？", "！", "!", "^"]):
            yield make_row(
                report_date=report_date,
                zg_code="ZG01",
                rule_id="Zg01_Rule6",
                form="资管产品基本信息校验",
                detail=f"产品代码_产品名称:{projcode}_{projname}",
                value1=f"产品名称:{projname}",
                rule="Zg01_Rule6:产品名称长度小于等于5个字，有特殊符号，需核实",
                error="产品名称过于简单，含有特殊字符（？、！、^），需核实",
            )


def _zg04(report_date: date, rows: list[dict[str, Any]], previous_rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    previous_by_key = {
        (text(r.get("projcode")), text(r.get("areacode")), text(r.get("clientkind")), text(r.get("moneytype"))): r
        for r in previous_rows
    }
    for row in rows:
        key = (text(row.get("projcode")), text(row.get("areacode")), text(row.get("clientkind")), text(row.get("moneytype")))
        prev = previous_by_key.get(key)
        if prev:
            expected_share = to_decimal(prev.get("endshares")) + to_decimal(row.get("curraiseshare")) - to_decimal(row.get("curcashshare"))
            actual_share = to_decimal(row.get("endshares"))
            if abs(actual_share - expected_share) > Decimal("0.01"):
                yield make_row(
                    report_date=report_date,
                    zg_code="ZG04",
                    rule_id="Zg04_Rule2",
                    form="资管产品存续期募集信息上下期校验",
                    detail="产品代码_地区_客户类型_币种_上期产品份额_当期申购份额_当期兑付/赎回份额_期末产品份额:"
                    f"{key[0]}_{key[1]}_{key[2]}_{key[3]}_{prev.get('endshares')}_{row.get('curraiseshare')}_{row.get('curcashshare')}_{row.get('endshares')}",
                    value1=f"期末产品份额:{row.get('endshares')}",
                    value2=f"份额跨期差值:{expected_share - actual_share}",
                    rule="Zg04_Rule2:产品份额比对不符合校验公式（当期期末产品份额=上期期末产品份额+当期申购份额-当期兑付份额），需核实",
                    error="产品份额比对不符合校验公式，需核实",
                )
        if has_value(row.get("currraiseamt")) != has_value(row.get("curraiseshare")):
            yield make_row(
                report_date=report_date,
                zg_code="ZG04",
                rule_id="Zg04_Rule10",
                form="资管产品存续期募集信息校验",
                detail=f"产品代码_地区_客户类型_币种:{key[0]}_{key[1]}_{key[2]}_{key[3]}",
                value1=f"当期申购金额:{row.get('currraiseamt')}",
                value2=f"当期申购份额:{row.get('curraiseshare')}",
                rule="Zg04_Rule10:当期申购金额与份额未同时有数，需核实",
            )


def _common_detail_rules(zg_code: str, report_date: date, rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    area_fields = {
        "ZG06": ["issuerareacode"],
        "ZG07": ["loanissuerareacode", "areacode"],
        "ZG12": ["areacode"],
        "ZG13": ["areacode"],
    }.get(zg_code, [])
    for row in rows:
        for field in area_fields:
            if area_not_county_level(row.get(field)):
                yield make_row(
                    report_date=report_date,
                    zg_code=zg_code,
                    rule_id=f"Zg{zg_code[-2:]}_Rule1",
                    form=f"{zg_code}明细信息校验",
                    detail=f"{field}:{row.get(field)}",
                    value1=f"{field}:{row.get(field)}",
                    rule=f"Zg{zg_code[-2:]}_Rule1:地区代码未填报到区县一级，需核实",
                )


def _zg08(report_date: date, rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    for row in rows:
        projcode = text(row.get("projcode"))
        riverprojcode = text(row.get("riverprojcode"))
        riverissuercode = text(row.get("riverissuercode"))
        if projcode and riverprojcode and projcode == riverprojcode:
            yield make_row(
                report_date=report_date,
                zg_code="ZG08",
                rule_id="Zg08_Rule12",
                form="特定目的载体交易对手明细信息校验",
                detail=f"产品代码_交易对手产品代码:{projcode}_{riverprojcode}",
                value1=f"交易对手产品代码:{riverprojcode}",
                rule="Zg08_Rule12:交易对手代码为自身产品代码，需核实",
            )
        if riverissuercode and riverprojcode and not riverprojcode.startswith(riverissuercode[:6]):
            yield make_row(
                report_date=report_date,
                zg_code="ZG08",
                rule_id="Zg08_Rule13",
                form="特定目的载体交易对手明细信息校验",
                detail=f"交易对手机构编码_交易对手产品代码:{riverissuercode}_{riverprojcode}",
                value1=f"交易对手机构编码:{riverissuercode}",
                value2=f"交易对手产品代码:{riverprojcode}",
                rule="Zg08_Rule13:交易对手机构编码与交易对手产品代码前6位不一致，需核实",
            )
```

Modify `DbValidationEngine.run()` to call `run_basic_rules(zg_code, report_date, current_rows, previous_rows)` and extend result rows.

- [ ] **Step 5: Run rule tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_db_validation_engine.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/auto_check/db_validation/rules src/auto_check/db_validation/engine.py tests/test_db_validation_engine.py
git commit -m "feat: add first db validation rules"
```

## Task 7: Server APIs and Background Job

**Files:**
- Modify: `src/auto_check/app/server.py`
- Test: extend `tests/test_server.py`

- [ ] **Step 1: Add failing API tests**

Append to `tests/test_server.py`:

```python
def test_db_validation_settings_api_persists(tmp_path):
    config_path = tmp_path / "config.json"
    router = ApiRouter(config_path=config_path)

    status, payload = router.handle("POST", "/api/db-validation/settings", {
        "metadata_config_name": "local",
        "metadata_source": "business",
        "baseinfo_table": "meta.xt_reg_table_baseinfo",
        "field_info_table": "meta.xt_reg_table_field_info",
    })

    assert status == 200
    assert payload["settings"]["metadata_config_name"] == "local"

    status, loaded = router.handle("GET", "/api/db-validation/settings", None)

    assert status == 200
    assert loaded["settings"]["metadata_source"] == "business"


def test_db_validation_configs_api_returns_existing_sources(tmp_path):
    config_path = tmp_path / "config.json"
    save_store(
        ConfigStore(
            configs=[
                NamedConfig(
                    name="local",
                    dws=DataSourceConfig("postgresql", "localhost", 5432, "dwdb", "dws", "u", "p"),
                    business=DataSourceConfig("mysql", "localhost", 3306, "bizdb", "", "u2", "p2"),
                    is_default=True,
                )
            ],
            default_name="local",
        ),
        config_path,
    )
    router = ApiRouter(config_path=config_path)

    status, payload = router.handle("GET", "/api/db-validation/configs", None)

    assert status == 200
    assert payload["data_sources"][0]["config_name"] == "local"
    assert payload["data_sources"][0]["source"] == "dws"
```

- [ ] **Step 2: Run failing API tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_server.py::test_db_validation_settings_api_persists tests/test_server.py::test_db_validation_configs_api_returns_existing_sources -q
```

Expected: status 404 for new endpoints.

- [ ] **Step 3: Implement settings and configs endpoints**

In `src/auto_check/app/server.py`, import settings converters:

```python
from auto_check.app.config import (
    DbValidationSettings,
    db_validation_settings_from_dict,
    db_validation_settings_to_dict,
)
```

Add routes near the PBC tools routes:

```python
if method == "GET" and path == "/api/db-validation/settings":
    store = load_store(self.config_path)
    return 200, {
        "settings": db_validation_settings_to_dict(store.db_validation),
        "data_sources": _pbc_import_data_sources(store),
    }

if method == "POST" and path == "/api/db-validation/settings":
    store = load_store(self.config_path)
    store.db_validation = db_validation_settings_from_dict(body or {})
    save_store(store, self.config_path)
    return 200, {"settings": db_validation_settings_to_dict(store.db_validation)}

if method == "GET" and path == "/api/db-validation/configs":
    store = load_store(self.config_path)
    return 200, {"data_sources": _pbc_import_data_sources(store)}
```

- [ ] **Step 4: Add job tests**

Append to `tests/test_server.py`:

```python
class FakeDbValidationRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        kwargs["log"]("生成结果文件", 100, "完成")
        output = kwargs["output_dir"] / "20260531-资管产品数据审核结果-模板校验（否）-公开信息校验（否）(Ver.20260202).xlsx"
        output.write_bytes(b"xlsx")
        return {
            "report_date": "2026-05-31",
            "error_count": 0,
            "excel_path": output,
            "warnings": [],
        }


def test_db_validation_job_runs_in_background(tmp_path):
    runner = FakeDbValidationRunner()
    router = ApiRouter(config_path=tmp_path / "config.json", db_validation_runner=runner)

    status, payload = router.handle("POST", "/api/db-validation/jobs", {
        "config_name": "",
        "source": "dws",
        "report_date": "2026-05-31",
    })

    assert status == 200
    job_id = payload["job_id"]
    for _ in range(20):
        status, payload = router.handle("GET", f"/api/db-validation/jobs/{job_id}", None)
        if payload["job"]["status"] == "completed":
            break
        time.sleep(0.05)

    assert payload["job"]["status"] == "completed"
    assert payload["job"]["error_count"] == 0
```

- [ ] **Step 5: Implement job class and runner wiring**

Modify `ApiRouter.__init__()` to accept `db_validation_runner: Callable[..., Any] | None = None`.

Add `_db_validation_jobs` and lock fields like PBC jobs.

Create `DbValidationJob` beside `PbcImportJob` with fields `id`, `report_date`, `status`, `progress`, `step`, `error_count`, `warnings`, `excel_path`, `logs`, `error`, timestamps, `thread`, and `to_payload()`.

Add `_start_db_validation_job()`, `_get_db_validation_job()`, and `_execute_db_validation_job()` methods using existing `threading.Thread(..., daemon=True)` pattern.

Default runner should build:

```python
engine = DbValidationEngine(
    data_client=DatabaseClient(data_source),
    metadata_client=DatabaseClient(metadata_source),
    baseinfo_table=store.db_validation.baseinfo_table,
    field_info_table=store.db_validation.field_info_table,
    output_dir=self.config_path.parent / "db-validation-results",
)
return engine.run(report_date=parsed_report_date, log=job.log)
```

- [ ] **Step 6: Run API tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_server.py -q
```

Expected: all server tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/auto_check/app/server.py tests/test_server.py
git commit -m "feat: add db validation APIs"
```

## Task 8: Download Endpoint

**Files:**
- Modify: `src/auto_check/app/server.py`
- Test: extend `tests/test_server.py`

- [ ] **Step 1: Add failing download tests**

Append to `tests/test_server.py`:

```python
def test_db_validation_job_payload_exposes_download_url(tmp_path):
    runner = FakeDbValidationRunner()
    router = ApiRouter(config_path=tmp_path / "config.json", db_validation_runner=runner)

    status, payload = router.handle("POST", "/api/db-validation/jobs", {"report_date": "2026-05-31"})
    job_id = payload["job_id"]
    for _ in range(20):
        status, payload = router.handle("GET", f"/api/db-validation/jobs/{job_id}", None)
        if payload["job"]["status"] == "completed":
            break
        time.sleep(0.05)

    assert payload["job"]["download_url"] == f"/api/db-validation/jobs/{job_id}/download"
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_server.py::test_db_validation_job_payload_exposes_download_url -q
```

Expected: missing `download_url`.

- [ ] **Step 3: Implement download metadata and handler**

Add `download_url` in `DbValidationJob.to_payload()` when `status == "completed"` and `excel_path` is set.

Add a `handle_db_validation_download(job_id)` method on `ApiRouter` returning `(status, path, filename)` or a small dict for testability.

In `AutoCheckRequestHandler.do_GET()`, before JSON API dispatch, route `/api/db-validation/jobs/<id>/download` to a binary response with:

```text
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename*=UTF-8''<quoted filename>
```

- [ ] **Step 4: Run download test and server tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_server.py -q
```

Expected: all server tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/auto_check/app/server.py tests/test_server.py
git commit -m "feat: add db validation result download"
```

## Task 9: Frontend Tool Entry

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Test: extend `tests/test_web_static.py`

- [ ] **Step 1: Add failing static tests**

Extend `tests/test_web_static.py` with checks:

```python
def test_db_validation_tool_markup_exists():
    html = (ROOT / "src" / "auto_check" / "web" / "index.html").read_text(encoding="utf-8")

    assert 'id="toolCardDbValidation"' in html
    assert 'id="dbValidationModalOverlay"' in html
    assert 'id="dbValidationDataSource"' in html
    assert 'id="dbValidationReportDate"' in html


def test_db_validation_frontend_calls_expected_apis():
    js = (ROOT / "src" / "auto_check" / "web" / "app.js").read_text(encoding="utf-8")

    assert "/api/db-validation/settings" in js
    assert "/api/db-validation/configs" in js
    assert "/api/db-validation/jobs" in js
```

- [ ] **Step 2: Run failing static tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_web_static.py::test_db_validation_tool_markup_exists tests/test_web_static.py::test_db_validation_frontend_calls_expected_apis -q
```

Expected: markup/API strings missing.

- [ ] **Step 3: Add modal markup**

In `index.html`, add a second tool card under `tools-grid`:

```html
<div class="tool-card tool-card-db-validation" id="toolCardDbValidation">
  <div class="tool-card-bar"></div>
  <div class="tool-card-content">
    <div class="tool-card-header">
      <div class="tool-card-icon">DB</div>
      <span class="tool-card-badge">新增</span>
    </div>
    <h3>资管逐笔数据库校验</h3>
    <p>从数据库读取逐笔表，生成旧格式审核结果 Excel。</p>
  </div>
</div>
```

Add modal fields:

```html
<div class="pbc-modal-overlay" id="dbValidationModalOverlay">
  <div class="pbc-modal">
    <button class="pbc-modal-close" id="dbValidationModalClose">&times;</button>
    <div class="pbc-modal-header">
      <div class="pbc-modal-header-left">
        <div class="pbc-modal-icon">DB</div>
        <div>
          <h3>资管逐笔数据库校验</h3>
          <p>选择数据源和报告期后执行校验。</p>
        </div>
      </div>
    </div>
    <div class="pbc-mapping-form">
      <label class="pbc-form-row">
        <span>逐笔数据源</span>
        <select id="dbValidationDataSource"></select>
      </label>
      <label class="pbc-form-row">
        <span>报告期</span>
        <input id="dbValidationReportDate" type="date" />
      </label>
      <label class="pbc-form-row">
        <span>字段映射来源</span>
        <select id="dbValidationMetadataSource"></select>
      </label>
      <label class="pbc-form-row">
        <span>表信息元数据表</span>
        <input id="dbValidationBaseinfoTable" placeholder="test.xt_reg_table_baseinfo" />
      </label>
      <label class="pbc-form-row">
        <span>字段元数据表</span>
        <input id="dbValidationFieldInfoTable" placeholder="test.xt_reg_table_field_info" />
      </label>
    </div>
    <div class="pbc-import-progress">
      <div class="pbc-progress-title" id="dbValidationProgressTitle">等待开始</div>
      <div class="pbc-progress-subtitle" id="dbValidationProgressSubtitle">请选择配置</div>
      <div class="pbc-progress-bar-track"><div class="pbc-progress-bar-fill" id="dbValidationProgressFill" style="width: 0%"></div></div>
      <div class="pbc-progress-percent" id="dbValidationProgressPercent">0%</div>
      <div id="dbValidationLog" class="pbc-import-log"></div>
    </div>
    <div class="pbc-modal-footer">
      <span class="modal-status" id="dbValidationStatus"></span>
      <button type="button" class="pbc-btn pbc-btn--outline" id="dbValidationSaveSettingsBtn">保存元数据设置</button>
      <button type="button" class="pbc-btn pbc-btn--primary" id="dbValidationStartBtn">开始校验</button>
      <a class="pbc-btn pbc-btn--success" id="dbValidationDownloadBtn" hidden>下载结果</a>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Add frontend JS**

In `app.js`, add DOM refs, state, and functions:

```javascript
const toolCardDbValidation = document.getElementById("toolCardDbValidation");
const dbValidationModalOverlay = document.getElementById("dbValidationModalOverlay");
const dbValidationModalClose = document.getElementById("dbValidationModalClose");
const dbValidationDataSource = document.getElementById("dbValidationDataSource");
const dbValidationMetadataSource = document.getElementById("dbValidationMetadataSource");
const dbValidationReportDate = document.getElementById("dbValidationReportDate");
const dbValidationBaseinfoTable = document.getElementById("dbValidationBaseinfoTable");
const dbValidationFieldInfoTable = document.getElementById("dbValidationFieldInfoTable");
const dbValidationSaveSettingsBtn = document.getElementById("dbValidationSaveSettingsBtn");
const dbValidationStartBtn = document.getElementById("dbValidationStartBtn");
const dbValidationDownloadBtn = document.getElementById("dbValidationDownloadBtn");
const dbValidationProgressFill = document.getElementById("dbValidationProgressFill");
const dbValidationProgressPercent = document.getElementById("dbValidationProgressPercent");
const dbValidationProgressTitle = document.getElementById("dbValidationProgressTitle");
const dbValidationProgressSubtitle = document.getElementById("dbValidationProgressSubtitle");
const dbValidationLog = document.getElementById("dbValidationLog");
const dbValidationStatus = document.getElementById("dbValidationStatus");
let dbValidationPollTimer = null;
```

Add API flow:

```javascript
function renderDbValidationSources(select, dataSources = [], selected = "") {
  if (!select) return;
  select.innerHTML = dataSources.map((item) => {
    const value = `${item.config_name}::${item.source}`;
    return `<option value="${escapeHtml(value)}">${escapeHtml(item.label)} (${escapeHtml(item.db_type)})</option>`;
  }).join("");
  if (selected) select.value = selected;
}

async function loadDbValidationSettings() {
  const [settingsPayload, configsPayload] = await Promise.all([
    api("/api/db-validation/settings"),
    api("/api/db-validation/configs"),
  ]);
  const settings = settingsPayload.settings || {};
  const sources = configsPayload.data_sources || [];
  renderDbValidationSources(dbValidationDataSource, sources);
  renderDbValidationSources(dbValidationMetadataSource, sources, `${settings.metadata_config_name || ""}::${settings.metadata_source || "dws"}`);
  if (dbValidationBaseinfoTable) dbValidationBaseinfoTable.value = settings.baseinfo_table || "test.xt_reg_table_baseinfo";
  if (dbValidationFieldInfoTable) dbValidationFieldInfoTable.value = settings.field_info_table || "test.xt_reg_table_field_info";
  if (dbValidationReportDate && !dbValidationReportDate.value) dbValidationReportDate.value = previousMonthEndDate();
}

function splitDbValidationSource(value) {
  const [configName, source] = String(value || "").split("::");
  return { config_name: configName || "", source: source || "dws" };
}

function appendDbValidationLog(message) {
  if (!dbValidationLog) return;
  const line = document.createElement("div");
  line.className = "pbc-log-entry";
  line.textContent = message;
  dbValidationLog.appendChild(line);
  dbValidationLog.scrollTop = dbValidationLog.scrollHeight;
}
```

Wire click handlers for open, close, save settings, start job, poll status, and download URL.

- [ ] **Step 5: Add minimal CSS**

Add styles to keep the new card/modal consistent with existing PBC modal:

```css
.tool-card-db-validation .tool-card-bar {
  background: #0f766e;
}

.tool-card-db-validation .tool-card-icon {
  background: #ecfdf5;
  color: #0f766e;
}
```

- [ ] **Step 6: Run static tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_web_static.py -q
```

Expected: all web static tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/auto_check/web/index.html src/auto_check/web/app.js src/auto_check/web/styles.css tests/test_web_static.py
git commit -m "feat: add db validation tool UI"
```

## Task 10: Local PostgreSQL Smoke Test

**Files:**
- No source files required unless test failures expose a bug.

- [ ] **Step 1: Run focused unit tests**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_db_validation_config.py tests/test_db_validation_tables.py tests/test_db_validation_metadata.py tests/test_db_validation_excel.py tests/test_db_validation_engine.py tests/test_server.py tests/test_web_static.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run a local engine smoke test against seeded PostgreSQL**

Run:

```powershell
@'
from datetime import date
from pathlib import Path
from auto_check.app.config import DataSourceConfig
from auto_check.app.db import DatabaseClient
from auto_check.db_validation.engine import DbValidationEngine

source = DataSourceConfig("postgresql", "127.0.0.1", 5432, "auto_check_test", "dws", "postgres", "postgres")
meta = DataSourceConfig("postgresql", "127.0.0.1", 5432, "auto_check_test", "test", "postgres", "postgres")
engine = DbValidationEngine(
    data_client=DatabaseClient(source),
    metadata_client=DatabaseClient(meta),
    baseinfo_table="test.xt_reg_table_baseinfo",
    field_info_table="test.xt_reg_table_field_info",
    output_dir=Path("config/db-validation-results"),
)
result = engine.run(report_date=date(2026, 5, 31))
print(result.error_count)
print(result.excel_path)
'@ | & 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -
```

Expected: prints an integer error count and an existing `.xlsx` path.

- [ ] **Step 3: Commit smoke-test fixes if needed**

If Step 2 finds a bug, fix it with the smallest scoped change and commit:

```powershell
git add src/auto_check/db_validation tests
git commit -m "fix: make db validation smoke test pass"
```

## Task 11: Full Verification and Packaging

**Files:**
- No source file expected.

- [ ] **Step 1: Run full test suite**

Per project preference, run this in a background/subagent thread if available:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Package Windows executable**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1
```

Expected: `dist/auto-check.exe` is refreshed.

- [ ] **Step 3: Run packaged app smoke check**

Run:

```powershell
& 'D:\xiaxin\auto_check\dist\auto-check.exe' --config D:\xiaxin\auto_check\config\local-pg-test-config.json --no-browser
```

Expected: server starts and prints the local URL. Stop it after confirming startup.

- [ ] **Step 4: Final status**

Collect:

- Last commit hash.
- Test command result.
- Package command result.
- Local smoke Excel path.

Report these in the final response.

## Self-Review

- Spec coverage: data source selection, metadata source setting, 13-table mapping, report-period suffix, Excel output, background job, MySQL/PostgreSQL abstraction, and local seeded PostgreSQL data are each represented by tasks.
- Scope choice: first implementation includes a running rule framework and high-confidence non-template/non-public rules. Template and public-information rules are excluded by confirmed scope.
- Placeholder scan: the plan contains no unresolved placeholder markers.
- Type consistency: settings, engine, result row, and API names match across tests and implementation steps.
