from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote

from .discovery import DiscoveredModule


_CONTENT_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".json": "application/json; charset=utf-8",
}
_MAX_ASSET_PATH_LENGTH = 2048
_MAX_PERCENT_DECODING_ROUNDS = 8


class ModuleAssetNotFound(LookupError):
    """Raised when a requested module asset is unavailable or unsafe."""


@dataclass(frozen=True)
class ModuleAsset:
    content: bytes
    content_type: str
    etag: str


def _decode_asset_path(relative_path: str) -> str:
    if not isinstance(relative_path, str) or len(relative_path) > _MAX_ASSET_PATH_LENGTH:
        raise ModuleAssetNotFound("module asset not found")

    decoded_path = relative_path
    for _ in range(_MAX_PERCENT_DECODING_ROUNDS):
        next_path = unquote(decoded_path)
        if next_path == decoded_path:
            return decoded_path
        decoded_path = next_path
    raise ModuleAssetNotFound("module asset not found")


def _asset_path_parts(relative_path: str) -> tuple[str, ...]:
    decoded_path = _decode_asset_path(relative_path)
    if (
        not decoded_path
        or decoded_path.startswith("/")
        or "\\" in decoded_path
        or ":" in decoded_path
        or PureWindowsPath(decoded_path).drive
        or PureWindowsPath(decoded_path).is_absolute()
    ):
        raise ModuleAssetNotFound("module asset not found")

    parts = tuple(decoded_path.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ModuleAssetNotFound("module asset not found")
    return parts


def _is_within_package_web_root(
    package_root: Traversable, web_root: Traversable, asset_path: Traversable
) -> bool:
    """Check filesystem-backed package and web boundaries without requiring paths for zip imports."""
    try:
        package_path = Path(package_root).resolve(strict=False)
        root_path = Path(web_root).resolve(strict=False)
        target_path = Path(asset_path).resolve(strict=False)
    except TypeError:
        return True
    except (OSError, RuntimeError):
        return False

    try:
        root_path.relative_to(package_path)
        target_path.relative_to(root_path)
    except ValueError:
        return False
    return True


def read_module_asset(module: DiscoveredModule, relative_path: str) -> ModuleAsset:
    """Read a whitelisted static asset packaged in a module's ``web`` directory."""
    parts = _asset_path_parts(relative_path)
    extension = "." + parts[-1].rsplit(".", maxsplit=1)[-1] if "." in parts[-1] else ""
    content_type = _CONTENT_TYPES.get(extension)
    if content_type is None:
        raise ModuleAssetNotFound("module asset not found")

    try:
        package_root = resources.files(module.package_name)
        web_root = package_root.joinpath("web")
        asset_path = web_root.joinpath(*parts)
        if not asset_path.is_file() or not _is_within_package_web_root(
            package_root, web_root, asset_path
        ):
            raise ModuleAssetNotFound("module asset not found")
        content = asset_path.read_bytes()
    except ModuleAssetNotFound:
        raise
    except (ModuleNotFoundError, OSError, ValueError):
        raise ModuleAssetNotFound("module asset not found") from None

    return ModuleAsset(
        content=content,
        content_type=content_type,
        etag=hashlib.sha256(content).hexdigest(),
    )
