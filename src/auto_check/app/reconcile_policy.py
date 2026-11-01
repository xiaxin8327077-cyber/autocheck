"""自动对数的应用字典配置与首次初始化。"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from auto_check.app.storage_dictionaries import DICTIONARIES, DICTIONARY_ITEMS, list_active_dictionary_items


BOND_COST_DICTIONARY = "reconcile_bond_cost_projects"
_INITIAL_PROJECTS = (
    ("2024XJC0001", "江苏信托-乐享稳利1号集合资金信托计划"),
    ("2024XJC0002", "江苏信托-乐享稳利2号集合资金信托计划"),
    ("2019KJC0072", "江苏信托·现金添利1号集合资金信托计划"),
    ("2020HJC0446", "江苏信托安鑫添利周开1号集合资金信托计划（SXZK01）"),
    ("2020HJC0771", "江苏信托安鑫添利周开2号集合资金信托计划（SXZK02）"),
)


def initialize_bond_cost_dictionary(database) -> None:
    """仅首次创建分类时填入项目；保留后续启停、增删和名称维护。"""
    with database.transaction() as connection:
        existing = connection.execute(
            select(DICTIONARIES).where(DICTIONARIES.c.dictionary_code == BOND_COST_DICTIONARY)
        ).mappings().all()
        if existing:
            return
        now = datetime.now(UTC).replace(tzinfo=None)
        audit = dict(created_by="system", created_at=now, updated_by="system", updated_at=now)
        statement = mysql_insert(DICTIONARIES).values(
            dictionary_code=BOND_COST_DICTIONARY, dictionary_name="债券成本备用核对项目",
            description="先比较估值金额，不一致再按成本核对；项目编码匹配，编码all、名称所有表示全部项目",
            enabled=1, system_locked=1, sort_order=30, **audit,
        )
        connection.execute(statement.on_duplicate_key_update(dictionary_code=DICTIONARIES.c.dictionary_code))
        for order, (code, name) in enumerate(_INITIAL_PROJECTS, start=1):
            statement = mysql_insert(DICTIONARY_ITEMS).values(
                dictionary_code=BOND_COST_DICTIONARY, item_code=code, item_name=name,
                description="启用债券f_cost备用一致性核对", enabled=1, sort_order=order * 10, **audit,
            )
            connection.execute(statement.on_duplicate_key_update(item_code=DICTIONARY_ITEMS.c.item_code))


def load_bond_cost_projects(database) -> frozenset[str]:
    """每次执行加载启用分类的启用项；无字典时不启用备用核对。"""
    with database.connect() as connection:
        items = list_active_dictionary_items(connection, BOND_COST_DICTIONARY)
    return frozenset(item["code"] for item in items)
