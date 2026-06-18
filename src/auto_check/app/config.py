from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from auto_check.app.local_store import (
    AUTH_KEY,
    CONFIG_STORE_KEY,
    load_json_file_payload,
    read_app_value,
    save_combined_payload,
    save_json_file_payload,
)
from auto_check.app.security import decrypt_secret, encrypt_secret


@dataclass(frozen=True)
class DataSourceConfig:
    db_type: str
    host: str
    port: int
    database: str
    schema: str
    username: str
    password: str


@dataclass(frozen=True)
class AppConfig:
    dws: DataSourceConfig
    business: DataSourceConfig


@dataclass
class DataSourceEntry:
    id: str
    name: str
    config: DataSourceConfig
    is_default: bool = False


@dataclass(frozen=True)
class ReconcileDataSourceSettings:
    dws_source_id: str = ""
    business_source_id: str = ""


@dataclass(frozen=True)
class DefaultSettings:
    session_expire_hours: int = 8
    page_size: int = 10
    combination_limit: int = 50
    auto_refresh_home: bool = False
    visual_effects: bool = True
    theme: str = "space-tech"
    dark_mode: bool = False


@dataclass(frozen=True)
class PbcImportToolSettings:
    recent_tables: list[str] = field(default_factory=list)
    last_config_name: str = ""
    last_source: str = "dws"


@dataclass(frozen=True)
class DbValidationDatasetSettings:
    source_id: str = ""
    sys_manage_id: str = ""
    classification_id: str = ""
    # Legacy fields are accepted during migration and ignored when writing the
    # new config format.
    config_name: str = ""
    source: str = "dws"


@dataclass(frozen=True)
class DbValidationSettings:
    detail: DbValidationDatasetSettings = field(default_factory=DbValidationDatasetSettings)
    public_info: DbValidationDatasetSettings = field(default_factory=DbValidationDatasetSettings)
    template: DbValidationDatasetSettings = field(default_factory=DbValidationDatasetSettings)
    field_mapping_source_id: str = ""
    # Legacy fields are accepted during migration and ignored when writing the
    # new config format.
    field_mapping_config_name: str = ""
    field_mapping_source: str = "dws"
    baseinfo_table: str = "xt_reg_table_baseinfo"
    field_info_table: str = "xt_reg_table_field_info"
    public_info_table: str = "public_information_rh"


@dataclass(frozen=True)
class FlowChainStep:
    flow_id: str
    name: str = ""


@dataclass(frozen=True)
class FlowChainConfig:
    id: str
    name: str
    steps: list[FlowChainStep] = field(default_factory=list)
    enabled: bool = True


@dataclass(frozen=True)
class FlowToolSettings:
    source_id: str = ""
    execute_url: str = ""
    flow_table: str = "sp_flow"
    task_table: str = "sp_task"
    poll_interval_seconds: int = 5
    step_timeout_minutes: int = 60
    chains: list[FlowChainConfig] = field(default_factory=list)


@dataclass
class NamedConfig:
    name: str
    dws: DataSourceConfig
    business: DataSourceConfig
    is_default: bool = False


@dataclass
class ConfigStore:
    configs: list[NamedConfig] = field(default_factory=list)
    data_sources: list[DataSourceEntry] = field(default_factory=list)
    reconcile_data_sources: ReconcileDataSourceSettings = field(default_factory=ReconcileDataSourceSettings)
    default_name: str = ""
    default_settings: DefaultSettings = field(default_factory=DefaultSettings)
    pbc_import_tool: PbcImportToolSettings = field(default_factory=PbcImportToolSettings)
    db_validation: DbValidationSettings = field(default_factory=DbValidationSettings)
    flow_tool: FlowToolSettings = field(default_factory=FlowToolSettings)


def _default_dws() -> DataSourceConfig:
    return DataSourceConfig(db_type="postgresql", host="127.0.0.1", port=5432, database="", schema="dws", username="", password="")


def _default_business() -> DataSourceConfig:
    return DataSourceConfig(db_type="mysql", host="127.0.0.1", port=3306, database="", schema="", username="", password="")


def default_config() -> AppConfig:
    return AppConfig(dws=_default_dws(), business=_default_business())


def default_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "auto-check" / "config.json"
    return Path.cwd() / "config" / "app-config.json"


def legacy_source_id(config_name: str, source: str) -> str:
    safe_name = str(config_name or "").strip()
    safe_source = _coerce_source(source)
    return f"legacy:{safe_name}:{safe_source}"


def resolve_data_source_entry(store: ConfigStore, source_id: str) -> DataSourceEntry:
    source_id = str(source_id or "").strip()
    for entry in normalize_store(store).data_sources:
        if entry.id == source_id:
            return entry
    raise ValueError("数据源不存在")


def resolve_data_source(store: ConfigStore, source_id: str) -> DataSourceConfig:
    return resolve_data_source_entry(store, source_id).config


def normalize_store(store: ConfigStore) -> ConfigStore:
    data_sources = list(store.data_sources)
    if not data_sources and store.configs:
        data_sources = _data_sources_from_legacy_configs(store.configs)

    default_name = store.default_name
    if not default_name and store.configs:
        default_config = next((config for config in store.configs if config.is_default), store.configs[0])
        default_name = default_config.name

    reconcile_settings = store.reconcile_data_sources
    if data_sources and (not reconcile_settings.dws_source_id or not reconcile_settings.business_source_id):
        reconcile_settings = _default_reconcile_settings(data_sources, store.configs, default_name)

    db_validation = _normalize_db_validation_settings(store.db_validation, default_name)
    return ConfigStore(
        configs=_legacy_configs_from_data_sources(data_sources),
        data_sources=data_sources,
        reconcile_data_sources=reconcile_settings,
        default_name=default_name,
        default_settings=store.default_settings,
        pbc_import_tool=store.pbc_import_tool,
        db_validation=db_validation,
        flow_tool=store.flow_tool,
    )


def _data_sources_from_legacy_configs(configs: list["NamedConfig"]) -> list[DataSourceEntry]:
    data_sources: list[DataSourceEntry] = []
    for config in configs:
        data_sources.append(
            DataSourceEntry(
                id=legacy_source_id(config.name, "dws"),
                name=f"{config.name} - DWS",
                config=config.dws,
                is_default=bool(config.is_default),
            )
        )
        data_sources.append(
            DataSourceEntry(
                id=legacy_source_id(config.name, "business"),
                name=f"{config.name} - 报表库",
                config=config.business,
                is_default=False,
            )
        )
    return data_sources


def _legacy_configs_from_data_sources(data_sources: list[DataSourceEntry]) -> list["NamedConfig"]:
    grouped: dict[str, dict[str, DataSourceEntry]] = {}
    for entry in data_sources:
        parts = entry.id.split(":", 2)
        if len(parts) != 3 or parts[0] != "legacy" or parts[2] not in {"dws", "business"}:
            continue
        grouped.setdefault(parts[1], {})[parts[2]] = entry
    configs: list[NamedConfig] = []
    for name, entries in grouped.items():
        if "dws" not in entries or "business" not in entries:
            continue
        configs.append(
            NamedConfig(
                name=name,
                dws=entries["dws"].config,
                business=entries["business"].config,
                is_default=bool(entries["dws"].is_default),
            )
        )
    return configs


def _default_reconcile_settings(
    data_sources: list[DataSourceEntry],
    configs: list["NamedConfig"],
    default_name: str,
) -> ReconcileDataSourceSettings:
    if configs:
        selected = next((config for config in configs if config.is_default or config.name == default_name), configs[0])
        return ReconcileDataSourceSettings(
            dws_source_id=legacy_source_id(selected.name, "dws"),
            business_source_id=legacy_source_id(selected.name, "business"),
        )
    default_entry = next((entry for entry in data_sources if entry.is_default), data_sources[0])
    fallback_business = next((entry for entry in data_sources if entry.id != default_entry.id), default_entry)
    return ReconcileDataSourceSettings(
        dws_source_id=default_entry.id,
        business_source_id=fallback_business.id,
    )


def _normalize_db_validation_settings(settings: DbValidationSettings, default_name: str) -> DbValidationSettings:
    return replace(
        settings,
        detail=_normalize_db_validation_dataset(settings.detail, default_name),
        public_info=_normalize_db_validation_dataset(settings.public_info, default_name),
        template=_normalize_db_validation_dataset(settings.template, default_name),
        field_mapping_source_id=(
            settings.field_mapping_source_id
            or _legacy_db_validation_source_id(
                settings.field_mapping_config_name or default_name,
                settings.field_mapping_source,
            )
        ),
    )


def _normalize_db_validation_dataset(
    settings: DbValidationDatasetSettings,
    default_name: str,
) -> DbValidationDatasetSettings:
    source_id = settings.source_id or _legacy_db_validation_source_id(settings.config_name or default_name, settings.source)
    return replace(settings, source_id=source_id)


def _legacy_db_validation_source_id(config_name: str, source: str) -> str:
    config_name = str(config_name or "").strip()
    if not config_name:
        return ""
    return legacy_source_id(config_name, source)


# ---- Store (multiple configs) ----

def load_store(path: str | Path | None = None) -> ConfigStore:
    config_path = Path(path) if path is not None else default_config_path()
    sqlite_payload = read_app_value(config_path, CONFIG_STORE_KEY)
    loaded_from_sqlite = isinstance(sqlite_payload, dict)
    if loaded_from_sqlite:
        snapshot = dict(sqlite_payload)
        existing_auth = _existing_auth(config_path)
        if existing_auth:
            snapshot[AUTH_KEY] = existing_auth
        save_json_file_payload(config_path, snapshot)

    if not config_path.exists():
        return ConfigStore()

    with config_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    # Migration: old single-config format -> store
    if "configs" not in payload and "data_sources" not in payload:
        if "dws" not in payload and "business" not in payload:
            store = ConfigStore()
            save_store(store, config_path)
            return store
        config = config_from_dict(payload)
        default_cfg = NamedConfig(name="默认测试数据源", dws=config.dws, business=config.business, is_default=True)
        store = normalize_store(ConfigStore(configs=[default_cfg], default_name="默认测试数据源"))
        save_store(store, config_path)
        return store

    if "data_sources" in payload:
        data_sources = [
            data_source_entry_from_dict(item)
            for item in payload.get("data_sources", [])
            if isinstance(item, dict)
        ]
        store = ConfigStore(
            configs=_legacy_configs_from_data_sources(data_sources),
            data_sources=data_sources,
            reconcile_data_sources=reconcile_data_source_settings_from_dict(payload.get("reconcile_data_sources", {})),
            default_name=str(payload.get("default_name", "")),
            default_settings=default_settings_from_dict(payload.get("default_settings", {})),
            pbc_import_tool=pbc_import_tool_settings_from_dict(payload.get("pbc_import_tool", {})),
            db_validation=db_validation_settings_from_dict(payload.get("db_validation", {})),
            flow_tool=flow_tool_settings_from_dict(payload.get("flow_tool", {})),
        )
        store = normalize_store(store)
        if not loaded_from_sqlite:
            save_store(store, config_path)
        return store

    configs = []
    for c in payload.get("configs", []):
        configs.append(NamedConfig(
            name=str(c["name"]),
            dws=_source_from_dict(c.get("dws", {}), _default_dws()),
            business=_source_from_dict(c.get("business", {}), _default_business()),
            is_default=bool(c.get("is_default", False)),
        ))
    store = ConfigStore(
        configs=configs,
        default_name=str(payload.get("default_name", "")),
        default_settings=default_settings_from_dict(payload.get("default_settings", {})),
        pbc_import_tool=pbc_import_tool_settings_from_dict(payload.get("pbc_import_tool", {})),
        db_validation=db_validation_settings_from_dict(payload.get("db_validation", {})),
        flow_tool=flow_tool_settings_from_dict(payload.get("flow_tool", {})),
    )
    store = normalize_store(store)
    save_store(store, config_path)
    return store


def save_store(store: ConfigStore, path: str | Path | None = None) -> None:
    config_path = Path(path) if path is not None else default_config_path()
    existing_auth = _existing_auth(config_path)
    store = normalize_store(store)
    payload = {
        "data_sources": [data_source_entry_to_dict(entry) for entry in store.data_sources],
        "reconcile_data_sources": reconcile_data_source_settings_to_dict(store.reconcile_data_sources),
        "default_name": store.default_name,
        "default_settings": default_settings_to_dict(store.default_settings),
        "pbc_import_tool": pbc_import_tool_settings_to_dict(store.pbc_import_tool),
        "db_validation": db_validation_settings_to_dict(store.db_validation),
        "flow_tool": flow_tool_settings_to_dict(store.flow_tool),
    }
    if existing_auth:
        payload[AUTH_KEY] = existing_auth
    save_combined_payload(config_path, payload)


def get_active_config(store: ConfigStore) -> AppConfig:
    store = normalize_store(store)
    if store.data_sources:
        try:
            return AppConfig(
                dws=resolve_data_source(store, store.reconcile_data_sources.dws_source_id),
                business=resolve_data_source(store, store.reconcile_data_sources.business_source_id),
            )
        except ValueError:
            pass
    for c in store.configs:
        if c.is_default or c.name == store.default_name:
            return AppConfig(dws=c.dws, business=c.business)
    if store.configs:
        c = store.configs[0]
        return AppConfig(dws=c.dws, business=c.business)
    return default_config()


# ---- Single config (backward compatible) ----

def load_config(path: str | Path | None = None) -> AppConfig:
    return get_active_config(load_store(path))


def save_config(config: AppConfig, path: str | Path | None = None) -> None:
    store = load_store(path)
    name = "默认测试数据源"
    dws_id = legacy_source_id(name, "dws")
    business_id = legacy_source_id(name, "business")
    store.data_sources = [entry for entry in store.data_sources if entry.id not in {dws_id, business_id}]
    store.data_sources.append(DataSourceEntry(id=dws_id, name=f"{name} - DWS", config=config.dws, is_default=True))
    store.data_sources.append(DataSourceEntry(id=business_id, name=f"{name} - 报表库", config=config.business))
    store.reconcile_data_sources = ReconcileDataSourceSettings(
        dws_source_id=dws_id,
        business_source_id=business_id,
    )
    store.default_name = name
    save_store(store, path)


def config_from_dict(payload: dict[str, Any]) -> AppConfig:
    defaults = default_config()
    return AppConfig(
        dws=_source_from_dict(payload.get("dws", {}), defaults.dws),
        business=_source_from_dict(payload.get("business", {}), defaults.business),
    )


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    return asdict(config)


def default_settings_from_dict(payload: dict[str, Any]) -> DefaultSettings:
    payload = payload or {}
    return DefaultSettings(
        session_expire_hours=_coerce_int(payload.get("session_expire_hours"), default=8, minimum=1, maximum=168),
        page_size=_coerce_int(payload.get("page_size"), default=10, minimum=1, maximum=500),
        combination_limit=_coerce_int(payload.get("combination_limit"), default=50, minimum=1, maximum=500),
        auto_refresh_home=_coerce_bool(payload.get("auto_refresh_home"), default=False),
        visual_effects=_coerce_bool(payload.get("visual_effects"), default=True),
        theme=_coerce_theme(payload.get("theme")),
        dark_mode=_coerce_bool(payload.get("dark_mode"), default=str(payload.get("theme", "")).strip() == "dark"),
    )


def default_settings_to_dict(settings: DefaultSettings) -> dict[str, Any]:
    return asdict(settings)


def data_source_entry_from_dict(payload: dict[str, Any]) -> DataSourceEntry:
    payload = payload or {}
    config_payload = payload.get("config") if isinstance(payload.get("config"), dict) else payload
    return DataSourceEntry(
        id=str(payload.get("id", "") or ""),
        name=str(payload.get("name", "") or ""),
        config=_source_from_dict(config_payload, _default_dws()),
        is_default=_coerce_bool(payload.get("is_default"), default=False),
    )


def data_source_entry_to_dict(entry: DataSourceEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "name": entry.name,
        **_source_to_dict(entry.config),
        "is_default": entry.is_default,
    }


def reconcile_data_source_settings_from_dict(payload: dict[str, Any]) -> ReconcileDataSourceSettings:
    payload = payload or {}
    return ReconcileDataSourceSettings(
        dws_source_id=str(payload.get("dws_source_id", "") or ""),
        business_source_id=str(payload.get("business_source_id", "") or ""),
    )


def reconcile_data_source_settings_to_dict(settings: ReconcileDataSourceSettings) -> dict[str, Any]:
    return asdict(settings)


def pbc_import_tool_settings_from_dict(payload: dict[str, Any]) -> PbcImportToolSettings:
    payload = payload or {}
    recent_tables: list[str] = []
    seen = set()
    for value in payload.get("recent_tables", []):
        table = str(value or "").strip()
        if table and table not in seen:
            seen.add(table)
            recent_tables.append(table)
    source = str(payload.get("last_source", "dws") or "dws").strip()
    if source not in {"dws", "business"}:
        source = "dws"
    return PbcImportToolSettings(
        recent_tables=recent_tables[:20],
        last_config_name=str(payload.get("last_config_name", "") or ""),
        last_source=source,
    )


def pbc_import_tool_settings_to_dict(settings: PbcImportToolSettings) -> dict[str, Any]:
    return asdict(settings)


def db_validation_settings_from_dict(payload: dict[str, Any]) -> DbValidationSettings:
    payload = payload or {}
    return DbValidationSettings(
        detail=db_validation_dataset_settings_from_dict(payload.get("detail", {})),
        public_info=db_validation_dataset_settings_from_dict(payload.get("public_info", {})),
        template=db_validation_dataset_settings_from_dict(payload.get("template", {})),
        field_mapping_source_id=str(payload.get("field_mapping_source_id", "") or ""),
        field_mapping_config_name=str(
            payload.get("field_mapping_config_name", payload.get("metadata_config_name", "")) or ""
        ),
        field_mapping_source=_coerce_source(payload.get("field_mapping_source", payload.get("metadata_source", "dws"))),
        baseinfo_table=str(payload.get("baseinfo_table", "xt_reg_table_baseinfo") or "xt_reg_table_baseinfo"),
        field_info_table=str(payload.get("field_info_table", "xt_reg_table_field_info") or "xt_reg_table_field_info"),
        public_info_table=str(payload.get("public_info_table", "public_information_rh") or "public_information_rh"),
    )


def db_validation_settings_to_dict(settings: DbValidationSettings) -> dict[str, Any]:
    return {
        "detail": db_validation_dataset_settings_to_dict(settings.detail),
        "public_info": db_validation_dataset_settings_to_dict(settings.public_info),
        "template": db_validation_dataset_settings_to_dict(settings.template),
        "field_mapping_source_id": settings.field_mapping_source_id,
        "baseinfo_table": settings.baseinfo_table,
        "field_info_table": settings.field_info_table,
        "public_info_table": settings.public_info_table,
    }


def db_validation_dataset_settings_from_dict(payload: dict[str, Any]) -> DbValidationDatasetSettings:
    payload = payload or {}
    return DbValidationDatasetSettings(
        source_id=str(payload.get("source_id", "") or ""),
        sys_manage_id=str(payload.get("sys_manage_id", "") or ""),
        classification_id=str(payload.get("classification_id", "") or ""),
        config_name=str(payload.get("config_name", "") or ""),
        source=_coerce_source(payload.get("source", "dws")),
    )


def db_validation_dataset_settings_to_dict(settings: DbValidationDatasetSettings) -> dict[str, Any]:
    return {
        "source_id": settings.source_id,
        "sys_manage_id": settings.sys_manage_id,
        "classification_id": settings.classification_id,
    }


def flow_tool_settings_from_dict(payload: dict[str, Any]) -> FlowToolSettings:
    payload = payload or {}
    return FlowToolSettings(
        source_id=str(payload.get("source_id", "") or ""),
        execute_url=str(payload.get("execute_url", "") or ""),
        flow_table=str(payload.get("flow_table", "sp_flow") or "sp_flow"),
        task_table=str(payload.get("task_table", "sp_task") or "sp_task"),
        poll_interval_seconds=_coerce_int(payload.get("poll_interval_seconds"), default=5, minimum=1, maximum=300),
        step_timeout_minutes=_coerce_int(payload.get("step_timeout_minutes"), default=60, minimum=1, maximum=1440),
        chains=[
            flow_chain_config_from_dict(item)
            for item in payload.get("chains", [])
            if isinstance(item, dict)
        ],
    )


def flow_tool_settings_to_dict(settings: FlowToolSettings) -> dict[str, Any]:
    return {
        "source_id": settings.source_id,
        "execute_url": settings.execute_url,
        "flow_table": settings.flow_table,
        "task_table": settings.task_table,
        "poll_interval_seconds": settings.poll_interval_seconds,
        "step_timeout_minutes": settings.step_timeout_minutes,
        "chains": [flow_chain_config_to_dict(chain) for chain in settings.chains],
    }


def flow_chain_config_from_dict(payload: dict[str, Any]) -> FlowChainConfig:
    payload = payload or {}
    return FlowChainConfig(
        id=str(payload.get("id", "") or ""),
        name=str(payload.get("name", "") or ""),
        enabled=_coerce_bool(payload.get("enabled"), default=True),
        steps=[
            flow_chain_step_from_dict(item)
            for item in payload.get("steps", [])
            if isinstance(item, dict)
        ],
    )


def flow_chain_config_to_dict(chain: FlowChainConfig) -> dict[str, Any]:
    return {
        "id": chain.id,
        "name": chain.name,
        "enabled": chain.enabled,
        "steps": [flow_chain_step_to_dict(step) for step in chain.steps],
    }


def flow_chain_step_from_dict(payload: dict[str, Any]) -> FlowChainStep:
    payload = payload or {}
    return FlowChainStep(
        flow_id=str(payload.get("flow_id", payload.get("id", "")) or ""),
        name=str(payload.get("name", "") or ""),
    )


def flow_chain_step_to_dict(step: FlowChainStep) -> dict[str, Any]:
    return {
        "flow_id": step.flow_id,
        "name": step.name,
    }


def _coerce_source(value: Any) -> str:
    source = str(value or "dws").strip()
    if source not in {"dws", "business"}:
        source = "dws"
    return source


def _source_from_dict(payload: dict[str, Any], default: DataSourceConfig) -> DataSourceConfig:
    merged = asdict(default) | payload
    password = str(merged.get("password", ""))
    encrypted_password = str(merged.get("password_encrypted", "") or "")
    if encrypted_password:
        password = decrypt_secret(encrypted_password)
    return DataSourceConfig(
        db_type=str(merged["db_type"]),
        host=str(merged["host"]),
        port=int(merged["port"]),
        database=str(merged["database"]),
        schema=str(merged["schema"]),
        username=str(merged["username"]),
        password=password,
    )


def _source_to_dict(source: DataSourceConfig) -> dict[str, Any]:
    payload = asdict(source)
    password = str(payload.pop("password", "") or "")
    if password:
        payload["password_encrypted"] = encrypt_secret(password)
    else:
        payload["password"] = ""
    return payload


def _existing_auth(config_path: Path) -> dict[str, Any]:
    auth = read_app_value(config_path, AUTH_KEY)
    if isinstance(auth, dict):
        return auth
    payload = load_json_file_payload(config_path)
    auth = payload.get("auth", {}) if isinstance(payload, dict) else {}
    return auth if isinstance(auth, dict) else {}


def _coerce_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


def _coerce_theme(value: Any) -> str:
    theme = str(value or "space-tech").strip()
    if theme in {"light", "space-tech"}:
        return theme
    return "space-tech"
