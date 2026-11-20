"""Versioned output names derived from the documented fields of a generated rule."""

import re
import unicodedata

from .contracts import AppError
from .issue_query_results import compiled_projection
from .sql_guard import guard_generated_sql


_DERIVED = {"violation_message": "异常说明", "issue_kind": "异常类型",
            "project_match_count": "项目匹配记录数", "related_count": "关联记录数"}
_ROLES = {"business_key": "业务编号", "project_code": "项目编号", "project_name": "项目名称",
          "data_date": "数据日期", "checked_value": "校验值", "comparison_value": "比较值", **_DERIVED}


def _column_labels(columns):
    result = {}
    for col in columns or []:
        for key in ("field_cn", "column_name_cn", "comment"):
            caption = col.get(key)
            if isinstance(caption, str) and re.search(r"[\u3400-\u9fff]", caption):
                result[col["column_name"]] = caption.strip()
                break
    return result


def _quote(name, dialect):
    quote = chr(96) if dialect == "mysql" else '"'
    return quote + name.replace(quote, quote * 2) + quote


def _usable_caption(caption, dialect):
    # The platform tokenizer recognizes parameter and comment markers even inside identifiers.
    if not caption.isprintable() or re.search(r"(?<!:):[A-Za-z_]|--|/\*|\*/", caption):
        return False
    try:
        guard_generated_sql(dialect, "SELECT 1 AS " + _quote(caption, dialect), set())
    except AppError:
        return False
    return True


def build_result_aliases(definition, columns, related=None, project=None):
    base_labels, related_labels = _column_labels(columns), _column_labels(related)
    project_labels = _column_labels(project) if project else related_labels
    dialect = str(definition.get("dialect") or "mysql")
    aliases, seen = {}, set()
    for role, field, other in compiled_projection(definition, named_unique_keys=True):
        labels = project_labels if other and role == "project_name" else related_labels if other else base_labels
        caption = labels.get(field)
        name = caption if caption and _usable_caption(caption, dialect) else field or _DERIVED[role]
        suffix = ""
        for number in range(1, len(seen) + 2):
            # PostgreSQL limits identifiers in bytes. MySQL derived-table column names use characters.
            stem = (name[:64 - len(suffix)] if dialect == "mysql" else
                    name.encode("utf-8")[:63 - len(suffix.encode("utf-8"))].decode("utf-8", "ignore"))
            candidate = stem.rstrip() + suffix
            key = unicodedata.normalize("NFKC", candidate).casefold()
            if key not in seen:
                seen.add(key)
                aliases[role] = candidate
                break
            suffix = "（" + _ROLES.get(role, "业务键") + (str(number) if number > 1 else "") + "）"
    return aliases


def quoted_output_aliases(definition, dialect):
    aliases = {role: role for role in _ROLES}
    for role, alias in definition.get("result_aliases", {}).items():
        if (not isinstance(alias, str) or not alias or not alias.isprintable()
                or (len(alias) > 64 if dialect == "mysql" else len(alias.encode("utf-8")) > 63)):
            raise AppError("VALIDATION_ERROR")
        aliases[role] = _quote(alias, dialect)
    return aliases
