"""A request-local view of the authorized document. Ranking only controls which details to send."""
from __future__ import annotations

from collections import Counter, defaultdict
import ast
import json
from math import log
import re

from .generation_policy import text_tokens
from .contracts import AppError
from .formula import arithmetic_fields, is_arithmetic
from .query_grounding import dictionary_options, resolve_report_date
from .query_spec import is_finite_number, type_family
from .semantic_grounding import _document_codes, _Unbound


def _tokens_in(tokens, row, keys):
    text = " ".join(str(row.get(k) or "") for k in keys).lower()
    return {t for t in tokens if t in text}


def _dictionary_labels(field):
    return " ".join(option["label"].lower() for option in dictionary_options(field))


_TABLE_FACTS = ("dimension", "period", "scope", "source_desc")
_GENERIC_ALIAS_WORDS = re.compile(r"项目|字段|数值|指标|数据|校验")
_GENERIC_METRICS = {"余额", "数值", "金额", "份额", "数量", "指标", "数据", "项目", "合计", "总额"}
_METRIC_MODIFIERS = re.compile("|".join(_GENERIC_METRICS) + "|" + _GENERIC_ALIAS_WORDS.pattern)


def _business_aliases(field):
    declaration = re.match(r"\s*业务别名[：:]\s*([^。；;.\r\n]+)", str(field.get("logic") or ""))
    if not declaration:
        return ()
    return tuple(name.strip().lower() for name in re.split(r"[、，,]", declaration[1]) if name.strip())


def documented_equation(request, fields):
    """Read a single required equality written out with unambiguous document fields and arithmetic symbols."""
    match = re.search(r"(?<![不未])(?:不满足|(?:应(?:当)?|须|必须)满足)(?:下列|以下|如下)?公式\s*[：:]\s*([^，,。；;\n]+)"
                      r"(?:[，,]\s*(?:请)?(?:核实|核查|复核))?[。！.!\s]*$", request)
    if not match:
        return None
    equation = match[1].translate(str.maketrans("（）＋－×÷＝", "()+-*/=")).lower()
    if equation.count("=") != 1 or not re.search(r"[-+*/]", equation):
        return None
    names = defaultdict(set)
    for field in fields:
        if type_family(field.get("data_type")) == "number":
            for name in (field["field_name"], field.get("field_cn"), *_business_aliases(field)):
                if name:
                    names[name.lower()].add(field["field_name"])
    aliases = sorted(names, key=len, reverse=True)
    if not aliases:
        return None
    tokens = re.compile("|".join(map(re.escape, aliases)) + r"|(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?|[-+*/()=]|\s+")
    mapped, bindings = [], {}
    offset = 0
    for token in tokens.finditer(equation):
        if token.start() != offset:
            return None
        value = token[0]
        offset = token.end()
        if value in names:
            if len(names[value]) != 1:
                return None
            value = "v" + str(len(bindings))
            bindings[value] = next(iter(names[token[0]]))
        mapped.append(value)
    if offset != len(equation) or not bindings:
        return None
    try:
        left, right = [ast.parse(s.strip(), mode="eval").body for s in "".join(mapped).split("=")]
    except (SyntaxError, RecursionError, ValueError):
        return None
    ops = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
    def operand(node):
        if isinstance(node, ast.Name) and node.id in bindings:
            return {"field": bindings[node.id]}
        if isinstance(node, ast.Constant) and is_finite_number(node.value):
            return {"value": node.value}
        if (isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd))
                and isinstance(node.operand, ast.Constant) and is_finite_number(node.operand.value)):
            return {"value": -node.operand.value if isinstance(node.op, ast.USub) else node.operand.value}
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return {"op": ops[type(node.op)], "left": operand(node.left), "right": operand(node.right)}
        raise ValueError
    try:
        left, right = operand(left), operand(right)
        if "value" in left:
            left, right = right, left
        result = {"op": "neq"}
        for side, node in (("left", left), ("right", right)):
            kind = "formula" if "op" in node else next(iter(node))
            if side == "right" or kind != "field":
                result[side + "_type"] = kind
            result[side] = node if kind == "formula" else node[kind]
        if is_arithmetic(result):
            arithmetic_fields(result)
            return result
    except (AppError, ValueError, RecursionError):
        return None
    return None


def _single_direct_source(field):
    if not re.fullmatch(r'直取[。.]?|直接取(?:值|数)?[。.]?', str(field.get('logic') or '').strip()):
        return None
    sources = str(field.get('source_table') or '').strip().splitlines()
    columns = str(field.get('source_field') or '').strip().splitlines()
    if len(sources) != len(columns):
        return None
    pairs = [(source.strip(), column.strip()) for source, column in zip(sources, columns)]
    if (not pairs or len({column for _, column in pairs}) != 1 or
            any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*', source)
                for source, _ in pairs) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', pairs[0][1])):
        return None
    names = {table.rsplit('.', 1)[-1] for table, _ in pairs}
    base = min(names, key=len)
    if names - {base, base + "_YYYY_MM"} or len(names) == 1 and len(set(pairs)) > 1:
        return None
    return base, pairs[0][1]


def _first_alias_fields(aliases, request, weights, order, top_tables):
    """Add narrowly scoped evidence for fields sharing the strongest registered alias match."""
    matches = []
    for table_id, name, alias in aliases:
        terms = text_tokens(_GENERIC_ALIAS_WORDS.sub(" ", alias))
        hits = [weights[t] for t in terms if len(t) >= 2 and t in weights]
        if hits:
            rank = (1, len(alias)) if alias in request else (0, max(hits))
            matches.append((rank, table_id, name))
    if not matches:
        return {}
    strongest = max(rank for rank, _, _ in matches)
    by_table = defaultdict(set)
    for rank, table_id, name in matches:
        if rank == strongest:
            by_table[table_id].add(name)
    additional = [i for i in order if i in by_table and i not in top_tables][:2]
    return {i: by_table[i] for i in [*top_tables, *additional] if i in by_table}


def _table_excerpt(value, wanted, limit):
    if len(value) <= limit:
        return value
    text = value.lower()
    matches = [(len(t), -pos) for t in wanted if (pos := text.find(t)) >= 0]
    position = -max(matches)[1] if matches else 0
    start = min(max(0, position - limit // 4), len(value) - limit)
    return ("…" if start else "") + value[start:start + limit] + ("…" if start + limit < len(value) else "")


def _request_source_pairs(field, anchors):
    """Show a direct column source only when every documented line leads to one matched field."""
    if _single_direct_source(field) not in anchors:
        return []
    tables = str(field.get("source_table") or "").splitlines()
    columns = str(field.get("source_field") or "").splitlines()
    if not 1 <= len(tables) == len(columns) <= 2:
        return []
    pairs = [(table.strip(), column.strip()) for table, column in zip(tables, columns)]
    return pairs


def _label_forms(field):
    label = str(field.get("field_cn") or "").lower()
    parts = label.split("_")
    if len(parts) == 2 and parts[0] and parts[1] in ("原始", "当前", "现行", "期初", "期末", "当期", "累计"):
        return [label, parts[1] + parts[0]]
    return [label] if label else []


def _date_label_base(field):
    label = str(field.get("field_cn") or "").strip().lower()
    return re.sub(r"^(?:当前|现行|原始)|(?:_(?:当前|现行|原始)|[（(](?:当前|现行|原始)[)）])$", "", label)


def _named_scope_fields(fields, selected, request):
    selected_labels = {label for f in selected for label in _label_forms(f)}
    spans = defaultdict(set)
    for field in fields:
        if not field.get("dictionary"):
            continue
        for label in _label_forms(field):
            if label in request and any(s in label or label in s for s in selected_labels):
                for match in re.finditer(re.escape(label), request):
                    spans[match.span()].add(field["field_name"])
    return _independent_mentions(spans)


def _independent_mentions(spans):
    # A plain noun occurring only inside a longer qualified name does not name two fields.
    named = set()
    covered_end = -1
    for start, end in sorted(spans, key=lambda span: (span[0], -span[1])):
        if end > covered_end:
            named.update(spans[(start, end)])
            covered_end = end
    return named


class DocumentEvidence:
    def __init__(self, tables, fields, request):
        self.fields = fields
        self.tables = tables
        self.request = str(request).lower()
        # A dictionary state followed by its entity names the population. The noun
        # can also prefix a metric alias at that boundary when the user omits 的.
        self.metric_request = self.request
        for table in tables:
            grain = str(table.get("dimension") or "").strip().lower()
            if not grain or grain not in self.request:
                continue
            labels = {str(o["label"]).lower() for field in fields.get(table["id"], []) if field.get("dictionary")
                      for o in dictionary_options(field)}
            for label in labels:
                if label and label + grain in self.request:
                    self.metric_request = re.sub(re.escape(label + grain) + r"(?!端|表)", " ", self.metric_request)
        self.metric_tokens = text_tokens(self.metric_request)
        self.details = {}
        wanted = self.wanted = text_tokens(request)
        matches = {}
        aliases = []
        self.document_names = defaultdict(set)
        self.named_tables = set()
        counts = Counter()
        field_count = sum(len(rows) for rows in fields.values())
        for table in tables:
            i = int(table["id"])
            physical = table["table_name"].lower()
            caption = str(table.get("table_name_cn") or "").lower().removesuffix("（" + physical + ".ktr）")
            if ((caption and caption.removesuffix("表") + "表" in self.request)
                    or re.search(r"(?<![a-z0-9_])" + re.escape(physical) + r"(?![a-z0-9_])", self.request)):
                self.named_tables.add(i)
            rows = []
            for f in fields.get(i, []):
                registered = _business_aliases(f)
                aliases.extend((i, f["field_name"], alias) for alias in registered)
                for label in (str(f.get("field_cn") or "").lower(), *registered):
                    if label and label in self.metric_request:
                        self.document_names[label].add((i, f["field_name"]))
                names = _tokens_in(wanted, f, ("field_cn", "field_name"))
                sources = _tokens_in(wanted, f, ("source_field", "source_field_cn", "logic", "source_table", "source_table_cn"))
                codes = _tokens_in(wanted, f, ("dictionary",))
                counts.update(names | sources | codes)
                rows.append((f["field_name"], names, sources, codes))
            matches[i] = rows
        # A short fragment in hundreds of lineage notes conveys far less than a rare business label.
        weights = {t: len(t) ** 1.3 * log(1 + (field_count + 1) / (1 + counts[t])) for t in wanted}
        self.weights = weights
        def best(tokens):
            return max((weights[t] for t in tokens), default=0)
        rankings = {}
        table_coverage = {}
        for table in tables:
            i = int(table["id"])
            ranked = [(max(best(names), .5 * best(sources), .8 * best(codes)), name)
                      for name, names, sources, codes in matches[i]]
            ranked.sort(key=lambda entry: -entry[0])
            rankings[i] = ranked
            label = _tokens_in(wanted, table, ("table_name", "table_name_cn", "dimension"))
            explanations = _tokens_in(wanted, table, ("period", "scope", "source_desc"))
            coverage = {t: weights[t] * .4 for t in explanations}
            coverage.update({t: weights[t] for t in label})
            for _, names, sources, codes in matches[i]:
                for hits, strength in ((names, 1), (sources, .35), (codes, .65)):
                    for t in hits:
                        coverage[t] = max(coverage.get(t, 0), weights[t] * strength)
            table_coverage[i] = coverage
        # Prefer a second table that contributes facts for a different part of the request.
        top_tables = []
        covered = {}
        for _ in range(min(2, len(tables))):
            remaining = [i for i in table_coverage if i not in top_tables]
            def gain(i):
                return sum(max(0, w - covered.get(t, 0)) for t, w in table_coverage[i].items())
            winner = max(remaining, key=gain)
            if gain(winner) == 0:
                break
            top_tables.append(winner)
            for t, weight in table_coverage[winner].items():
                covered[t] = max(weight, covered.get(t, 0))
        others = sorted((i for i in table_coverage if i not in top_tables),
                        key=lambda i: sum(table_coverage[i].values()), reverse=True)
        self.expansion_order = [*top_tables, *others]
        alias_fields = _first_alias_fields(aliases, self.metric_request, weights, self.expansion_order, top_tables)
        self.table_summaries = {}
        self.partial_tables = set()
        for table in tables:
            table_id = table["id"]
            summary = {}
            for key in _TABLE_FACTS:
                value = str(table.get(key) or "").strip()
                if not value:
                    continue
                excerpt = _table_excerpt(value, wanted, 96 if table_id in top_tables else 48)
                summary[key if excerpt == value else key + "_excerpt"] = excerpt
                if excerpt != value:
                    self.partial_tables.add(table_id)
            self.table_summaries[table_id] = summary
        for i, ranked in rankings.items():
            rows = fields.get(i, [])
            if len(tables) == 1 and len(rows) <= 12:
                self.details[i] = {f["field_name"] for f in rows}
                continue
            selected = i in top_tables or len(tables) == 1
            names = set()
            if selected and ranked:
                # The directory preserves all lower-ranked candidates and requests their complete evidence as needed.
                threshold = max(1.0, ranked[0][0] * .25)
                names = {name for score, name in ranked[:6] if score >= threshold}
                names.update(f["field_name"] for f in rows if f.get("field_cn") and f["field_cn"] in request
                             or f["field_name"].lower() in wanted)
            names.update(alias_fields.get(i, ()))
            if selected or i in alias_fields:
                names.update(f["field_name"] for f in rows if f.get("is_pk") == "Y")
                date, choices = resolve_report_date(rows)
                if date:
                    names.add(date)
                else:
                    names.update(field["field_name"] for field in choices)
            self.details[i] = names
        self.request_field_evidence = defaultdict(list)
        self._collect_request_evidence(tables, set(top_tables) | set(alias_fields))

    def _collect_request_evidence(self, tables, selected):
        # The initial shortlist already includes its metrics and competitors. Highlight exact
        # document facts without turning a lexical match or copied value into a rule decision.
        remaining = 800  # UTF-8 bytes conservatively bound additional prompt tokens across all tables.
        owners = Counter(t["table_name"] for t in tables)
        anchors = set()
        def encoded_size(value):
            return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

        def add(table, field, fact, *, expand=False):
            nonlocal remaining
            i, name = table["id"], field["field_name"]
            note = {"field": name, **fact}
            cost = encoded_size(note) + (1 if self.request_field_evidence[i] else 30)
            if expand and name not in self.details[i] and cost <= remaining:
                single = self.describe(table, names={name})
                full_cost = encoded_size({k: single[k] for k in ("fields", "shared_dictionaries") if k in single})
                if cost + full_cost <= remaining:
                    self.details[i].add(name)
                    cost += full_cost
            if cost <= remaining:
                self.request_field_evidence[i].append(note)
                remaining -= cost

        for table in tables:
            if table["id"] not in selected:
                continue
            for field in self.fields.get(table["id"], []):
                label = str(field.get("field_cn") or "").lower()
                alias = max((a for a in _business_aliases(field) if a in self.metric_request), key=len, default="")
                # Document headings can place a qualifier after the noun, e.g. "运行方式_原始".
                reordered = next((form for form in _label_forms(field)[1:] if form in self.request), "")
                if reordered:
                    add(table, field, {"request_label": reordered}, expand=True)
                elif alias:
                    add(table, field, {"registered_alias": alias})
                elif not label or label not in self.request:
                    continue
                if owners[table["table_name"]] == 1:
                    anchors.add((table["table_name"], field["field_name"]))

        if anchors:
            for table in tables:
                for field in self.fields.get(table["id"], []):
                    if (table["table_name"], field["field_name"]) not in anchors:
                        continue
                    origin = self._document_origin(table, field)
                    if not origin:
                        continue
                    owner, source = origin
                    pair = (owner["table_name"], source["field_name"])
                    if pair not in anchors:
                        add(table, field, {"direct_sources": [list(p) for p in _request_source_pairs(field, {pair})],
                            "document_origin": {"table": pair[0], "field": pair[1], "label": source.get("field_cn") or pair[1],
                                                "dimension": owner.get("dimension") or ""}})
            # A copied column can live just outside the selected tables. Check only the
            # next two document candidates, and serialize only exact direct-source links.
            neighbors = [i for i in self.expansion_order if i not in selected][:2]
            for table in tables:
                if table["id"] not in selected and table["id"] not in neighbors:
                    continue
                others = {origin for origin in anchors if origin[0] != table["table_name"]}
                if not others:
                    continue
                # Prefer the checked measure's origin before repeated copies of its scope.
                for field in sorted(self.fields.get(table["id"], []), key=lambda f: bool(f.get("dictionary"))):
                    pairs = _request_source_pairs(field, others)
                    if pairs:
                        add(table, field, {"direct_sources": [list(pair) for pair in pairs]})

    def describe(self, table, *, full=False, names=None):
        i = int(table["id"])
        fields = self.fields.get(i, [])
        selected = self.details[i] if names is None else names
        expanded = fields if full else [f for f in fields if f["field_name"] in selected]
        others = [] if full or names is not None else [f for f in fields if f["field_name"] not in selected]
        labels = Counter(f.get("field_cn") for f in fields)
        directory = []
        for field in others:
            label, name = field.get("field_cn"), field["field_name"]
            directory.append(f"{label}|{name}" if label and labels[label] > 1 else label or name)
        dictionaries = {}
        rows = []
        for f in expanded:
            row = [f["field_name"], f.get("field_cn") or "", f.get("data_type") or ""]
            facts = {k: f[k] for k in ("logic", "source_table", "source_table_cn", "source_field", "source_field_cn", "default_value", "nullable")
                     if f.get(k) not in (None, "")}
            if f.get("is_pk") == "Y":
                facts["pk"] = True
            if f.get("dictionary"):
                code = dictionaries.setdefault(f["dictionary"], f"D{len(dictionaries) + 1}")
                facts["dictionary_ref"] = code
            if facts:
                row.append(facts)
            rows.append(row)
        label = table.get("table_name_cn") or ""
        label = label.removesuffix("（" + table["table_name"] + ".ktr）")
        result = {"table": table["table_name"], "label": label}
        if full:
            result.update({k: table[k] for k in _TABLE_FACTS if table.get(k)})
        else:
            result.update(self.table_summaries[i])
        if directory:
            result["directory"] = directory
        if rows:
            result["fields"] = rows
        if dictionaries:
            result["shared_dictionaries"] = {ref: content for content, ref in dictionaries.items()}
        if names is None and self.request_field_evidence.get(i):
            result["request_field_evidence"] = self.request_field_evidence[i]
        return result

    def fully_expanded(self, table):
        i = int(table["id"])
        return i not in self.partial_tables and len(self.details[i]) == len(self.fields.get(i, []))

    def _document_origin(self, table, field):
        direct = _single_direct_source(field)
        family = type_family(field.get("data_type"))
        if not direct or direct[0] == table["table_name"] or not family:
            return None
        matches = [(t, f) for t in self.tables if t["table_name"] == direct[0]
                   and t.get("data_source_name") == table.get("data_source_name")
                   for f in self.fields.get(t["id"], []) if f["field_name"] == direct[1]
                   and type_family(f.get("data_type")) == family]
        return matches[0] if len(matches) == 1 else None

    def authoritative_metric_origin(self, table, name):
        """Return a verified origin when a selected copy's own grain was not requested."""
        caption = str(table.get("table_name_cn") or "").lower().removesuffix("表")
        grain = str(table.get("dimension") or "").strip().lower()
        short = re.sub(r"(?:明细|信息|清单|记录)$", "", caption)
        if (table["id"] in self.named_tables or name.lower() in self.wanted or caption and caption in self.request or
                any(entity + marker in self.request for entity in (grain, short) if len(entity) >= 2
                    for marker in ("端", "表", "维度"))):
            return None
        field = next((f for f in self.fields.get(table["id"], []) if f["field_name"] == name), None)
        origin = self._document_origin(table, field) if field else None
        return (origin[0]["table_name"], origin[1]["field_name"]) if origin else None

    def exact_metric_field(self, table, name, term):
        """Bind a full request name only if its documented owner is unambiguous."""
        term = str(term or "").strip().lower()
        owners = self.document_names.get(term, set())
        if (not owners or (term in _GENERIC_METRICS and not self.named_tables)
                or any(term != other and term in other for other in self.document_names)):
            return False
        if self.named_tables == {table["id"]}:
            owners = {pair for pair in owners if pair[0] == table["id"]}
        return owners == {(table["id"], name)}

    def explicitly_named_scopes(self, table_id, selected):
        return _named_scope_fields(self.fields.get(table_id, ()), selected, self.request)

    def named_metric_choices(self):
        spans = defaultdict(set)
        for label, owners in self.document_names.items():
            for match in re.finditer(re.escape(label), self.request):
                spans[match.span()].update(owners)
        return _independent_mentions(spans)

    def unique_requested_category(self, table_id, field_name, term):
        """Recognize an explicit category modifier backed by exactly one dictionary in its table."""
        if (not isinstance(term, str) or len(term.strip()) < 2
                or not re.search(r"(?:^|[，,；;。]|且)\s*" + re.escape(term) + r"\s*的", self.request, re.I)):
            return False
        owners = []
        for field in self.fields.get(table_id, ()):
            if term not in str(field.get("dictionary") or ""):
                continue
            try:
                if term in _document_codes(field).values():
                    owners.append(field["field_name"])
            except _Unbound:
                return False
        return owners == [field_name]

    def _qualified_date_owner(self, table, field):
        """A shared date caption can name one entity when its table subject qualifies the date in the request."""
        label = str(field.get("field_cn") or "").lower()
        owners = {i for i, _ in self.document_names.get(label, ())}
        if len(owners) < 2 or table["id"] not in owners:
            return False
        for owner in self.tables:
            if owner["id"] not in owners:
                continue
            caption = str(owner.get("table_name_cn") or "").lower().split("（", 1)[0]
            caption = re.sub(r"(?:明细|信息|记录|清单)?表$", "", caption)
            subjects = [s.strip() for s in re.split(r"及(?:其他|其它)?|、|与", caption) if len(s.strip()) >= 2]
            if not subjects:
                return False
            if owner["id"] == table["id"]:
                if not any(s + label in self.request or s + "的" + label in self.request for s in subjects):
                    return False
            elif owner["id"] in self.named_tables or any(s in self.request for s in subjects):
                return False
        return True

    def competing_fields(self, table, names, term, tables, *, category=False, across_tables=False):
        """Find evidence to review, without deciding that matching labels are interchangeable."""
        tokens = (self.wanted if category else self.metric_tokens) & text_tokens(term)
        own = {field["field_name"]: field for field in self.fields.get(table["id"], [])}
        selected = [own[name] for name in names if isinstance(name, str) and name in own]
        if not tokens or not selected:
            return []
        if category:
            named = self.explicitly_named_scopes(table["id"], selected)
            if any(f["field_name"].lower() in self.wanted for f in selected) or (named and named <= set(names)):
                return []
        keys = ("dictionary",) if category else ("field_name", "field_cn", "source_field_cn", "logic")
        explicit_alias = None if category else max(
            (alias for field in selected for alias in _business_aliases(field)
             if alias in self.metric_request and any(token in alias for token in tokens)),
            key=len, default=None)
        selected_text = [_dictionary_labels(f) if category else " ".join(str(f.get(k) or "") for k in keys).lower()
                         for f in selected]
        anchor = explicit_alias or max((token for token in tokens if any(token in text for text in selected_text)),
                                      key=lambda token: self.weights.get(token, 0), default=None)
        if anchor is None:
            return []

        def score(field, *, selected_field=False):
            # A match on just “余额” cannot compete with an explicit “专项权益余额” alias.
            if category:
                dictionary = _dictionary_labels(field)
                if anchor not in dictionary:
                    return 0
                return max((self.weights[token] for token in tokens if token in dictionary), default=0)
            label = str(field.get("field_cn") or "").lower()
            direct = " ".join(str(field.get(key) or "") for key in ("field_name", "field_cn", "source_field_cn")).lower()
            searchable = " ".join((direct, *_business_aliases(field)))
            if explicit_alias:
                return int(explicit_alias in searchable)
            if selected_field:
                searchable += " " + str(field.get("logic") or "").lower()
            if anchor not in searchable:
                return 0
            named = max((self.weights.get(token, 0) * (2 if label.endswith(token) else 1)
                         for token in tokens if token in direct), default=0)
            if named:
                return named
            return .5 * max((self.weights.get(token, 0) for token in tokens if token in searchable), default=0)

        specificity = max(score(field, selected_field=True) for field in selected)
        if not specificity:
            return []
        families = {type_family(field.get("data_type")) for field in selected}
        if across_tables and not category and families == {"date"} and len(selected) == 1 and self._qualified_date_owner(table, selected[0]):
            across_tables = False
        owner_dimension = str(table.get("dimension") or "").strip().lower()
        if across_tables and not category and owner_dimension and re.search(
                re.escape(owner_dimension) + r"(?:端|表)(?:中|内)?(?:的)?\s*" + re.escape(anchor), self.metric_request):
            across_tables = False
        scoped_date = (not category and families == {"date"} and
                       (table["id"] in self.named_tables or (owner_dimension and (
                           owner_dimension + "的" in self.request or
                           any(t.startswith(owner_dimension) and t.endswith(anchor) for t in self.wanted)))))
        selected_names = {_date_label_base(f) for f in selected} - {""} if scoped_date else set()
        if (not category and len(selected) == 1 and self.exact_metric_field(table, selected[0]["field_name"], term)
                and (not scoped_date or term.lower() not in selected_names)):
            return [{"table": table["table_name"], "table_id": table["id"], "dimension": table.get("dimension") or "",
                     "fields": [selected[0]["field_name"]], "request_term": term}]
        selected_aliases = {alias for f in selected for alias in _business_aliases(f)}
        result = []
        for candidate in tables:
            if not across_tables and candidate["id"] != table["id"]:
                continue
            rows = self.fields.get(candidate["id"], [])
            dimension = str(candidate.get("dimension") or "").strip().lower()
            other_entity_named = (candidate["id"] != table["id"] and (candidate["id"] in self.named_tables
                                  or (dimension and dimension != owner_dimension and dimension in self.request)))
            compare_date_names = scoped_date and not other_entity_named
            if compare_date_names:
                # A common date suffix cannot bind a different business event, even in the same table.
                rows = [f for f in rows if _date_label_base(f) in selected_names
                        or (candidate["id"] == table["id"] and f["field_name"] in names)
                        or selected_aliases.intersection(_business_aliases(f))]
            fields = [field["field_name"] for field in rows
                      if (bool(field.get("dictionary")) if category else type_family(field.get("data_type")) in families)
                      and (compare_date_names or score(field) >= specificity)]
            if fields:
                result.append({"table": candidate["table_name"], "table_id": candidate["id"],
                               "dimension": candidate.get("dimension") or "", "fields": fields, "request_term": anchor})
        if not category:
            pairs = [(candidate["table"], name) for candidate in result for name in candidate["fields"]]
            for candidate in result:
                kept = []
                for name in candidate["fields"]:
                    field = next(field for field in self.fields[candidate["table_id"]] if field["field_name"] == name)
                    direct = _single_direct_source(field)
                    selected_here = candidate["table_id"] == table["id"] and name in names
                    copied = direct and direct[0] != candidate['table'] and direct in pairs
                    if selected_here or not copied:
                        kept.append(name)
                candidate["fields"] = kept
            result = [candidate for candidate in result if candidate["fields"]]
        covered = {hit["table_id"] for hit in result} | {table["id"]}
        if (across_tables and not category and not scoped_date and not explicit_alias and len(selected) == 1 and len(covered) < 3
                and selected[0]["field_name"].lower() not in self.wanted
                and any(anchor in alias for alias in _business_aliases(selected[0]))):
            # A shared piece of a registered business name can justify fetching the other
            # definition. Only the model can decide whether the two measures are applicable.
            fragments = text_tokens(_METRIC_MODIFIERS.sub(" ", anchor))
            weak = {}
            for peer in tables:
                if not fragments or peer["id"] in covered:
                    continue
                names = [f["field_name"] for f in self.fields.get(peer["id"], ())
                         if type_family(f.get("data_type")) in families
                         and any(t in alias for alias in _business_aliases(f) for t in fragments)]
                if names:
                    weak[peer["id"]] = {"table": peer["table_name"], "table_id": peer["id"],
                                        "dimension": peer.get("dimension") or "", "fields": names,
                                        "request_term": anchor, "requires_model_review": True}
            result.extend([weak[i] for i in self.expansion_order if i in weak][:3 - len(covered)])
        return result


def _array(mapping, key):
    items = mapping.get(key)
    return items if isinstance(items, list) else []


def referenced_fields(draft):
    """Look up the fields the model used, with each association scoped to its table role."""
    names = {"base": set(), "related": set()}
    def add(role, name):
        if isinstance(role, str) and role in names and isinstance(name, str):
            names[role].add(name)
    if draft.get("business_key"):
        add("base", draft["business_key"])
    expression = draft.get("expression") or {}
    conditions = expression.get("conditions", [expression]) if isinstance(expression, dict) else []
    if not isinstance(conditions, list):
        conditions = []
    conditions = [part for part in conditions if isinstance(part, dict)]
    intent = draft.get("semantic_intent") or {}
    if not isinstance(intent, dict):
        return names
    for part in conditions:
        if is_arithmetic(part):
            try:
                names["base"].update(arithmetic_fields(part))
            except AppError:
                pass
        add("base", part.get("left"))
        if part.get("right_type", "field") == "field":
            add(part.get("right_table", "base"), part.get("right"))
    for metric in _array(intent, "metrics"):
        if not isinstance(metric, dict) or not isinstance(metric.get("fields"), list):
            continue
        for index, part in enumerate(conditions):
            if metric.get("condition_index", index) != index:
                continue
            role = part.get("right_table", "base") if metric.get("side") == "right" else "base"
            for name in metric["fields"]:
                add(role, name)
    for scope in _array(intent, "scopes"):
        if isinstance(scope, dict) and isinstance(scope.get("fields"), list):
            for name in scope["fields"]:
                add(scope.get("table", "base"), name)
    for item in _array(draft, "filters"):
        if isinstance(item, dict):
            add(item.get("table", "base"), item.get("field"))
    join = draft.get("join") or {}
    if isinstance(join, dict):
        add("related", join.get("report_date_field"))
        for pair in _array(join, "on"):
            if isinstance(pair, dict):
                add("base", pair.get("left"))
                add("related", pair.get("right"))
    return names


def compact_directory(views):
    """Deduplicate repeated directory labels while retaining their exact document memberships."""
    table_indices = defaultdict(list)
    for i, table in enumerate(views):
        for label in table.get("directory", []):
            table_indices[label].append(i)
    groups = defaultdict(list)
    for label, indices in table_indices.items():
        if len(set(indices)) > 1:
            groups[tuple(i + 1 for i in indices)].append(label)
    for table in views:
        if "directory" in table:
            table["directory"] = [s for s in table["directory"] if len(set(table_indices[s])) <= 1]
            if not table["directory"]:
                del table["directory"]
    result = {"tables": views}
    if groups:
        result["common_directory"] = [[list(indices), labels] for indices, labels in groups.items()]
    return result
