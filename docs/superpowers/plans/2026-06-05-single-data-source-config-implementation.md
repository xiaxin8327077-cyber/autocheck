# Single Data Source Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace grouped `DWS + 业务库` data-source configuration with a single-data-source registry and business-use references.

**Architecture:** Keep the existing `DataSourceConfig` connection model, add a `DataSourceEntry` registry, and add small compatibility helpers that assemble legacy `AppConfig(dws, business)` for existing reconciliation paths. Database validation settings will resolve each purpose directly from a `source_id` instead of `config_name + dws/business`.

**Tech Stack:** Python 3.12 dataclasses/JSON config, existing local HTTP server, static HTML/CSS/JS, pytest, existing Windows packaging script.

---

## File Structure

- Modify `src/auto_check/app/config.py`: add `DataSourceEntry`, `ReconcileDataSourceSettings`, single-source serialization, legacy migration, and compatibility helpers.
- Modify `src/auto_check/app/server.py`: update config APIs, source selection helpers, test-connection handling, reconciliation config lookup, PBC import source lists, and database validation source resolution.
- Modify `src/auto_check/web/index.html`: replace grouped data-source form with single-source form and add reconciliation source selectors.
- Modify `src/auto_check/web/app.js`: update data-source list rendering, edit/save/delete/test flows, and database validation source selectors.
- Modify `src/auto_check/web/styles.css`: adjust settings layout only where selectors/forms change.
- Modify `tests/test_config.py`: cover legacy migration and single-source persistence.
- Modify `tests/test_db_validation_config.py`: cover `source_id` settings and old-field migration.
- Modify `tests/test_server.py`: cover new APIs and deletion protection.
- Modify `tests/test_web_static.py`: cover frontend wiring.

## Task 1: Config Model and Migration

**Files:**
- Modify: `src/auto_check/app/config.py`
- Test: `tests/test_config.py`
- Test: `tests/test_db_validation_config.py`

- [ ] **Step 1: Write failing config tests**

Add tests that create an old-format store with `configs[].dws/business`, load it, and assert:

```python
assert len(loaded.data_sources) == 2
assert loaded.reconcile_data_sources.dws_source_id == "legacy:对账数据源:dws"
assert loaded.reconcile_data_sources.business_source_id == "legacy:对账数据源:business"
assert loaded.db_validation.detail.source_id == "legacy:逐笔校验数据源:dws"
assert loaded.db_validation.field_mapping_source_id == "legacy:逐笔校验数据源:dws"
```

Also assert `save_store()` writes `data_sources` and does not write plaintext passwords.

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m pytest tests/test_config.py::test_store_migrates_grouped_configs_to_single_data_sources tests/test_db_validation_config.py::test_db_validation_settings_migrates_old_config_source_pair -q
```

Expected: fails because `data_sources`, `source_id`, and migration helpers do not exist.

- [ ] **Step 3: Implement config dataclasses**

In `config.py`, add:

```python
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
```

Extend `ConfigStore` with:

```python
data_sources: list[DataSourceEntry] = field(default_factory=list)
reconcile_data_sources: ReconcileDataSourceSettings = field(default_factory=ReconcileDataSourceSettings)
```

Keep `configs` for compatibility during migration, but new saves should write `data_sources`.

- [ ] **Step 4: Implement old-to-new migration**

Add helpers:

```python
def legacy_source_id(config_name: str, source: str) -> str:
    return f"legacy:{config_name}:{source}"


def resolve_data_source(store: ConfigStore, source_id: str) -> DataSourceConfig:
    for entry in store.data_sources:
        if entry.id == source_id:
            return entry.config
    raise ValueError("数据源不存在")
```

When loading old `configs`, split each config into two `DataSourceEntry` records and migrate database validation settings from `config_name + source` to `source_id`.

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
python -m pytest tests/test_config.py tests/test_db_validation_config.py -q
```

Expected: selected tests pass.

## Task 2: Backend API Compatibility

**Files:**
- Modify: `src/auto_check/app/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing API tests**

Add tests for:

```python
status, payload = router.handle("GET", "/api/configs", {})
assert payload["data_sources"][0]["id"]
assert "dws" not in payload["data_sources"][0]
assert "business" not in payload["data_sources"][0]
```

Add a deletion-protection test: a data source referenced by `reconcile_data_sources` or `db_validation` returns HTTP 400 and a readable error.

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m pytest tests/test_server.py::test_configs_api_returns_single_data_sources tests/test_server.py::test_referenced_data_source_cannot_be_deleted -q
```

Expected: fails because the API still returns grouped configs and deletion does not inspect references.

- [ ] **Step 3: Update `/api/configs` handlers**

Return:

```json
{
  "data_sources": [
    {
      "id": "...",
      "name": "...",
      "db_type": "postgresql",
      "host": "127.0.0.1",
      "port": 5432,
      "database": "auto_check_test",
      "schema": "dws",
      "username": "postgres",
      "password_set": true,
      "is_default": true
    }
  ],
  "default_source_id": "..."
}
```

Accept POST bodies containing either new single-source fields or old `dws/business` fields. For old bodies, split into two source entries.

- [ ] **Step 4: Add reconciliation source settings API**

Implement:

```text
GET /api/settings/reconcile-data-sources
POST /api/settings/reconcile-data-sources
```

The GET response includes `data_sources` and current `settings`. The POST validates that both ids exist.

- [ ] **Step 5: Update runtime source resolution**

Replace direct reads of `NamedConfig.dws/business` with compatibility helpers:

```python
def app_config_from_store(store: ConfigStore) -> AppConfig:
    return AppConfig(
        dws=resolve_data_source(store, store.reconcile_data_sources.dws_source_id),
        business=resolve_data_source(store, store.reconcile_data_sources.business_source_id),
    )
```

Keep old reconciliation, history, and repository callers receiving `AppConfig`.

- [ ] **Step 6: Verify GREEN**

Run:

```powershell
python -m pytest tests/test_server.py tests/test_config.py -q
```

Expected: selected tests pass.

## Task 3: Database Validation Source IDs

**Files:**
- Modify: `src/auto_check/app/config.py`
- Modify: `src/auto_check/app/server.py`
- Test: `tests/test_db_validation_config.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing DB validation tests**

Assert `GET /api/tools/db-validation/settings` returns single-source `data_sources` and settings with `source_id` fields:

```python
assert payload["settings"]["detail"]["source_id"] == detail_id
assert payload["settings"]["field_mapping_source_id"] == field_mapping_id
assert all("source" not in item for item in payload["data_sources"])
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m pytest tests/test_db_validation_config.py tests/test_server.py::test_db_validation_settings_use_single_data_sources -q
```

Expected: fails because settings still use `config_name` and `source`.

- [ ] **Step 3: Update DB validation dataclasses and converters**

Change `DbValidationDatasetSettings` to:

```python
@dataclass(frozen=True)
class DbValidationDatasetSettings:
    source_id: str = ""
    sys_manage_id: str = ""
    classification_id: str = ""
```

Change `DbValidationSettings.field_mapping_source_id` to hold the field-mapping data source id. Converters must still read old keys and migrate them when the full store is loaded.

- [ ] **Step 4: Update DB validation job startup**

Resolve:

```python
data_source = resolve_data_source(store, settings.detail.source_id)
metadata_source = resolve_data_source(store, settings.field_mapping_source_id)
public_info_source = resolve_data_source(store, settings.public_info.source_id)
```

Use source ids in job payloads for traceability.

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
python -m pytest tests/test_db_validation_config.py tests/test_server.py -q
```

Expected: selected tests pass.

## Task 4: Frontend Settings Update

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Test: `tests/test_web_static.py`

- [ ] **Step 1: Write failing frontend static tests**

Assert:

```python
assert 'id="reconcileDwsSource"' in html
assert 'id="reconcileBusinessSource"' in html
assert "field_mapping_source_id" in app_js
assert "::business" not in db_validation_settings_section
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m pytest tests/test_web_static.py::test_settings_uses_single_data_source_model -q
```

Expected: fails because the UI still renders grouped DWS/业务库 source values.

- [ ] **Step 3: Update settings markup**

Replace grouped DWS/业务库 fields with a single-source form and add reconciliation selectors:

```html
<select id="reconcileDwsSource"></select>
<select id="reconcileBusinessSource"></select>
```

Keep database validation settings in system settings and remove the old `configName::source` value format.

- [ ] **Step 4: Update frontend JavaScript**

Use source ids directly:

```javascript
function dbValidationSourceValue(item = {}) {
  return item.id || "";
}
```

Save payloads with:

```javascript
detail: { source_id: dbValidationDetailSource.value, ... }
field_mapping_source_id: dbValidationMetadataSource.value
```

Data-source CRUD calls should send one source entry per request.

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
python -m pytest tests/test_web_static.py -q
node --check src/auto_check/web/app.js
```

Expected: selected tests pass and JavaScript syntax is valid.

## Task 5: Field Mapping Refresh Error Clarity

**Files:**
- Modify: `src/auto_check/app/server.py`
- Modify: `src/auto_check/db_validation/field_mapping_cache.py`
- Modify: `src/auto_check/web/app.js`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing refresh-error test**

Use a fake field mapping loader that raises `RuntimeError("relation does not exist")`. Assert manual refresh returns HTTP 200 with:

```python
assert payload["field_mapping"]["last_error"]
assert "baseinfo" in payload["field_mapping"]["last_error"]
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m pytest tests/test_server.py::test_db_validation_field_mapping_refresh_returns_readable_status_on_failure -q
```

Expected: fails because the route currently bubbles into a generic operation failure.

- [ ] **Step 3: Implement readable error path**

Store the first line of the loader exception in `FieldMappingCache.last_error`. Wrap `load_db_validation_field_mapping()` errors with source name/schema/table context. Manual refresh should return the cache status payload even on refresh failure.

- [ ] **Step 4: Update frontend toast behavior**

If `payload.field_mapping.last_error` exists, render the status and show an error toast. Only show success toast when no error exists.

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
python -m pytest tests/test_server.py::test_db_validation_field_mapping_refresh_returns_readable_status_on_failure -q
node --check src/auto_check/web/app.js
```

Expected: tests pass and JavaScript syntax is valid.

## Task 6: Full Verification and Packaging

**Files:**
- Read: all modified files
- Build output: `dist/auto-check.exe`

- [ ] **Step 1: Run full tests in a subagent/background worker**

Run:

```powershell
python -m pytest -q
node --check src/auto_check/web/app.js
```

Expected: all tests pass and JavaScript syntax is valid.

- [ ] **Step 2: Package Windows executable**

Stop any running `auto-check.exe` from `D:\xiaxin\auto_check\dist` if it locks the target, then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package-windows.ps1 -SkipTests -Clean
```

Expected: `dist/auto-check.exe` is refreshed.

- [ ] **Step 3: Report result**

Summarize changed files, test output, package path, and any residual risks.
