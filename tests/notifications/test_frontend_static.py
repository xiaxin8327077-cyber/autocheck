import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INDEX_HTML = (ROOT / "src/auto_check/web/index.html").read_text("utf-8")
NOTIFICATION_JS = (ROOT / "src/auto_check/web/notification_center.js").read_text("utf-8")
NOTIFICATION_CSS = (ROOT / "src/auto_check/web/notification_center.css").read_text("utf-8")


def extract_function(source, name):
    pattern = rf"(?:function\s+{name}|const\s+{name}\s*=\s*(?:async\s+)?function|(?:async\s+)?{name}\s*=\s*(?:async\s+)?\()"
    match = re.search(pattern, source)
    if not match:
        return ""
    start = match.start()
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    return source[start:]


class TestNotificationResources:
    def test_resources_and_topbar_mount_are_present(self):
        assert '<link rel="stylesheet" href="/notification_center.css"' in INDEX_HTML
        assert '<script src="/notification_center.js"' in INDEX_HTML
        assert 'data-notification-bell' in INDEX_HTML
        assert 'data-notification-badge' in INDEX_HTML
        assert 'data-notification-panel' in INDEX_HTML
        assert 'data-notification-toast-region' in INDEX_HTML

    def test_badge_caps_visual_value_at_99_plus(self):
        assert 'count > 99 ? "99+" : String(count)' in NOTIFICATION_JS

    def test_opening_panel_does_not_call_mark_read(self):
        open_panel = extract_function(NOTIFICATION_JS, "openPanel")
        assert "/read" not in open_panel

    def test_notification_center_stops_event_source_and_polling(self):
        stop = extract_function(NOTIFICATION_JS, "stop")
        assert ".close()" in stop
        assert "clearInterval" in stop

    def test_notification_time_includes_seconds(self):
        assert "pad(d.getSeconds())" in NOTIFICATION_JS
        assert "${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}" in NOTIFICATION_JS
