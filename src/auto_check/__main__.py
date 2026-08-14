from __future__ import annotations

import argparse
import json
import os

from auto_check.app.server import run_server
from auto_check.package_smoke import run_package_smoke


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Auto Check local Web app")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=_parse_port, default=None)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--config", default=None)
    parser.add_argument("--package-smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.package_smoke_test:
        print(json.dumps(run_package_smoke(), ensure_ascii=False, sort_keys=True))
        return

    host = args.host or os.environ.get("AUTO_CHECK_HOST", DEFAULT_HOST)
    try:
        port = args.port if args.port is not None else _parse_port(os.environ.get("AUTO_CHECK_PORT", str(DEFAULT_PORT)))
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    config_path = args.config if args.config is not None else os.environ.get("AUTO_CHECK_CONFIG") or None

    run_server(
        host=host,
        port=port,
        open_browser=not (args.no_browser or _env_flag("AUTO_CHECK_NO_BROWSER")),
        config_path=config_path,
    )


def _parse_port(value: str | int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _env_flag(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    main()
