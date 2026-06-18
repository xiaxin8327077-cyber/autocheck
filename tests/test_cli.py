from __future__ import annotations

import sys

import pytest

import auto_check.__main__ as cli


def test_main_uses_fixed_default_port(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.delenv("AUTO_CHECK_HOST", raising=False)
    monkeypatch.delenv("AUTO_CHECK_PORT", raising=False)
    monkeypatch.delenv("AUTO_CHECK_CONFIG", raising=False)
    monkeypatch.setattr(sys, "argv", ["auto-check", "--no-browser"])
    monkeypatch.setattr(cli, "run_server", lambda **kwargs: calls.update(kwargs))

    cli.main()

    assert calls == {
        "host": "127.0.0.1",
        "port": 8765,
        "open_browser": False,
        "config_path": None,
    }


def test_main_reads_deployment_defaults_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setenv("AUTO_CHECK_HOST", "0.0.0.0")
    monkeypatch.setenv("AUTO_CHECK_PORT", "9876")
    monkeypatch.setenv("AUTO_CHECK_CONFIG", "/etc/auto-check/config.json")
    monkeypatch.setattr(sys, "argv", ["auto-check", "--no-browser"])
    monkeypatch.setattr(cli, "run_server", lambda **kwargs: calls.update(kwargs))

    cli.main()

    assert calls == {
        "host": "0.0.0.0",
        "port": 9876,
        "open_browser": False,
        "config_path": "/etc/auto-check/config.json",
    }


def test_main_rejects_invalid_deployment_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_CHECK_PORT", "0")
    monkeypatch.setattr(sys, "argv", ["auto-check"])
    monkeypatch.setattr(cli, "run_server", lambda **kwargs: None)

    with pytest.raises(SystemExit):
        cli.main()
