from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


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


@dataclass(frozen=True)
class DbValidationRunResult:
    report_date: str
    error_count: int
    excel_path: Path
    rows: list[ValidationResultRow]
    warnings: list[str]
