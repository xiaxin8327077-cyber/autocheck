from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "src" / "auto_check" / "web" / "index.html"
APP_JS = ROOT / "src" / "auto_check" / "web" / "app.js"


def test_history_detail_uses_info_modal_and_shared_close_button():
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")

    assert 'id="historyDetailCard"' not in html
    assert 'class="btn-close close-history-detail"' not in js
    assert 'e.target.closest(".close-history-detail")' not in js
    assert "function closeHistoryDetailRow()" not in js
    assert 'id="infoModal"' in html
    assert "function showHistoryDetailModal(id)" in js
    assert 'modalClass: "modal-info--history-detail"' in js
    assert 'id="infoFooter"' in html
    assert 'document.querySelector("#infoFooter .restore-history-detail")' in js
    assert "selectedHistoryId = \"\"" in js

    start = js.index("function renderHistoryDetailContent(run)")
    end = js.index("function renderHistoryDetailLoading", start)
    detail = js[start:end]
    complete = 'historySection("本次完整核对结果", run.results || [], "complete")'
    added = 'historySection("本次新增差异", historyDiffItems(run, "added_results"), "added")'
    removed = 'historySection("本次减少差异", historyDiffItems(run, "removed_results"), "removed")'
    assert detail.index(complete) < detail.index(added) < detail.index(removed)


def test_history_ui_uses_added_and_removed_difference_labels():
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")

    assert "新增差异" in html
    assert "减少差异" in html
    assert "新增差异" in js
    assert "减少差异" in js
    assert "多出来" not in html
    assert "少掉" not in html
    assert "多出来" not in js
    assert "少掉" not in js
