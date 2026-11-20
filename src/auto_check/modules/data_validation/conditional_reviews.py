"""Ground named conditional null checks and turn documented field alternatives into choices."""
from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
import re
from typing import Any, Callable

from .parallel_checks import NONEMPTY_REQUIREMENT, contains_check_predicate, parse_mixed_group, parse_number_comparison, parse_numeric_group
from .query_spec import UNARY_OPS, type_family

_ENTITY = r"(?:信托)?(?:项目|产品|合同|客户|记录|账户|资产)"
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_NAMED_CATEGORY = (r"(?:请)?(?:检查|校验|核查)?(?:当|若|如果)?(?P<scope>\w{1,80}?)(?:等于|为|是)"
                   r"(?P<label>\w{1,80}?)")
_NAMED_WHEN = re.compile(_NAMED_CATEGORY + r"时[，,、：:]?(?P<check>.+)")
_NAMED_ENTITY = re.compile(_NAMED_CATEGORY + rf"的(?P<entity>{_ENTITY})(?:的|[，,、：:])(?P<check>.+)")
# A business category can qualify an entity without naming a physical column.
# Its meaning and complete set of codes must still come from that table's dictionary.
_CATEGORY_ENTITY = rf"(?:请)?(?:检查|核查|校验|针对)?(?P<label>[\w]{{1,40}}?(?:型|类))(?:的)?(?P<entity>{_ENTITY})"
_CATEGORY_CHECK = re.compile(_CATEGORY_ENTITY + r"(?:的|[，,：:])?(?P<check>.+)")
_NONEMPTY_SUBJECT = re.compile(rf"(?P<measure>\w{{1,80}}?){NONEMPTY_REQUIREMENT}(?P<rest>.*)")
_PLAIN_NULL = re.compile(rf"(?:请)?(?:检查|核查|校验)?(?P<term>\w{{1,80}}?){NONEMPTY_REQUIREMENT}")
_NULL_FIELD_REVIEW = "需确认「{}」对应的文档字段及非空检查"
_NUMERIC_NOUNS = ("净值", "余额", "金额", "数量", "比例", "比率", "利率", "收益率")
_HISTORICAL = re.compile(r"期初|上期|上月|上年|昨日|前期")
_FIELD_REVIEW_WORDS = (
    "需求 用户 要求 中 的 未明确 未指定 不明确 不确定 尚未 确定 具体 指 是 指的是 指代 使用 采用 哪个 哪一项 "
    "字段 还是 其中 或 或者 与 和 对应 备选 二选一 口径 可选 候选 请选择 请明确 "
    "需确认 待确认 待用户确认 需用户确认 请确认 需要确认 当前 暂 按 生成 规则 校验 建议 优先 "
    "可能 需明确 是否也需检查 是否还需检查 是否 以 为准 含义 列 文档 实际 所指"
)


def metric_choices(term: str, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return actual documented columns for this field term, with physical names taking precedence."""
    term = term.strip()
    if not term:
        return []
    physical = [field for field in fields if field["field_name"] == term]
    if physical:
        return physical
    numeric = term.endswith(_NUMERIC_NOUNS)
    broad = term in _NUMERIC_NOUNS
    matches, exact = [], []
    for field in fields:
        label = str(field.get("field_cn") or "").strip()
        # A documented reporting variant remains a distinct choice; keep its full label in the question.
        caption = re.sub(r"[_＿](?:人行|人民银行|监管报送)$", "", label)
        if not caption.endswith(term) or (numeric and type_family(field.get("data_type")) != "number"):
            continue
        if not broad and _HISTORICAL.search(caption.removesuffix(term)):
            continue
        matches.append(field)
        if label == term:
            exact.append(field)
    return matches if broad else exact or matches


def bind_document_metric_questions(candidate: dict, roles: dict, subject: str) -> None:
    """Ask once for a shared operand when the request names more than one documented field."""
    expression = candidate.get("expression") or {}
    group = expression.get("conditions")
    parsed = parse_mixed_group(subject) or parse_numeric_group(subject)
    anchors = parsed[1] if parsed else []
    if not anchors:
        single = parse_number_comparison(subject)
        if single and len(single[0]) == 1:
            anchors = [(single[0][0], single[1], single[2])]
    if group is None and not anchors:
        return
    questions = candidate.setdefault("questions", [])
    named_fields = set(_IDENTIFIER.findall(subject))
    shared = {}
    for index, item in enumerate(group if isinstance(group, list) else [expression]):
        sides = ("left",) if item.get("right_type") == "value" or item.get("op") in ("is_null", "is_not_null") else ("left", "right")
        for side in sides:
            table = item.get("right_table", "base") if side == "right" else "base"
            fields = roles.get(table, [])
            selected = next((f for f in fields if f["field_name"] == item.get(side)), None)
            if not selected:
                continue
            caption = str(selected.get("field_cn") or "").strip()
            if selected["field_name"] in named_fields:
                continue
            target = f"expression.conditions.{index}.{side}" if group is not None else f"expression.{side}"
            terms = {term for term, op, value in anchors if side == "left" and (op in UNARY_OPS or item.get("right_type") == "value")
                     and item.get("op") == op and item.get("right") == value}
            term = next(iter(terms)) if len(terms) == 1 else next(
                (caption[i:] for i in range(len(caption) - 1) if caption[i:] in subject), ""
            )
            options = [f for f in metric_choices(term, fields)
                       if type_family(f.get("data_type")) == type_family(selected.get("data_type"))]
            if len(options) < 2 or selected not in options:
                continue
            existing = next((q for q in questions if target == q["id"] or target in q.get("targets", [])), None)
            key = (side, table, term)
            question = existing or shared.get(key)
            if question is None:
                text = f"这里的「{term}」指哪个字段？"
                question = {"id": target, "text": text, "uncertainty": text}
                questions.append(question)
                candidate.setdefault("uncertainties", []).append(text)
            shared[key] = question
            question["options"] = [{"value": f["field_name"], "label": f"{f['field_cn']}（{f['field_name']}）"}
                                   for f in options]
            if group is not None:
                targets = question.setdefault("targets", [question["id"]])
                if target not in targets:
                    targets.append(target)


def plain_null_check(request: str, fields: list[dict[str, Any]]) -> ConditionalNullCheck | None:
    """Recognize an unqualified nonempty requirement, never a clause with an additional scope."""
    match = _PLAIN_NULL.fullmatch(re.sub(r"\s+", "", request).rstrip("。.!！"))
    if not match or contains_check_predicate(match["term"]):
        return None
    term = match["term"]
    measures = metric_choices(term, fields)
    # Unknown terms and scopes still need the existing semantic and relationship grounding paths.
    if not measures:
        return None
    return ConditionalNullCheck("", "", term, [], measures, "")


def category_scope_only(request: str) -> re.Match | None:
    return re.fullmatch(_CATEGORY_ENTITY, re.sub(r"\s+", "", request).rstrip("。.!！?？"))


@dataclass
class ConditionalNullCheck:
    scope: str
    label: str
    term: str
    selections: list[dict[str, Any]]
    measures: list[dict[str, Any]]
    extra: str
    entity: str = ""
    dictionary_entries: dict[str, list[dict[str, Any]]] = dataclass_field(default_factory=dict)

    @property
    def scope_text(self) -> str:
        return self.label + self.entity if self.scope == self.entity else f"{self.scope}为{self.label}"

    def scope_question(self, fields: list[dict[str, Any]], proposed_filters=()) -> dict[str, Any] | None:
        if len(self.selections) < 2:
            return None
        names = {f["field_name"]: f.get("field_cn") or f["field_name"] for f in fields}
        options = []
        for index, selection in enumerate(self.selections):
            name = selection["field"]
            values = selection["value"] if selection["op"] == "in" else [selection["value"]]
            codes = sorted(map(str, values))
            option = {"value": str(index), "label": f"{names[name]}（{name}），字典取值 {'、'.join(map(str, values))}",
                      "selection": selection}
            for raw in proposed_filters:
                if raw.get("table", "base") != "base" or raw.get("field") not in (name, names[name]) or raw.get("op") != selection["op"]:
                    continue
                proposed = raw.get("value")
                proposed_values = proposed if isinstance(proposed, list) else [proposed]
                if sorted(map(str, proposed_values)) == codes:
                    option["tag"] = "模型建议"
                    break
            options.append(option)
        text = f"「{self.scope_text}」采用哪个筛选字段？"
        return {"id": "filters.0", "text": text, "uncertainty": text, "options": options}

    def coverage_issue(self, candidate: dict[str, Any]) -> str:
        if not self.term:
            return f"已指定「{self.scope_text}」的范围，请补充要检查的字段和异常条件。"
        if self.scope and not self.selections:
            return f"当前文档未能唯一核实「{self.scope_text}」的字段与完整字典取值。"
        if self.extra:
            return f"还需核对需求中的附加条件「{self.extra}」，才能生成完整预览。"
        if candidate.get("join"):
            return "这项非空检查的范围和字段都来自主表，请核对额外关联是否改变检查范围。"
        expression = candidate.get("expression") or {}
        if expression.get("op") != "is_null" or expression.get("left") not in {
                field["field_name"] for field in self.measures}:
            return _NULL_FIELD_REVIEW.format(self.term) + "。"
        return self.filter_issue(candidate)

    def filter_issue(self, candidate: dict[str, Any]) -> str:
        filters = candidate.get("filters") or []
        if not self.scope:
            return "这项非空检查未指定筛选范围，请核对附加条件。" if filters else ""
        if len(filters) == 1:
            current = filters[0]
            for selection in self.selections:
                if (current.get("table", "base") != "base"
                        or any(current.get(key) != selection[key] for key in ("field", "op"))):
                    continue
                value, expected = current.get("value"), selection["value"]
                if value == expected or (isinstance(expected, list) and isinstance(value, list)
                                         and len(expected) == len(value) and all(item in value for item in expected)):
                    return ""
        return f"需求中的「{self.scope_text}」尚未落实到完整筛选条件。"


def _matches_subject(subject: str, alias: str) -> bool:
    if not alias:
        return False
    entity = re.match(_ENTITY, alias)
    name = alias[entity.end():].removeprefix("的") if entity else alias
    forms = {name}
    # A separated modifier in the document is a meaningful part of the name.
    # It can precede the noun in speech. Keep both words and the owning entity.
    parts = re.fullmatch(r"([^_（）()]+?)(?:_([^_（）()]+)|[（(]([^_（）()]+)[）)])", name)
    if parts:
        noun, modifier = parts[1], parts[2] or parts[3]
        forms.update((noun + modifier, modifier + noun, modifier + "的" + noun))
    requested_entity = re.match(_ENTITY, subject)
    if requested_entity and entity and requested_entity[0] != entity[0]:
        return False
    unqualified = subject[requested_entity.end():].removeprefix("的") if requested_entity else subject
    return subject == alias or unqualified in forms


def documented_dictionary_group(field: dict[str, Any], term: str, parse: Callable) -> list[dict[str, Any]]:
    # Check every line, independent of the model's proposed values or the normal UI display limit.
    selected = {}
    labels = {}
    for line in re.split(r"[\n\r；;]+", str(field.get("dictionary") or "")):
        line = line.strip()
        if not line or re.fullmatch(r"【[^】]+】|\[[^\]]+\]", line):
            continue
        options = parse({**field, "dictionary": line})
        if len(options) != 1:
            return []
        value, label = options[0]["value"], options[0]["label"]
        if value in labels and labels[value] != label:
            return []
        labels[value] = label
        if term not in label:
            continue
        if re.search(r"(?:非|不属于|不含|不包括|不是|未|无|除外)" + re.escape(term), label):
            continue
        if not label.endswith(term) or re.search(r"非|不|未|排除|除外|以及|兼有|或|[/、]", label[:-len(term)]):
            return []
        selected[value] = label
    return [{"value": code, "label": name} for code, name in selected.items()] if len(selected) <= 50 else []


def _scope_parts(request: str) -> re.Match | None:
    text = re.sub(r"\s+", "", request).rstrip("。.!！")
    return _NAMED_WHEN.fullmatch(text) or _NAMED_ENTITY.fullmatch(text) or _CATEGORY_CHECK.fullmatch(text) or category_scope_only(text)


def _document_scope(match: re.Match, fields: list[dict[str, Any]], parse_dictionary: Callable,
                    dimension: str) -> ConditionalNullCheck:
    entity = match.groupdict().get("entity") or ""
    named = match.groupdict().get("scope") or ""
    scope, label = named or entity, match["label"]
    if named:
        exact = [f for f in fields if scope in {f["field_name"], f.get("field_cn")}]
        matches = exact or [f for f in fields if _matches_subject(scope, str(f.get("field_cn") or ""))]
        if entity:
            scoped = []
            for field in matches:
                owner = re.match(_ENTITY, str(field.get("field_cn") or ""))
                if owner and owner[0].removeprefix("信托") != entity.removeprefix("信托") and not named.startswith(owner[0]):
                    continue
                if ((owner and owner[0].removeprefix("信托") == entity.removeprefix("信托"))
                        or dimension.strip().removeprefix("信托") == entity.removeprefix("信托")):
                    scoped.append(field)
            matches = scoped
    else:
        matches = []
        for field in fields:
            owner = re.match(_ENTITY, str(field.get("field_cn") or ""))
            if ((owner and owner[0].removeprefix("信托") == entity.removeprefix("信托"))
                    or (not owner and dimension.strip().removeprefix("信托") == entity.removeprefix("信托"))):
                matches.append(field)
    selections = []
    dictionary_entries = {}
    for field in matches:
        entries = documented_dictionary_group(field, label, parse_dictionary)
        if not entries:
            if not named:
                continue
            selections = []
            dictionary_entries = {}
            break
        dictionary_entries[field["field_name"]] = entries
        values = [item["value"] for item in entries]
        selections.append({"table": "base", "field": field["field_name"], "confirmed": True,
                           "op": "in" if len(values) > 1 else "eq", "value": values if len(values) > 1 else values[0]})
    return ConditionalNullCheck(scope, label, "", selections, [], "", entity, dictionary_entries)


def _review_clauses(text: str, separators: str) -> list[str]:
    """Keep examples such as (A—label, B—label) attached to the question they qualify."""
    parts = []
    start = depth = 0
    for pos, char in enumerate(text):
        if char in "（(":
            depth += 1
        elif char in "）)" and depth:
            depth -= 1
        elif not depth and char in separators:
            parts.append(text[start:pos])
            start = pos + 1
    return [part for part in [*parts, text[start:]] if part.strip()]


def _dictionary_text(text: str) -> str:
    return re.sub(r"""[\s"'“”‘’「」`]+""", "", text).translate(str.maketrans("（）：，；", "():,;"))


def _exact_dictionary_list(text: str, entries: list[dict[str, Any]]) -> bool:
    """Consume the whole assertion; every cited label must belong to its adjacent code."""
    spellings = {}
    for index, entry in enumerate(entries):
        code = str(entry["value"])
        codes = {code}
        if isinstance(entry["value"], float) and entry["value"].is_integer():
            codes.add(str(int(entry["value"])))
        label = _dictionary_text(entry["label"])
        for code in codes:
            spellings.setdefault(code, set()).add(index)
            for sep in ("", "=", "-", "—", ":", "－"):
                spellings.setdefault(f"{code}{sep}{label}", set()).add(index)
            spellings.setdefault(f"{code}({label})", set()).add(index)
            spellings.setdefault(f"{label}({code})", set()).add(index)
    items = sorted(spellings, key=len, reverse=True)
    seen = set()
    while text:
        token = next((token for token in items if text.startswith(token)), "")
        if not token or len(spellings[token]) != 1:
            return False
        index = next(iter(spellings[token]))
        if index in seen:
            return False
        seen.add(index)
        text = text[len(token):]
        if text:
            delimiter = re.match(r"以及|或者|并且|[、,和或及与/]", text)
            if not delimiter or delimiter.end() == len(text):
                return False
            text = text[delimiter.end():]
    return len(seen) == len(entries)


def _check_subject(match: re.Match) -> str:
    subject = match.groupdict().get("check") or ""
    return re.sub("^" + _ENTITY + "的", "", subject) if match.re is _NAMED_WHEN else subject


def conditional_null_check(request: str, fields: list[dict[str, Any]], parse_dictionary: Callable,
                           *, dimension: str = "") -> ConditionalNullCheck | None:
    match = _scope_parts(request)
    if not match:
        return None
    subject = _check_subject(match)
    requirement = _NONEMPTY_SUBJECT.fullmatch(subject)
    if subject and (not requirement or contains_check_predicate(requirement["measure"])):
        return None
    scope = _document_scope(match, fields, parse_dictionary, dimension)
    if requirement:
        scope.term = requirement["measure"]
        scope.measures = metric_choices(scope.term, fields)
        scope.extra = requirement["rest"]
    return scope


@dataclass
class CategoryNumericCheck:
    scope: ConditionalNullCheck
    subject: str
    logic: str
    comparisons: list[tuple[str, str, int | float | None]]
    metric_options: dict[str, list[dict[str, Any]]]

    @property
    def term(self) -> str:
        return "、".join(self.metric_options)

    @property
    def measures(self) -> list[dict[str, Any]]:
        # Existing callers seed the first operand only when every operand can be bound.
        return next(iter(self.metric_options.values())) if all(self.metric_options.values()) else []

    def expression(self, name: str) -> dict[str, Any]:
        operands = {term: choices[0]["field_name"] for term, choices in self.metric_options.items()}
        operands[self.comparisons[0][0]] = name
        conditions = [{"left": operands[term], "op": op} if op in UNARY_OPS else
                      {"left": operands[term], "op": op, "right_type": "value", "right": value} for term, op, value in self.comparisons]
        return {"logic": self.logic, "conditions": conditions} if self.logic else conditions[0]

    def coverage_issue(self, candidate: dict[str, Any]) -> str:
        if candidate.get("join"):
            return "请核实附加关联对分类范围和指标的影响。"
        return self.expression_issue(candidate.get("expression")) or self.scope.filter_issue(candidate)

    def expression_issue(self, expression: Any) -> str:
        for term, choices in self.metric_options.items():
            if not choices:
                return f"请确认「{term}」对应的文档字段。"
        if not isinstance(expression, dict):
            return f"请按需求完整保留「{self.term}」的比较条件。"
        conditions = expression.get("conditions") if self.logic else [expression]
        if (self.logic and (expression.get("logic") != self.logic or set(expression) != {"logic", "conditions"})
                or not isinstance(conditions, list)
                or len(conditions) != len(self.comparisons)):
            return f"请按需求完整保留「{self.term}」的比较条件。"
        unmatched = []
        for item in conditions:
            if not isinstance(item, dict) or not isinstance(item.get("left"), str) or not isinstance(item.get("op"), str):
                return f"请按需求完整保留「{self.term}」的比较条件。"
            if item.get("op") in UNARY_OPS:
                complete = set(item) == {"left", "op"}
            else:
                complete = (item.get("right_type") == "value" and type(item.get("right")) in (float, int)
                            and item.get("right_table", "base") == "base"
                            and not set(item).difference({"left", "op", "right", "right_type", "right_table"}))
            if not complete:
                return f"请按需求核对「{self.term}」的比较方向和阈值。"
            unmatched.append((item["left"], item["op"], item.get("right")))
        # Bind each named metric consistently across its own predicates, even after the user reorders branches.
        for term, choices in sorted(self.metric_options.items(), key=lambda pair: len(pair[1])):
            predicates = [(op, value) for check_term, op, value in self.comparisons if check_term == term]
            for choice in choices:
                available = unmatched.copy()
                for op, value in predicates:
                    expected = (choice["field_name"], op, value)
                    if expected not in available:
                        break
                    available.remove(expected)
                else:
                    unmatched = available
                    break
            else:
                return f"请按需求核对「{term}」的比较字段、方向和阈值。"
        return ""

    def bind_questions(self, candidate: dict[str, Any], fields: list[dict[str, Any]], draft: dict[str, Any],
                       *, document_scope: str = "") -> bool:
        selections = self.scope.selections
        candidate["filters"] = [{**selections[0], "confirmed": len(selections) == 1}] if selections else []
        scope_fields = {item["field"] for item in selections}
        scope_labels = {field.get("field_cn") for field in fields if field["field_name"] in scope_fields}
        for raw in draft.get("filters") or []:
            if (raw.get("table", "base") == "base" and isinstance(raw.get("field"), str)
                    and raw["field"] in scope_fields | scope_labels
                    and raw.get("op") in ("eq", "in")):
                continue
            # A further proposed predicate must stay visible and must not narrow the
            # request silently. Its scope needs independent confirmation.
            candidate["filters"].append({**raw, "confirmed": False})
        questions = candidate.setdefault("questions", [])
        bind_document_metric_questions(candidate, {"base": fields}, self.subject)
        question = self.scope.scope_question(fields, draft.get("filters") or [])
        if question:
            questions.append(question)
        problem = self.coverage_issue(candidate)
        if problem:
            candidate["status"] = "needs_clarification"
            candidate["preview_error"] = problem
        table = (draft.get("target") or {}).get("table") or ""
        reviews = list(candidate.get("uncertainties", []))
        if reviews and not problem:
            evidence = BoundReviewEvidence(self, fields, table, document_scope)
            reviews = [residual for note in reviews if (residual := evidence.remaining(note))]
        reviews = unresolved_identity_reviews(self.scope, self.term, self.measures, fields, reviews, table)
        if problem:
            reviews.append(problem)
        reviews.extend(q["uncertainty"] for q in questions if q.get("uncertainty"))
        candidate["uncertainties"] = list(dict.fromkeys(reviews))
        return not problem


class BoundReviewEvidence:
    """Match complete statements to the document and the field/range decisions they concern."""

    def __init__(self, check: CategoryNumericCheck | ConditionalNullCheck, fields: list[dict[str, Any]], table: str,
                 document_scope: str):
        self.check = check
        self.scope = check.scope if isinstance(check, CategoryNumericCheck) else check
        self.table = table
        self.fields = fields
        self.scope_names = {item["field"] for item in self.scope.selections}
        self.metric_families = {type_family(f.get("data_type")) for f in check.measures}
        self.aliases = {}
        for index, field in enumerate(fields):
            label, name = field.get("field_cn"), field["field_name"]
            for alias in (name, label, f"{table}.{name}", f"{table}中{name}"):
                if alias:
                    self.aliases.setdefault(alias, set()).add(index)
        self.alias_pattern = re.compile("|".join(re.escape(key) for key in sorted(self.aliases, key=len, reverse=True)))
        scope_fields = [f for f in fields if f["field_name"] in self.scope_names]
        self.scope_captions = {f.get("field_cn") for f in scope_fields if f.get("field_cn")}
        scope_context = [document_scope, *(str(f.get("logic") or "") for f in [*scope_fields, *check.measures])]
        scope_context.extend(str(f["logic"]) for f in fields if f.get("logic")
                             and re.search(r"校验|核查|核验|核对", str(f["logic"])))
        self.document_restrictions = [part for text in scope_context for part in re.split(r"[。；;，,\n]", text)
                                      if re.search(r"排除|剔除|不纳入|不包括|不得纳入|仅纳入|仅限|除.+外", part)]
        self.dictionary_questions = []
        category = re.escape(self.scope.label)
        for name, entries in self.scope.dictionary_entries.items():
            field = next(f for f in fields if f["field_name"] == name)
            refs = {name, f"{table}.{name}"}
            caption = field.get("field_cn")
            if caption and len(self.aliases[caption]) == 1:
                refs.add(caption)
            if self.scope.scope != self.scope.entity and len(self.scope_names) == 1:
                refs.add(self.scope.scope)
            field_ref = "(?:" + "|".join(re.escape(r) for r in sorted(refs, key=len, reverse=True)) + ")"
            codes = r"(?:字典)?(?:码值|取值|代码|编码)"
            which = rf"(?:哪些|哪几个|哪个|何种){codes}"
            belongs = r"(?:属于|对应|代表|表示|视为|归为|归入)"
            inquiry = rf"(?:字段)?{field_ref}(?:字段|列)?(?:中|里|的)?{which}{belongs}{category}"
            reverse = rf"{category}(?:在(?:字段)?{field_ref}(?:字段)?中|对应的(?:字段)?{field_ref})(?:对应)?(?:的)?{which}"
            question = re.compile(rf"(?:需要?|尚需|还需|请|待)?(?:确认|核对|核实|明确)?(?:{inquiry}|{reverse})[?？]?")
            self.dictionary_questions.append((question, entries))

    def _cited_entries_match(self, tail: str, entries: list[dict[str, Any]]) -> bool:
        if not tail:
            return True
        term = re.escape(self.scope.label)
        # A cited list and a proposed classification are independent assertions. Both
        # must cover the complete group; one correct list cannot excuse an incorrect one.
        conclusion = re.search(rf"(?:是否)?(?:均|都|皆)?(?:应)?(?:视为|属于|归为|归入|对应|代表|表示){term}[?？]?$", tail)
        if conclusion:
            before = tail[:conclusion.start()]
            question = re.search(r"(?:^|[,;])是否", before)
            cited, proposed = (before[:question.start()], before[question.end():]) if question else ("", before)
            if not _exact_dictionary_list(proposed, entries):
                return False
            tail = cited
        if not tail:
            return True
        cited = re.sub(r"^(?:当前|已导入)?(?:文档|字典)(?:中|内)?"
                       r"(?:线索|取值|码值|列出|给出|显示|说明|条目)?(?:为|是|:)?", "", tail)
        return _exact_dictionary_list(cited, entries)

    def remaining_dictionary_review(self, note: str) -> str:
        """Answer a membership inquiry from its actual field's complete dictionary, preserving other clauses."""
        if not self.dictionary_questions or "哪" not in note:
            return note
        remaining = []
        changed = False
        for sentence in _review_clauses(note, "。\n"):
            # A parenthesis immediately after the question introduces supporting
            # statements. Parentheses within a code/label pair remain part of that pair.
            parts = []
            for part in _review_clauses(sentence, "，,；;"):
                opening = next((m.start() for m in re.finditer("[（(]", part)
                                if any(q.fullmatch(_dictionary_text(part[:m.start()])) for q, _ in self.dictionary_questions)), None)
                if opening is not None and part.rstrip().endswith((")", "）")):
                    parts.extend([part[:opening], *_review_clauses(part[opening + 1:].rstrip()[:-1], "，,;；")])
                else:
                    parts.append(part)
            i = 0
            while i < len(parts):
                head = _dictionary_text(parts[i])
                entries = next((items for question, items in self.dictionary_questions if question.fullmatch(head)), None)
                if entries is None:
                    remaining.append(parts[i].strip())
                    i += 1
                    continue
                end = i + 1
                while end < len(parts):
                    part = _dictionary_text(parts[end])
                    if not (re.match(r"^(?:当前|已导入)?(?:字典|文档)|^(?:是否)?[A-Za-z0-9+-]", part)
                            or any(part.startswith(str(item["value"])) for item in entries)):
                        break
                    end += 1
                if self._cited_entries_match(_dictionary_text(",".join(parts[i + 1:end])), entries):
                    changed = True
                else:
                    remaining.extend(parts[i:end])
                i = end
        return "；".join(remaining) if changed else note

    def _tokens(self, text: str) -> str:
        def substitute(match):
            indices = self.aliases[match[0]]
            return f"@{next(iter(indices))}@" if len(indices) == 1 else match[0]
        return self.alias_pattern.sub(substitute, text)

    def _metric_statement(self, clause: str, prior: str) -> bool:
        term = re.escape(self.check.term)
        # A bare term is the user's requested concept. Keep it distinguishable
        # from a longer document label which merely contains that concept.
        tokens = self._tokens(clause)
        ref = re.search(r"@(\d+)@", tokens)
        if ref:
            field = self.fields[int(ref[1])]
            if type_family(field.get("data_type")) not in self.metric_families:
                return False
            token = re.escape(ref[0])
            one_field = rf"{token}(?:{token})?"
            # Proves the quoted physical field and caption refer to the same actual column.
            fact = re.fullmatch(rf"{token}(?:为|是|对应|表示){token}", tokens)
            adopted = re.fullmatch(rf"(?:本|当前)?(?:规则|校验)?(?:采用|使用|选择){one_field}", tokens)
            additional = re.fullmatch(rf"(?:请确认)?是否(?:还|也)?需(?:要)?(?:核查|检查|校验){one_field}", tokens)
            equivalent = re.fullmatch(rf"{one_field}(?:也|还)?(?:可能)?(?:被理解为|代表|指代|即为|是指){term}", tokens)
            return bool(fact or equivalent or ((adopted or additional) and field in self.check.measures))
        if re.fullmatch(rf"(?:需求中?的?)?{term}(?:字段|指标|口径)(?:尚未|没有|未)(?:明确)?(?:指定|说明|明确)", clause):
            return True
        return prior == "metric" and bool(re.fullmatch(
            rf"(?:是否|能否)(?:即为|等同于|是指|代表|理解为){term}(?:仍?需(?:要)?确认)?", clause))

    def _scope_fact(self, clause: str) -> bool:
        scope = self.scope
        for selection in scope.selections:
            name = selection["field"]
            prefix = rf"(?:{re.escape(scope.label)}(?:的)?(?:{re.escape(scope.entity)})?)?"
            role = r"(?:(?:的)?(?:判定|判断|识别|筛选|分类))?(?:的)?(?:字段|依据|口径)?"
            match = re.fullmatch(prefix + role + rf"(?:为|是|使用|采用)?(?:{re.escape(self.table)}\.)?"
                                 + re.escape(name) + r"(?:的)?(?:字典)?(?:取值|码值|编码|代码)?(?:为|是|等于)(.+)", clause)
            if not match:
                continue
            values = selection["value"] if selection["op"] == "in" else [selection["value"]]
            stated = re.split(r"或者|或|和|及|与|、", match[1])
            if sorted(stated) == sorted(str(value) for value in values):
                return True
        return False

    def _missing_dictionary_entry(self, clause: str) -> bool:
        """A missing-code question is answered only by the requested label in this exact field's dictionary."""
        for field in self.fields:
            if field["field_name"] not in self.scope_names:
                continue
            aliases = {field["field_name"], f"{self.table}.{field['field_name']}", str(field.get("field_cn") or "")}
            if self.scope.scope != self.scope.entity:
                aliases.add(self.scope.scope)
            ref = "(?:" + "|".join(re.escape(v) for v in sorted(aliases, key=len, reverse=True) if v) + ")"
            label = re.escape(self.scope.label)
            identity = rf"{ref}(?:字段|列)?(?:{ref})?(?:中|里|内|的)?(?:的)?{label}"
            value = r"(?:所?对应)?(?:的)?(?:具体|完整|实际)?(?:字典)?(?:码值|编码|代码|取值)"
            missing = r"(?:尚?未|没有)(?:在(?:当前|活动)?(?:文档|字典)中?)?(?:明确|列出|提供|给出|说明|记载)"
            if re.fullmatch(identity + value + missing, clause):
                return True
        return False

    def _unspecified_exclusion(self, clause: str) -> bool:
        captions = [re.escape(caption) for caption in self.scope_captions]
        categories = "|".join([*captions, "状态", "类型", "类别", "情形", "取值"])
        match = re.fullmatch(r"(?:需要?|请|待)?(?:确认|明确|核对)?是否(?:还|仍|另外)?(?:需要?)?"
                             rf"(?:排除|剔除|过滤)(?:其他|其它)(?:特殊)?(?P<kind>{categories})", clause)
        if not match:
            return False
        # An upstream exclusion of a different product or project does not imply
        # a status exclusion. Preserve instructions about the actual scope dimension.
        kind = match["kind"]
        tokens = {kind, *(f["field_name"] for f in self.fields if kind in str(f.get("field_cn") or ""))}
        if kind in self.scope_captions or kind == "取值":
            tokens.update(self.scope_names)
            tokens.update(self.scope_captions)
        return not any(re.search(r"校验|核查|核验|核对", part) or any(token in part for token in tokens)
                       for part in self.document_restrictions)

    def remaining(self, note: str) -> str:
        if "@" in note:
            return note
        note = self.remaining_dictionary_review(note)
        result = []
        changed = False
        for sentence in re.split(r"[；;。\n]", note):
            if isinstance(self.check, CategoryNumericCheck) and any(op == "is_null" for _, op, _ in self.check.comparisons):
                # Earlier candidates could persist the unary fallback's own diagnostic with a whole predicate as its field.
                # Only that generated diagnostic, for this request's actual complete compound check, is superseded.
                legacy = re.fullmatch(_NULL_FIELD_REVIEW.format(r"(.+)"), sentence.strip())
                if (legacy and contains_check_predicate(legacy[1])
                        and re.fullmatch(re.escape(legacy[1]) + NONEMPTY_REQUIREMENT, self.check.subject)):
                    changed = True
                    continue
            prior = ""
            for raw in re.split(r"[，,]", sentence):
                clause = re.sub(r"""[\s"'“”‘’「」`]+""", "", raw)
                clause = re.sub(r"^(?:但是|但|且)", "", clause).rstrip("？?")
                if not clause:
                    continue
                if self._scope_fact(clause) or self._missing_dictionary_entry(clause):
                    prior = "scope"
                elif self._metric_statement(clause, prior):
                    prior = "metric"
                elif prior == "scope" and (self._unspecified_exclusion(clause)
                        or re.fullmatch(r"(?:已)?按(?:此|该)(?:范围|口径)(?:执行|筛选|校验)", clause)):
                    pass
                elif prior and re.fullmatch(r"(?:请|需要?|待)?(?:进一步|再次|人工)?(?:确认|核实|核对)", clause):
                    pass
                else:
                    prior = ""
                    result.append(raw.strip())
                    continue
                changed = True
        return "；".join(result) if changed else note

    def apply_answers(self, definition: dict[str, Any]) -> None:
        """Reconcile old reviews only after the saved answers identify the operands now in the rule."""
        if (definition.get("questions") or self.check.coverage_issue(definition)
                or not all(item.get("confirmed") is True for item in definition.get("filters") or [])):
            return
        notes = definition.get("uncertainties") or []
        answers = definition.get("uncertainty_resolutions") or []
        pairs = [(note, answers[i] if i < len(answers) else "") for i, note in enumerate(notes)]
        if not any(not answer for _, answer in pairs):
            return
        expression = definition["expression"]
        metric = (expression["conditions"][0] if "conditions" in expression else expression)["left"]

        def answered(subject: str, chosen: str) -> bool:
            caption = next((f.get("field_cn") for f in self.fields if f["field_name"] == chosen), "")
            legacy = (f"已选择{caption}" if caption and sum(f.get("field_cn") == caption for f in self.fields) == 1 else None)
            labels = {chosen, f"{caption}（{chosen}）"}
            if chosen in self.scope_names:
                question = self.scope.scope_question(self.fields)
                labels.update(option["label"] for option in (question or {}).get("options", []) if option["selection"]["field"] == chosen)
            return any(subject in note and re.search(r"字段|指标|口径", note)
                       and (re.sub(r"^(?:明确选择|已选择)\s*", "", answer) in labels or answer == legacy)
                       for note, answer in pairs)

        if ((len(self.check.measures) > 1 and not answered(self.check.term, metric))
                or (len(self.scope_names) > 1 and not answered(self.scope.label, definition["filters"][0]["field"]))):
            return
        remaining = []
        resolutions = []
        for note, answer in pairs:
            residual = note if answer else self.remaining(note)
            if residual and not answer:
                unresolved = unresolved_identity_reviews(self.scope, self.check.term, self.check.measures,
                                                         self.fields, [residual], self.table)
                residual = "；".join(unresolved)
            if residual:
                remaining.append(residual)
                resolutions.append(answer)
        definition["uncertainties"] = remaining
        definition["uncertainty_resolutions"] = resolutions


def unresolved_identity_reviews(scope: ConditionalNullCheck, term: str, measures: list[dict[str, Any]],
                                fields: list[dict[str, Any]], notes: list[str], table: str) -> list[str]:
    # Resolve only a complete question about documented identities. E.g. using a different
    # documented metric removes the need to assume a proposed performance column means NAV.
    selections = scope.selections
    scope_names = {item["field"] for item in selections}
    families = {type_family(m.get("data_type")) for m in measures}
    scope_fields = [field for field in fields if field["field_name"] in scope_names]
    scope_terms = [scope.label, scope.scope, re.sub("^" + _ENTITY, "", scope.scope), *scope_names]
    scope_terms.extend(str(field.get("field_cn") or "") for field in scope_fields)
    dictionary_ids = [key for field in scope_fields
                      for key in re.findall(r"【([^】]+)】", str(field.get("dictionary") or ""))]
    sources = {(field["logic"], field.get("dictionary")) for field in scope_fields
               if re.fullmatch(r"直接取[^；;\n]+\[[A-Za-z_][A-Za-z_0-9]*\][。.]?", str(field.get("logic") or "").strip())}
    same_sources = [f for f in fields if (f.get("logic"), f.get("dictionary")) in sources]

    def identity_question(text: str) -> bool:
        scope_issue = any(word and word in text for word in scope_terms) and any(
            word in text for word in ("识别", "筛选", "判定", "字典", "码值", "取数逻辑"))
        metric_issue = term in text.replace(scope.label, "") and ("字段" in text or "代表" in text or "指" in text)
        if scope_issue and not selections:
            return False
        if not ((scope_issue and selections) or (metric_issue and measures)):
            return False
        refs = [f for f in fields if (scope_issue and f["field_name"] in scope_names)
                or (metric_issue and type_family(f.get("data_type")) in families)]
        literals = [term, scope.label, scope.entity]
        if scope_issue:
            literals.extend([*scope_terms, *dictionary_ids])
            for field in same_sources:
                literals.extend([field["field_name"], str(field.get("field_cn") or "")])
            if same_sources:
                literals.extend(["同值", "取数逻辑相同", "不影响"])
        for field in refs:
            literals.extend([field["field_name"], f"{table}.{field['field_name']}", str(field.get("field_cn") or "")])
        return _document_only(text, literals, _FIELD_REVIEW_WORDS +
                              " 其他 识别 判定 筛选 取值 码值 字典码值 字典码 字典 代表 其 且 分别 两者 均 按照 对 为"
                              " 未在 给出 提供 相关 需核对 对应的 缺少 无法 需 非空 已由 确认 但 该 存在")
    reviews = []
    for note in notes:
        parts = [part.strip() for part in re.split(r"[；;。\n]+", note) if part.strip()]
        kept = []
        changed = False
        for part in parts:
            if identity_question(part):
                changed = True
                continue
            clauses = re.split(r"[，,]", part)
            residual = [clause for clause in clauses if not identity_question(clause)]
            if len(residual) != len(clauses):
                changed = True
                kept.extend(residual)
            else:
                kept.append(part)
        if kept:
            reviews.append("；".join(kept) if changed else note)
    return reviews


def category_numeric_check(request: str, fields: list[dict[str, Any]], parse_dictionary: Callable,
                           *, dimension: str = "") -> CategoryNumericCheck | None:
    """A documented category and one metric with one or more fully stated numeric predicates."""
    match = _scope_parts(request)
    if not match:
        return None
    subject = _check_subject(match)
    group = parse_mixed_group(subject) or parse_numeric_group(subject)
    if group:
        logic, checks = group
    else:
        single = parse_number_comparison(subject)
        if not single or len(single[0]) != 1:
            return None
        logic, checks = "", [(single[0][0], single[1], single[2])]
    scope = _document_scope(match, fields, parse_dictionary, dimension)
    options = {}
    for term in dict.fromkeys(term for term, _, _ in checks):
        requires_number = any(subject_term == term and op not in UNARY_OPS for subject_term, op, _ in checks)
        options[term] = [field for field in metric_choices(term, fields)
                         if not requires_number or type_family(field.get("data_type")) == "number"]
    return CategoryNumericCheck(scope, subject, logic, checks, options)


def _document_only(text: str, literals: list[str], vocabulary: str) -> bool:
    """Match only a complete technical question. Unknown clauses remain reviewable."""
    words = sorted({word for word in [*literals, *vocabulary.split()] if word}, key=len, reverse=True)
    return not re.sub(r"""[\s，,。；;：:（）()“”‘’'"、？?]+|""" + "|".join(map(re.escape, words)), "", text)


def selector_field_choices(selection: dict[str, Any], fields: list[dict[str, Any]], request: str,
                           table: str) -> list[dict[str, Any]]:
    """Recheck the first-stage proposals using the request, actual labels, and compatible types."""
    by_name = {field["field_name"]: field for field in fields}
    result = []

    def add(term, names, side=None, recommended=None):
        if not isinstance(term, str) or len(term) < 2 or term not in request or not isinstance(names, list):
            return
        valid = {field["field_name"] for field in metric_choices(term, fields)}
        names = list(dict.fromkeys(name for name in names if isinstance(name, str) and name in valid))
        if len(names) < 2:
            return
        families = {type_family(by_name[name].get("data_type")) for name in names}
        if len(families) != 1 or not next(iter(families)):
            return
        result.append({"term": term, "fields": names, "side": side,
                       "recommended": recommended if recommended in names else None})

    typed = selection.get("field_choices")
    for choice in typed[:8] if isinstance(typed, list) else []:
        if isinstance(choice, dict) and choice.get("side") in ("left", "right"):
            add(choice.get("term"), choice.get("fields"), choice["side"], choice.get("recommended"))
    # Earlier templates return prose. A shared label in the user's own wording
    # provides evidence for alternatives, while a common character alone does not.
    notes = selection.get("uncertainties") or []
    for note in notes if isinstance(notes, list) else []:
        if not isinstance(note, str) or not re.search(r"字段|列|二选一|选择|备选|采用|使用", note):
            continue
        owners = re.findall(r"(?<![\w.])([A-Za-z_][A-Za-z_0-9]*)\.[A-Za-z_][A-Za-z_0-9]*", note, re.ASCII)
        if any(owner != table for owner in owners):
            continue
        identifiers = set(_IDENTIFIER.findall(note))
        refs = [f for name, f in by_name.items() if name in identifiers or (f.get("field_cn") and f["field_cn"] in note)]
        if len(refs) < 2:
            continue
        caption = str(refs[0].get("field_cn") or "")
        term = next((caption[i:] for i in range(len(caption) - 1) if caption[i:] in request
                     and all(str(f.get("field_cn") or "").endswith(caption[i:]) for f in refs)), "")
        add(term, [f["field_name"] for f in refs])
    return result


def bind_selector_choices(draft: dict[str, Any], choices: list[dict[str, Any]], fields: list[dict[str, Any]],
                          table: str) -> None:
    """Carry only choices for the draft's actual operand through to its ordinary field review."""
    expression = draft.get("expression")
    if not isinstance(expression, dict) or "conditions" in expression or draft.get("join"):
        return
    labels = {f["field_name"]: str(f.get("field_cn") or "") for f in fields}
    accepted = []
    for choice in choices:
        for side in ("left", "right"):
            if choice["side"] not in (None, side) or (side == "right" and expression.get("right_type", "field") != "field"):
                continue
            names = choice["fields"]
            if expression.get(side) not in [choice["term"], *names, *(labels[name] for name in names)]:
                continue
            if any(item["side"] == side for item in accepted):
                continue
            accepted.append({**choice, "side": side})
    if not accepted:
        return
    sides = {item["side"] for item in accepted}
    previous = draft.get("field_choices")
    previous = previous if isinstance(previous, list) else []
    draft["field_choices"] = [*accepted, *(c for c in previous if isinstance(c, dict) and c.get("side") not in sides)]
    # Keep unrelated clauses and all original text in stage judgments. Link only fully
    # documented field-choice questions to the choice that will replace their operand.
    notes = []
    for note in draft.get("uncertainties") or []:
        parts = [part.strip() for part in re.split(r"[；;。\n]+", note) if part.strip()]
        kept = []
        for part in parts:
            for choice in accepted:
                literals = [choice["term"]]
                names = choice["fields"]
                for name in names:
                    literals.extend([name, labels[name], f"{table}.{name}"])
                if (sum(name in _IDENTIFIER.findall(part) or labels[name] in part for name in names) >= 2
                        and _document_only(part, literals, _FIELD_REVIEW_WORDS + " 为")):
                    break
            else:
                kept.append(part)
        if kept:
            notes.append(note if len(kept) == len(parts) else "；".join(kept))
    draft["uncertainties"] = notes


def reconcile_field_choices(candidate: dict[str, Any], fields: list[dict[str, Any]], request: str) -> None:
    """Bind real, same-table alternatives cited by a model to the editable left operand."""
    existing = next((q for q in candidate.get("questions") or [] if q["id"] == "expression.left"), None)
    existing_names = {option["value"] for option in existing["options"]} if existing else set()
    expression = candidate.get("expression") or {}
    chosen = expression.get("left")
    current = next((field for field in fields if field["field_name"] == chosen), None)
    if not current:
        return
    caption = str(current.get("field_cn") or "")
    family = type_family(current.get("data_type"))
    # Unrelated labels that happen to share a character do not identify a business metric.
    term = next((caption[i:] for i in range(len(caption) - 1) if caption[i:] in request), "")
    if not term or not family:
        return
    available = {f["field_name"]: f for f in fields if str(f.get("field_cn") or "").endswith(term)
                 and type_family(f.get("data_type")) == family}
    if len(available) < 2:
        return
    choices = set()
    retained = []
    for issue in candidate.get("uncertainties") or []:
        remaining = []
        changed = False
        for part in re.split(r"[；;。\n]+", issue):
            if not part:
                continue
            identifiers = set(_IDENTIFIER.findall(part))
            refs = {name for name, field in available.items() if name in identifiers or field["field_cn"] in part}
            if (len(refs) >= 2 and chosen in refs and (not existing or refs <= existing_names)
                    and re.search(r"还是|或|选择|二选一|备选|候选", part)
                    and _document_only(part, [term, *refs, *(available[n]["field_cn"] for n in refs)], _FIELD_REVIEW_WORDS)):
                choices.update(refs)
                changed = True
            else:
                remaining.append(part)
        if not changed:
            retained.append(issue)
        elif remaining:
            retained.append("；".join(remaining))
    if not choices:
        return
    if existing:
        text = existing.get("uncertainty") or existing["text"]
        existing["uncertainty"] = text
        candidate["uncertainties"] = list(dict.fromkeys([*retained, text]))
        return
    text = f"这里的“{term}”指哪个字段？"
    names = [chosen, *(name for name in available if name != chosen and name in choices)]
    candidate.setdefault("questions", []).append({
        "id": "expression.left", "text": text, "uncertainty": text,
        "options": [{"value": name, "label": f"{available[name]['field_cn']}（{name}）",
                     **({"tag": "模型建议"} if name == chosen else {})} for name in names],
    })
    candidate["uncertainties"] = list(dict.fromkeys([*retained, text]))


def bind_verified_null_fields(candidate: dict[str, Any], check: ConditionalNullCheck, fields: list[dict[str, Any]],
                              *, table: str = "", recommended: bool = True, document_scope: str = "") -> None:
    """Use verified operands and structured questions for a fully covered request."""
    questions = candidate["questions"]
    previous = next((item for item in questions if item["id"] == "expression.left"), None)
    chosen = candidate["expression"]["left"]
    available = {field["field_name"]: field for field in check.measures}
    family = type_family(available[chosen].get("data_type"))
    options = [item for item in (previous or {}).get("options", []) if item["value"] in available]
    listed = {option["value"] for option in options}
    ordered = [available[chosen], *(field for name, field in available.items() if name != chosen)]
    options.extend(
        {"value": field["field_name"], "label": f"{field.get('field_cn') or field['field_name']}（{field['field_name']}）",
         **({"tag": "模型建议"} if recommended and field["field_name"] == chosen else {})}
        for field in ordered if field["field_name"] not in listed and type_family(field.get("data_type")) == family
    )
    options = options[:20]
    if previous:
        questions.remove(previous)
    if len(options) > 1:
        text = (previous or {}).get("text") or f"这里的“{check.term}”指哪个字段？"
        questions.insert(0, {"id": "expression.left", "text": text, "uncertainty": text, "options": options})
    # The original model observations remain in model_judgments. A technical
    # note from an earlier stage is not a new obligation once coverage is proven.
    requirements = [question["uncertainty"] for question in questions if question.get("uncertainty")]
    raw_reviews = candidate.get("uncertainties", [])
    if raw_reviews:
        evidence = BoundReviewEvidence(check, fields, table, document_scope)
        raw_reviews = [residual for note in raw_reviews if (residual := evidence.remaining(note))]
    if check.scope:
        retained = unresolved_identity_reviews(check, check.term, check.measures, fields, raw_reviews, table)
        requirements = list(dict.fromkeys([*retained, *requirements]))
    else:
        prior_note = (previous or {}).get("uncertainty")
        retained = []
        literals = [check.term, *available, *(f.get("field_cn") or "" for f in available.values())]
        for note in raw_reviews:
            if note == prior_note:
                continue
            parts = [part for part in re.split(r"[；;。？?\n]+", note) if part.strip()]
            remaining = [part for part in parts if not (
                check.term in part and ("字段" in part or any(name and name in part for name in literals[1:]))
                and _document_only(part, literals, _FIELD_REVIEW_WORDS))]
            if len(remaining) == len(parts):
                retained.append(note)
            elif remaining:
                retained.append("；".join(remaining))
        requirements = list(dict.fromkeys([*retained, *requirements]))
    candidate["uncertainties"] = requirements
