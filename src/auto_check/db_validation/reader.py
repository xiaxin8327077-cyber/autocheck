from __future__ import annotations

from typing import Any

from auto_check.app.db import qualified_name


class ValidationTableReader:
    def __init__(self, client: Any):
        self.client = client

    def fetch_table(self, table_name: str) -> list[dict[str, Any]]:
        quoted = qualified_name(self.client.config, table_name)
        return self.client.fetch_all(f"SELECT * FROM {quoted}")
