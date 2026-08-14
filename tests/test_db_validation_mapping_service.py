from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from auto_check.app.pbc_import import TableColumn
from auto_check.db_validation.mapping_models import FieldMapping, TableMapping
from auto_check.db_validation.mapping_service import DbValidationMappingService
from auto_check.db_validation.metadata import TableFieldCatalog
from auto_check.db_validation.rules.basic import (
    OPTIONAL_CHINESE_FIELDS_BY_SCOPE,
    REQUIRED_CHINESE_FIELDS_BY_SCOPE,
)


@dataclass
class FakeConfig:
    db_type: str = "postgresql"
    schema: str = "meta"


class FakeMetadataClient:
    def __init__(self, tables: list[dict[str, Any]], fields: list[dict[str, Any]]):
        self.config = FakeConfig()
        self.tables = tables
        self.fields = fields
        self._id_by_table = {
            row["table_name_en"]: f"t{index}" for index, row in enumerate(tables, start=1)
        }

    def fetch_all(self, sql: str, params=()):
        if "field_propert" in sql:
            rows = []
            for field_index, field in enumerate(self.fields, start=1):
                table_name = field.get("table")
                if table_name is None and len(self.tables) == 1:
                    table_name = self.tables[0]["table_name_en"]
                table_id = self._id_by_table.get(str(table_name))
                if table_id is None:
                    continue
                rows.append(
                    {
                        "table_id": table_id,
                        "field_propert": field["english"],
                        "field_name": field["chinese"],
                        "sort": str(field_index),
                    }
                )
            return rows
        if "SELECT id, table_name_en" in sql:
            return [
                {"id": self._id_by_table[row["table_name_en"]], "table_name_en": row["table_name_en"]}
                for row in self.tables
            ]
        return [{"table_name_en": row["table_name_en"]} for row in self.tables]


class FakeDataClient:
    def __init__(self, columns_by_table: dict[str, list[str]]):
        self.config = FakeConfig(schema="dws")
        self.columns_by_table = columns_by_table

    def table_columns(self, table):
        if hasattr(table, "parts"):
            name = table.parts[-1]
        elif hasattr(table, "name"):
            name = table.name
        else:
            name = str(table)
        return [TableColumn(name=column) for column in self.columns_by_table.get(name, [])]


class FakeStorage:
    def __init__(self, tables: list[TableMapping], overrides: list[dict[str, Any]] | None = None):
        self.tables = list(tables)
        self.overrides = list(overrides or [])
        self.saved: dict[str, Any] | None = None
        self.cross_tables = []

    def load_tables(self) -> tuple[TableMapping, ...]:
        return tuple(self.tables)

    def load_active_overrides(self) -> list[dict[str, Any]]:
        return [item for item in self.overrides if item.get("active", True)]

    def save_snapshot(self, *, signature, refresh_source, tables, fields) -> TableFieldCatalog:
        self.saved = {
            "signature": signature,
            "refresh_source": refresh_source,
            "tables": list(tables),
            "fields": list(fields),
        }
        table_mappings = {
            (item.relation_type, item.logical_code, item.scope_code): item.effective_table_name
            for item in tables
        }
        by_table: dict[str, dict[str, str]] = {}
        for item in fields:
            if item.mapping_status == "mapped" and item.chinese_name and item.effective_field_name:
                by_table.setdefault(next(
                    table.effective_table_name
                    for table in tables
                    if (table.relation_type, table.logical_code, table.scope_code)
                    == (item.relation_type, item.logical_code, item.scope_code)
                ), {})[item.chinese_name] = item.effective_field_name
        return TableFieldCatalog(by_table=by_table, table_mappings=table_mappings)

    def refresh_cross_table_mappings(self, mappings) -> None:
        self.cross_tables = list(mappings)


SEED_TABLES = [
    TableMapping("detail", "ZG01", "", "zgxgzh_baseinfo_zg01_26"),
    TableMapping("detail", "ZG09", "", "zgxgzh_debtordate_zg09"),
    TableMapping("template", "ZG09", "1", "balance_sheet_info"),
    TableMapping("template", "ZG09", "2", "balance_sheet_info_zcglxt"),
    TableMapping("public_info", "PUBLIC_INFO", "", "public_information_rh"),
]


def _service_with_storage(storage: FakeStorage) -> DbValidationMappingService:
    service = DbValidationMappingService(database=object())
    service.storage = storage
    return service


def test_mapping_requirements_use_each_zg_table_official_business_field_names():
    assert "发行机构代码" in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG01"]

    assert "资产收益权内部编码" in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG06"]
    assert "受益权代码" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG06"]
    assert "基础资产投向对象行业" in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG06"]
    assert "基础资产投向对象规模" in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG06"]
    assert "基础资产投向部门所属行业" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG06"]
    assert "基础资产投向部门规模" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG06"]
    assert "基础资产期末余额折人民币" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG06"]
    assert "数据管理机构" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG06"]

    assert "转让展期到期日期" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG07"]
    assert "贷款展期到期日期" in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG07"]
    assert "利率是否固定" in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG07"]

    assert "发行机构代码" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG08"]

    for code in ("ZG09", "ZG10"):
        assert "信托产品类型口径" in REQUIRED_CHINESE_FIELDS_BY_SCOPE[code]
        assert "基础资产出让机构代码" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE[code]
        assert "发行机构代码" in REQUIRED_CHINESE_FIELDS_BY_SCOPE[code]
        assert "法人金融机构名称" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE[code]
        assert "数据管理机构" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE[code]

    assert "转让起始日期" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG12"]
    assert "除资产收益权外其他债权起始日期" in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG12"]
    assert "内部编码" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG12"]
    assert "除资产收益权外其他债权内部编码" in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG12"]

    assert "余额折人民币" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG13"]
    assert "其他股权余额折人民币" in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG13"]
    assert "数据管理机构" not in REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG13"]


def test_mapping_requirements_include_zg05_rule_indicator_names():
    assert {
        "A5100_除回购和拆借外贷款",
        "AD200_除资产收益权外其他债权",
        "A7310_非金融企业股权",
        "A7320_金融机构股权",
        "C1110_住户",
        "C1210_住户",
        "C1180_境外",
        "C1280_境外",
    }.issubset(REQUIRED_CHINESE_FIELDS_BY_SCOPE["ZG05"])


def test_optional_mapping_fields_remain_visible_without_becoming_validation_blockers():
    assert OPTIONAL_CHINESE_FIELDS_BY_SCOPE == {
        "ZG06": frozenset({"数据管理机构"}),
        "ZG08": frozenset({"发行机构代码"}),
        "ZG09": frozenset({"数据管理机构", "法人金融机构名称"}),
        "ZG10": frozenset({"数据管理机构", "法人金融机构名称"}),
        "ZG13": frozenset({"数据管理机构"}),
    }
    for scope_code, chinese_names in OPTIONAL_CHINESE_FIELDS_BY_SCOPE.items():
        assert chinese_names.isdisjoint(REQUIRED_CHINESE_FIELDS_BY_SCOPE.get(scope_code, frozenset()))


def test_refresh_updates_detail_table_from_source_but_keeps_template_and_public_seed_names():
    storage = FakeStorage(SEED_TABLES)
    service = _service_with_storage(storage)
    metadata = FakeMetadataClient(
        tables=[
            {"table_name_en": "zgxgzh_baseinfo_zg01_new"},
            {"table_name_en": "zgxgzh_debtordate_zg09"},
        ],
        fields=[
            {"table": "zgxgzh_baseinfo_zg01_new", "chinese": "产品代码", "english": "projcode"},
            {"table": "zgxgzh_debtordate_zg09", "chinese": "信托产品类型口径", "english": "cpkj"},
            {"table": "balance_sheet_info", "chinese": "指标值", "english": "field_value"},
            {"table": "public_information_rh", "chinese": "产品代码", "english": "projcode"},
        ],
    )
    data_clients = {
        "detail": FakeDataClient(
            {
                "zgxgzh_baseinfo_zg01_new": ["projcode", "orphan_col"],
                "zgxgzh_debtordate_zg09": ["cpkj"],
            }
        ),
        "template": FakeDataClient({"balance_sheet_info": ["field_value"], "balance_sheet_info_zcglxt": []}),
        "public_info": FakeDataClient({"public_information_rh": ["projcode"]}),
    }

    service.refresh(
        metadata_client=metadata,
        data_clients=data_clients,
        baseinfo_table="xt_reg_table_baseinfo",
        field_info_table="xt_reg_table_field_info",
        sys_manage_id="",
        classification_id="",
        signature=("sig",),
        source="manual",
        required_chinese_fields_by_scope={"ZG01": frozenset({"产品代码"})},
    )

    assert storage.saved is not None
    tables = {(item.relation_type, item.logical_code, item.scope_code): item for item in storage.saved["tables"]}
    assert tables[("detail", "ZG01", "")].automatic_table_name == "zgxgzh_baseinfo_zg01_new"
    assert tables[("template", "ZG09", "1")].automatic_table_name == "balance_sheet_info"
    assert tables[("public_info", "PUBLIC_INFO", "")].automatic_table_name == "public_information_rh"


def test_refresh_prefers_stable_detail_table_over_change_variant():
    storage = FakeStorage([TableMapping("detail", "ZG01", "", "zgxgzh_baseinfo_zg01_change")])
    service = _service_with_storage(storage)
    metadata = FakeMetadataClient(
        tables=[
            {"table_name_en": "zgxgzh_baseinfo_zg01_26"},
            {"table_name_en": "zgxgzh_baseinfo_zg01_change"},
        ],
        fields=[],
    )

    service.refresh(
        metadata_client=metadata,
        data_clients={"detail": FakeDataClient({"zgxgzh_baseinfo_zg01_26": []})},
        baseinfo_table="xt_reg_table_baseinfo", field_info_table="xt_reg_table_field_info",
        sys_manage_id="", classification_id="", signature=("sig",), source="manual",
    )

    assert storage.saved["tables"][0].automatic_table_name == "zgxgzh_baseinfo_zg01_26"


def test_refresh_builds_cross_table_rows_for_all_current_zg09_zg10_metric_fields():
    storage = FakeStorage([
        TableMapping("detail", "ZG09", "", "zg09"),
        TableMapping("detail", "ZG10", "", "zg10"),
        TableMapping("template", "ZG09", "1", "template_zg09"),
        TableMapping("template", "ZG10", "1", "template_zg10"),
    ])
    service = _service_with_storage(storage)
    metadata = FakeMetadataClient(
        tables=[{"table_name_en": "zg09"}, {"table_name_en": "zg10"}],
        fields=[
            {"table": "zg09", "chinese": "表内资产余额", "english": "fb00001"},
            {"table": "zg09", "chinese": "期限指标", "english": "g123b"},
            {"table": "zg10", "chinese": "配置指标", "english": "h15000"},
        ],
    )
    clients = {
        "detail": FakeDataClient({"zg09": ["fb00001", "g123b"], "zg10": ["h15000"]}),
        "template": FakeDataClient({"template_zg09": [], "template_zg10": []}),
    }

    service.refresh(
        metadata_client=metadata, data_clients=clients,
        baseinfo_table="xt_reg_table_baseinfo", field_info_table="xt_reg_table_field_info",
        sys_manage_id="", classification_id="", signature=("sig",), source="manual",
    )

    pairs = {(item.logical_code, item.automatic_detail_field_name): item.automatic_template_field_name for item in storage.cross_tables}
    assert pairs == {
        ("ZG09", "fb00001"): "f1",
        ("ZG09", "g123b"): "B_g12300",
        ("ZG10", "h15000"): "A_h15000",
    }


def test_refresh_only_lists_rule_required_fields_and_ignores_metadata_and_physical_extras():
    storage = FakeStorage([TableMapping("detail", "ZG01", "", "zgxgzh_baseinfo_zg01_26")])
    service = _service_with_storage(storage)
    metadata = FakeMetadataClient(
        tables=[{"table_name_en": "zgxgzh_baseinfo_zg01_26"}],
        fields=[
            {"chinese": "产品代码", "english": "projcode"},
            {"chinese": "幽灵字段", "english": "ghost_col"},
        ],
    )
    data_clients = {
        "detail": FakeDataClient({"zgxgzh_baseinfo_zg01_26": ["projcode", "orphan_col", "id"]}),
    }

    service.refresh(
        metadata_client=metadata,
        data_clients=data_clients,
        baseinfo_table="xt_reg_table_baseinfo",
        field_info_table="xt_reg_table_field_info",
        sys_manage_id="",
        classification_id="",
        signature=("sig",),
        source="manual",
        required_chinese_fields_by_scope={"ZG01": frozenset({"产品代码", "产品名称"})},
    )

    fields = storage.saved["fields"]
    by_key = {(item.chinese_name, item.automatic_field_name): item for item in fields}
    assert by_key[("产品代码", "projcode")].mapping_status == "mapped"
    assert by_key[("产品代码", "projcode")].is_required is True
    assert not any(item.automatic_field_name == "orphan_col" for item in fields)
    assert not any(item.chinese_name == "幽灵字段" for item in fields)
    required_missing = [item for item in fields if item.mapping_status == "required_missing"]
    assert any(item.chinese_name == "产品名称" for item in required_missing)


def test_refresh_keeps_optional_unmapped_field_without_marking_required_missing():
    storage = FakeStorage([TableMapping("detail", "ZG06", "", "zg06")])
    service = _service_with_storage(storage)
    metadata = FakeMetadataClient(tables=[{"table_name_en": "zg06"}], fields=[])

    service.refresh(
        metadata_client=metadata,
        data_clients={"detail": FakeDataClient({"zg06": []})},
        baseinfo_table="xt_reg_table_baseinfo",
        field_info_table="xt_reg_table_field_info",
        sys_manage_id="",
        classification_id="",
        signature=("sig",),
        source="manual",
        required_chinese_fields_by_scope={"ZG06": frozenset()},
        optional_chinese_fields_by_scope={"ZG06": frozenset({"数据管理机构"})},
    )

    assert len(storage.saved["fields"]) == 1
    item = storage.saved["fields"][0]
    assert item.chinese_name == "数据管理机构"
    assert item.mapping_status == "unmapped"
    assert item.is_required is False


def test_refresh_maps_optional_field_without_marking_it_required():
    storage = FakeStorage([TableMapping("detail", "ZG06", "", "zg06")])
    service = _service_with_storage(storage)
    metadata = FakeMetadataClient(
        tables=[{"table_name_en": "zg06"}],
        fields=[{"chinese": "数据管理机构", "english": "manager_org"}],
    )

    service.refresh(
        metadata_client=metadata,
        data_clients={"detail": FakeDataClient({"zg06": ["manager_org"]})},
        baseinfo_table="xt_reg_table_baseinfo",
        field_info_table="xt_reg_table_field_info",
        sys_manage_id="",
        classification_id="",
        signature=("sig",),
        source="manual",
        required_chinese_fields_by_scope={"ZG06": frozenset()},
        optional_chinese_fields_by_scope={"ZG06": frozenset({"数据管理机构"})},
    )

    item = storage.saved["fields"][0]
    assert item.mapping_status == "mapped"
    assert item.effective_field_name == "manager_org"
    assert item.is_required is False


def test_refresh_treats_field_as_required_when_present_in_both_scope_maps():
    storage = FakeStorage([TableMapping("detail", "ZG06", "", "zg06")])
    service = _service_with_storage(storage)
    metadata = FakeMetadataClient(tables=[{"table_name_en": "zg06"}], fields=[])

    service.refresh(
        metadata_client=metadata,
        data_clients={"detail": FakeDataClient({"zg06": []})},
        baseinfo_table="xt_reg_table_baseinfo",
        field_info_table="xt_reg_table_field_info",
        sys_manage_id="",
        classification_id="",
        signature=("sig",),
        source="manual",
        required_chinese_fields_by_scope={"ZG06": frozenset({"数据管理机构"})},
        optional_chinese_fields_by_scope={"ZG06": frozenset({"数据管理机构"})},
    )

    assert len(storage.saved["fields"]) == 1
    item = storage.saved["fields"][0]
    assert item.mapping_status == "required_missing"
    assert item.is_required is True


def test_refresh_excludes_template_storage_columns_from_field_mapping():
    storage = FakeStorage([TableMapping("template", "ZG09", "1", "balance_sheet_info")])
    service = _service_with_storage(storage)
    metadata = FakeMetadataClient(
        tables=[{"table_name_en": "balance_sheet_info"}],
        fields=[],
    )
    data_clients = {
        "template": FakeDataClient({
            "balance_sheet_info": [
                "id", "field_name", "field_value", "field_type", "create_by", "create_date",
            ],
        }),
    }

    service.refresh(
        metadata_client=metadata,
        data_clients=data_clients,
        baseinfo_table="xt_reg_table_baseinfo",
        field_info_table="xt_reg_table_field_info",
        sys_manage_id="",
        classification_id="",
        signature=("sig",),
        source="manual",
    )

    assert storage.saved["fields"] == []


def test_refresh_loads_public_info_metadata_with_its_own_filters():
    class FilteredMetadataClient(FakeMetadataClient):
        def fetch_all(self, sql: str, params=()):
            if "SELECT table_name_en" in sql and "SELECT id" not in sql:
                return [{"table_name_en": "zgxgzh_baseinfo_zg01_26"}]
            if "SELECT id, table_name_en" in sql:
                selected = "public_information_rh" if "PUBLIC_SYS" in params else "zgxgzh_baseinfo_zg01_26"
                return [{"id": self._id_by_table[selected], "table_name_en": selected}]
            return super().fetch_all(sql, params)

    storage = FakeStorage([
        TableMapping("detail", "ZG01", "", "zgxgzh_baseinfo_zg01_26"),
        TableMapping("public_info", "PUBLIC_INFO", "", "public_information_rh"),
    ])
    service = _service_with_storage(storage)
    metadata = FilteredMetadataClient(
        tables=[
            {"table_name_en": "zgxgzh_baseinfo_zg01_26"},
            {"table_name_en": "public_information_rh"},
        ],
        fields=[
            {"table": "zgxgzh_baseinfo_zg01_26", "chinese": "产品代码", "english": "projcode"},
            {"table": "public_information_rh", "chinese": "信息类型名称", "english": "infotype"},
            {"table": "public_information_rh", "chinese": "产品代码", "english": "productcode"},
        ],
    )

    service.refresh(
        metadata_client=metadata,
        data_clients={
            "detail": FakeDataClient({"zgxgzh_baseinfo_zg01_26": ["projcode"]}),
            "public_info": FakeDataClient({"public_information_rh": ["infotype", "productcode"]}),
        },
        baseinfo_table="xt_reg_table_baseinfo",
        field_info_table="xt_reg_table_field_info",
        sys_manage_id="DETAIL_SYS",
        classification_id="DETAIL_CLASS",
        public_info_sys_manage_id="PUBLIC_SYS",
        public_info_classification_id="PUBLIC_CLASS",
        signature=("sig",),
        source="manual",
        required_chinese_fields_by_scope={
            "PUBLIC_INFO": frozenset({"信息类型名称", "产品代码"}),
        },
    )

    public_fields = {
        item.chinese_name: item
        for item in storage.saved["fields"]
        if item.relation_type == "public_info"
    }
    assert public_fields["信息类型名称"].effective_field_name == "infotype"
    assert public_fields["信息类型名称"].mapping_status == "mapped"
    assert public_fields["产品代码"].effective_field_name == "productcode"
    assert not [item for item in public_fields.values() if item.mapping_status == "required_missing"]


def test_refresh_marks_non_exact_required_name_as_semantic_match():
    storage = FakeStorage([TableMapping("public_info", "PUBLIC_INFO", "", "public_information_rh")])
    service = _service_with_storage(storage)
    metadata = FakeMetadataClient(
        tables=[{"table_name_en": "public_information_rh"}],
        fields=[
            {"chinese": "地区代码", "english": "areacode"},
            {"chinese": "实际终止日", "english": "realdate"},
        ],
    )

    service.refresh(
        metadata_client=metadata,
        data_clients={"public_info": FakeDataClient({"public_information_rh": ["areacode", "realdate"]})},
        baseinfo_table="xt_reg_table_baseinfo",
        field_info_table="xt_reg_table_field_info",
        sys_manage_id="",
        classification_id="",
        signature=("sig",),
        source="manual",
        required_chinese_fields_by_scope={
            "PUBLIC_INFO": frozenset({"地区", "产品实际终止日期"}),
        },
    )

    public_fields = {item.chinese_name: item for item in storage.saved["fields"]}
    assert public_fields["地区"].mapping_status == "mapped"
    assert public_fields["地区"].status_message == "语义匹配：元数据“地区代码”"
    assert public_fields["产品实际终止日期"].status_message == "语义匹配：元数据“实际终止日”"
    assert not [item for item in public_fields.values() if item.mapping_status == "required_missing"]


def test_refresh_does_not_replace_rule_field_with_uncertain_metadata_name():
    storage = FakeStorage([TableMapping("detail", "ZG06", "", "zg06")])
    service = _service_with_storage(storage)
    metadata = FakeMetadataClient(
        tables=[{"table_name_en": "zg06"}],
        fields=[
            {"chinese": "基础资产投向部门所属行业", "english": "txbmhy"},
            {"chinese": "基础资产投向部门规模", "english": "txbmgm"},
        ],
    )

    service.refresh(
        metadata_client=metadata,
        data_clients={"detail": FakeDataClient({"zg06": ["txbmhy", "txbmgm"]})},
        baseinfo_table="xt_reg_table_baseinfo",
        field_info_table="xt_reg_table_field_info",
        sys_manage_id="",
        classification_id="",
        signature=("sig",),
        source="manual",
        required_chinese_fields_by_scope={
            "ZG06": frozenset({"基础资产投向对象行业", "基础资产投向对象规模"}),
        },
    )

    fields = {item.chinese_name: item for item in storage.saved["fields"]}
    assert set(fields) == {"基础资产投向对象行业", "基础资产投向对象规模"}
    assert {item.mapping_status for item in fields.values()} == {"required_missing"}
    assert {item.effective_field_name for item in fields.values()} == {None}


def test_refresh_merges_exact_and_semantic_rule_names_into_one_metadata_row():
    storage = FakeStorage([TableMapping("detail", "ZG02", "", "zg02")])
    service = _service_with_storage(storage)
    metadata = FakeMetadataClient(
        tables=[{"table_name_en": "zg02"}],
        fields=[{"chinese": "地区", "english": "areacode"}],
    )

    service.refresh(
        metadata_client=metadata,
        data_clients={"detail": FakeDataClient({"zg02": ["areacode"]})},
        baseinfo_table="xt_reg_table_baseinfo",
        field_info_table="xt_reg_table_field_info",
        sys_manage_id="",
        classification_id="",
        signature=("sig",),
        source="manual",
        required_chinese_fields_by_scope={"ZG02": frozenset({"地区", "地区代码"})},
    )

    assert [(item.chinese_name, item.effective_field_name) for item in storage.saved["fields"]] == [
        ("地区", "areacode"),
    ]
    assert storage.saved["fields"][0].status_message == "语义匹配：校验字段“地区代码”共用元数据“地区”"


def test_refresh_preserves_active_field_and_table_overrides():
    tables = [
        TableMapping(
            "detail",
            "ZG01",
            "",
            "zgxgzh_baseinfo_zg01_26",
            override_table_name="zgxgzh_baseinfo_zg01_override",
        )
    ]
    storage = FakeStorage(
        tables,
        overrides=[
            {
                "mapping_kind": "field",
                "relation_type": "detail",
                "logical_code": "ZG01",
                "scope_code": "",
                "chinese_name": "产品代码",
                "override_value": "projcode_new",
                "active": True,
            }
        ],
    )
    service = _service_with_storage(storage)
    metadata = FakeMetadataClient(
        tables=[{"table_name_en": "zgxgzh_baseinfo_zg01_26"}],
        fields=[{"chinese": "产品代码", "english": "projcode_old"}],
    )
    data_clients = {
        "detail": FakeDataClient({"zgxgzh_baseinfo_zg01_override": ["projcode_new"]}),
    }

    service.refresh(
        metadata_client=metadata,
        data_clients=data_clients,
        baseinfo_table="xt_reg_table_baseinfo",
        field_info_table="xt_reg_table_field_info",
        sys_manage_id="",
        classification_id="",
        signature=("sig",),
        source="manual",
        required_chinese_fields_by_scope={"ZG01": frozenset({"产品代码"})},
    )

    saved_table = storage.saved["tables"][0]
    assert saved_table.override_table_name == "zgxgzh_baseinfo_zg01_override"
    assert saved_table.effective_table_name == "zgxgzh_baseinfo_zg01_override"
    field = next(item for item in storage.saved["fields"] if item.chinese_name == "产品代码")
    assert isinstance(field, FieldMapping)
    assert field.override_field_name == "projcode_new"
    assert field.effective_field_name == "projcode_new"
    assert field.mapping_status == "mapped"
