from __future__ import annotations

from typing import Any

from auto_check.app.db import qualified_name


class ValidationTableReader:
    def __init__(self, client: Any):
        self.client = client

    def fetch_table(self, table_name: str, decrypt_column: str = "") -> list[dict[str, Any]]:
        quoted = qualified_name(self.client.config, table_name)
        decrypt_expr = _decrypt_column_expr(self.client.config.db_type, decrypt_column)
        if decrypt_expr:
            return self.client.fetch_all(f"SELECT *, {decrypt_expr} FROM {quoted}")
        return self.client.fetch_all(f"SELECT * FROM {quoted}")


def _decrypt_column_expr(db_type: str, column: str) -> str:
    # 解密列由引擎按字段映射解析后传入，读取层不持有任何业务表名或英文字段名。
    if not column:
        return ""
    quoted = _quote_identifier(db_type, column)
    if db_type == "postgresql":
        return (
            f"convert_from(public.decrypt(decode(convert_from({quoted}, 'UTF8'), 'hex'), "
            f"'JsxtConsole', 'aes'), 'UTF8') AS {quoted}"
        )
    if db_type == "mysql":
        return (
            f"CONVERT(AES_DECRYPT(UNHEX({quoted}), 'JsxtConsole') "
            f"USING utf8mb4) AS {quoted}"
        )
    return ""


def _quote_identifier(db_type: str, identifier: str) -> str:
    if db_type == "postgresql":
        return '"' + identifier.replace('"', '""') + '"'
    if db_type == "mysql":
        return "`" + identifier.replace("`", "``") + "`"
    raise ValueError(f"Unsupported database type: {db_type}")
