from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .validator import ValidationError


_INTEGER = re.compile(r"[+-]?\d+\Z")
_WORD = re.compile(r"(?:[^\W\d]|_)[\w$]*")
_DOLLAR_QUOTE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$")
_NUMBER = re.compile(r"\d+")

# These are intentionally the shared, conservative reserved words needed by
# the small grammar below.  Keeping them separate from ordinary identifiers is
# important: a keyword followed by ``(`` is not silently treated as a pure
# function merely because it has a familiar spelling.
_RESERVED_KEYWORDS = frozenset({
    "ALL", "AND", "AS", "BETWEEN", "BY", "CASE", "ELSE", "END", "EXISTS", "FILTER",
    "FOR", "FROM", "GROUP", "GROUPS", "HAVING", "IN", "INTO", "IS", "JOIN", "LOCK",
    "MATERIALIZED", "NOT", "NULL", "ON", "OR", "ORDER", "OVER", "PARTITION", "RANGE",
    "RECURSIVE", "ROWS", "SELECT", "SHARE", "THEN", "UNION", "VALUES", "WHEN", "WHERE",
    "WITH",
})

_PROHIBITED_WORDS = frozenset({
    "ALTER", "ANALYZE", "BEGIN", "CALL", "CLUSTER", "COMMIT", "COPY", "CREATE", "DEALLOCATE",
    "DELETE", "DO", "DROP", "DUMPFILE", "EXECUTE", "GRANT", "HANDLER", "INSERT", "INTO", "LOAD",
    "LOCK", "MERGE", "OUTFILE", "PREPARE", "PROCEDURE", "REFRESH", "REINDEX", "REPLACE", "REVOKE",
    "ROLLBACK", "SET", "TRUNCATE", "UPDATE", "USE", "VACUUM",
})
MYSQL_SAFE_SQL_MODE = "STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION"


@dataclass(frozen=True)
class _SqlToken:
    raw: str
    kind: str

    @property
    def upper(self) -> str:
        return self.raw.upper()


@dataclass(frozen=True)
class _SqlStructure:
    statement: str
    syntax_parentheses: frozenset[int]
    cte_names: frozenset[str]
    query_source_indexes: frozenset[int]


@dataclass(frozen=True)
class QueryPreview:
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    has_more: bool
    returned_count: int
    tested_signature: str


def validate_readonly_query(source: Any, sql: str) -> None:
    """Validate that SQL is one read-only query without executing it."""
    _validate_readonly_sql(sql, _source_db_type(source))


def validate_storable_query(source: Any, sql: str) -> None:
    """Allow invalid draft SQL to be stored while rejecting obvious unsafe operations.

    A saved query is validated again by :func:`validate_readonly_query` before
    every execution.  This lighter check therefore protects configuration
    storage from clear write/DDL, multi-statement and locking operations without
    turning successful parsing or execution into a prerequisite for saving.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise ValidationError("请输入 SQL", fields={"sql_text": "请输入 SQL"})
    db_type = _source_db_type(source)
    try:
        tokens = _lex_sql(sql, db_type)
    except ValidationError:
        _validate_unlexable_storable_sql(sql)
        return
    if not tokens:
        raise ValidationError("请输入 SQL", fields={"sql_text": "请输入 SQL"})
    semicolons = [index for index, token in enumerate(tokens) if token.raw == ";"]
    if semicolons and semicolons != [len(tokens) - 1]:
        raise ValidationError("只允许保存单条查询 SQL")
    words = [token.upper for token in tokens if token.kind in {"word", "keyword"}]
    if _contains_prohibited_command(tokens) or _contains_locking_clause(words):
        raise ValidationError("只允许保存查询 SQL，不能包含写入、DDL 或锁表操作")


class SqlPreviewExecutor:
    def __init__(
        self,
        connect_timeout_seconds: int = 5,
        query_timeout_seconds: int = 10,
        preview_limit: int = 10,
    ) -> None:
        self.connect_timeout_seconds = connect_timeout_seconds
        self.query_timeout_seconds = query_timeout_seconds
        self.preview_limit = preview_limit

    @classmethod
    def signature_for(
        cls, source: Any, sql: str, fields: Sequence[Any], shape: str
    ) -> str:
        active = _active_fields(fields)
        payload = {
            "datasource_id": _source_id(source),
            "sql": _normalize_sql(sql, _source_db_type(source)),
            "fields": sorted(
                (
                    {
                        "alias": _field_value(field, "field_alias"),
                        "type": _field_value(field, "value_type"),
                        "nullable": bool(_field_value(field, "nullable")),
                    }
                    for field in active
                ),
                key=lambda item: (str(item["alias"]), str(item["type"])),
            ),
            "shape": shape,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def validate_query(source: Any, sql: str) -> None:
        validate_readonly_query(source, sql)

    def execute(
        self, source: Any, sql: str, fields: Sequence[Any], shape: str
    ) -> QueryPreview:
        self.validate_query(source, sql)
        if shape not in {"scalar", "list"}:
            raise ValidationError("数据区域形态无效")
        active_fields = _active_fields(fields)
        if not active_fields:
            raise ValidationError("数据区域至少需要一个启用字段")
        signature = self.signature_for(source, sql, active_fields, shape)
        try:
            columns, rows = self._query(source, sql)
        except ValidationError:
            raise
        except Exception as error:
            raise ValidationError(_query_failure_message(error)) from None
        required_aliases = [_field_value(field, "field_alias") for field in active_fields]
        normalized_columns = [str(column).lower() for column in columns]
        if len(set(normalized_columns)) != len(normalized_columns):
            raise ValidationError("查询结果包含重复列名")
        positions = {name: index for index, name in enumerate(normalized_columns)}
        missing = [alias for alias in required_aliases if alias not in positions]
        if missing:
            raise ValidationError(
                "查询结果缺少必需字段：" + "、".join(missing),
                fields={alias: "查询结果缺少该字段" for alias in missing},
            )
        if shape == "scalar" and len(rows) > 1:
            raise ValidationError("单值数据区域最多只能返回一行")
        converted_rows = tuple(
            {
                alias: _convert_value(row[positions[alias]], field)
                for alias, field in zip(required_aliases, active_fields)
            }
            for row in rows[: self.preview_limit]
        )
        return QueryPreview(
            columns=tuple(required_aliases),
            rows=converted_rows,
            has_more=len(rows) > self.preview_limit,
            returned_count=len(converted_rows),
            tested_signature=signature,
        )

    def _query(self, source: Any, sql: str) -> tuple[list[str], list[Sequence[Any]]]:
        config = getattr(source, "config", source)
        db_type = str(getattr(config, "db_type", ""))
        connection = self._connect(config)
        try:
            with connection.cursor() as cursor:
                if db_type == "postgresql":
                    cursor.execute("BEGIN READ ONLY")
                    cursor.execute(
                        "SELECT set_config('statement_timeout', %s, true)",
                        (str(self.query_timeout_seconds * 1000),),
                    )
                    cursor.execute(
                        "SELECT set_config('search_path', %s, true)",
                        ("pg_catalog",),
                    )
                elif db_type == "mysql":
                    cursor.execute("SET SESSION sql_mode = %s", (MYSQL_SAFE_SQL_MODE,))
                    cursor.execute("SET SESSION TRANSACTION READ ONLY")
                    cursor.execute("START TRANSACTION READ ONLY")
                else:
                    raise ValidationError("不支持的数据源类型")
                cursor.execute(sql)
                columns = [str(column[0]) for column in cursor.description or ()]
                rows = list(cursor.fetchmany(self.preview_limit + 1))
                return columns, rows
        finally:
            rollback = getattr(connection, "rollback", None)
            if callable(rollback):
                try:
                    rollback()
                except Exception:
                    pass
            connection.close()

    def _connect(self, config: Any) -> Any:
        db_type = str(getattr(config, "db_type", ""))
        if db_type == "postgresql":
            import psycopg

            return psycopg.connect(
                host=config.host,
                port=config.port,
                dbname=config.database,
                user=config.username,
                password=config.password,
                connect_timeout=self.connect_timeout_seconds,
            )
        if db_type == "mysql":
            import pymysql

            return pymysql.connect(
                host=config.host,
                port=config.port,
                database=config.database,
                user=config.username,
                password=config.password,
                charset="utf8mb4",
                connect_timeout=self.connect_timeout_seconds,
                read_timeout=self.query_timeout_seconds,
                write_timeout=self.query_timeout_seconds,
            )
        raise ValidationError("不支持的数据源类型")


def _query_failure_message(error: Exception) -> str:
    """Turn driver failures into useful messages without exposing credentials."""
    detail = str(error)
    lowered = detail.lower()

    relation = re.search(
        r"\brelation\s+[\"'`]?([a-z_][a-z0-9_$.]*)[\"'`]?\s+does\s+not\s+exist\b",
        detail,
        re.IGNORECASE,
    )
    table = re.search(
        r"\btable\s+[\"'`]([a-z_][a-z0-9_$.]*)[\"'`]\s+doesn?'?t\s+exist\b",
        detail,
        re.IGNORECASE,
    )
    missing_table = relation or table
    if missing_table:
        return f"查询失败：数据表不存在：{missing_table.group(1)}"

    unknown_column = re.search(
        r"\bunknown\s+column\s+[\"'`]([a-z_][a-z0-9_$.]*)[\"'`]",
        detail,
        re.IGNORECASE,
    )
    missing_column = re.search(
        r"\bcolumn\s+[\"'`]?([a-z_][a-z0-9_$.]*)[\"'`]?\s+does\s+not\s+exist\b",
        detail,
        re.IGNORECASE,
    )
    column = unknown_column or missing_column
    if column:
        return f"查询失败：字段不存在：{column.group(1)}"

    if "unknown database" in lowered or re.search(
        r"\bdatabase\s+[\"'`][^\"'`]+[\"'`]\s+does\s+not\s+exist\b",
        detail,
        re.IGNORECASE,
    ):
        return "查询失败：指定数据库不存在"
    if "syntax error" in lowered or "error in your sql syntax" in lowered or "parse error" in lowered:
        return "查询失败：SQL 语法错误，请检查查询语句"
    if any(item in lowered for item in (
        "access denied", "permission denied", "authentication failed",
        "not authorized", "insufficient privilege",
    )):
        return "查询失败：数据库认证或查询权限不足"
    if any(item in lowered for item in (
        "timed out", "timeout", "statement timeout", "query execution was interrupted",
        "lock wait timeout",
    )):
        return "查询失败：数据库连接或查询超时"
    if any(item in lowered for item in (
        "can't connect", "cannot connect", "connection refused", "connection reset",
        "lost connection", "server closed the connection", "network is unreachable",
    )):
        return "查询失败：无法连接数据源或数据库连接已中断"
    if any(item in lowered for item in (
        "invalid input syntax", "invalid datetime format", "date/time field value out of range",
        "incorrect date value", "incorrect datetime value", "truncated incorrect",
    )):
        return "查询失败：查询值或日期格式不符合数据库要求"
    if "must appear in the group by" in lowered or "isn't in group by" in lowered:
        return "查询失败：聚合字段与 GROUP BY 不匹配"
    if "ambiguous" in lowered and "column" in lowered:
        return "查询失败：查询中存在含义不明确的同名字段"
    if "division by zero" in lowered:
        return "查询失败：查询表达式发生除零错误"
    if "function" in lowered and "does not exist" in lowered:
        return "查询失败：数据库函数不存在或参数类型不匹配"
    if any(item in lowered for item in ("operator does not exist", "cannot cast", "type mismatch")):
        return "查询失败：查询表达式的数据类型不匹配"
    if "does not exist" in lowered:
        return "查询失败：查询引用的数据库对象不存在"
    return "查询执行失败，请检查数据源、查询条件和字段类型"


def _active_fields(fields: Sequence[Any]) -> list[Any]:
    return [field for field in fields if _field_value(field, "enabled", True)]


def _field_value(field: Any, name: str, default: Any = None) -> Any:
    if isinstance(field, Mapping):
        return field.get(name, default)
    return getattr(field, name, default)


def _source_id(source: Any) -> str:
    value = _field_value(source, "id")
    if value is None:
        raise ValidationError("数据源无效")
    return str(value)


def _source_db_type(source: Any) -> str:
    config = getattr(source, "config", source)
    return str(getattr(config, "db_type", ""))


def _convert_value(value: Any, field: Any) -> Any:
    alias = str(_field_value(field, "field_alias"))
    nullable = bool(_field_value(field, "nullable"))
    if value is None:
        if nullable:
            return None
        raise ValidationError(f"字段 {alias} 不能为空", fields={alias: "字段值不能为空"})
    value_type = _field_value(field, "value_type")
    try:
        if value_type == "string":
            return str(value)
        if value_type == "integer":
            if isinstance(value, bool):
                raise ValueError
            if isinstance(value, int):
                return value
            if isinstance(value, Decimal) and value == value.to_integral_value():
                return int(value)
            text = str(value).strip()
            if _INTEGER.fullmatch(text) is None:
                raise ValueError
            return int(text)
        if value_type == "decimal":
            if isinstance(value, bool):
                raise ValueError
            converted = Decimal(str(value).strip())
            if not converted.is_finite():
                raise ValueError
            return str(converted)
        if value_type == "boolean":
            if isinstance(value, bool):
                return value
            if value in (0, 1):
                return bool(value)
            text = str(value).strip().lower()
            if text in {"true", "1"}:
                return True
            if text in {"false", "0"}:
                return False
            raise ValueError
        if value_type == "date":
            if isinstance(value, datetime):
                return value.date().isoformat()
            if isinstance(value, date):
                return value.isoformat()
            return date.fromisoformat(str(value).strip()).isoformat()
        if value_type == "datetime":
            if isinstance(value, datetime):
                return value.isoformat()
            return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00")).isoformat()
    except (ValueError, TypeError, InvalidOperation):
        raise ValidationError(f"字段 {alias} 的类型不符合要求", fields={alias: "字段类型不匹配"}) from None
    raise ValidationError(f"字段 {alias} 的类型无效", fields={alias: "字段类型无效"})


def _validate_readonly_sql(sql: str, db_type: str) -> None:
    if not isinstance(sql, str) or not sql.strip():
        raise ValidationError("只允许单条只读查询")
    tokens = _lex_sql(sql, db_type)
    if not tokens:
        raise ValidationError("只允许单条只读查询")
    semicolons = [index for index, token in enumerate(tokens) if token.raw == ";"]
    if semicolons:
        if semicolons != [len(tokens) - 1]:
            raise ValidationError("只允许单条只读查询")
        tokens = tokens[:-1]
    if not tokens or not _balanced_parentheses(tokens):
        raise ValidationError("只允许单条只读查询")
    structure = _parse_sql_structure(tokens)
    if structure is None or structure.statement != "SELECT":
        raise ValidationError("只允许单条只读查询")
    words = [token.upper for token in tokens if token.kind in {"word", "keyword"}]
    if _contains_prohibited_command(tokens):
        raise ValidationError("只允许单条只读查询")
    if _contains_locking_clause(words):
        raise ValidationError("只允许单条只读查询")


def _validate_unlexable_storable_sql(sql: str) -> None:
    """Conservatively inspect malformed SQL that the tokenizer cannot finish."""
    stripped = sql.rstrip()
    if ";" in stripped.rstrip(";"):
        raise ValidationError("只允许保存单条查询 SQL")
    prohibited = "|".join(sorted(re.escape(word) for word in _PROHIBITED_WORDS))
    if re.search(rf"(?<![\w$])(?:{prohibited})(?![\w$])", sql, re.IGNORECASE):
        raise ValidationError("只允许保存查询 SQL，不能包含写入、DDL 或锁表操作")


def _lex_sql(sql: str, db_type: str = "postgresql") -> list[_SqlToken]:
    """Tokenize enough SQL structure to identify one query and ignore comments."""
    tokens: list[_SqlToken] = []
    index = 0
    length = len(sql)
    while index < length:
        char = sql[index]
        following = sql[index + 1] if index + 1 < length else ""
        if char == "-" and following == "-":
            line_end = sql.find("\n", index + 2)
            index = length if line_end < 0 else line_end + 1
            continue
        if char == "/" and following == "*":
            comment_end = sql.find("*/", index + 2)
            if comment_end < 0:
                raise ValidationError("只允许单条只读查询")
            index = comment_end + 2
            continue
        if char == "#" and db_type == "mysql":
            line_end = sql.find("\n", index + 1)
            index = length if line_end < 0 else line_end + 1
            continue
        if char.isspace():
            index += 1
            continue
        if char in {"'", '"', "`"}:
            end = _quoted_end(sql, index, char, db_type)
            tokens.append(_SqlToken(sql[index:end], "quoted" if char != "'" else "literal"))
            index = end
            continue
        delimiter = "$$" if db_type == "postgresql" and sql.startswith("$$", index) else None
        if delimiter is None:
            match = _DOLLAR_QUOTE.match(sql, index) if db_type == "postgresql" else None
            delimiter = match.group(0) if match else None
        if delimiter is not None:
            end = sql.find(delimiter, index + len(delimiter))
            if end < 0:
                raise ValidationError("只允许单条只读查询")
            end += len(delimiter)
            tokens.append(_SqlToken(sql[index:end], "literal"))
            index = end
            continue
        word = _WORD.match(sql, index)
        if word:
            raw = word.group(0)
            tokens.append(_SqlToken(
                raw, "keyword" if raw.upper() in _RESERVED_KEYWORDS else "word"
            ))
            index = word.end()
            continue
        number = _NUMBER.match(sql, index)
        if number:
            tokens.append(_SqlToken(number.group(0), "number"))
            index = number.end()
            continue
        operator = next((item for item in ("->>", "::", "->", "<=", ">=", "<>", "!=", "||") if sql.startswith(item, index)), None)
        if operator is not None:
            tokens.append(_SqlToken(operator, "operator"))
            index += len(operator)
            continue
        tokens.append(_SqlToken(char, "operator" if char in "+-*/%=<>!" else "symbol"))
        index += 1
    return tokens


def _quoted_end(sql: str, start: int, quote: str, db_type: str) -> int:
    index = start + 1
    escaped_literal = quote == "'" and db_type == "postgresql" and start > 0 and sql[start - 1] in {"E", "e"} and (
        start == 1 or not (sql[start - 2].isalnum() or sql[start - 2] in {"_", "$"})
    )
    allow_backslash = db_type == "mysql" and quote in {"'", '"'} or escaped_literal
    while index < len(sql):
        char = sql[index]
        if char == "\\" and allow_backslash and index + 1 < len(sql):
            index += 2
            continue
        if char == quote:
            if index + 1 < len(sql) and sql[index + 1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    raise ValidationError("只允许单条只读查询")


def _normalize_sql(sql: str, db_type: str) -> str:
    return " ".join(token.raw for token in _lex_sql(sql, db_type))


def _balanced_parentheses(tokens: Sequence[_SqlToken]) -> bool:
    depth = 0
    for token in tokens:
        if token.raw == "(":
            depth += 1
        elif token.raw == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _parse_sql_structure(tokens: Sequence[_SqlToken]) -> _SqlStructure | None:
    if tokens[0].upper == "SELECT":
        syntax_parentheses = _syntax_parentheses(tokens, set())
        return _SqlStructure(
            statement="SELECT",
            syntax_parentheses=frozenset(syntax_parentheses),
            cte_names=frozenset(),
            query_source_indexes=frozenset(_query_source_indexes(tokens)),
        )
    if tokens[0].upper != "WITH":
        return None
    index = 1
    cte_names: set[str] = set()
    syntax_parentheses: set[int] = set()
    if index < len(tokens) and tokens[index].upper == "RECURSIVE":
        index += 1
    while index < len(tokens):
        if tokens[index].kind != "word":
            return None
        cte_names.add(tokens[index].upper)
        index += 1
        if index < len(tokens) and tokens[index].raw == "(":
            column_list_end = _cte_column_list_end(tokens, index)
            if column_list_end is None:
                return None
            syntax_parentheses.add(index)
            index = column_list_end + 1
        if index >= len(tokens) or tokens[index].upper != "AS":
            return None
        index += 1
        if index < len(tokens) and tokens[index].upper in {"MATERIALIZED", "NOT"}:
            index += 1
            if index < len(tokens) and tokens[index].upper == "MATERIALIZED":
                index += 1
        if index >= len(tokens) or tokens[index].raw != "(":
            return None
        syntax_parentheses.add(index)
        index = _after_parenthesized(tokens, index)
        if index is None:
            return None
        if index < len(tokens) and tokens[index].raw == ",":
            index += 1
            continue
        if index >= len(tokens) or tokens[index].upper != "SELECT":
            return None
        syntax_parentheses.update(_syntax_parentheses(tokens, syntax_parentheses))
        return _SqlStructure(
            statement="SELECT",
            syntax_parentheses=frozenset(syntax_parentheses),
            cte_names=frozenset(cte_names),
            query_source_indexes=frozenset(_query_source_indexes(tokens)),
        )
    return None


def _syntax_parentheses(tokens: Sequence[_SqlToken], known: set[int]) -> set[int]:
    """Return only the small set of grammar-confirmed non-function brackets."""
    positions = set(known)
    for index, token in enumerate(tokens):
        if token.raw != "(" or index == 0 or index in positions:
            continue
        if (
            _is_exists_subquery(tokens, index)
            or _is_in_expression(tokens, index)
            or _is_filter_clause(tokens, index)
            or _is_over_clause(tokens, index)
            or _is_derived_query_source(tokens, index)
        ):
            positions.add(index)
    return positions


def _cte_column_list_end(tokens: Sequence[_SqlToken], start: int) -> int | None:
    """Validate a CTE header column list while parsing the actual CTE header."""
    close = _closing_parenthesis(tokens, start)
    if close is None or close == start + 1:
        return None
    expect_name = True
    for token in tokens[start + 1:close]:
        if expect_name:
            if token.kind != "word":
                return None
        elif token.raw != ",":
            return None
        expect_name = not expect_name
    return None if expect_name else close


def _is_exists_subquery(tokens: Sequence[_SqlToken], start: int) -> bool:
    if start < 2 or tokens[start - 1].kind != "keyword" or tokens[start - 1].upper != "EXISTS":
        return False
    if tokens[start - 2].raw == ".":
        return False
    return _is_query_parenthesis(tokens, start)


def _is_in_expression(tokens: Sequence[_SqlToken], start: int) -> bool:
    if start < 3 or tokens[start - 1].kind != "keyword" or tokens[start - 1].upper != "IN":
        return False
    expression_end = tokens[start - 2]
    if expression_end.raw != ")" and expression_end.kind not in {
        "word", "quoted", "literal", "number",
    }:
        return False
    close = _closing_parenthesis(tokens, start)
    if close is None or close == start + 1:
        return False
    # A subquery or a non-empty literal/expression list is sufficient here.
    return True


def _is_filter_clause(tokens: Sequence[_SqlToken], start: int) -> bool:
    if start < 3 or tokens[start - 1].kind != "keyword" or tokens[start - 1].upper != "FILTER":
        return False
    if not _has_function_before(tokens, start - 1):
        return False
    close = _closing_parenthesis(tokens, start)
    return close is not None and close > start + 2 and tokens[start + 1].upper == "WHERE"


def _is_over_clause(tokens: Sequence[_SqlToken], start: int) -> bool:
    if start < 3 or tokens[start - 1].kind != "keyword" or tokens[start - 1].upper != "OVER":
        return False
    if not _has_function_before(tokens, start - 1):
        return False
    close = _closing_parenthesis(tokens, start)
    if close is None:
        return False
    return close == start + 1 or tokens[start + 1].upper in {
        "PARTITION", "ORDER", "ROWS", "RANGE", "GROUPS",
    }


def _is_derived_query_source(tokens: Sequence[_SqlToken], start: int) -> bool:
    return (
        start >= 2
        and tokens[start - 1].kind == "keyword"
        and tokens[start - 1].upper in {"FROM", "JOIN"}
        and tokens[start - 2].raw != "."
        and _is_query_parenthesis(tokens, start)
    )


def _is_query_parenthesis(tokens: Sequence[_SqlToken], start: int) -> bool:
    close = _closing_parenthesis(tokens, start)
    return close is not None and start + 1 < close and tokens[start + 1].upper in {"SELECT", "WITH"}


def _has_function_before(tokens: Sequence[_SqlToken], keyword_index: int) -> bool:
    if keyword_index == 0 or tokens[keyword_index - 1].raw != ")":
        return False
    opening = _opening_parenthesis(tokens, keyword_index - 1)
    if opening is None or opening == 0:
        return False
    name = tokens[opening - 1]
    if name.kind == "keyword" and name.upper == "FILTER":
        return _has_function_before(tokens, opening - 1)
    return name.kind in {"word", "quoted", "keyword"}


def _query_source_indexes(tokens: Sequence[_SqlToken]) -> set[int]:
    return {
        index
        for index, token in enumerate(tokens[:-1])
        if token.kind == "keyword"
        and token.upper in {"FROM", "JOIN"}
        and not _is_function_syntax_from(tokens, index)
    }


def _is_function_syntax_from(tokens: Sequence[_SqlToken], position: int) -> bool:
    """Recognize only the direct ``FROM`` syntax of EXTRACT/TRIM.

    Do not discard every FROM nested in a function: a scalar subquery is still
    a real SELECT source when parsing query structure.
    """
    enclosing = [
        index
        for index, token in enumerate(tokens[:position])
        if token.raw == "(" and (_closing_parenthesis(tokens, index) or -1) > position
    ]
    if not enclosing:
        return False
    opening = enclosing[-1]
    if opening == 0 or tokens[opening - 1].kind != "word":
        return False
    if tokens[opening - 1].upper not in {"EXTRACT", "TRIM"}:
        return False
    # A query opener inside the special function changes the source scope; it
    # is no longer the function's own FROM syntax.
    return not any(token.upper in {"SELECT", "WITH"} for token in tokens[opening + 1:position])


def _after_parenthesized(tokens: Sequence[_SqlToken], start: int) -> int | None:
    depth = 0
    for index in range(start, len(tokens)):
        if tokens[index].raw == "(":
            depth += 1
        elif tokens[index].raw == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _contains_locking_clause(words: Sequence[str]) -> bool:
    pairs = zip(words, words[1:])
    if any(first == "FOR" and second in {"UPDATE", "SHARE"} for first, second in pairs):
        return True
    return any(words[index:index + 4] == ["LOCK", "IN", "SHARE", "MODE"] for index in range(len(words)))


def _contains_prohibited_command(tokens: Sequence[_SqlToken]) -> bool:
    """Reject non-query commands while allowing arbitrary database functions."""
    for index, token in enumerate(tokens):
        if token.kind not in {"word", "keyword"} or token.upper not in _PROHIBITED_WORDS:
            continue
        if index + 1 < len(tokens) and tokens[index + 1].raw == "(":
            continue
        return True
    return False


def _closing_parenthesis(tokens: Sequence[_SqlToken], start: int) -> int | None:
    after = _after_parenthesized(tokens, start)
    return after - 1 if after is not None else None


def _opening_parenthesis(tokens: Sequence[_SqlToken], close: int) -> int | None:
    depth = 0
    for index in range(close, -1, -1):
        if tokens[index].raw == ")":
            depth += 1
        elif tokens[index].raw == "(":
            depth -= 1
            if depth == 0:
                return index
    return None
