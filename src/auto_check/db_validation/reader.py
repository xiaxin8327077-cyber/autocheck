from __future__ import annotations

from typing import Any

from auto_check.app.db import qualified_name


ZG07_DETAIL_TABLE = "zgxgzh_ioudetail_zg07"
ZG07_BORROWER_CODE_COLUMN = "debtorcode"


class ValidationTableReader:
    def __init__(self, client: Any):
        self.client = client

    def fetch_table(self, table_name: str) -> list[dict[str, Any]]:
        quoted = qualified_name(self.client.config, table_name)
        decrypt_expr = _zg07_borrower_code_decrypt_expr(self.client.config.db_type, table_name)
        if decrypt_expr:
            return self.client.fetch_all(f"SELECT *, {decrypt_expr} FROM {quoted}")
        return self.client.fetch_all(f"SELECT * FROM {quoted}")


def _zg07_borrower_code_decrypt_expr(db_type: str, table_name: str) -> str:
    if not _is_zg07_detail_table(table_name):
        return ""
    column = _quote_identifier(db_type, ZG07_BORROWER_CODE_COLUMN)
    if db_type == "postgresql":
        return (
            f"convert_from(public.decrypt(decode(convert_from({column}, 'UTF8'), 'hex'), "
            f"'JsxtConsole', 'aes'), 'UTF8') AS {column}"
        )
    if db_type == "mysql":
        return (
            f"CONVERT(AES_DECRYPT(UNHEX({column}), 'JsxtConsole') "
            f"USING utf8mb4) AS {column}"
        )
    return ""


def _is_zg07_detail_table(table_name: str) -> bool:
    normalized = table_name.lower()
    return normalized == ZG07_DETAIL_TABLE or normalized.startswith(f"{ZG07_DETAIL_TABLE}_")


def _quote_identifier(db_type: str, identifier: str) -> str:
    if db_type == "postgresql":
        return '"' + identifier.replace('"', '""') + '"'
    if db_type == "mysql":
        return "`" + identifier.replace("`", "``") + "`"
    raise ValueError(f"Unsupported database type: {db_type}")
