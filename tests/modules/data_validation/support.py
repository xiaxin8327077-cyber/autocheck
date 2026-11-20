from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from auto_check.modules.data_validation.service import DataValidationService
from auto_check.modules.data_validation.storage import METADATA, RuleStorage


class MemoryDatabase:
    def __init__(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.sql: list[str] = []
        METADATA.create_all(self.engine)

        def record(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
            self.sql.append(statement)

        event.listen(self.engine, "before_cursor_execute", record)

    @contextmanager
    def begin(self):
        with self.engine.begin() as connection:
            yield connection

    connect = begin


def service(metadata=None, model=None, report_navigation=None) -> tuple[MemoryDatabase, DataValidationService]:
    database = MemoryDatabase()
    return database, DataValidationService(
        RuleStorage(database), metadata=metadata, model=model, report_navigation=report_navigation,
    )


def user(user_id: str = "1", role: str = "user") -> dict[str, str]:
    return {"id": user_id, "role": role}


def loan_definition(**overrides) -> dict:
    definition = {
        "name": "贷款期限合理性校验",
        "description": "期限",
        "rule_type": "field_compare",
        "dialect": "mysql",
        "source_id": "src",
        "table_name": "loan",
        "business_key": "project_code",
        "violation_message": "贷款期限异常",
        "null_policy": "skip",
        "equality_policy": "allow_equal",
        "expression": {"left": "maturity_date", "op": "lt", "right": "issue_date"},
    }
    definition.update(overrides)
    return definition


class Metadata:
    def __init__(self, columns=None, rows=None, error=None, truncated=False, tables=None, sources=None) -> None:
        self.columns = columns or [
            # 物理名沿用旧 fixture，中文角色改为中性“贷款业务编号”，证明门禁不靠物理名猜项目。
            {"column_name": "project_code", "data_type": "varchar", "comment": "贷款业务编号"},
            {"column_name": "maturity_date", "data_type": "date", "comment": "到期日"},
            {"column_name": "issue_date", "data_type": "date", "comment": "发放日"},
            {"column_name": "report_date", "data_type": "date", "comment": "报送日期"},
        ]
        self.tables = [{"schema_name": "", "table_name": "loan", "comment": "贷款台账"}] if tables is None else tables
        self.sources = sources
        self.rows = () if rows is None else rows
        self.error = error
        self.truncated = truncated
        self.calls: list[str] = []

    def list_sources(self):
        from types import SimpleNamespace
        if self.sources is not None:
            return list(self.sources)
        return [SimpleNamespace(id="src", name="监管报表", dialect="mysql")]

    def list_tables(self, _source_id, *, keyword="", page=1, page_size=100):
        start = (max(int(page), 1) - 1) * int(page_size)
        items = self.tables[start:start + int(page_size)]
        return {"items": items, "total": len(self.tables), "page": page, "page_size": page_size}

    def describe_table(self, _source_id, _table_name):
        return {"columns": self.columns, "mapping_version": "map"}

    def execute_select(self, _source_id, sql, _params, timeout_seconds, max_rows):
        self.calls.append(sql)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(columns=("business_key",), rows=tuple(self.rows), truncated=self.truncated)


class TransactionOnlyDatabase:
    """模拟生产应用库：只暴露 transaction/connect，不提供 begin。"""

    def __init__(self, base) -> None:
        self.base = base

    def transaction(self):
        return self.base.begin()

    def connect(self):
        return self.base.begin()


class SequenceModel:
    """按调用顺序返回不同 JSON 的模型（选表/生成两阶段）。"""

    def __init__(self, payloads, error=None) -> None:
        self.payloads = list(payloads)
        self.error = error
        self.calls: list[dict] = []

    def complete(self, model_id, messages, timeout_seconds, *, cancel_event=None):
        self.calls.append({"model_id": model_id, "messages": messages})
        if self.error:
            raise self.error
        index = len(self.calls) - 1
        payload = self.payloads[index] if index < len(self.payloads) else self.payloads[-1]
        import json
        return json.dumps(payload, ensure_ascii=False)

    def complete_with_options(self, model_id, messages, *, options, **kwargs):
        content = self.complete(model_id, messages, **kwargs)
        self.calls[-1]["options"] = dict(options)
        return {"content": content, "finish_reason": "stop", "usage": {}}


def doc_xlsx_bytes(
    *,
    table: str = "test_table",
    sheet: str = "集市层_测试表",
    table_cn: str = "测试表",
    dimension: str = "业务记录",
    period: str = "月",
    fields=None,
) -> bytes:
    """生成一份符合文档约定的最小 xlsx（集市层表头在第 6 行）。"""
    import io

    from openpyxl import Workbook

    default_fields = [
        ("row_id", "编号", "varchar", "Y"),
        ("maturity_date", "到期日期", "date", ""),
        ("issue_date", "发放日期", "date", ""),
    ]
    rows = default_fields if fields is None else fields
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet
    worksheet.cell(row=1, column=1, value=table)
    meta = [("表名", f"{table_cn}（{table}.ktr）"), ("数据来源", "测试来源"), ("维度", dimension), ("采集周期", period)]
    for index, (label, value) in enumerate(meta, start=2):
        worksheet.cell(row=index, column=1, value=label)
        worksheet.cell(row=index, column=3, value=value)
    header = ["序号", "集市层字段名", "人行", "1104", "中信EA", "全要素", "集市层字段名（中文）", "字段类型", "主键", "默认值", "字典", "取数逻辑"]
    for column, label in enumerate(header, start=1):
        worksheet.cell(row=6, column=column, value=label)
    for offset, (name, cn, data_type, pk) in enumerate(rows, start=7):
        worksheet.cell(row=offset, column=1, value=offset - 6)
        worksheet.cell(row=offset, column=2, value=name)
        worksheet.cell(row=offset, column=7, value=cn)
        worksheet.cell(row=offset, column=8, value=data_type)
        worksheet.cell(row=offset, column=9, value=pk)
        worksheet.cell(row=offset, column=12, value="直取")
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()
