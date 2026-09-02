from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Callable

from auto_check.db_validation.excel import result_filename, write_result_excel
from auto_check.db_validation.metadata import TableFieldCatalog
from auto_check.db_validation.models import DbValidationRunResult, ValidationResultRow
from auto_check.db_validation.reader import ValidationTableReader
from auto_check.db_validation.rules.basic import run_basic_rules
from auto_check.db_validation.tables import DETAIL_TABLE_DEPENDENCIES, ZG_CODES, previous_table_name


ProgressLogger = Callable[[str, int | None, str | None], None]


class DbValidationEngine:
    def __init__(
        self,
        *,
        data_client: Any,
        metadata_client: Any | None = None,
        output_dir: str | Path,
        public_info_client: Any | None = None,
        template_client: Any | None = None,
        field_catalog: TableFieldCatalog | None = None,
        baseinfo_table: str = "xt_reg_table_baseinfo",
        field_info_table: str = "xt_reg_table_field_info",
        detail_sys_manage_id: str = "",
        detail_classification_id: str = "",
        template_sys_manage_id: str = "",
        template_classification_id: str = "",
    ):
        self.data_reader = ValidationTableReader(data_client)
        self.public_info_reader = ValidationTableReader(public_info_client) if public_info_client is not None else None
        self.template_reader = ValidationTableReader(template_client) if template_client is not None else None
        self.metadata_client = metadata_client
        self.baseinfo_table = baseinfo_table
        self.template_sys_manage_ids = _split_semicolon_values(template_sys_manage_id)
        self.template_classification_ids = _split_semicolon_values(template_classification_id)
        self.field_catalog = field_catalog or TableFieldCatalog({})
        self.output_dir = Path(output_dir)

    def run(
        self,
        *,
        report_date: date,
        selected_tables: list[str] | None = None,
        enable_public_info_check: bool = False,
        enable_template_check: bool = False,
        log: ProgressLogger | None = None,
    ) -> DbValidationRunResult:
        logger = log or (lambda message, progress=None, step=None: None)
        table_codes = selected_tables or list(ZG_CODES)
        warnings: list[str] = []
        rows: list[ValidationResultRow] = []
        current_rows_by_code: dict[str, list[dict[str, Any]]] = {}
        public_info_rows: list[dict[str, Any]] = []
        template_rows_by_code = self._template_rows_by_code(table_codes, enable_template_check, logger, warnings)

        field_catalog = self.field_catalog
        if enable_public_info_check:
            if self.public_info_reader is None:
                warnings.append("公开信息数据源未配置，已跳过公开信息校验")
            else:
                logger("读取公开信息表", 8, "公开信息")
                try:
                    public_table = _mapped_table(field_catalog, "public_info", "PUBLIC_INFO")
                except KeyError:
                    raise RuntimeError(
                        "公开信息物理表映射缺失，请先在系统设置刷新字段映射或人工维护映射关系后再执行"
                    )
                try:
                    public_info_rows = _apply_field_aliases(
                        self.public_info_reader.fetch_table(public_table),
                        public_table,
                        field_catalog,
                    )
                except Exception as exc:
                    warnings.append(f"公开信息表缺失或不可读（{exc}）")
        for index, zg_code in enumerate(table_codes, start=1):
            base_table = _mapped_table(field_catalog, "detail", zg_code, fallback="")
            prev_table = previous_table_name(base_table, report_date)
            progress = 10 + int(index / max(len(table_codes), 1) * 70)
            if zg_code in current_rows_by_code:
                logger(f"复用 {zg_code} 当期表 {base_table}", progress, zg_code)
            else:
                logger(f"读取 {zg_code} 当期表 {base_table}", progress, zg_code)
            current_rows = self._current_rows_for(zg_code, current_rows_by_code, field_catalog)
            previous_rows: list[dict[str, Any]] = []
            try:
                previous_rows = _apply_field_aliases(
                    self.data_reader.fetch_table(prev_table, self._decrypt_column_for(zg_code, base_table)),
                    base_table,
                    field_catalog,
                )
            except Exception:
                warnings.append(f"上期表缺失或不可读：{prev_table}")
            if not current_rows:
                warnings.append(f"{zg_code} 当期表无数据：{base_table}")
            rows.extend(
                run_basic_rules(
                    zg_code,
                    report_date,
                    current_rows,
                    previous_rows,
                    related_rows=self._related_rows_for(
                        zg_code,
                        current_rows_by_code,
                        public_info_rows,
                        field_catalog,
                        template_rows_by_code,
                    ),
                    enable_template_check=enable_template_check,
                    field_catalog=field_catalog,
                    table_name=base_table,
                )
            )

        output_path = self.output_dir / result_filename(
            report_date,
            enable_public_info_check=enable_public_info_check,
            enable_template_check=enable_template_check,
        )
        write_result_excel(output_path, rows)
        logger(f"生成结果文件：{output_path.name}", 100, "完成")
        return DbValidationRunResult(
            report_date=report_date.isoformat(),
            error_count=len(rows),
            excel_path=output_path,
            rows=rows,
            warnings=warnings,
        )

    def _related_rows_for(
        self,
        zg_code: str,
        current_rows_by_code: dict[str, list[dict[str, Any]]],
        public_info_rows: list[dict[str, Any]],
        field_catalog: TableFieldCatalog,
        template_rows_by_code: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        related: dict[str, list[dict[str, Any]]] = {}
        if public_info_rows:
            related["PUBLIC_INFO"] = public_info_rows
        if template_rows_by_code.get(zg_code):
            related["TEMPLATE"] = template_rows_by_code[zg_code]

        for dependency in DETAIL_TABLE_DEPENDENCIES.get(zg_code, ()):
            self._current_rows_for(dependency, current_rows_by_code, field_catalog)
            related[dependency] = current_rows_by_code[dependency]
        return related

    def _template_rows_by_code(
        self,
        table_codes: list[str],
        enable_template_check: bool,
        logger: ProgressLogger,
        warnings: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        if not enable_template_check:
            return {}
        if self.template_reader is None:
            warnings.append("模板数据源未配置，已跳过模板校验")
            return {}
        rows_by_code: dict[str, list[dict[str, Any]]] = {}
        for zg_code in table_codes:
            for table_name in _template_tables_for_zg(zg_code, self.field_catalog):
                logger(f"读取模板表 {table_name}", 9, "模板")
                try:
                    rows = self.template_reader.fetch_table(table_name)
                except Exception as exc:
                    warnings.append(f"模板表缺失或不可读：{table_name}（{exc}）")
                    continue
                rows = _apply_field_aliases(rows, table_name, self.field_catalog)
                rows_by_code.setdefault(zg_code, []).extend(
                    _with_template_table_name(rows, table_name)
                )
        return rows_by_code

    def _current_rows_for(
        self,
        zg_code: str,
        current_rows_by_code: dict[str, list[dict[str, Any]]],
        field_catalog: TableFieldCatalog,
    ) -> list[dict[str, Any]]:
        if zg_code not in current_rows_by_code:
            base_table = _mapped_table(field_catalog, "detail", zg_code)
            current_rows_by_code[zg_code] = _apply_field_aliases(
                self.data_reader.fetch_table(base_table, self._decrypt_column_for(zg_code, base_table)),
                base_table,
                field_catalog,
            )
        return current_rows_by_code[zg_code]

    def _decrypt_column_for(self, zg_code: str, table_name: str) -> str:
        # ZG07 借款人代码为密文存储；解密列按字段映射动态解析，不写死物理表名或英文列名。
        if zg_code != "ZG07" or not table_name:
            return ""
        try:
            return self.field_catalog.resolve_field(table_name, "借款人代码")
        except AttributeError:
            return ""


def _apply_field_aliases(
    rows: list[dict[str, Any]],
    table_name: str,
    field_catalog: TableFieldCatalog,
) -> list[dict[str, Any]]:
    try:
        mapping = field_catalog.fields_for_table(table_name)
    except KeyError:
        return rows
    if not mapping:
        return rows

    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        enriched = dict(row)
        for chinese_name, english_name in mapping.items():
            # Only mirror current English → Chinese so rules can read business names.
            # Do not invent abandoned English columns from Chinese values.
            if english_name in row and chinese_name not in enriched:
                enriched[chinese_name] = row[english_name]
        enriched_rows.append(enriched)
    return enriched_rows


def _with_template_table_name(rows: list[dict[str, Any]], table_name: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        enriched = dict(row)
        enriched["template_table"] = table_name
        normalized.append(enriched)
    return normalized


def _mapped_table(
    catalog: TableFieldCatalog,
    relation_type: str,
    logical_code: str,
    scope_code: str = "",
    *,
    fallback: str = "",
) -> str:
    try:
        return catalog.table_for(relation_type, logical_code, scope_code)
    except KeyError:
        if fallback:
            return fallback
        raise


def _template_tables_for_zg(zg_code: str, catalog: TableFieldCatalog) -> tuple[str, ...]:
    tables: list[str] = []
    for scope_code in ("1", "2"):
        try:
            tables.append(catalog.table_for("template", zg_code, scope_code))
        except KeyError:
            continue
    return tuple(tables)


def _split_semicolon_values(value: str) -> tuple[str, ...]:
    parts = [part.strip() for part in str(value or "").split(";")]
    return tuple(part for part in parts if part)


def _placeholders(count: int) -> str:
    return ", ".join(["%s"] * count)
