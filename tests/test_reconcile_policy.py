from decimal import Decimal

from mysql_config_test_support import MemoryApplicationDatabase

from auto_check.app.storage_dictionaries import (
    create_dictionary_item, delete_dictionary_item, list_dictionaries,
    update_dictionary, update_dictionary_item,
)


def test_bond_cost_dictionary_initializes_five_projects_without_all():
    from auto_check.app.reconcile_policy import initialize_bond_cost_dictionary, load_bond_cost_projects

    db = MemoryApplicationDatabase()
    initialize_bond_cost_dictionary(db)
    initialize_bond_cost_dictionary(db)
    assert load_bond_cost_projects(db) == frozenset({
        "2024XJC0001", "2024XJC0002", "2019KJC0072", "2020HJC0446", "2020HJC0771",
    })
    with db.connect() as connection:
        dictionaries = list_dictionaries(connection)
    assert len(dictionaries) == 1
    assert dictionaries[0]["code"] == "reconcile_bond_cost_projects"
    assert dictionaries[0]["system_locked"] is True
    assert len(dictionaries[0]["items"]) == 5


def test_bond_cost_dictionary_respects_disabled_deleted_and_all_items():
    from auto_check.app.reconcile_policy import initialize_bond_cost_dictionary, load_bond_cost_projects

    db = MemoryApplicationDatabase()
    assert load_bond_cost_projects(db) == frozenset()
    initialize_bond_cost_dictionary(db)
    code = "reconcile_bond_cost_projects"
    with db.transaction() as connection:
        items = list_dictionaries(connection)[0]["items"]
        update_dictionary_item(connection, code, items[0]["id"], enabled=False)
        delete_dictionary_item(connection, code, items[1]["id"])
        all_item = create_dictionary_item(connection, dictionary_code=code, item_code="all", item_name="所有")
    initialize_bond_cost_dictionary(db)
    assert load_bond_cost_projects(db) == frozenset({"2019KJC0072", "2020HJC0446", "2020HJC0771", "all"})
    with db.transaction() as connection:
        update_dictionary_item(connection, code, all_item["id"], enabled=False)
    assert "all" not in load_bond_cost_projects(db)
    with db.transaction() as connection:
        update_dictionary(connection, code, enabled=False)
    initialize_bond_cost_dictionary(db)
    assert load_bond_cost_projects(db) == frozenset()


def test_runner_reads_current_dictionary_on_each_execution(tmp_path):
    from auto_check.app.reconcile_policy import initialize_bond_cost_dictionary
    from auto_check.app.server import ApiRouter, default_config

    db = MemoryApplicationDatabase()
    initialize_bond_cost_dictionary(db)
    router = ApiRouter(config_path=tmp_path / "config.json", application_database=db, start_field_mapping_auto_refresh=False)
    runner = router._create_runner(default_config(), max_combination_rows=50)
    assert "2020HJC0446" in runner.bond_cost_projects
    assert "all" not in runner.bond_cost_projects
    with db.transaction() as connection:
        create_dictionary_item(connection, dictionary_code="reconcile_bond_cost_projects", item_code="all", item_name="所有")
    next_runner = router._create_runner(default_config(), max_combination_rows=50)
    assert "all" in next_runner.bond_cost_projects
    assert "all" not in runner.bond_cost_projects


def test_enabled_project_cost_match_leaves_reverse_repo_as_explanation():
    from auto_check.app.reconcile_policy import initialize_bond_cost_dictionary, load_bond_cost_projects
    from auto_check.engine.models import ProjectBalance, ValuationRow
    from auto_check.engine.reconcile import ReconcileEngine
    from test_reconcile import FakeRepo

    db = MemoryApplicationDatabase()
    initialize_bond_cost_dictionary(db)
    repo = FakeRepo()
    code = "2020HJC0446"
    repo.projects = [ProjectBalance(code, "截图项目", Decimal("442716974.77"), Decimal("442716775.77"))]
    repo.asset_total[code] = Decimal("442716775.77")
    repo.valuation[code] = [
        ValuationRow("1501.01.1C.01.253096", "23姜交03", Decimal("16036304.00")),
        ValuationRow("1111.03.01.01", "逆回购", Decimal("18000000.00")),
    ]
    repo.security_balance_amounts[code] = [{"stock_code": "253096", "security_name": "23姜交03", "amount": Decimal("16008989.25")}]
    repo.valuation_cost_rows[code] = [{"account_code": "1501.01.1C.01.253096", "account_name": "23姜交03", "cost": Decimal("16008989.25")}]
    repo.reverse_repo_business_amounts[code] = Decimal("18000199.00")
    result = ReconcileEngine(repo, bond_cost_projects=load_bond_cost_projects(db)).run("2026-10-31")[0]
    assert result.match_status == "已解释"
    data = result.details[-1].data
    assert data["difference_total"] == "199.00"
    assert [row["asset_type"] for row in data["rows"]] == ["逆回购"]
