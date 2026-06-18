# Auto Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows-packagable local Web tool that reconciles project balance differences across business, DWS, FA, TA, and AM tables with saved database configuration.

**Architecture:** Use a Python backend with a small local HTTP server serving static HTML/CSS/JS and JSON APIs. Keep reconciliation logic pure and testable, with database repositories separated behind query interfaces. Package later with PyInstaller so runtime users do not need Python installed.

**Tech Stack:** Python 3.12, stdlib `http.server`, `decimal.Decimal`, pytest, `psycopg` for PostgreSQL, `PyMySQL` for MySQL, PyInstaller for `.exe` packaging.

---

## Working Rules

- Do not commit during implementation. The user requested one final commit after development is complete.
- Follow TDD for production behavior: add failing tests before implementing reconciliation and config behavior.
- Keep database writes out of the runtime application. SQL scripts are test/setup artifacts only.
- Use exact `Decimal` comparisons for all money fields.

## File Structure

- Create: `pyproject.toml` - package metadata, dependencies, pytest config.
- Create: `.gitignore` - ignore local config, caches, build artifacts, virtual environments.
- Create: `README.md` - run, test, and packaging notes.
- Create: `src/auto_check/__init__.py` - package marker.
- Create: `src/auto_check/__main__.py` - executable entrypoint.
- Create: `src/auto_check/app/server.py` - local HTTP API and static file serving.
- Create: `src/auto_check/app/config.py` - app config load/save and connection models.
- Create: `src/auto_check/app/db.py` - DB adapter factory and read-only query execution.
- Create: `src/auto_check/app/repositories.py` - database query functions for each source table.
- Create: `src/auto_check/engine/models.py` - dataclasses for inputs, matches, details, and results.
- Create: `src/auto_check/engine/money.py` - Decimal conversion and exact comparison helpers.
- Create: `src/auto_check/engine/matching.py` - single-row, grouped, and bounded combination matching.
- Create: `src/auto_check/engine/reconcile.py` - orchestration of the full business rule chain.
- Create: `src/auto_check/web/index.html` - local Web UI.
- Create: `src/auto_check/web/styles.css` - UI styling.
- Create: `src/auto_check/web/app.js` - browser-side config, run, progress, and result rendering.
- Create: `sql/fa_accountbalance_dws.postgres.sql` - cleaned local-test DDL.
- Create: `sql/currency_report_duration.mysql.sql` - cleaned local-test DDL.
- Create: `tests/test_money.py` - Decimal helper tests.
- Create: `tests/test_matching.py` - estimation matching tests.
- Create: `tests/test_reconcile.py` - end-to-end engine tests with in-memory fake repositories.
- Create: `tests/test_config.py` - config persistence tests.
- Create: `tests/test_server.py` - API smoke tests.

## Task 1: Project Scaffolding

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/auto_check/__init__.py`

- [ ] **Step 1: Create Python package scaffold**

Create `.gitignore` with:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
dist/
build/
*.spec
config/
*.log
.superpowers/
```

Create `pyproject.toml` with:

```toml
[project]
name = "auto-check"
version = "0.1.0"
description = "Local reconciliation tool for project balance differences"
requires-python = ">=3.12"
dependencies = [
  "psycopg[binary]>=3.2.0",
  "PyMySQL>=1.1.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0.0",
  "pyinstaller>=6.0.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

Create `README.md` with exact commands using the bundled Python path or a local Python 3.12 install.

- [ ] **Step 2: Install dev dependencies**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pip install -e .[dev]
```

Expected: package installs without errors.

## Task 2: Money Helpers

**Files:**
- Create: `tests/test_money.py`
- Create: `src/auto_check/engine/money.py`

- [ ] **Step 1: Write failing tests**

```python
from decimal import Decimal

from auto_check.engine.money import to_decimal, amounts_equal


def test_to_decimal_preserves_exact_decimal_values():
    assert to_decimal("123.4500") == Decimal("123.4500")
    assert to_decimal(None) == Decimal("0")


def test_amounts_equal_requires_exact_equality():
    assert amounts_equal(Decimal("1.00"), Decimal("1.00"))
    assert not amounts_equal(Decimal("1.00"), Decimal("1.0001"))
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_money.py -q
```

Expected: import failure for `auto_check.engine.money`.

- [ ] **Step 3: Implement helpers**

Implement `to_decimal(value)` and `amounts_equal(left, right)` using `Decimal(str(value))` and no tolerance.

- [ ] **Step 4: Verify GREEN**

Run the same pytest command. Expected: 2 passed.

## Task 3: Matching Engine

**Files:**
- Create: `tests/test_matching.py`
- Create: `src/auto_check/engine/models.py`
- Create: `src/auto_check/engine/matching.py`

- [ ] **Step 1: Write failing tests**

Cover these behaviors:

```python
from decimal import Decimal

from auto_check.engine.matching import find_valuation_matches
from auto_check.engine.models import ValuationRow


def row(code, value, name="asset"):
    return ValuationRow(account_code=code, account_name=name, market_value=Decimal(value))


def test_finds_single_row_match_first():
    matches = find_valuation_matches([row("1001.01.01.01.0001", "5")], Decimal("5"))
    assert matches.match_type == "single"
    assert [m.account_code for m in matches.rows] == ["1001.01.01.01.0001"]


def test_finds_grouped_account_match_after_single_match_fails():
    rows = [row("1001.01.01.01.0001", "2"), row("1001.01.01.01.0001", "3")]
    matches = find_valuation_matches(rows, Decimal("5"))
    assert matches.match_type == "grouped"
    assert len(matches.rows) == 2


def test_finds_bounded_combination_match():
    rows = [row("1001.01.01.01.0001", "2"), row("1002.01.01.01.0002", "3"), row("1003.01.01.01.0003", "9")]
    matches = find_valuation_matches(rows, Decimal("5"), max_combination_rows=10)
    assert matches.match_type == "combination"
    assert [m.market_value for m in matches.rows] == [Decimal("2"), Decimal("3")]


def test_marks_combination_overflow_when_candidates_exceed_limit():
    rows = [row(f"1001.01.01.01.{i:04d}", "1") for i in range(12)]
    matches = find_valuation_matches(rows, Decimal("99"), max_combination_rows=10)
    assert matches.match_type == "combination_overflow"
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_matching.py -q
```

Expected: import failure for matching/models.

- [ ] **Step 3: Implement models and matching**

Implement `ValuationRow`, `ValuationMatch`, and `find_valuation_matches(rows, target, max_combination_rows=18)`. Match order must be single, grouped by account code, then bounded combinations.

- [ ] **Step 4: Verify GREEN**

Run the same pytest command. Expected: 4 passed.

## Task 4: Reconciliation Engine

**Files:**
- Create: `tests/test_reconcile.py`
- Create: `src/auto_check/engine/reconcile.py`
- Modify: `src/auto_check/engine/models.py`

- [ ] **Step 1: Write failing tests**

Cover these behaviors with fake repository objects:

```python
from decimal import Decimal

from auto_check.engine.models import ProjectBalance, ValuationRow, PactAssetRow
from auto_check.engine.reconcile import ReconcileEngine


class FakeRepo:
    def __init__(self):
        self.projects = []
        self.fa4001 = {}
        self.ta = {}
        self.asset_total = {}
        self.valuation = {}
        self.pact_assets = {}

    def list_project_balances(self, date):
        return self.projects

    def get_fa_4001_balance(self, project_code, date):
        return self.fa4001.get(project_code, Decimal("0"))

    def get_ta_assetshare_sum(self, project_code, date):
        return self.ta.get(project_code, Decimal("0"))

    def get_valuation_asset_total(self, project_code, date):
        return self.asset_total.get(project_code)

    def list_valuation_leaf_rows(self, project_code, date, account_prefix=None):
        rows = self.valuation.get(project_code, [])
        if account_prefix:
            return [r for r in rows if r.account_code.startswith(account_prefix)]
        return rows

    def list_pact_assets(self, project_code, date, asset_name):
        return self.pact_assets.get((project_code, asset_name), [])


def test_fa_ta_match_short_circuits_later_matching():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("100"), Decimal("90"))]
    repo.fa4001["P1"] = Decimal("20")
    repo.ta["P1"] = Decimal("10")

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "FA与TA实收不一致"
    assert results[0].match_status == "已解释"


def test_negative_difference_can_restrict_valuation_rows_to_prefix_1():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("90"), Decimal("100"))]
    repo.asset_total["P1"] = Decimal("80")
    repo.valuation["P1"] = [
        ValuationRow("2001.01.01.01.0001", "ignored", Decimal("-10")),
        ValuationRow("1001.01.01.01.0002", "asset", Decimal("-10")),
    ]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].valuation_match.rows[0].account_code.startswith("1")


def test_am_stockcode_mismatch_sets_reason():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("110"), Decimal("100"))]
    repo.valuation["P1"] = [ValuationRow("1001.01.01.01.0002", "Asset A", Decimal("10"))]
    repo.pact_assets[("P1", "Asset A")] = [PactAssetRow("P1", "Asset A", "9999")]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "FA与AM标的不一致"
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_reconcile.py -q
```

Expected: import failure for reconcile engine or missing models.

- [ ] **Step 3: Implement engine**

Implement `ReconcileEngine.run(date)` to execute the approved business rule chain and return result dataclasses.

- [ ] **Step 4: Verify GREEN**

Run the same pytest command. Expected: 3 passed.

## Task 5: Config Persistence

**Files:**
- Create: `tests/test_config.py`
- Create: `src/auto_check/app/config.py`

- [ ] **Step 1: Write failing tests**

Test save/load of two data sources and default source kinds.

- [ ] **Step 2: Verify RED**

Run:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_config.py -q
```

Expected: import failure for config module.

- [ ] **Step 3: Implement config**

Implement dataclasses `DataSourceConfig`, `AppConfig`, `default_config()`, `load_config(path)`, and `save_config(config, path)`.

- [ ] **Step 4: Verify GREEN**

Run the same pytest command. Expected: config tests pass.

## Task 6: Database Access and Repositories

**Files:**
- Create: `src/auto_check/app/db.py`
- Create: `src/auto_check/app/repositories.py`

- [ ] **Step 1: Add read-only SQL guard tests if practical**

Add tests that `ensure_select_only("select 1")` passes and `ensure_select_only("delete from x")` raises.

- [ ] **Step 2: Implement DB adapters**

Implement driver selection for PostgreSQL and MySQL, parameterized query execution, identifier quoting for schema-qualified table names, and a guard that only allows SQL beginning with `SELECT` or `WITH`.

- [ ] **Step 3: Implement repositories**

Implement queries for:

- `list_project_balances(date)`
- `get_fa_4001_balance(project_code, date)`
- `get_ta_assetshare_sum(project_code, date)`
- `get_valuation_asset_total(project_code, date)`
- `list_valuation_leaf_rows(project_code, date, account_prefix=None)`
- `list_pact_assets(project_code, date, asset_name)`

## Task 7: Local HTTP API and UI

**Files:**
- Create: `tests/test_server.py`
- Create: `src/auto_check/app/server.py`
- Create: `src/auto_check/__main__.py`
- Create: `src/auto_check/web/index.html`
- Create: `src/auto_check/web/styles.css`
- Create: `src/auto_check/web/app.js`

- [ ] **Step 1: Write API smoke tests**

Test `GET /api/config`, `POST /api/config`, and `POST /api/run` using fake services.

- [ ] **Step 2: Implement server**

Use stdlib `http.server.ThreadingHTTPServer`. Serve static files from `src/auto_check/web` and JSON APIs under `/api`.

- [ ] **Step 3: Implement UI**

Create one-page UI with tabs/sections for configuration, run date, progress, result table, filters, and expandable details.

- [ ] **Step 4: Browser verify**

Run the local server and open it in the in-app browser. Confirm configuration form, run form, result rendering, and responsive layout are usable.

## Task 8: SQL Scripts and Packaging Notes

**Files:**
- Create: `sql/fa_accountbalance_dws.postgres.sql`
- Create: `sql/currency_report_duration.mysql.sql`
- Modify: `README.md`

- [ ] **Step 1: Add cleaned DDL scripts**

Use the provided DDL as source, preserving required columns and indexes needed by the app.

- [ ] **Step 2: Add packaging command**

Document:

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m PyInstaller --onefile --name auto-check --paths src --add-data "src/auto_check/web;auto_check/web" src/auto_check/__main__.py
```

## Task 9: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run full tests**

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run app smoke check**

```powershell
& 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m auto_check --no-browser --port 8765
```

Expected: local server starts and serves the UI.

- [ ] **Step 3: Check git status**

```powershell
git status --short --branch
```

Expected: implementation files are changed or untracked, no commit yet.
