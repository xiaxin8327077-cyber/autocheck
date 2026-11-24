import sqlite3

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.candidate_preview import run_preview_cases
from auto_check.modules.data_validation.compiler import compile_rule
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.query_spec import validate_spec_against_columns
from auto_check.modules.data_validation.sql_display import inline_sql_parameters
from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc


FIELDS = [('row_id', '记录编号', 'varchar', 'Y'), ('day', '数据日期', 'date', ''),
          ('caption', '标题', 'varchar', ''), ('kind', '类别', 'varchar', '')]
INCLUDED = ['夏日', "%_!'\\", '赤']
EXCLUDED = ['托管', '转发']


def proposal(filters, op='neq', value='02'):
    return {'target': {'table': 'test_table'}, 'draft': {
        'business_key': 'row_id', 'rule_name': '分类核查', 'rule_type': 'field_compare',
        'expression': {'left': 'kind', 'op': op, 'right_type': 'value', 'right': value},
        'filters': filters, 'null_policy': 'skip', 'violation_message': '分类有误',
        'semantic_intent': {'metrics': [{'side': 'left', 'term': '类别', 'fields': ['kind']}],
                            'scopes': [], 'open_questions': []}}}


@pytest.mark.parametrize('dialect', ['mysql', 'postgresql'])
def test_substrings_and_text_codes_match_sql_and_synthetic_cases(dialect):
    filters = [{'field': 'caption', 'op': 'contains_any', 'value': INCLUDED},
               {'field': 'caption', 'op': 'not_contains_any', 'value': EXCLUDED}]
    rules, _ = _rules_with_doc([proposal(filters)], fields=FIELDS)
    result = rules.parse_rule_request(user(), _request(request_text='核查指定标题的类别', analysis_protocol=2))
    preview = result['preview']
    definition = {**preview['definition'], 'dialect': dialect}
    assert definition['expression']['right'] == '02'
    assert run_preview_cases(preview)['failed_count'] == 0
    assert {c['expected_count'] for c in preview['cases']} == {0, 1}
    excluded_case = next(c for c in preview['cases'] if '同时含排除词' in c['name'])
    title = excluded_case['row']['base']['caption']
    assert any(x in title for x in INCLUDED) and any(x in title for x in EXCLUDED)
    sql, params = compile_rule({'definition': definition})
    assert '夏日' not in sql
    display = inline_sql_parameters(sql, params, dialect)
    assert ':report_date' in display and ':right_value' not in display and ':filter_' not in display
    data = [('a', '夏日计划', '2'), ('b', "x%_!'\\y", '3'), ('c', '红赤色', '2'),
            ('d', 'xxAA!y', '2'), ('e', '夏日托管', '2'), ('f', '夏日转发', '2'),
            ('g', '夏日', '02'), ('h', '夏日', None), ('i', '夏日', ''), ('j', None, '2')]
    with sqlite3.connect(':memory:') as conn:
        register_literal_position_dialects(conn)
        conn.execute('CREATE TABLE test_table(row_id TEXT, day DATE, caption TEXT, kind TEXT)')
        conn.executemany('INSERT INTO test_table VALUES(?, CURRENT_DATE, ?, ?)', data)
        date = conn.execute('SELECT CURRENT_DATE').fetchone()[0]
        assert {r[0] for r in conn.execute(sql, {**params, 'report_date': date})} == {'a', 'b', 'c'}


def register_literal_position_dialects(conn):
    # SQLite's built-in instr has the same literal position contract as PostgreSQL strpos.
    for name in ("C", "utf8mb4_bin"):
        conn.create_collation(name, lambda left, right: (left > right) - (left < right))
    conn.create_function("STRPOS", 2, lambda string, word:
                         conn.execute("SELECT instr(?, ?)", (string, word)).fetchone()[0])


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
@pytest.mark.parametrize("op", ["contains_any", "not_contains_any"])
def test_keywords_are_case_sensitive_with_case_insensitive_source_collation(dialect, op):
    from auto_check.modules.data_validation.compiler import _filter_predicate
    from auto_check.modules.data_validation.query_samples import filter_matches

    words = ["center", "Été", "%_!'\\", "研究院"]
    params = {}
    predicate = _filter_predicate(dialect, "t", {"field": "caption", "op": op, "value": words}, params, 1)
    data = ["CENTER", "center", "Center", "ÉTÉ", "Été", "E\u0301te\u0301", "xx%_!'\\yy", "ABCXYZ", "市研究院", "", None]
    with sqlite3.connect(":memory:") as conn:
        register_literal_position_dialects(conn)
        conn.execute("CREATE TABLE captions(caption TEXT COLLATE NOCASE)")
        conn.executemany("INSERT INTO captions VALUES (?)", [(value,) for value in data])
        hits = [r[0] for r in conn.execute("SELECT caption FROM captions AS t WHERE " + predicate, params)]
    expected = [v for v in data if filter_matches(op, v, words)]
    assert hits == expected


def test_model_literal_alternation_is_canonicalized_but_real_regex_is_clarified():
    first = proposal([{'op': 'regexp', 'field': 'caption', 'value': '雪|月'},
                      {'op': 'not_regexp', 'field': 'caption', 'value': '内部|草稿'}])
    rules, _ = _rules_with_doc([first], fields=FIELDS)
    request = _request(request_text='核查所提标题的分类', analysis_protocol=2)
    result = rules.parse_rule_request(user(), request)
    assert [(f['op'], f['value']) for f in result['preview']['definition']['filters']] == [
        ('contains_any', ['雪', '月']), ('not_contains_any', ['内部', '草稿'])]
    definition = result['preview']['definition']
    saved = rules.save_draft(user(), definition)
    reloaded = rules.storage.latest_version(saved['id'])['definition']
    assert reloaded['expression'] == definition['expression']
    assert reloaded['filters'] == definition['filters']
    reloaded['name'] = '保存后重命名'
    rules.save_draft(user(), reloaded, saved['id'])
    updated = rules.storage.latest_version(saved['id'])['definition']
    assert updated['name'] == '保存后重命名' and updated['expression']['right'] == '02'
    rules, _ = _rules_with_doc([proposal([{'op': 'regexp', 'field': 'caption', 'value': '^雪.*月$'}])], fields=FIELDS)
    result = rules.parse_rule_request(user(), request)
    assert not result.get('preview') and '正则' in str(result.get('unsupported_requirements') or result['uncertainties'])


@pytest.mark.parametrize('wrong_code', ['2', '7'])
def test_named_dictionary_label_is_bound_to_its_exact_text_code(wrong_code):
    rules, _ = _rules_with_doc([proposal([], value=wrong_code)], fields=FIELDS)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'kind').values(dictionary='02-加急\n7-普通'))
    request = _request(request_text='类别未归为“加急”时请核对', analysis_protocol=2)
    result = rules.parse_rule_request(user(), request)
    assert result['preview']['definition']['expression']['right'] == '02'


@pytest.mark.parametrize('dtype,op,literal,valid', [
    ('enum', 'eq', '02', True), ('varchar', 'neq', 'X', True), ('numeric', 'eq', '2', False),
    ('varchar', 'lt', '2', False), ('date', 'eq', '2026-01-01', False), ('varchar', 'eq', 2, False)])
def test_text_comparison_only_eq_neq_on_documented_character_fields(dtype, op, literal, valid):
    definition = {'rule_type': 'field_compare', 'expression': proposal([], op, literal)['draft']['expression'],
                  'filters': [{'field': 'caption', 'op': 'is_not_null'}], 'business_key': 'row_id',
                  'report_date_field': 'day', 'include_result_fields': True}
    columns = [{'column_name': n, 'data_type': dtype if n == 'kind' else t} for n, _, t, _ in FIELDS]
    if valid:
        validate_spec_against_columns(definition, columns)
    else:
        with pytest.raises(AppError):
            validate_spec_against_columns(definition, columns)
