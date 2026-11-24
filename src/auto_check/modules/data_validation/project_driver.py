"""Document-proven project-first binding for newly generated field comparisons.

The execution expression keeps its original base/related ownership.  A driver marker
only identifies which side supplies the authoritative project collection.  No business
rows are read here: every decision comes from the active document's table and field
metadata.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .contracts import AppError
from .project_context import (
    EVENT_DATE_COMMENTS,
    base_type,
    is_period_date_field,
    normalize_project_context,
    project_code_fields,
    project_key_family,
    project_name_fields,
    project_unique_evidence,
)

BASE = "base"
RELATED = "related"
DRIVER_VERSION = 3
_UNSET = object()
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_JOIN_KEYS = {
    "table_name", "on", "report_date_field", "unmatched_policy",
    "relationship_confirmed", "right_aggregate",
}


def _fail() -> None:
    raise AppError("VALIDATION_ERROR")


def _field_name(field: dict[str, Any]) -> str:
    return str(field.get("field_name") or field.get("column_name") or "")


def _table_id(table: dict[str, Any]) -> int:
    try:
        return int(table.get("id"))
    except (TypeError, ValueError):
        return -1


def normalize_project_driver(raw: Any) -> dict[str, Any]:
    """Validate the complete public marker shape; booleans are not version integers."""
    if not isinstance(raw, dict) or set(raw) != {"version", "table_role"}:
        _fail()
    if type(raw.get("version")) is not int or raw["version"] not in (1, 2, DRIVER_VERSION):
        _fail()
    if raw.get("table_role") not in (BASE, RELATED):
        _fail()
    return {"version": raw["version"], "table_role": raw["table_role"]}


def validate_project_driver(
    definition: dict[str, Any], *, context: Any = _UNSET, join: Any = _UNSET,
) -> dict[str, Any] | None:
    """Validate marker/context/join relationships without consulting field metadata."""
    if "project_driver" not in definition:
        return None
    driver = normalize_project_driver(definition["project_driver"])
    context = definition.get("project_context") if context is _UNSET else context
    join = definition.get("join") if join is _UNSET else join
    if definition.get("rule_type") != "field_compare" or context is None:
        _fail()
    context = normalize_project_context(context)
    role = driver["table_role"]
    if role == BASE:
        if context["mode"] != BASE:
            _fail()
    else:
        if not isinstance(join, dict) or context["mode"] != "lookup":
            _fail()
        if join.get("right_aggregate") is not None:
            _fail()
        if (context["table_name"] != join.get("table_name")
                or context["code_field"] != context["key"]["left"]
                or context["key"] not in join.get("on", [])
                or context.get("date_field") is None
                or context["date_field"] != join.get("report_date_field")):
            _fail()

    if join is not None:
        if not isinstance(join, dict) or set(join) - _JOIN_KEYS:
            _fail()
        pairs = join.get("on")
        if not isinstance(pairs, list) or not pairs:
            _fail()
        if role == BASE:
            required = [item for item in pairs if isinstance(item, dict)
                        and item.get("left") == context["code_field"]]
            if len(required) != 1:
                _fail()
            project_pair = required[0]
        else:
            project_pair = context["key"]
        date_pair = {
            "left": str(definition.get("report_date_field") or "report_date"),
            "right": join.get("report_date_field"),
        }
        for pair in pairs:
            if (not isinstance(pair, dict) or set(pair) != {"left", "right"}
                    or pair not in (project_pair, date_pair)):
                _fail()
    return driver


def validate_project_driver_columns(
    definition: dict[str, Any],
    base_columns: list[dict[str, Any]],
    related_columns: list[dict[str, Any]] | None,
    *,
    context: Any = _UNSET,
    join: Any = _UNSET,
) -> dict[str, Any] | None:
    """Recheck project identity, DATE and key families against real/document columns.

    Database ``describe_table`` responses do not necessarily expose PK flags.  When
    those flags are present (as they are in the active document), uniqueness evidence
    is mandatory; execution still detects duplicate project keys in the fixed SQL.
    """
    context = definition.get("project_context") if context is _UNSET else context
    join = definition.get("join") if join is _UNSET else join
    driver = validate_project_driver(definition, context=context, join=join)
    if driver is None:
        return None
    context = normalize_project_context(context)
    base = {_field_name(item): item for item in base_columns or []}
    related = {_field_name(item): item for item in related_columns or []}
    role = driver["table_role"]
    project = base if role == BASE else related
    if not project:
        _fail()
    code = context["code_field"] if role == BASE else context["key"]["right"]
    name = context["name_field"]
    day = (str(definition.get("report_date_field") or "report_date") if role == BASE
           else context["date_field"])
    if any(not _IDENTIFIER.fullmatch(str(part or "")) for part in (code, name, day)):
        _fail()
    if code not in project or name not in project or day not in project:
        _fail()
    if base_type(project[day].get("data_type")) != "date":
        _fail()

    if join is not None:
        detail = related if role == BASE else base
        detail_day_name = join.get("report_date_field") if role == BASE else str(
            definition.get("report_date_field") or "report_date"
        )
        detail_day = detail.get(detail_day_name)
        if detail_day is None or base_type(detail_day.get("data_type")) != "date":
            _fail()
        if role == BASE:
            pair = next(item for item in join["on"] if item["left"] == code)
            detail_code_name = pair["right"]
            detail_code = detail.get(detail_code_name)
        else:
            detail_code_name = context["key"]["left"]
            detail_code = base.get(detail_code_name)
        if detail_code is None or project_key_family(detail_code.get("data_type")) != project_key_family(
            project[code].get("data_type")
        ):
            _fail()

    project_fields = list(project.values())
    if any("is_pk" in item for item in project_fields):
        evidence = project_unique_evidence(project_fields, project[code], project[day])
        if evidence is None:
            _fail()
        if role == RELATED:
            claimed = context["unique_evidence"]
            if (claimed.get("kind") != "pk" or claimed.get("confirmed") is not True
                    or set(claimed.get("fields") or []) != set(evidence["fields"])):
                _fail()
    return driver


def _source_links(field: dict[str, Any]) -> list[tuple[str, str]]:
    tables = [item.strip() for item in str(field.get("source_table") or "").splitlines() if item.strip()]
    fields = [item.strip() for item in str(field.get("source_field") or "").splitlines() if item.strip()]
    if not tables or len(tables) != len(fields):
        return []
    return list(zip(tables, fields))


def _source_table_name(raw: str) -> str:
    parts = [part.strip().strip("`\" ") for part in str(raw or "").split(".")]
    name = parts[-1] if parts else ""
    # Documented current/archive alternatives name the same logical table.
    if name.endswith("_YYYY_MM"):
        name = name[:-8]
    return name


def _table_lookup(tables: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for table in tables:
        result.setdefault(str(table.get("table_name") or ""), []).append(table)
    return result


def _period_field(field: dict[str, Any]) -> bool:
    if is_period_date_field(field):
        return True
    label = str(field.get("field_cn") or field.get("comment") or "")
    return (base_type(field.get("data_type")) == "date"
            and not EVENT_DATE_COMMENTS.search(label)
            and bool(re.search(r"数据日期|业务日期|报送日期", str(field.get("logic") or ""))))


def _entity(table: dict[str, Any], fields: list[dict[str, Any]], period: str = "") -> tuple[dict[str, Any] | None, str]:
    codes = [item for item in project_code_fields(fields) if str(item.get("is_pk") or "") == "Y"]
    names = project_name_fields(fields)
    dates = [item for item in fields if _period_field(item)]
    if period:
        dates = [item for item in dates if _field_name(item) == period]
    if len(codes) != 1:
        return None, f"项目表 {table.get('table_name')} 需要唯一的项目编号主键及 TCMP 含义证明。"
    if len(names) != 1:
        return None, f"项目表 {table.get('table_name')} 需要唯一的项目名称字段。"
    if len(dates) != 1 or base_type(dates[0].get("data_type")) != "date":
        return None, f"项目表 {table.get('table_name')} 需要唯一的项目数据日期 DATE 字段。"
    evidence = project_unique_evidence(fields, codes[0], dates[0])
    if evidence is None:
        return None, f"项目表 {table.get('table_name')} 未证明同日同 TCMP 唯一。"
    return {
        "table": table,
        "fields": list(fields),
        "code": codes[0],
        "name": names[0],
        "date": dates[0],
        "evidence": evidence,
    }, ""


def _find_entity(
    base_table: dict[str, Any],
    tables: list[dict[str, Any]],
    fields_by_table: dict[int, list[dict[str, Any]]],
    definition: dict[str, Any],
) -> tuple[dict[str, Any] | None, bool, list[str]]:
    project_tables = [item for item in tables if str(item.get("dimension") or "").strip() == "项目"]
    base_id = _table_id(base_table)
    base_is_project = any(_table_id(item) == base_id for item in project_tables)
    if len(project_tables) > 1:
        return None, base_is_project, ["当前同源分类文档存在多个项目实体，不能猜测项目驱动表。"]
    if not project_tables:
        return None, False, []
    table = project_tables[0]
    join = definition.get("join")
    period = (str(definition.get("report_date_field") or "") if base_is_project else
              str(join.get("report_date_field") or "") if isinstance(join, dict)
              and join.get("table_name") == table.get("table_name") else "")
    entity, issue = _entity(table, fields_by_table.get(_table_id(table)) or [], period)
    return entity, base_is_project, [issue] if issue else []


def _resolve_source_table(raw: str, lookup: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    matches = lookup.get(_source_table_name(raw)) or []
    return matches[0] if len(matches) == 1 else None


def _reaches_project_code(
    table: dict[str, Any],
    field_name: str,
    entity: dict[str, Any],
    fields_by_table: dict[int, list[dict[str, Any]]],
    lookup: dict[str, list[dict[str, Any]]],
    visited: set[tuple[int, str]],
) -> bool:
    table_id = _table_id(table)
    if table_id == _table_id(entity["table"]):
        return field_name == _field_name(entity["code"])
    marker = (table_id, field_name)
    if marker in visited:
        return False
    fields = fields_by_table.get(table_id) or []
    field = next((item for item in fields if _field_name(item) == field_name), None)
    if field is None:
        return False
    links = _source_links(field)
    if not links:
        return False
    next_visited = {*visited, marker}
    for source_table, source_field in links:
        source = _resolve_source_table(source_table, lookup)
        if source is None or not _reaches_project_code(
            source, source_field, entity, fields_by_table, lookup, next_visited,
        ):
            return False
    return True


def _lineage_fields(
    base_table: dict[str, Any],
    fields: list[dict[str, Any]],
    entity: dict[str, Any],
    fields_by_table: dict[int, list[dict[str, Any]]],
    lookup: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [
        item for item in fields
        if _reaches_project_code(base_table, _field_name(item), entity, fields_by_table, lookup, set())
    ]


def _direct_project_mapping(
    fields: list[dict[str, Any]],
    entity: dict[str, Any],
    lookup: dict[str, list[dict[str, Any]]],
) -> dict[str, str]:
    project_names = {_field_name(item) for item in entity["fields"]}
    result = {}
    for field in fields:
        links = _source_links(field)
        targets = []
        for source_table, source_field in links:
            source = _resolve_source_table(source_table, lookup)
            if source is not None and _table_id(source) == _table_id(entity["table"]) and source_field in project_names:
                targets.append(source_field)
        if links and len(targets) == len(links) and len(set(targets)) == 1:
            result[_field_name(field)] = targets[0]
    return result


def _selected_period(definition: dict[str, Any], fields: list[dict[str, Any]]) -> dict[str, Any] | None:
    dates = [item for item in fields if _period_field(item)]
    selected = str(definition.get("report_date_field") or "")
    if selected:
        return next((item for item in dates if _field_name(item) == selected), None)
    return dates[0] if len(dates) == 1 else None


def _valid_join_shape(join: dict[str, Any], required: dict[str, str], date_pair: dict[str, str]) -> bool:
    if set(join) - _JOIN_KEYS or not isinstance(join.get("on"), list) or required not in join["on"]:
        return False
    return all(isinstance(pair, dict) and set(pair) == {"left", "right"}
               and pair in (required, date_pair) for pair in join["on"])


def _dictionary_compatible(source: dict[str, Any], target: dict[str, Any]) -> bool:
    left = str(source.get("dictionary") or "").strip()
    right = str(target.get("dictionary") or "").strip()
    return left == right


def _remap_filters(
    definition: dict[str, Any],
    base_fields: list[dict[str, Any]],
    entity: dict[str, Any],
    mapping: dict[str, str],
) -> None:
    base = {_field_name(item): item for item in base_fields}
    project = {_field_name(item): item for item in entity["fields"]}
    project_semantics = {_field_name(item) for item in [*project_code_fields(base_fields), *project_name_fields(base_fields)]}
    for item in definition.get("filters") or []:
        if not isinstance(item, dict) or item.get("table", BASE) != BASE:
            continue
        name = item.get("field")
        target = mapping.get(name)
        if target is not None:
            if not _dictionary_compatible(base[name], project[target]):
                raise ValueError(f"项目范围字段 {name} 与项目表 {target} 的字典含义不一致。")
            item["table"] = RELATED
            item["field"] = target
        elif name in project_semantics:
            raise ValueError(f"项目属性 {name} 缺少从项目表直取的来源证明，不能使用明细副本驱动范围。")


def _validate_scope_mapping(
    definition: dict[str, Any],
    base_fields: list[dict[str, Any]],
    entity: dict[str, Any],
    mapping: dict[str, str],
) -> None:
    intent = definition.get("semantic_intent")
    scopes = intent.get("scopes") if isinstance(intent, dict) else None
    if not isinstance(scopes, list):
        return
    base = {_field_name(item): item for item in base_fields}
    project = {_field_name(item): item for item in entity["fields"]}
    for scope in scopes:
        if not isinstance(scope, dict) or scope.get("table", BASE) != BASE:
            continue
        names = scope.get("fields")
        if not isinstance(names, list):
            continue
        mapped = [name in mapping for name in names]
        if any(mapped) and not all(mapped):
            raise ValueError("同一项目范围候选混合了项目直取字段和独立明细字段，不能静默合并角色。")
        if all(mapped):
            for name in names:
                target = mapping[name]
                if name not in base or target not in project or not _dictionary_compatible(base[name], project[target]):
                    raise ValueError(f"项目范围候选 {name} 与项目表 {target} 的含义或字典不一致。")


def _failure(definition, issues, *, unsupported=(), entity=None):
    return {
        "definition": deepcopy(definition),
        "involved": True,
        "project_table": (entity or {}).get("table"),
        "project_fields": list((entity or {}).get("fields") or []),
        "field_mapping": {},
        "uncertainties": list(issues),
        "unsupported_requirements": list(unsupported),
    }


def bind_project_driver(
    definition: dict[str, Any],
    base_table: dict[str, Any],
    base_fields: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    fields_by_table: dict[int, list[dict[str, Any]]],
    *,
    required: bool = False,
    preserve_version: bool = False,
) -> dict[str, Any]:
    """Bind a new draft to the unique documented project entity, if involved.

    The returned definition is always a private copy.  Failure never falls back to a
    detail-driven marker and never removes an existing comparison or join.
    """
    original = deepcopy(definition)
    requested = None
    if "project_driver" in original:
        try:
            requested = normalize_project_driver(original["project_driver"])
        except AppError:
            return _failure(original, [], unsupported=["项目驱动标记版本或角色无效，请重新生成。"])

    entity, base_is_project, entity_issues = _find_entity(base_table, tables, fields_by_table, original)
    lookup = _table_lookup(tables)
    lineage = ([] if entity is None or base_is_project else
               _lineage_fields(base_table, base_fields, entity, fields_by_table, lookup))
    raw_join = original.get("join")
    join_is_project = bool(entity and isinstance(raw_join, dict)
                           and raw_join.get("table_name") == entity["table"].get("table_name"))
    involved = bool(required or requested or base_is_project or lineage or join_is_project
                    or project_code_fields(base_fields) or project_name_fields(base_fields))
    if not involved:
        return {
            "definition": original, "involved": False, "project_table": None, "project_fields": [],
            "field_mapping": {}, "uncertainties": [], "unsupported_requirements": [],
        }
    if entity is None:
        return _failure(original, entity_issues or ["当前文档不能唯一证明项目实体、TCMP、项目名、数据日期及唯一性。"])
    if entity_issues:
        return _failure(original, entity_issues, entity=entity)

    role = BASE if base_is_project else RELATED if lineage else ""
    if not role:
        return _failure(original, ["明细字段来源未能完整追溯到项目表 TCMP，不能退回明细驱动。"], entity=entity)
    if len(lineage) > 1:
        return _failure(original, ["多个明细字段都能映射项目 TCMP，项目关联键不唯一。"], entity=entity)
    if requested is not None and requested["table_role"] != role:
        return _failure(original, [], unsupported=["模型声明的项目驱动侧与文档字段归属不一致。"], entity=entity)
    if role == RELATED and isinstance(raw_join, dict) and not join_is_project:
        return _failure(
            original, [], entity=entity,
            unsupported=["当前比较已使用另一张非项目表，再接入项目表将超过两表能力，不能丢弃原条件或项目维度。"],
        )

    candidate = deepcopy(original)
    version = requested["version"] if preserve_version and requested else DRIVER_VERSION
    candidate["project_driver"] = {"version": version, "table_role": role}
    code = _field_name(entity["code"])
    name = _field_name(entity["name"])
    project_day = _field_name(entity["date"])

    try:
        if role == BASE:
            candidate["project_context"] = {
                "mode": BASE, "code_field": code, "name_field": name, "confirmed": True,
            }
            candidate["report_date_field"] = project_day
            if raw_join is not None:
                if not isinstance(raw_join, dict):
                    raise ValueError("项目明细关联结构无效。")
                detail = _resolve_source_table(str(raw_join.get("table_name") or ""), lookup)
                if detail is None or _table_id(detail) == _table_id(base_table):
                    raise ValueError("项目明细关联表不是当前文档中的唯一真实表。")
                detail_fields = fields_by_table.get(_table_id(detail)) or []
                detail_lineage = _lineage_fields(detail, detail_fields, entity, fields_by_table, lookup)
                if len(detail_lineage) != 1:
                    raise ValueError("项目与明细之间缺少唯一、完整的 TCMP 来源链。")
                detail_day = next((item for item in detail_fields
                                   if _field_name(item) == raw_join.get("report_date_field")
                                   and _period_field(item)), None)
                if detail_day is None:
                    raise ValueError("明细关联日期不是已证明的数据日期 DATE 字段。")
                required_pair = {"left": code, "right": _field_name(detail_lineage[0])}
                date_pair = {"left": project_day, "right": _field_name(detail_day)}
                if not _valid_join_shape(raw_join, required_pair, date_pair):
                    raise ValueError("项目驱动 ON 只允许已证明的 TCMP 对及可重复数据日期对。")
                aggregate = raw_join.get("right_aggregate") == "sum"
                candidate["join"] = {
                    **deepcopy(raw_join), "relationship_confirmed": True,
                    "unmatched_policy": "review" if aggregate and raw_join.get("unmatched_policy") != "exclude" else "exclude",
                }
        else:
            detail_day = _selected_period(candidate, base_fields)
            if detail_day is None:
                raise ValueError("明细表缺少唯一、已证明的数据日期 DATE 字段。")
            detail_code = _field_name(lineage[0])
            required_pair = {"left": detail_code, "right": code}
            date_pair = {"left": _field_name(detail_day), "right": project_day}
            if raw_join is not None:
                if not isinstance(raw_join, dict) or raw_join.get("right_aggregate") is not None:
                    raise ValueError("related 项目驱动不支持 SUM 或无效关联。")
                if not _valid_join_shape(raw_join, required_pair, date_pair):
                    raise ValueError("项目驱动 ON 只允许已证明的 TCMP 对及可重复数据日期对。")
            join = {
                "table_name": str(entity["table"]["table_name"]),
                "on": deepcopy(raw_join["on"]) if isinstance(raw_join, dict) else [required_pair],
                "report_date_field": project_day,
                "relationship_confirmed": True,
                "unmatched_policy": "exclude",
            }
            candidate["join"] = join
            candidate["report_date_field"] = _field_name(detail_day)
            candidate["project_context"] = {
                "mode": "lookup", "code_field": detail_code, "name_field": name,
                "table_name": str(entity["table"]["table_name"]), "key": required_pair,
                "date_field": project_day, "unique_evidence": deepcopy(entity["evidence"]),
                "confirmed": True,
            }
            mapping = _direct_project_mapping(base_fields, entity, lookup)
            _remap_filters(candidate, base_fields, entity, mapping)
            _validate_scope_mapping(candidate, base_fields, entity, mapping)
            candidate["_project_field_mapping"] = mapping

        if requested is not None and original.get("project_context") is not None:
            if normalize_project_context(original["project_context"]) != normalize_project_context(candidate["project_context"]):
                raise ValueError("已声明的项目上下文与唯一项目实体或 TCMP 来源不一致。")
        if not preserve_version and candidate.get("join"):
            # The project template already adds the same-period match. Normalize only
            # new drafts; stored versions must retain their exact SQL and hashes.
            candidate["join"]["on"] = [required_pair]
        validate_project_driver(candidate)
    except (ValueError, AppError) as exc:
        message = str(exc) or "项目驱动结构与文档证据不一致。"
        return _failure(original, [message], entity=entity)

    mapping = candidate.pop("_project_field_mapping", {})
    return {
        "definition": candidate,
        "involved": True,
        "project_table": entity["table"],
        "project_fields": list(entity["fields"]),
        "field_mapping": mapping,
        "uncertainties": [],
        "unsupported_requirements": [],
    }


def resolve_project_driver(
    definition: dict[str, Any],
    base_table: dict[str, Any],
    base_fields: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    fields_by_table: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Strictly revalidate a marked definition for preview/save; never auto-convert."""
    bound = bind_project_driver(
        definition, base_table, base_fields, tables, fields_by_table, required=True, preserve_version=True,
    )
    expected = bound["definition"]
    if (bound["uncertainties"] or bound["unsupported_requirements"]
            or "project_driver" not in expected):
        _fail()
    for key in ("project_driver", "project_context", "join", "report_date_field", "filters"):
        if definition.get(key) != expected.get(key):
            _fail()
    join = definition.get("join")
    related_fields = []
    if isinstance(join, dict):
        related = next((item for item in tables if item.get("table_name") == join.get("table_name")), None)
        if related is None:
            _fail()
        related_fields = fields_by_table.get(_table_id(related)) or []
    validate_project_driver_columns(definition, base_fields, related_fields or None)
    return {
        "context": normalize_project_context(definition["project_context"]),
        "project_table": bound["project_table"],
        "project_fields": list(bound["project_fields"]),
    }
