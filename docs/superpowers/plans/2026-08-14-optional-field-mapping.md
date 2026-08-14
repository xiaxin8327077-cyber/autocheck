# Optional Field Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep selected non-required business fields in field mapping, classify unmapped ones as `unmapped`, and exclude them from required-missing run blockers.

**Architecture:** Add an explicit optional-field scope map beside the required-field scope map. The mapping service resolves both maps per logical table, merges them with required fields taking precedence, and assigns status from the field classification without adding frontend exceptions.

**Tech Stack:** Python 3.11, dataclasses, pytest, existing mapping snapshot storage.

## Global Constraints

- Required fields remain the only fields that can produce `required_missing` and block validation runs.
- Optional fields remain visible and manually editable; missing optional fields produce `unmapped` with `is_required=false`.
- Do not infer optional fields from all metadata columns.
- Do not modify frontend code.
- Do not create a worktree or make Git commits in this directory.

---

### Task 1: Optional field classification and refresh behavior

**Files:**
- Modify: `src/auto_check/db_validation/rules/basic.py`
- Modify: `src/auto_check/db_validation/mapping_service.py`
- Modify: `src/auto_check/app/server.py`
- Test: `tests/test_db_validation_mapping_service.py`

**Interfaces:**
- Produces: `OPTIONAL_CHINESE_FIELDS_BY_SCOPE: dict[str, frozenset[str]]`
- Extends: `DbValidationMappingService.refresh(..., optional_chinese_fields_by_scope: dict[str, frozenset[str]] | None = None)`
- Extends: `_build_fields_for_table(..., required: frozenset[str], optional: frozenset[str])`

- [x] **Step 1: Write failing mapping-service tests**

Add tests proving an optional field without a metadata match is saved as `unmapped`/`is_required=False`, a mapped optional field is `mapped`/`is_required=False`, and required wins when the same name appears in both maps.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m pytest tests/test_db_validation_mapping_service.py -k "optional" -q
```

Expected: failures because optional fields are not accepted or emitted.

- [x] **Step 3: Add the optional field scope map**

Add the seven approved optional entries to `OPTIONAL_CHINESE_FIELDS_BY_SCOPE` in `basic.py`:

```python
OPTIONAL_CHINESE_FIELDS_BY_SCOPE = {
    "ZG06": frozenset({"数据管理机构"}),
    "ZG08": frozenset({"发行机构代码"}),
    "ZG09": frozenset({"数据管理机构", "法人金融机构名称"}),
    "ZG10": frozenset({"数据管理机构", "法人金融机构名称"}),
    "ZG13": frozenset({"数据管理机构"}),
}
```

- [x] **Step 4: Implement required/optional merging in the mapping service**

Resolve both sets for each table, remove required names from the optional set, and build one ordered list of `(chinese_name, is_required)`. Use `required_missing` only when `is_required` is true; otherwise use `unmapped`. Preserve the existing `mapped`, `missing_physical`, semantic-match, override, and claimed-field behavior while setting each row's `is_required` value correctly.

- [x] **Step 5: Wire the optional scope map through the server**

Add `_db_validation_optional_chinese_fields_by_scope()` beside the existing required-map helper and pass it into `DbValidationMappingService.refresh`.

- [x] **Step 6: Run focused tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_db_validation_mapping_service.py -q
```

Expected: all mapping-service tests pass.

---

### Task 2: Run-blocker and regression verification

**Files:**
- Test: `tests/test_db_validation_mapping_storage.py`
- Test: `tests/test_db_validation_mapping_service.py`

**Interfaces:**
- Consumes: `FieldMapping.is_required` and existing `required_missing_for_tables` storage query.
- Produces: regression proof that optional unmapped rows remain visible but never appear in the required-missing blocker query.

- [x] **Step 1: Add a failing storage regression test if current coverage does not assert optional exclusion**

Insert one optional `unmapped` row and one required `required_missing` row, then assert the blocker query returns only the required row.

- [x] **Step 2: Run the storage test**

Run:

```powershell
python -m pytest tests/test_db_validation_mapping_storage.py -k "required_missing" -q
```

Expected: pass if the existing storage predicate already honors `is_required`; otherwise fail and require the smallest query correction.

- [x] **Step 3: Run the complete related regression suite**

Run:

```powershell
python -m pytest tests/test_db_validation_mapping_service.py tests/test_db_validation_mapping_storage.py tests/test_db_validation_rules.py tests/test_db_validation_engine.py tests/test_db_validation_engine_public_info.py tests/test_db_validation_field_resolve.py -q
```

Expected: all tests pass.

- [x] **Step 4: Restart and verify port 9999**

Restart with `PYTHONPATH=D:\cherry\autocheck_jmxkf\autocheck\src`, verify the process command line, and confirm `http://127.0.0.1:9999/` returns HTTP 200.
