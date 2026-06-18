# Asset Missing Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the confirmed asset-missing refinement chain and write the formatted `①②③` result directly into the `具体原因` field.

**Architecture:** Keep top-level `difference_reason` unchanged as `资产缺失`; add a focused asset-missing refinement model in the reconcile engine, repository query methods for the new DM/report tables, and display/export support for an `asset_missing_refinement` table section. Special-purpose-vehicle AM matching covers `1101.05.01.01`、`1101.05.02.01`、`1101.05.03.01`、`1101.05.04.01`、`1101.05.05.01`、`1101.05.07.01`; `1101.05.06.01` remains private fund handling.

**Tech Stack:** Python 3.12, pytest, existing repository abstraction, existing static JS export helper, PowerShell packaging.

---

### Task 1: Engine Unit Tests For Formatted Specific Reasons

**Files:**
- Modify: `tests/test_reconcile.py`
- Modify: `src/auto_check/engine/reconcile.py`

- [ ] Write failing tests for single and multiple asset-missing reasons:
  - bond missing with final reason -> `①债券缺失：23苏城投MTN004；原因：该债券债券类别_人行字段（sbm_seclas_h2024）为空`
  - multiple rows -> numbered lines for bond and loan.
- [ ] Run targeted tests and verify they fail on current short-title behavior.
- [ ] Add lightweight refinement data classes/helpers in `reconcile.py`:
  - classify each matched valuation row.
  - format `①资产类型缺失：资产名称；原因：原因`.
  - keep `specific_reason` on the `asset_gap` detail.
- [ ] Re-run targeted tests and verify pass.

### Task 2: Repository Query Methods

**Files:**
- Modify: `src/auto_check/engine/reconcile.py`
- Modify: `src/auto_check/app/repositories.py`
- Modify: `tests/test_repositories.py`

- [ ] Extend `ReconcileRepository` protocol with methods for:
  - `get_security_balance_refinement`
  - `get_project_invest_refinement`
  - `get_spv_project_invest_refinement`
  - `get_property_right_refinement`
  - `has_report_rows`
  - `has_reverse_repo_blank_rows`
- [ ] Add repository tests that assert SQL uses the confirmed tables and filters.
- [ ] Implement methods using `TableRef(...).quoted(...)` for fixed schema tables and `COALESCE` for non-zero checks.
- [ ] Re-run repository tests.

### Task 3: Asset-Missing Refinement Chain

**Files:**
- Modify: `src/auto_check/engine/reconcile.py`
- Modify: `tests/test_reconcile.py`

- [ ] Add tests for each major chain:
  - bond/stock/fund/private fund security table missing, field blank, report missing.
  - reverse repo project filter and blank-field result.
  - loan and equity investment DM rows/report rows.
  - trust plan income right and asset income right.
  - special purpose vehicle AM missing, FA/AM mismatch, project-invest zero, SPV missing, `svd_assettype` invalid,收益凭证 report missing, non收益凭证 report missing.
- [ ] Implement one chain at a time, using existing TDD red/green loops.
- [ ] Ensure unresolved checks leave that row without `；原因：...`.
- [ ] Preserve existing `资产差异` behavior for 1541 property-right amount mismatch before normal asset-missing refinement.

### Task 4: Display, Export, Docs, Data

**Files:**
- Modify: `src/auto_check/app/server.py`
- Modify: `src/auto_check/web/export_detail.js`
- Modify: `src/auto_check/web/app.js`
- Modify: `README.md`
- Modify: `docs/reconcile-rules.zh-CN.md`
- Modify: `docs/reconcile-logic-history.zh-CN.md`
- Modify: `sql/append_20260531_ta_received_trust_scenarios.postgres.sql`
- Modify: `tests/test_server.py`
- Modify: `tests/test_export_detail.py`
- Modify: `tests/test_web_static.py`

- [ ] Add an `资产缺失细分` display table section with序号、资产类型、资产名称、FA科目编码、科目尾段、FA估值金额、核查表、核查结果、关键字段、原因.
- [ ] Ensure export detail includes the `具体原因` value with line breaks intact.
- [ ] Update README, rule docs, and in-app changelog.
- [ ] Extend local scenario SQL enough to exercise representative refinements.
- [ ] Run targeted tests, full tests, reload local scenario data, inspect representative output, run `git diff --check`, package `dist\auto-check.exe`.

### Self-Review

- The plan covers the confirmed chain document, including formatted reasons, repository access, display/export, tests, docs, local data, and packaging.
- No placeholders or deferred “implement later” steps remain.
- Types and method names are descriptive; exact signatures will be finalized in the TDD implementation against existing code style.
