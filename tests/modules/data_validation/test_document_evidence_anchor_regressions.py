from sqlalchemy import update

from auto_check.modules.data_validation.document_evidence import DocumentEvidence
from auto_check.modules.data_validation.storage import DOC_FIELDS, DOC_TABLES
from tests.modules.data_validation.test_ai_latency_pipeline import combined, run
from tests.modules.data_validation.test_ai_service import _rules_with_doc
from tests.modules.data_validation.test_followup_service_bridge import _add_table
from tests.modules.data_validation.test_semantic_generation import draft


def field(name, label, logic="", dictionary=""):
    return {"field_name": name, "field_cn": label, "logic": logic, "dictionary": dictionary,
            "data_type": "varchar" if dictionary else "numeric"}


def candidates(request, term, first, others, *, category=False):
    tables = [{"id": 1, "table_name": "base"}, {"id": 2, "table_name": "details"}]
    evidence = DocumentEvidence(tables, {1: [first], 2: others}, request)
    groups = evidence.competing_fields(tables[0], [first["field_name"]], term, tables,
                                       category=category, across_tables=True)
    return {name for group in groups for name in group["fields"]}


def test_crossed_multiline_lineage_cannot_hide_an_independent_metric():
    first = field('base_metric', '权益余额')
    copy = field('copied', '权益余额', '直取')
    copy.update(source_table='doc.base\nother.unrelated', source_field='not_the_metric\nbase_metric')
    assert candidates('权益余额低于19', '权益余额', first, [copy]) == {'base_metric', 'copied'}


def test_a_transformed_direct_looking_field_cannot_be_deduplicated():
    first = field('base_metric', '权益余额')
    copy = field('copied', '权益余额', '直接取后另按规则换算')
    copy.update(source_table='doc.base', source_field='base_metric')
    assert candidates('权益余额低于19', '权益余额', first, [copy]) == {'base_metric', 'copied'}


def test_model_abbreviation_preserves_full_alias_and_excludes_incidental_lineage():
    first = field("balance", "基础期末余额", "业务别名：权益余额、专项权益余额。定义：期末业务值。")
    others = [field("account", "账户余额"),
              field("recognized", "期末测量值", "业务别名：专项权益余额。定义：按另一维度独立计量。"),
              field("incidental", "调整后余额", "业务别名：估算余额。定义：计算时扣除专项权益余额。")]
    assert candidates("专项权益余额低于19要核实", "余额", first, others) == {"balance", "recognized"}


def test_ordinary_lineage_is_not_a_registered_business_alias():
    first = field("balance", "期末余额", "汇总说明引用专项权益余额。")
    assert "account" in candidates("专项权益余额低于19要核实", "余额", first, [field("account", "账户余额")])


def test_two_documented_interpretations_of_a_generic_term_remain_competitors():
    first = field("capital", "权益合计", "业务别名：项目实收信托、项目4001实收信托余额。定义：同日报送。")
    others = [field("share", "期末份额", "业务别名：募集期末实收份额。定义：含待结转收益。"),
              field("fee", "手续费", "业务别名：当期手续费。定义：按实收份额计算。")]
    assert candidates("存续项目的实收不得小于0", "实收", first, others) == {"capital", "share"}


def test_category_evidence_only_competes_on_dictionary_meaning():
    first = field("mode", "运行方式", dictionary="1-净值型\n2-其他")
    others = [field("original", "原始运行方式", dictionary="Y-净值型\nN-非净值型"),
              field("flag", "归档状态", "业务别名：净值型。", dictionary="Y-是\nN-否")]
    assert candidates("净值型项目净值不为空", "净值型", first, others, category=True) == {"mode", "original"}


def test_first_prompt_expands_both_paid_in_metrics_keys_dates_and_accepts_complete_plans():
    request = "项目的实收低于0要核实"
    project = draft("capital")
    contract = draft("share")
    contract["target"] = {"table": "contracts"}
    for part in (project, contract):
        part["semantic_intent"]["metrics"][0]["term"] = "实收"
        part['expression']['right'] = 0
    plans = {"plans": [project, contract]}
    rules, model = _rules_with_doc([combined(plans), {"ai_suggestions": []}], fields=[
        ("project_key", "业务编号", "varchar", "Y"), ("as_of", "数据日期", "date", ""),
        ("capital", "权益合计", "numeric", "")])
    _add_table(rules, name="contracts", cn="合同明细", dimension="合同",
               fields=[("contract_key", "合同编号", "varchar", "Y"), ("cutoff", "业务日期", "date", ""),
                       ("share", "期末份额", "numeric", "")])
    _add_table(rules, name="checks", cn=request, dimension="状态",
               fields=[("flag", "标记", "varchar", "")])
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_TABLES).values(sheet_name='人行_合成口径'))
        for name, alias in (("capital", "项目实收信托"), ("share", "募集期末实收份额")):
            conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == name).values(
                logic=f"业务别名：{alias}。定义：依据独立的明细数据。"))

    result = run(rules, request)

    assert len(model.calls) == 2 and "本轮只提出独立补充校验建议" in model.calls[1]["messages"][0]["content"]
    prompt = model.calls[0]["messages"][0]["content"]
    for name in ("project_key", "as_of", "capital", "contract_key", "cutoff", "share"):
        assert f'"{name}"' in prompt
    assert {option["candidate"]["table_name"] for option in result["candidate_options"]} == {"test_table", "contracts"}


def test_long_registered_alias_adds_only_its_own_field_and_preserves_the_rest_of_the_directory():
    request = "核实项目的专项权益余额字段的数值"
    tables = [{"id": i, "table_name": f"tab{i}"} for i in range(1, 7)]
    tables[0]["table_name_cn"] = request
    fields = {
        1: [field("id", "索引")],
        2: [field("amount", "测量值", "业务别名：专项权益余额。定义：本期完整逻辑。"),
            *[field(f"flag{i}", f"标记{i}", dictionary="Y-是\nN-否") for i in range(9)]],
        3: [field("other", "计算结果", "业务别名：其他余额。")],
        4: [field("incidental", "结果", "业务别名：其他量。定义：引用专项权益余额。")],
        5: [field("generic", "标准值", "业务别名：项目指标、字段、数值。")],
        6: [field("short", "账户值", "业务别名：余额。")],
    }
    index = DocumentEvidence(tables, fields, request)
    target = index.describe(tables[1])
    assert set(i for i in range(2, 7) if index.details[i]) == {2}
    assert target["fields"][0][3]["logic"] == "业务别名：专项权益余额。定义：本期完整逻辑。"
    assert len(target["directory"]) == 9 and "shared_dictionaries" not in target


def test_add_at_most_two_alias_tables_and_keep_overflow_in_the_directory():
    request = "实收低于19要核实"
    tables = [{"id": i, "table_name": f"t{i}", "table_name_cn": request if i == 1 else "记录"}
              for i in range(1, 6)]
    fields = {i: [field(f"m{i}", f"列{i}", "业务别名：明细实收份额。")] for i in range(2, 6)}
    fields[1] = [field("id", "条目")]
    index = DocumentEvidence(tables, fields, request)
    assert sum(bool(index.details[i]) for i in range(2, 6)) == 2
    assert all(index.describe(table).get("directory") == [f"列{table['id']}"]
               for table in tables[1:] if not index.details[table["id"]])


def test_generic_request_words_alone_do_not_expand_business_aliases():
    request = "请核实项目字段的数值"
    tables = [{"id": 1, "table_name": "checks", "table_name_cn": request}, {"id": 2, "table_name": "others"}]
    fields = {1: [field("id", "索引")], 2: [field("noise", "编码", "业务别名：项目字段数值、数值。")]}
    assert DocumentEvidence(tables, fields, request).details[2] == set()
