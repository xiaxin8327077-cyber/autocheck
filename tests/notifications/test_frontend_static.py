import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INDEX_HTML = (ROOT / "src/auto_check/web/index.html").read_text("utf-8")
NOTIFICATION_JS = (ROOT / "src/auto_check/web/notification_center.js").read_text("utf-8")
NOTIFICATION_CSS = (ROOT / "src/auto_check/web/notification_center.css").read_text("utf-8")
NOTIFICATION_JS_PATH = ROOT / "src/auto_check/web/notification_center.js"
APP_JS = (ROOT / "src/auto_check/web/app.js").read_text("utf-8")


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

    def test_report_navigation_notification_passes_the_full_action_object(self):
        view_action = extract_function(NOTIFICATION_JS, "handleViewAction")
        assert "window.handleReportNavTodoAction(item.action);" in view_action
        assert "window.handleReportNavTodoAction(item.action.route, item.action.query);" not in view_action


def extract_arrow_body(source, marker):
    """Extract the balanced `{...}` body that follows the `=>` after ``marker``.

    Unlike :func:`extract_function`, this tolerates destructured arrow
    parameters (which contain braces before the body).
    """
    idx = source.index(marker)
    arrow = source.index("=>", idx)
    start = source.index("{", arrow)
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    return source[start:]


class TestNotificationAuthRecovery:
    def test_api_request_prefers_platform_api(self):
        api_request = extract_function(NOTIFICATION_JS, "apiRequest")
        assert api_request
        assert "state.api" in api_request
        assert "typeof state.api === \"function\"" in api_request

    def test_start_stores_platform_api(self):
        start = extract_arrow_body(NOTIFICATION_JS, "const start = async")
        assert "state.api" in start

    def test_app_bootstraps_notification_center_with_platform_api(self):
        # ensureAuthenticated 不再传 api: null。
        assert "api: null" not in APP_JS
        assert "api," in APP_JS

    def test_update_session_contract_present_and_same_user_only(self):
        update_session = extract_arrow_body(NOTIFICATION_JS, "const updateSession = async")
        assert "state.userId" in update_session
        assert "closeEventSource()" in update_session
        assert "startEventSource()" in update_session
        assert "bindEvents()" not in update_session
        assert "{ start, stop, updateSession }" in NOTIFICATION_JS


def test_update_session_rebuilds_connection_and_reloads_via_platform_api(tmp_path):
    script = f"""
    const assert = require("node:assert/strict");
    const esInstances = [];
    globalThis.EventSource = class {{
      constructor(url) {{
        this.url = url;
        this.closed = false;
        esInstances.push(this);
      }}
      addEventListener() {{}}
      close() {{ this.closed = true; }}
    }};
    const apiCalls = [];
    const api = async (url, options) => {{
      apiCalls.push({{ url, options }});
      return {{ items: [], unread_count: 3, next_cursor: null }};
    }};
    const noopEl = () => ({{
      style: {{}}, setAttribute() {{}}, removeAttribute() {{}},
      addEventListener() {{}}, appendChild() {{}}, classList: {{ add() {{}}, remove() {{}} }},
    }});
    globalThis.document = {{
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener() {{}},
      createElement: noopEl,
    }};
    globalThis.window = {{}};
    require({json.dumps(str(NOTIFICATION_JS_PATH))});
    const nc = window.AutoCheckNotificationCenter;
    (async () => {{
      await nc.start({{ user: {{ id: "user-1", username: "zhangsan" }}, csrfToken: "tok-1", api }});
      const afterStart = esInstances.length;
      assert.ok(afterStart >= 1, "start must create an EventSource");
      await nc.updateSession({{ user: {{ id: "user-1" }}, csrfToken: "tok-2" }});
      assert.equal(esInstances.length, afterStart + 1, "updateSession must rebuild EventSource");
      assert.equal(esInstances[afterStart - 1].closed, true, "old EventSource must be closed");
      assert.ok(apiCalls.length >= 1, "updateSession must reload via platform api");
      // 其他用户不重建连接。
      const before = esInstances.length;
      await nc.updateSession({{ user: {{ id: "user-2" }}, csrfToken: "tok-3" }});
      assert.equal(esInstances.length, before, "different user must not rebuild");
      console.log("OK");
    }})().catch((error) => {{ console.error(error && error.stack || error); process.exitCode = 1; }});
    """
    path = tmp_path / "notification_update_session.cjs"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(path)], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout
