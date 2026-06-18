from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WINDOWS_DEPLOY_SCRIPT = ROOT / "scripts" / "run-deployed-windows.ps1"
LINUX_DEPLOY_SCRIPT = ROOT / "scripts" / "run-deployed-linux.sh"
DEPLOYMENT_DOC = ROOT / "docs" / "deployment.zh-CN.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fixed_port_deployment_scripts_and_docs_are_present() -> None:
    windows_script = _read(WINDOWS_DEPLOY_SCRIPT)
    linux_script = _read(LINUX_DEPLOY_SCRIPT)
    deployment_doc = _read(DEPLOYMENT_DOC)

    for text in [windows_script, linux_script, deployment_doc]:
        assert "8765" in text
        assert "AUTO_CHECK_HOST" in text
        assert "AUTO_CHECK_PORT" in text

    assert "--host" in windows_script
    assert "--port" in windows_script
    assert "--no-browser" in windows_script
    assert "--host" in linux_script
    assert "--port" in linux_script
    assert "--no-browser" in linux_script
    assert "0.0.0.0" in deployment_doc


def test_linux_deployment_doc_covers_operational_steps() -> None:
    deployment_doc = _read(DEPLOYMENT_DOC)

    for expected in [
        "python3.12",
        "python3.12-venv",
        "python -m pip install -e .",
        "AUTO_CHECK_CONFIG=/var/lib/auto-check/config.json",
        "systemctl daemon-reload",
        "systemctl enable --now auto-check",
        "journalctl -u auto-check -f",
        "ufw allow",
        "firewall-cmd",
        "curl -I http://127.0.0.1:",
        "tar -czf",
    ]:
        assert expected in deployment_doc
