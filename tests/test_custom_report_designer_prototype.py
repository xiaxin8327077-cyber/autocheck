from pathlib import Path


PROTOTYPE = Path("docs/prototypes/custom-report-designer-preview.html")


def test_custom_report_designer_prototype_has_required_workflow() -> None:
    html = PROTOTYPE.read_text(encoding="utf-8")

    assert "<title>监管智核 · 自定义报表设计预览</title>" in html
    assert html.count('data-step="') >= 6
    assert 'id="schemaExplorer"' in html
    assert 'id="relationCanvas"' in html
    assert 'id="propertyPanel"' in html
    assert 'id="dataPreviewPanel"' in html
    assert 'id="previewButton"' in html
    assert 'id="saveTemplateButton"' in html
    assert "showToast" in html


def test_custom_report_designer_prototype_stays_light_theme_only() -> None:
    html = PROTOTYPE.read_text(encoding="utf-8").lower()

    assert "theme-toggle" not in html
    assert "dark-mode" not in html
