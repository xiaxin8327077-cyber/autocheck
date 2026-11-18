"""项目上下文输出维度的纯文档 grounding 与结构校验。

只使用活动文档中的真实表/字段证据：本表能取就取；本表缺名称时，仅在文档明确
项目实体表、关联键、同期间和唯一性证据后建议第二张维度表。模型或客户端声称的
confirmed 不能替代文档证据。
"""

from __future__ import annotations

import math
import re
from typing import Any

from .contracts import AppError

BASE_MODE = "base"
LOOKUP_MODE = "lookup"
MODES = (BASE_MODE, LOOKUP_MODE)
_FULL_PROJECT_NAME_TABLE = "reg_pub_project_info"
_FULL_PROJECT_NAME_FIELD = "c_projname"

PROJECT_CODE_COMMENTS = re.compile(r"项目编号|项目编码|项目代码|项目唯一标识|项目号|项目ID|项目 Id|项目 id")
PROJECT_NAME_COMMENTS = re.compile(r"项目名称|项目中文名|项目简称|项目名|项目 ID 名称|项目 Id 名称")
PERIOD_DATE_COMMENTS = re.compile(
    r"(?:数据|业务|报送|报告|统计|余额|会计|核算|账务|帐务)日期"
    r"|(?:期末|期初|日终|月结)日期?",
)
EVENT_DATE_COMMENTS = re.compile(
    r"开始|生效|成立|签发|签订|发生|到期|结束|截止|创建|更新|录入|采集|同步|提交"
    r"|起息|结息|放款|还款|销户|开业|注销|计划|预计|审批|复核|记账|入账",
)

STATUS_OK = "ok"
STATUS_MISSING_CODE = "missing_code"
STATUS_MISSING_NULL = "missing_null"
STATUS_MISSING_REFERENCE = "missing_reference"
STATUS_DUPLICATE = "duplicate"
STATUS_UNMAPPED = "unmapped"
STATUS_NOT_REQUIRED = "not_required"
PROJECT_STATUSES = (
    STATUS_OK, STATUS_MISSING_CODE, STATUS_MISSING_NULL, STATUS_MISSING_REFERENCE,
    STATUS_DUPLICATE, STATUS_UNMAPPED, STATUS_NOT_REQUIRED,
)

_BASE_KEYS = {"mode", "code_field", "name_field", "confirmed"}
_LOOKUP_KEYS = {"mode", "code_field", "name_field", "table_name", "key", "date_field",
                "unique_evidence", "confirmed"}
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _fail() -> None:
    raise AppError("VALIDATION_ERROR")


def _identifier(value: Any) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def base_type(data_type: Any) -> str:
    return str(data_type or "").strip().lower().split("(", 1)[0].strip()


def _field_name(field: dict[str, Any]) -> str:
    return str(field.get("field_name") or field.get("column_name") or "")


def _field_cn(field: dict[str, Any]) -> str:
    return str(field.get("field_cn") or field.get("comment") or "")


def _field_text(field: dict[str, Any]) -> str:
    return f"{_field_name(field)} {_field_cn(field)} {field.get('logic') or ''} {field.get('dictionary') or ''}"


def is_period_date_field(field: dict[str, Any]) -> bool:
    if base_type(field.get("data_type")) != "date":
        return False
    comment = _field_cn(field).strip()
    return bool(comment) and bool(PERIOD_DATE_COMMENTS.search(comment)) and not EVENT_DATE_COMMENTS.search(comment)


def project_code_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只按字段自身中文角色识别，不把取数逻辑的他列引用当成本列身份。"""
    # A reference to another column in lineage/logic does not make this column
    # an identifier. The role must describe the field itself.
    return [field for field in fields
            if (PROJECT_CODE_COMMENTS.search(_field_cn(field))
                or (str(field.get("is_pk") or "") == "Y" and _field_cn(field).strip() == "项目标识"))
            and not re.search(r"名称|简称", _field_cn(field))]


def project_name_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [field for field in fields if PROJECT_NAME_COMMENTS.search(_field_cn(field))]


def _project_names_for_table(table: dict[str, Any] | None, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # 用户明确指定这一张表的项目名全称；其他表仍按文档中文角色识别。
    if (table or {}).get("table_name") == _FULL_PROJECT_NAME_TABLE:
        return [field for field in fields if _field_name(field) == _FULL_PROJECT_NAME_FIELD]
    return project_name_fields(fields)


def normalize_project_context(raw: Any) -> dict[str, Any]:
    """结构规范化；不访问列结构。未知键拒绝，confirmed 缺省 false。"""
    if not isinstance(raw, dict):
        _fail()
    mode = raw.get("mode")
    if mode not in MODES:
        _fail()
    allowed = _BASE_KEYS if mode == BASE_MODE else _LOOKUP_KEYS
    if set(raw) - allowed:
        _fail()
    code_field = raw.get("code_field")
    name_field = raw.get("name_field")
    if not _identifier(code_field) or not _identifier(name_field):
        _fail()
    confirmed = raw.get("confirmed", False)
    if not isinstance(confirmed, bool):
        _fail()
    if mode == BASE_MODE:
        return {
            "mode": BASE_MODE, "code_field": code_field, "name_field": name_field,
            "confirmed": confirmed,
        }
    table_name = raw.get("table_name")
    if not _identifier(table_name):
        _fail()
    key = raw.get("key")
    if not isinstance(key, dict) or set(key) - {"left", "right"}:
        _fail()
    left, right = key.get("left"), key.get("right")
    if not _identifier(left) or not _identifier(right):
        _fail()
    date_field = raw.get("date_field")
    if date_field is not None and not _identifier(date_field):
        _fail()
    evidence_raw = raw.get("unique_evidence")
    if not isinstance(evidence_raw, dict) or set(evidence_raw) - {"kind", "fields", "text", "confirmed"}:
        _fail()
    kind = evidence_raw.get("kind")
    if kind not in ("pk", "logic"):
        _fail()
    evidence_fields = evidence_raw.get("fields") or []
    if not isinstance(evidence_fields, list) or any(not _identifier(item) for item in evidence_fields):
        _fail()
    text = str(evidence_raw.get("text") or "").strip()
    evidence_confirmed = evidence_raw.get("confirmed", False)
    if not isinstance(evidence_confirmed, bool):
        _fail()
    if kind == "pk" and not evidence_fields:
        _fail()
    if kind == "logic" and not text:
        _fail()
    if kind == "pk":
        if right not in evidence_fields:
            _fail()
        lookup_keys = {right} | ({date_field} if date_field is not None else set())
        if len(set(evidence_fields)) != len(evidence_fields) or not set(evidence_fields).issubset(lookup_keys):
            _fail()
    return {
        "mode": LOOKUP_MODE,
        "code_field": code_field,
        "name_field": name_field,
        "table_name": table_name,
        "key": {"left": left, "right": right},
        "date_field": date_field,
        "unique_evidence": {
            "kind": kind,
            "fields": list(evidence_fields),
            "text": text,
            "confirmed": evidence_confirmed,
        },
        "confirmed": confirmed,
    }


def validate_project_context(raw: Any) -> dict[str, Any]:
    return normalize_project_context(raw)


def _key_family(data_type: Any) -> str:
    kind = base_type(data_type).split(" ", 1)[0]
    if kind in {"int", "integer", "bigint", "smallint", "tinyint", "mediumint", "decimal", "numeric", "number"}:
        return "number"
    if kind in {"char", "varchar", "varchar2", "nvarchar", "nchar", "text", "bpchar", "citext"}:
        return "text"
    return kind


def validate_project_context_against_columns(
    context: dict[str, Any],
    base_types: dict[str, Any],
    lookup_types: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """核对字段存在、类型 family 与严格 DATE；返回 normalized context。"""
    normalized = normalize_project_context(context)
    if normalized["code_field"] not in base_types:
        _fail()
    if normalized["mode"] == BASE_MODE:
        if normalized["name_field"] not in base_types:
            _fail()
        return normalized
    if not lookup_types:
        _fail()
    if normalized["key"]["left"] not in base_types:
        _fail()
    for name in (normalized["name_field"], normalized["key"]["right"]):
        if name not in lookup_types:
            _fail()
    if _key_family(base_types[normalized["key"]["left"]]) != _key_family(lookup_types[normalized["key"]["right"]]):
        _fail()
    if normalized["date_field"] is not None:
        if normalized["date_field"] not in lookup_types:
            _fail()
        if base_type(lookup_types.get(normalized["date_field"])) != "date":
            _fail()
    return normalized


def project_output_columns(context: dict[str, Any] | None) -> list[str]:
    if context is None:
        return []
    return ["project_code", "project_name", "project_name_status"]


def project_row_status(
    *, mode: str, code: Any, name: Any, match_count: Any = None,
) -> str:
    if code is None or (isinstance(code, str) and not code.strip()):
        return STATUS_MISSING_CODE
    if mode == BASE_MODE:
        return STATUS_OK if name is not None and str(name).strip() else STATUS_MISSING_NULL
    if match_count is None:
        return STATUS_UNMAPPED
    try:
        if isinstance(match_count, bool):
            return STATUS_UNMAPPED
        count = int(match_count)
        if count < 0 or (not isinstance(match_count, str) and match_count != count):
            return STATUS_UNMAPPED
    except (TypeError, ValueError, OverflowError):
        return STATUS_UNMAPPED
    if count == 0:
        return STATUS_MISSING_REFERENCE
    if count > 1:
        return STATUS_DUPLICATE
    return STATUS_OK if name is not None and str(name).strip() else STATUS_MISSING_NULL


def project_semantics_required(definition: dict[str, Any], base_table: dict[str, Any] | None = None) -> bool:
    """判断该规则是否属于项目口径；供 executor 显式要求 project_context。"""
    texts = [
        str((base_table or {}).get("dimension") or ""),
        str((base_table or {}).get("table_name_cn") or ""),
        str((base_table or {}).get("scope") or ""),
        str(definition.get("scope_description") or ""),
        str(definition.get("name") or ""),
        str(definition.get("description") or ""),
    ]
    return any("项目" in text for text in texts)


def _unique_evidence(
    fields: list[dict[str, Any]], key_field: dict[str, Any], date_field: dict[str, Any] | None,
) -> dict[str, Any] | None:
    pk_names = {_field_name(field) for field in fields if str(field.get("is_pk") or "") == "Y"}
    key_name = _field_name(key_field)
    if key_name not in pk_names:
        return None
    lookup_keys = {key_name}
    if date_field is not None:
        lookup_keys.add(_field_name(date_field))
    # A PK with an extra contract/sequence column does NOT prove uniqueness of
    # project + period. Conversely a globally unique project key remains unique
    # when an additional reporting-period predicate is applied.
    if not pk_names.issubset(lookup_keys):
        return None
    evidence_fields = [key_name] + sorted(pk_names - {key_name})
    return {"kind": "pk", "fields": evidence_fields, "text": "", "confirmed": True}


def _question(question_id: str, text: str, options: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": question_id, "text": text, "options": options}


def infer_project_context(
    definition: dict[str, Any],
    base_table: dict[str, Any] | None,
    fields: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    fields_by_table: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    """纯文档推断项目上下文。

    返回 {"required": bool, "context": dict|None, "questions": [...],
           "project_columns": list[dict]}。只给真实选项；多候选不静默选择，
    缺证据返回具体 uncertainty 文本而不是泛化“补充需求”。
    """

    questions: list[dict[str, Any]] = []
    uncertainties: list[str] = []
    base_codes = project_code_fields(fields)
    base_names = _project_names_for_table(base_table, fields)
    fixed_name = (base_table or {}).get("table_name") == _FULL_PROJECT_NAME_TABLE
    supplied = definition.get("project_context") or {}
    if not isinstance(supplied, dict) or set(supplied) - _LOOKUP_KEYS:
        _fail()
    if supplied.get("mode") not in (None, BASE_MODE, LOOKUP_MODE):
        _fail()
    required = bool(project_semantics_required(definition, base_table) or base_codes or base_names or fixed_name or supplied)
    if not required:
        return {"required": False, "context": None, "questions": [],
                "project_columns": [], "uncertainties": []}
    if fixed_name and not base_names:
        return {"required": True, "context": None, "questions": [], "project_columns": [],
                "uncertainties": [f"活动文档缺少 {_FULL_PROJECT_NAME_TABLE} 的项目名全称字段 {_FULL_PROJECT_NAME_FIELD}。"]}
    # If the document identifies exactly one project-key column in the actual
    # row PK, it is the row entity identity. Secondary government/external
    # project references must not replace it or pair with the row's own name.
    primary_codes = [field for field in base_codes if str(field.get("is_pk") or "") == "Y"]
    if len(primary_codes) == 1:
        base_codes = primary_codes
    selected_code = supplied.get("code_field")
    if selected_code is not None:
        if selected_code not in {_field_name(field) for field in base_codes}:
            _fail()
        base_codes = [field for field in base_codes if _field_name(field) == selected_code]
    lookup_selected = not fixed_name and (supplied.get("mode") == LOOKUP_MODE or bool(supplied.get("table_name")))
    selected_name = supplied.get("name_field")
    if not fixed_name and selected_name is not None and not lookup_selected:
        if selected_name not in {_field_name(field) for field in base_names}:
            _fail()
        base_names = [field for field in base_names if _field_name(field) == selected_name]
    if lookup_selected:
        # A deliberate, real-document lookup choice is not replaced by a
        # newly discovered local name; its relationship is checked below.
        base_names = []

    if len(base_codes) > 1:
        questions.append(_question(
            "project_context.code_field", "本表用哪个真实字段作为项目编号？",
            [{"value": _field_name(field), "label": f"{_field_cn(field) or _field_name(field)}（{_field_name(field)}）"}
             for field in base_codes[:20]],
        ))
        base_codes = []
    if len(base_names) > 1:
        questions.append(_question(
            "project_context.name_field", "本表用哪个真实字段作为项目名称？",
            [{"value": _field_name(field), "label": f"{_field_cn(field) or _field_name(field)}（{_field_name(field)}）"}
             for field in base_names[:20]],
        ))
        base_names = []

    if base_codes and base_names:
        context = {
            "mode": BASE_MODE,
            "code_field": _field_name(base_codes[0]),
            "name_field": _field_name(base_names[0]),
            "confirmed": True,
        }
        return {"required": True, "context": context, "questions": questions,
                "project_columns": [], "uncertainties": uncertainties}

    if questions:
        return {"required": True, "context": None, "questions": questions,
                "project_columns": [], "uncertainties": []}
    code_field = base_codes[0] if base_codes else None
    if code_field is None:
        message = "文档未在本表识别到带“项目编号/编码/代码”中文证据的字段；不能凭物理名猜项目编号。"
        if base_table is not None:
            message = f"基表 {base_table.get('table_name') or ''}：{message}"
        uncertainties.append(message)
        return {"required": required, "context": None, "questions": questions,
                "project_columns": [], "uncertainties": uncertainties}

    if base_names:
        # 本表有编号但名称字段存在却未通过唯一识别时，仍以本表为候选，不跨表乱找。
        context = {
            "mode": BASE_MODE,
            "code_field": _field_name(code_field),
            "name_field": _field_name(base_names[0]),
            "confirmed": True,
        }
        return {"required": True, "context": context, "questions": questions,
                "project_columns": [], "uncertainties": uncertainties}

    candidates: list[dict[str, Any]] = []
    seen = set()
    base_id = int(base_table.get("id")) if base_table is not None and base_table.get("id") is not None else None
    for table in tables or []:
        table_id = int(table.get("id")) if table.get("id") is not None else None
        if table_id is None or table_id == base_id:
            continue
        base_source = str((base_table or {}).get("data_source_name") or "")
        lookup_source = str(table.get("data_source_name") or "")
        if base_source and lookup_source and base_source != lookup_source:
            continue
        table_fields = list(fields_by_table.get(table_id) or [])
        if not table_fields:
            continue
        lookup_names = _project_names_for_table(table, table_fields)
        if not lookup_names:
            continue
        table_text = " ".join(str(table.get(key) or "") for key in ("dimension", "table_name_cn", "scope", "source_desc"))
        if "项目" not in table_text:
            continue
        for name_field in lookup_names:
            for key_field in project_code_fields(table_fields):
                period_fields = [item for item in table_fields if is_period_date_field(item)]
                for date_field in period_fields or [None]:
                    marker = (table_id, _field_name(key_field), _field_name(name_field),
                              _field_name(date_field) if date_field else None)
                    if marker in seen:
                        continue
                    seen.add(marker)
                    evidence = _unique_evidence(table_fields, key_field, date_field)
                    if evidence is None:
                        continue
                    candidates.append({
                        "table": table,
                        "fields": table_fields,
                        "key_field": key_field,
                        "name_field": name_field,
                        "date_field": date_field,
                        "evidence": evidence,
                    })

    selected_key = supplied.get("key")
    if selected_key is not None:
        if not isinstance(selected_key, dict) or set(selected_key) - {"left", "right"}:
            _fail()
        if selected_key.get("left") not in (None, _field_name(code_field)):
            _fail()
    if supplied.get("confirmed") is not None and not isinstance(supplied["confirmed"], bool):
        _fail()
    has_lookup_choice = lookup_selected or selected_key is not None
    if has_lookup_choice:
        unfiltered = candidates
        candidates = [item for item in candidates
                      if (not supplied.get("table_name") or item["table"]["table_name"] == supplied["table_name"])
                      and (not selected_name or _field_name(item["name_field"]) == selected_name)
                      and (not selected_key or not selected_key.get("right")
                           or _field_name(item["key_field"]) == selected_key["right"])
                      and ("date_field" not in supplied
                           or (_field_name(item["date_field"]) if item["date_field"] else None) == supplied["date_field"])]
        if unfiltered and not candidates:
            _fail()
    if not candidates:
        message = (
            f"基表 {base_table.get('table_name') if base_table else ''} 有项目编号字段 "
            f"{_field_name(code_field)}，但文档没有同时具备“项目粒度、项目编号、项目名称、同期间日期”且能证明唯一对应的项目表；"
            "不能 INNER JOIN、不能任取 first/MIN，也不能编造项目名称。"
        )
        uncertainties.append(message)
        return {"required": required, "context": None, "questions": questions,
                "project_columns": [], "uncertainties": uncertainties}

    distinct_tables: dict[int, dict[str, Any]] = {}
    for item in candidates:
        table = item["table"]
        distinct_tables.setdefault(int(table["id"]), table)
    if len(distinct_tables) > 1:
        options = [
            {
                "value": str(table.get("table_name") or ""),
                "label": f"{table.get('table_name_cn') or table.get('table_name')}（{table.get('table_name')}）",
                "selection": {"mode": LOOKUP_MODE, "code_field": _field_name(code_field),
                              "table_name": str(table.get("table_name") or "")},
                "description": "真实文档候选；仍需核验项目键、同期间日期与唯一性证据。",
            }
            for table in distinct_tables.values()
        ]
        questions.append(_question(
            "project_context.table_name", "从哪个真实项目表补取项目名称？", options,
        ))
        return {"required": required, "context": None, "questions": questions,
                "project_columns": [], "uncertainties": uncertainties}

    if len(candidates) > 1:
        # 同一张表内也有多组键/名称证据时不得静默选第一组。
        options = [
            {
                "value": f"{item['table'].get('table_name')}|{_field_name(item['key_field'])}|"
                         f"{_field_name(item['name_field'])}|{_field_name(item['date_field']) if item['date_field'] else ''}",
                "label": f"{item['table'].get('table_name')}：{_field_name(item['key_field'])} ↔ "
                         f"{_field_name(item['name_field'])}"
                         + (f"（{_field_name(item['date_field'])}）" if item['date_field'] else ""),
                "selection": {
                    "mode": LOOKUP_MODE, "code_field": _field_name(code_field),
                    "table_name": str(item["table"].get("table_name") or ""),
                    "key": {"left": _field_name(code_field), "right": _field_name(item["key_field"])},
                    "name_field": _field_name(item["name_field"]),
                    "date_field": _field_name(item["date_field"]) if item["date_field"] else None,
                },
                "description": "真实文档候选映射；仍需确认唯一性证据。",
            }
            for item in candidates[:20]
        ]
        questions.append(_question(
            "project_context.mapping", "采用哪一组项目编号/名称映射？", options,
        ))
        return {"required": required, "context": None, "questions": questions,
                "project_columns": [], "uncertainties": uncertainties}

    only = candidates[0]
    table = only["table"]
    date_field = only["date_field"]
    evidence = only["evidence"]
    if evidence is None:
        uncertainties.append(
            f"候选项目表 {table.get('table_name')} 未在文档主键/唯一性说明中证明 "
            f"{_field_name(only['key_field'])}"
            + (f"+{_field_name(date_field)}" if date_field else "")
            + " 唯一对应，不能任取名称。"
        )
    context = {
        "mode": LOOKUP_MODE,
        "code_field": _field_name(code_field),
        "name_field": _field_name(only["name_field"]),
        "table_name": str(table.get("table_name") or ""),
        "key": {"left": _field_name(code_field), "right": _field_name(only["key_field"])},
        "date_field": _field_name(date_field) if date_field else None,
        "unique_evidence": evidence,
        "confirmed": supplied.get("confirmed") is True,
    }
    if not context["confirmed"]:
        questions.append(_question(
            "project_context.confirmed",
            f"请确认 {base_table.get('table_name') if base_table else '主表'}.{_field_name(code_field)} "
            f"与 {table['table_name']}.{_field_name(only['key_field'])} 使用同一项目编号口径。",
            [{"value": "true", "label": "确认这组真实项目关联口径"}],
        ))
    return {
        "required": required,
        "context": context,
        "questions": questions,
        "project_columns": list(only["fields"]),
        "uncertainties": uncertainties,
    }
