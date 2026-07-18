from __future__ import annotations

import re
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOGIN_HTML = ROOT / "src" / "auto_check" / "web" / "login.html"
APP_JS = ROOT / "src" / "auto_check" / "web" / "app.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _initial_theme_script() -> str:
    html = _read(LOGIN_HTML)
    match = re.search(
        r'<script id="initialLoginThemeColorScript">(?P<body>.*?)</script>',
        html,
        re.S,
    )
    assert match is not None
    assert match.start() < html.index("<style>")
    return match.group("body")


def _run_bootstrap_scenario(tmp_path: Path, scenario: str) -> None:
    script = textwrap.dedent(
        f"""
        const assert = require("node:assert/strict");
        const cssVariables = new Map();
        const attrs = new Map([["data-login-theme", "light"]]);
        const values = new Map();
        const writes = [];
        globalThis.document = {{
          documentElement: {{
            style: {{ setProperty: (key, value) => cssVariables.set(key, value) }},
            getAttribute: (key) => attrs.get(key) || null,
            setAttribute: (key, value) => attrs.set(key, String(value)),
          }},
        }};
        globalThis.localStorage = {{
          getItem: (key) => values.get(key) ?? null,
          setItem: (key, value) => {{
            values.set(key, String(value));
            writes.push({{ key, value: String(value) }});
          }},
        }};
        globalThis.window = {{}};
        {scenario}
        {_initial_theme_script()}
        Promise.resolve(runScenario({{ assert, cssVariables, attrs, values, writes }}))
          .catch((error) => {{ console.error(error); process.exitCode = 1; }});
        """
    )
    path = tmp_path / "login-theme-bootstrap.cjs"
    path.write_text(script, encoding="utf-8")
    subprocess.run(["node", str(path)], check=True, cwd=ROOT)


def test_login_first_paint_uses_strict_last_successful_effective_color_cache(tmp_path: Path):
    _run_bootstrap_scenario(
        tmp_path,
        r"""
        values.set("autoCheckLastEffectiveThemeColors", JSON.stringify({
          vitality: "#abcdef",
          calm: "#123456",
        }));
        values.set("autoCheckThemeUserKey", "id:7");
        values.set("autoCheckTheme:id:7", "light");
        values.set("autoCheckLoginTheme", "dark");
        async function runScenario(h) {
          assert.equal(h.attrs.get("data-login-theme"), "dark");
          assert.equal(h.cssVariables.get("--theme-accent"), "#123456");
          assert.match(h.cssVariables.get("--theme-page-background"), /^#[0-9A-F]{6}$/);
          assert.match(h.cssVariables.get("--theme-accent-readable"), /^#[0-9A-F]{6}$/);
          assert.match(h.cssVariables.get("--theme-focus-ring"), /^rgba\(/);
          assert.deepEqual(window.autoCheckLoginThemeColors.colors(), {
            vitality: "#ABCDEF",
            calm: "#123456",
          });
        }
        """,
    )


def test_login_cache_bad_fields_fall_back_independently_and_never_enable_gradient(tmp_path: Path):
    _run_bootstrap_scenario(
        tmp_path,
        r"""
        values.set("autoCheckLastEffectiveThemeColors", JSON.stringify({
          vitality: "#123",
          calm: "#abcdef",
          gradient: true,
        }));
        values.set("autoCheckThemeUserKey", "id:9");
        values.set("autoCheckTheme:id:9", "space-tech");
        async function runScenario(h) {
          assert.equal(h.cssVariables.get("--theme-accent"), "#3F6FAF");
          assert.deepEqual(window.autoCheckLoginThemeColors.colors(), {
            vitality: "#3F6FAF",
            calm: "#ABCDEF",
          });
          assert.equal([...h.cssVariables.values()].some((value) => /gradient/i.test(value)), false);
          assert.equal(document.documentElement.getAttribute("data-theme-gradient"), null);
        }
        """,
    )


def test_anonymous_refresh_applies_system_colors_without_polluting_success_cache(tmp_path: Path):
    _run_bootstrap_scenario(
        tmp_path,
        r"""
        values.set("autoCheckLastEffectiveThemeColors", JSON.stringify({
          vitality: "#111111",
          calm: "#222222",
        }));
        globalThis.fetch = async (path) => {
          assert.equal(path, "/api/settings/interface/theme-colors");
          return {
            ok: true,
            json: async () => ({
              colors: {
                system: { vitality: "#456789", calm: "#987654" },
                effective: { vitality: "#456789", calm: "#987654" },
              },
            }),
          };
        };
        async function runScenario(h) {
          assert.equal(await window.autoCheckLoginThemeColors.refresh(), true);
          assert.deepEqual(window.autoCheckLoginThemeColors.colors(), {
            vitality: "#456789",
            calm: "#987654",
          });
          assert.equal(h.writes.some((item) => item.key === "autoCheckLastEffectiveThemeColors"), false);
          assert.equal(window.autoCheckLoginThemeColors.cacheSuccessful(), true);
          assert.deepEqual(
            JSON.parse(h.values.get("autoCheckLastEffectiveThemeColors")),
            { vitality: "#456789", calm: "#987654" },
          );
        }
        """,
    )


def test_login_success_is_the_only_auth_path_that_updates_effective_color_cache():
    html = _read(LOGIN_HTML)
    handler = re.search(
        r'form\.addEventListener\("submit", async \(event\) => \{(?P<body>.*?)\n      \}\);',
        html,
        re.S,
    )
    assert handler is not None
    body = handler.group("body")
    success_call = "window.autoCheckLoginThemeColors.cacheSuccessful();"
    assert body.count(success_call) == 1
    assert body.index('await apiAuth("/api/auth/login"') < body.index(success_call)
    assert body.index('await apiAuth("/api/auth/setup"') < body.index(success_call)
    catch_body = body[body.index("} catch (error) {") :]
    assert success_call not in catch_body
    assert "autoCheckLastEffectiveThemeColors" not in catch_body


def test_login_and_main_app_share_effective_color_defaults_and_cache_key():
    login = _read(LOGIN_HTML)
    app = _read(APP_JS)
    for source in (login, app):
        assert 'vitality: "#3F6FAF"' in source
        assert 'calm: "#355F63"' in source
        assert '"autoCheckLastEffectiveThemeColors"' in source


def test_login_light_and_dark_share_geometry_and_use_solid_theme_tokens():
    html = _read(LOGIN_HTML)
    assert "linear-gradient" not in html
    assert "radial-gradient" not in html
    assert "data-theme-gradient" not in html
    assert "autoCheckLastInterfaceThemeGradient" not in html
    assert "grid-template-columns" not in html
    assert 'class="left-panel"' not in html
    assert 'class="floating-shapes"' not in html
    assert 'class="feature-card"' not in html
    dark_rules = re.findall(
        r':root\[data-login-theme="dark"\][^{]*\{(?P<body>.*?)\}',
        html,
        re.S,
    )
    for body in dark_rules:
        for forbidden in (
            "display:",
            "width:",
            "height:",
            "padding:",
            "margin:",
            "border-radius:",
            "grid-template",
        ):
            assert forbidden not in body
    for token in (
        "background: var(--theme-page-background)",
        "background: var(--theme-accent)",
        "color: var(--theme-on-accent)",
        "color: var(--theme-accent-readable)",
        "caret-color: var(--theme-accent-readable)",
        "border-color: var(--theme-accent-readable)",
        "box-shadow: 0 0 0 4px var(--theme-focus-ring)",
        "accent-color: var(--theme-accent)",
    ):
        assert token in html
    password_toggle = re.search(r"\.password-toggle\s*\{(?P<body>.*?)\}", html, re.S)
    assert password_toggle is not None
    assert "color: var(--theme-accent-readable)" in password_toggle.group("body")
