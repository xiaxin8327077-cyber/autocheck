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
        const attrs = new Map([["data-login-theme", "dark"]]);
        const values = new Map();
        globalThis.document = {{
          documentElement: {{
            style: {{ setProperty: (key, value) => cssVariables.set(key, value) }},
            getAttribute: (key) => attrs.get(key) || null,
            setAttribute: (key, value) => attrs.set(key, String(value)),
          }},
        }};
        globalThis.localStorage = {{
          getItem: (key) => values.get(key) ?? null,
          setItem: (key, value) => values.set(key, String(value)),
        }};
        globalThis.window = {{}};
        {scenario}
        {_initial_theme_script()}
        Promise.resolve(runScenario({{ assert, cssVariables, attrs, values }}))
          .catch((error) => {{ console.error(error); process.exitCode = 1; }});
        """
    )
    path = tmp_path / "login-theme-bootstrap.cjs"
    path.write_text(script, encoding="utf-8")
    subprocess.run(["node", str(path)], check=True, cwd=ROOT)


def test_login_first_paint_is_forced_light_and_uses_fixed_logo_palette(tmp_path: Path):
    _run_bootstrap_scenario(
        tmp_path,
        r"""
        values.set("autoCheckLoginTheme", "dark");
        values.set("autoCheckLastEffectiveThemeColors", JSON.stringify({
          vitality: "#ABCDEF",
          calm: "#123456",
        }));
        async function runScenario(h) {
          assert.equal(h.attrs.get("data-login-theme"), "light");
          assert.equal(h.cssVariables.get("--theme-accent"), "#3466D9");
          assert.equal(h.cssVariables.get("--theme-accent-gradient-end"), "#6AA4FF");
          assert.equal(
            h.cssVariables.get("--theme-accent-gradient"),
            "linear-gradient(90deg, #3466D9 0%, #6AA4FF 100%)",
          );
          assert.match(h.cssVariables.get("--theme-page-background"), /radial-gradient/);
          assert.match(h.cssVariables.get("--theme-accent-readable"), /^#[0-9A-F]{6}$/);
          assert.match(h.cssVariables.get("--theme-focus-ring"), /^rgba\(/);
          assert.deepEqual(window.autoCheckLoginThemeColors.colors(), {
            vitality: "#3466D9",
            calm: "#355F63",
          });
        }
        """,
    )


def test_login_theme_runtime_has_no_system_color_fetch_or_success_cache():
    html = _read(LOGIN_HTML)
    app = _read(APP_JS)

    assert "/api/settings/interface/theme-colors" not in html
    assert "autoCheckLastEffectiveThemeColors" not in html
    assert "cacheSuccessful" not in html
    assert "autoCheckLoginThemeColors.refresh" not in html
    for source in (html, app):
        assert 'vitality: "#3466D9"' in source
        assert 'calm: "#355F63"' in source


def test_login_uses_one_light_layout_with_login_only_background_and_logo_animation():
    html = _read(LOGIN_HTML)

    assert 'root.setAttribute("data-login-theme", "light")' in html
    assert "LOGIN_PAGE_BACKGROUNDS" in html
    assert "radial-gradient" in html
    assert "linear-gradient(135deg, #EEF4FF" in html
    assert "data-theme-gradient" not in html
    assert "autoCheckLastInterfaceThemeGradient" not in html
    assert "grid-template-columns" not in html
    assert 'class="left-panel"' not in html
    assert 'class="floating-shapes"' not in html
    assert 'class="feature-card"' not in html
    assert "@keyframes lightBrandBubbleFloat" in html
    assert "@keyframes lightBrandBubbleWarmth" in html
    assert "animation: lightBrandBubbleFloat 14s linear infinite alternate" in html
    for token in (
        "background: var(--theme-page-background)",
        "background-image: var(--theme-accent-gradient)",
        "color: var(--theme-on-accent)",
        "color: var(--theme-accent-readable)",
        "caret-color: var(--theme-accent-readable)",
        "border-color: var(--theme-accent-readable)",
        "box-shadow: 0 0 0 4px var(--theme-focus-ring)",
        "accent-color: var(--theme-accent)",
    ):
        assert token in html


def test_login_footer_contact_copy_is_removed():
    html = _read(LOGIN_HTML)

    assert "还没有账户" not in html
    assert "去联系管理员" not in html
