"""数据校验模块的错误码与哈希。"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

PBC_REPORT_CATEGORIES = frozenset({"pbc_central", "pbc_template"})
PBC_SHARED_CATEGORY = "group:pbc"
PBC_SHARED_CATEGORY_NAME = "人行报送"


class AppError(Exception):
    def __init__(self, code: str, *, stage: str = "", reference: str = "") -> None:
        self.code = code
        self.stage = stage
        self.reference = reference
        super().__init__(code)


def content_hash(definition: dict[str, Any], dialect: str, mapping_version: str, sql: str) -> str:
    payload = {
        "definition": definition,
        "dialect": dialect,
        "mapping_version": mapping_version,
        "sql": sql,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()
