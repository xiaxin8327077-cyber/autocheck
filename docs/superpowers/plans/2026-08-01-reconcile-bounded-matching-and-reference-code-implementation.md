# Reconcile Bounded Matching and Reference Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make asset matching bounded and deterministic for large candidate pools while preserving dotted business codes and correct asset classification.

**Architecture:** Keep repository loading and reconciliation orchestration unchanged. Replace the path-heavy subset-sum implementation with cardinality-layered matching in `matching.py`, add one domain property for complete business-code extraction, and route existing AM/DM lookups through it. Preserve current leaf filtering and make its production regression explicit in tests.

**Tech Stack:** Python 3.12, `Decimal`, pytest, existing PostgreSQL/MySQL repository abstraction, vanilla JavaScript static tests.

## Global Constraints

- Preserve all unrelated uncommitted workspace changes.
- Use a shared 60-second hard deadline per project.
- Fast matching covers 2–5 rows across large candidate pools; deep matching covers 6–10 rows, and whole-group/complement matching covers occasional 20–30 row results within the configured candidate threshold.
- Preserve existing actual-leaf and asset classification behavior.
- Do not package `dist/auto-check.exe` unless explicitly requested.

---

### Task 1: Complete business-code extraction

**Files:**
- Modify: `src/auto_check/engine/models.py`
- Modify: `src/auto_check/engine/reconcile.py`
- Test: `tests/test_reconcile.py`
- Test: `tests/test_server.py`
- Test: `tests/test_export_detail.py`

**Interfaces:**
- Produces: `ValuationRow.account_business_code -> str`
- Consumes: existing `ValuationRow.account_code` and `account_tail_code`

- [x] **Step 1: Write failing tests** for dotted SPV code, standard four-level security code, three-level loan code, two-level property-right code, AM matching, detail display and export.
- [x] **Step 2: Run targeted tests** and confirm failures show the current value `51` instead of `JS0508-2.51`.
- [x] **Step 3: Add the property** that consumes up to three two-digit hierarchy segments after the four-digit first segment and rejoins the remaining suffix.
- [x] **Step 4: Replace business matching call sites** in AM, DM security, loan, equity, trust and property-right paths while leaving literal-tail-only displays unchanged where appropriate.
- [x] **Step 5: Run targeted tests** and confirm all new reference-code cases pass.

### Task 2: Cardinality-layered bounded matching

**Files:**
- Modify: `src/auto_check/engine/matching.py`
- Modify: `src/auto_check/engine/reconcile.py`
- Test: `tests/test_matching.py`
- Test: `tests/test_reconcile.py`

**Interfaces:**
- Produces: extended `find_valuation_matches(..., deadline: float | None = None, max_combination_size: int = 30)`
- Produces: `combination_timeout` result on deadline exhaustion
- Consumes: existing `ValuationMatch`, cancellation callback and configured row threshold

- [x] **Step 1: Write failing tests** for 74 candidates with 2-, 3-, 4- and 5-row solutions, preserved result ordering, 6–10 row fallback, 20–30 row whole-group/complement matching and forced timeout.
- [x] **Step 2: Run matching tests** and confirm the large-pool tests fail with `combination_overflow` or timeout behavior is missing.
- [x] **Step 3: Implement 2–5 row fast search** using complement, pair and triple indexes; store only exact target groups and check deadline/cancellation inside loops.
- [x] **Step 4: Implement 6–10 row bounded DFS** with remaining-sum bounds and failed-state memoization, plus 20～30 row whole-group/complement matching.
- [x] **Step 5: Share one deadline** across the initial match and natural-group fallback in `ReconcileEngine`.
- [x] **Step 6: Run matching and reconcile tests** and confirm preserved output ordering, ambiguity limits and timeout messages.

### Task 3: Bond-only DM balance query

**Files:**
- Modify: `src/auto_check/app/repositories.py`
- Modify: `tests/test_repositories.py`
- Modify: `docs/reconcile-execution-flow.zh-CN.md`

**Interfaces:**
- Consumes: configured `fa_security_balance_dm.bond_category`
- Produces: DM bond rows excluding NULL, empty and whitespace classifications

- [x] **Step 1: Change the repository SQL test** to require `TRIM(COALESCE(..., '')) <> ''` and verify the current `IS NOT NULL` assertion fails.
- [x] **Step 2: Update the query** with the portable blank filter.
- [x] **Step 3: Run repository tests** and confirm the bond query remains limited to its existing call site.

### Task 4: Diagnostic log throttling

**Files:**
- Modify: `src/auto_check/engine/reconcile.py`
- Modify: `tests/test_reconcile.py`

**Interfaces:**
- Produces: `_should_log_candidate_group(index: int, total: int) -> bool`
- Consumes: existing `RunJob` 200-record UI limit

- [x] **Step 1: Write a failing test** for 200 AM candidate groups and assert logs are emitted for groups 1–5, every 20th group and the final group only.
- [x] **Step 2: Add the predicate** and guard the per-group progress log.
- [x] **Step 3: Run reconcile tests** and confirm early threshold logs are not displaced by per-group noise.

### Task 5: Documentation and full verification

**Files:**
- Modify: `docs/reconcile-execution-flow.zh-CN.md`
- Modify: `docs/reconcile-rules.zh-CN.md`
- Modify: `docs/reconcile-logic-history.zh-CN.md`
- Modify: `README.md`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Consumes: behavior delivered by Tasks 1–4
- Produces: user-facing and authoritative rule documentation

- [x] **Step 1: Document** the shared deadline, 2–5 fast layer, 6–10 deep layer, 20–30 whole-group/complement layer, actual-leaf invariant, business-code parsing and robust bond blank filter.
- [x] **Step 2: Add README details** and keep the current concise application changelog entry `系统优化及BUG修复。`.
- [x] **Step 3: Run targeted tests** for matching, reconciliation, repository, server, export and web static behavior.
- [x] **Step 4: Run full verification** with `python -m pytest -q` and `git diff --check`.
- [x] **Step 5: Review `git diff`** to confirm no unrelated user changes were overwritten and no package was produced.
