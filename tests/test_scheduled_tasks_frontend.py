from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "src" / "auto_check" / "web" / "index.html"
APP_JS = ROOT / "src" / "auto_check" / "web" / "app.js"
STYLES_CSS = ROOT / "src" / "auto_check" / "web" / "styles.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_scheduled_tasks_is_a_system_management_submenu_and_page():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'data-page="scheduled-tasks" data-capability="sys.scheduled_tasks"' in html
    assert 'id="page-scheduled-tasks"' in html
    assert '"scheduled-tasks"' in app_js.split("const systemMgmtPages", 1)[1].split(";", 1)[0]
    assert ':root[data-page="scheduled-tasks"] #page-scheduled-tasks' in css
    for heading in ("任务名称", "执行规则", "状态", "最近执行", "执行状态", "操作"):
        assert f"<th>{heading}</th>" in html


def test_scheduled_task_actions_and_configuration_are_wired():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    assert 'dictionaryActionButton(label, className, listener)' in app_js
    assert 'scheduledTaskActionButton("立即执行"' in app_js
    assert 'scheduledTaskActionButton("配置"' in app_js
    assert 'enabled ? "停用" : "启用"' in app_js
    assert "toggleScheduledTaskEnabled(task)" in app_js
    assert 'scheduledTaskActionButton("删除"' in app_js
    assert '/api/system/scheduled-tasks/${encodeURIComponent(task.task_code)}/run' in app_js
    assert '/api/system/scheduled-tasks/${encodeURIComponent(task.task_code)}/restore' in app_js
    assert "定时任务管理仅限管理员访问" in app_js
    assert 'id="scheduledTaskEnabled"' not in html
    assert 'syncCustomSelect(scheduleTypeSelect)' in app_js


def test_scheduled_task_page_reuses_dictionary_list_visual_language():
    html = _read(INDEX_HTML)
    css = _read(STYLES_CSS)

    assert html.count("management-list-table") >= 2
    assert ".scheduled-task-status--success" in css
    assert ".scheduled-task-status--running" in css
    assert ".scheduled-task-status--failed" in css
    assert ".scheduled-task-modal" in css
    assert ".management-list-action-btn" in css
    assert ".management-list-action--danger" in css
    assert ".management-list-status--on" in css
    assert ".management-list-status--off" in css


def test_scheduled_task_list_paginates_after_ten_rows(tmp_path):
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    assert 'id="scheduledTaskPagination"' in html
    assert "const scheduledTaskPageSize = 10;" in app_js
    assert "visibleRows.slice(pagination.start, pagination.end)" in app_js

    start = app_js.index("function managementListPaginationState")
    end = app_js.index("\n}\n", start) + 3
    scenario = tmp_path / "pagination-state.js"
    scenario.write_text(
        app_js[start:end]
        + "\n"
        + "const first = managementListPaginationState(11, 1, 10);\n"
        + "const second = managementListPaginationState(11, 2, 10);\n"
        + "const clamped = managementListPaginationState(11, 99, 10);\n"
        + "if (first.totalPages !== 2 || first.start !== 0 || first.end !== 10) process.exit(1);\n"
        + "if (second.page !== 2 || second.start !== 10 || second.end !== 11) process.exit(2);\n"
        + "if (clamped.page !== 2) process.exit(3);\n",
        encoding="utf-8",
    )
    result = subprocess.run(["node", str(scenario)], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_scheduled_task_modal_uses_aligned_full_width_and_two_column_grid():
    html = _read(INDEX_HTML)
    css = _read(STYLES_CSS)

    assert 'id="scheduledTaskName" class="prompt-input" type="text" readonly' in html
    assert 'readonly disabled' not in html.split('id="scheduledTaskName"', 1)[1].split("/>", 1)[0]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert ".scheduled-task-form .dictionary-edit-row:first-child" in css
    assert "grid-column: 1 / -1;" in css
    assert ".scheduled-task-form .dictionary-edit-row" in css
    assert ".scheduled-task-form .prompt-input" in css
    assert ".scheduled-task-form .filter-select" in css
