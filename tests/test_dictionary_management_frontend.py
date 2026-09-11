"""系统管理—字典管理前端静态结构测试。

覆盖：菜单与页面结构、能力控制、切页加载、弹窗与保存调用、能力树注册，
以及"不以 innerHTML 拼接用户输入"的渲染约束。
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "src" / "auto_check" / "web" / "app.js"
INDEX_HTML = ROOT / "src" / "auto_check" / "web" / "index.html"
STYLES_CSS = ROOT / "src" / "auto_check" / "web" / "styles.css"


@pytest.fixture(scope="module")
def app_js():
    return APP_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def index_html():
    return INDEX_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def styles_css():
    return STYLES_CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dictionary_section(app_js):
    start = app_js.index("// ================= 系统管理：字典管理 =================")
    end = app_js.index("function setStatus(t) {")
    return app_js[start:end]


def test_dictionary_menu_registered_with_capability(index_html):
    assert 'data-page="dictionaries" data-capability="sys.dictionaries"' in index_html
    assert index_html.index('data-page="dictionaries"') > index_html.index('data-page="users"')


def test_dictionary_page_structure_present(index_html):
    assert 'id="page-dictionaries"' in index_html
    assert 'id="dictionaryCategoryBody"' in index_html
    assert 'id="dictionaryItemBody"' in index_html
    assert 'id="dictionaryItemsModal"' in index_html
    assert 'class="card result-card"' in index_html
    assert 'class="table-wrap"' in index_html
    assert 'class="result-table management-list-table dictionary-main-table"' in index_html
    assert 'id="newDictionaryBtn" type="button" class="btn-primary btn-sm management-toolbar-add"' in index_html
    assert 'id="dictionaryCategoryFilter" class="prompt-input management-toolbar-filter"' in index_html
    assert 'id="clearDictionaryCategoryFilter" class="filter-clear-button"' in index_html
    assert 'placeholder="筛选字典名称或编码"' in index_html
    assert 'id="newDictionaryItemBtn"' in index_html
    assert "字典名称" in index_html and "字典编码" in index_html
    assert "键值数量" in index_html
    main_table = index_html[index_html.index('class="result-table management-list-table dictionary-main-table"'):index_html.index('id="dictionaryCategoryBody"')]
    assert "<th>说明</th>" in main_table
    assert "<th>排序</th>" not in main_table


def test_dictionary_edit_modals_present(index_html):
    assert 'id="dictionaryCategoryModal"' not in index_html
    assert 'id="dictionaryCategoryCode"' not in index_html
    assert 'id="dictionaryItemModal"' not in index_html
    assert 'id="dictionaryItemsSave"' in index_html
    assert 'id="dictionaryConfigDescription"' in index_html
    assert 'id="dictionaryConfigCode" class="prompt-input" disabled' in index_html
    assert 'id="dictionaryConfigName" class="prompt-input"' in index_html
    assert 'id="dictionaryConfigName" class="prompt-input" disabled' not in index_html
    assert 'id="dictionaryCategorySort"' not in index_html


def test_dictionary_item_list_has_only_required_columns(index_html):
    config_modal = index_html[index_html.index('id="dictionaryItemsModal"'):index_html.index('id="userModal"')]
    assert '<thead><tr><th>序号</th><th>键值编码</th><th>键值名称</th><th>操作</th></tr></thead>' in config_modal
    assert "<th>说明</th>" not in config_modal
    assert "<th>排序</th>" not in config_modal
    assert "<th>状态</th>" not in config_modal
    assert 'id="dictionaryItemsFilter"' not in config_modal
    assert "查询" not in config_modal


def test_dictionary_page_wired_into_system_management(app_js):
    assert 'const systemMgmtPages = new Set(["settings", "role-permissions", "users", "dictionaries", "scheduled-tasks"]);' in app_js
    assert 'if (name === "dictionaries" && !hasCapability("sys.dictionaries"))' in app_js
    assert 'showToast("无权访问字典管理", "error");' in app_js
    assert 'if (name === "dictionaries") await loadDictionaries();' in app_js


def test_dictionary_page_has_display_whitelist_rule(styles_css):
    # 页面显隐靠 CSS 白名单，必须存在 dictionaries 规则，否则页面空白
    assert ':root[data-page="dictionaries"] #page-dictionaries { display: flex !important; }' in styles_css


def test_dictionary_capability_registered_for_role_permission_tree(app_js):
    assert '{ code: "sys.dictionaries", label: "字典管理", type: "menu" }' in app_js


def test_dictionary_loads_and_saves_via_unified_api(dictionary_section):
    assert 'api("/api/system/dictionaries", { method: "GET" })' in dictionary_section
    assert 'await api("/api/system/dictionaries", {' in dictionary_section
    assert "/items/${encodeURIComponent(item.id)}" in dictionary_section
    assert 'method: "DELETE"' in dictionary_section
    assert "method: \"PUT\"" in dictionary_section
    assert "method: \"POST\"" in dictionary_section


def test_dictionary_rendering_avoids_innerhtml_user_input(dictionary_section):
    # 仅允许清空 innerHTML = ""，不允许模板拼接
    assert ".innerHTML = \"\"" in dictionary_section
    assert ".innerHTML = `" not in dictionary_section
    assert "cell.textContent = String(value" in dictionary_section or "dictionaryTextCell" in dictionary_section
    assert "async function loadDictionaries" in dictionary_section
    assert "function renderDictionaryCategories" in dictionary_section
    assert "function renderDictionaryItems" in dictionary_section


def test_dictionary_items_are_configured_in_a_modal(dictionary_section):
    assert "function openDictionaryItemsModal" in dictionary_section
    assert 'dictionaryActionButton("配置"' in dictionary_section
    assert 'dictionaryActionButton("删除"' in dictionary_section
    assert 'row.addEventListener("click"' not in dictionary_section
    assert "deleteDictionaryCategory" in dictionary_section
    assert "dictionaryItemsModal.hidden = false;" in dictionary_section
    assert 'document.getElementById("dictionaryItemsModalClose")?.addEventListener' in dictionary_section
    assert 'document.getElementById("dictionaryItemsCancel")?.addEventListener' in dictionary_section
    assert 'document.getElementById("dictionaryItemsSave")?.addEventListener' in dictionary_section
    assert "dictionarySelectedCode = entry.code;" in dictionary_section
    assert 'dictionaryActionButton("删除"' in dictionary_section
    assert 'dictionaryActionButton("编辑"' not in dictionary_section
    assert 'dictionaryActionButton("修改"' not in dictionary_section
    assert "codeInput.disabled = !item.editing" not in dictionary_section
    assert "nameInput.disabled = !item.editing" not in dictionary_section
    assert 'document.getElementById("dictionaryConfigDescription")' in dictionary_section
    assert "saveDictionaryConfiguration" in dictionary_section
    assert "appendDictionaryItemDraftRow" in dictionary_section
    assert "function openNewDictionaryConfiguration" in dictionary_section
    assert 'document.getElementById("newDictionaryBtn")?.addEventListener("click", openNewDictionaryConfiguration)' in dictionary_section
    assert "openDictionaryCategoryModal" not in dictionary_section
    assert "saveDictionaryCategory" not in dictionary_section
    assert 'document.getElementById("dictionaryCategoryFilter")?.addEventListener("input"' in dictionary_section
    assert 'document.getElementById("clearDictionaryCategoryFilter")?.addEventListener("click"' in dictionary_section
    assert "dictionaryCategoryFilter" in dictionary_section
    assert "dictionaryItemFilter" not in dictionary_section
    assert "^[A-Za-z0-9][A-Za-z0-9_]{0,63}$" in dictionary_section


def test_dictionary_modal_error_keeps_open_on_failure(dictionary_section):
    assert "setModalStatus(status, userFriendlyError(error.message));" in dictionary_section
    assert "closeDictionaryItemsModal();" in dictionary_section


def test_business_system_empty_hint_special_case(dictionary_section):
    assert "暂无业务系统，请新增字典项" in dictionary_section


def test_dictionary_styles_use_theme_variables(styles_css):
    assert "#page-dictionaries .dictionary-main-table" in styles_css
    assert "#page-dictionaries .dictionary-status" in styles_css
    assert "var(--ui-radius)" in styles_css
    assert ".dictionary-items-table" in styles_css
    assert "min-width: 0" in styles_css[styles_css.index(".dictionary-items-table"):]
    assert ".dictionary-item-input" in styles_css
    assert ".management-toolbar-filter" in styles_css
    assert ".management-toolbar-filter-shell" in styles_css
    assert ".management-toolbar-add" in styles_css
    assert "280px minmax(0, 1fr)" in styles_css
    assert "width: min(260px, 100%)" in styles_css
    assert ".dictionary-config-summary textarea" in styles_css
    assert "max-height: min(370px, calc(100vh - 240px))" in styles_css
    assert ".app-modal-shell .dictionary-items-wrap::-webkit-scrollbar" in styles_css
    assert "width: var(--ui-thin-scrollbar-size, 6px)" in styles_css
    assert "scrollbar-color: var(--ui-thin-scrollbar-thumb, #c5d0e0) transparent" in styles_css
    assert "z-index: 20" in styles_css
    # 不提供主题光晕悬浮反馈
    dictionary_css_start = styles_css.index("/* ================= 系统管理：字典管理 ================= */")
    dictionary_css = styles_css[dictionary_css_start:]
    assert "box-shadow: 0 0 0 1px" not in dictionary_css
    assert "glow" not in dictionary_css.lower()
