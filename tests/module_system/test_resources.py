from __future__ import annotations

import hashlib
import importlib
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
from urllib.parse import quote

import pytest

import auto_check.app.module_system.resources as resources_module
from auto_check.app.module_system.discovery import discover_modules
from auto_check.app.module_system.resources import (
    ModuleAssetNotFound,
    _asset_path_parts,
    _decode_asset_path,
    read_module_asset,
)


FIXTURE_PARENT = Path(__file__).resolve().parents[1] / "fixtures"


def _link_directory(link_path: Path, target_path: Path) -> None:
    try:
        link_path.symlink_to(target_path, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        result = subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(link_path), str(target_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr or result.stdout


@pytest.fixture
def alpha_module(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    return next(
        module
        for module in discover_modules("module_packages")
        if module.manifest.id == "alpha"
    )


@pytest.fixture
def temporary_asset_package(tmp_path, monkeypatch):
    def create(files: dict[str, bytes]):
        package_name = f"asset_package_{abs(hash(str(tmp_path)))}"
        package_path = tmp_path / package_name
        web_path = package_path / "web"
        web_path.mkdir(parents=True)
        (package_path / "__init__.py").write_text("", encoding="utf-8")
        for relative_path, content in files.items():
            file_path = web_path / relative_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)
        monkeypatch.syspath_prepend(str(tmp_path))
        importlib.invalidate_caches()
        return SimpleNamespace(package_name=package_name), web_path

    return create


def test_reads_packaged_module_javascript(alpha_module):
    asset = read_module_asset(alpha_module, "index.js")

    assert b"export function mount" in asset.content
    assert asset.content_type == "text/javascript; charset=utf-8"
    assert asset.etag == hashlib.sha256(asset.content).hexdigest()


def test_returns_a_stable_etag_for_identical_module_content(alpha_module):
    first = read_module_asset(alpha_module, "index.js")
    second = read_module_asset(alpha_module, "index.js")

    assert first.etag == second.etag


@pytest.mark.parametrize(
    ("extension", "content_type"),
    [
        (".js", "text/javascript; charset=utf-8"),
        (".css", "text/css; charset=utf-8"),
        (".svg", "image/svg+xml"),
        (".png", "image/png"),
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".webp", "image/webp"),
        (".json", "application/json; charset=utf-8"),
    ],
)
def test_reads_each_whitelisted_extension_with_its_mime_type(
    temporary_asset_package, extension, content_type
):
    content = b"module asset"
    module, _ = temporary_asset_package({f"asset{extension}": content})

    asset = read_module_asset(module, f"asset{extension}")

    assert asset.content == content
    assert asset.content_type == content_type
    assert asset.etag == hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize(
    "path",
    [
        "../manifest.json",
        "%2e%2e/manifest.json",
        "%252e%252e%252fmanifest.json",
        "/index.js",
        "//server/share/index.js",
        r"\\server\share\index.js",
        "nested/../../index.js",
        r"nested\\index.js",
        "%255cindex.js",
        "",
    ],
)
def test_rejects_module_asset_path_traversal(alpha_module, path):
    with pytest.raises(ModuleAssetNotFound):
        read_module_asset(alpha_module, path)


def test_rejects_unknown_extension(alpha_module):
    with pytest.raises(ModuleAssetNotFound):
        read_module_asset(alpha_module, "secret.bin")


@pytest.mark.parametrize("path", ["C:relative.js", "D:asset.js", "index.js:stream"])
def test_rejects_windows_drive_relative_and_alternate_stream_paths(path):
    with pytest.raises(ModuleAssetNotFound):
        _asset_path_parts(path)


def test_rejects_excessively_long_paths_before_resource_lookup():
    with pytest.raises(ModuleAssetNotFound):
        _decode_asset_path("a" * 2049)


def test_rejects_paths_that_need_too_many_percent_decoding_rounds(temporary_asset_package):
    module, _ = temporary_asset_package({"space name.js": b"encoded asset"})
    encoded_path = "space name.js"
    for _ in range(9):
        encoded_path = quote(encoded_path, safe="")

    with pytest.raises(ModuleAssetNotFound):
        read_module_asset(module, encoded_path)


def test_rejects_directory_requests(temporary_asset_package):
    module, web_path = temporary_asset_package({})
    (web_path / "nested").mkdir()

    with pytest.raises(ModuleAssetNotFound):
        read_module_asset(module, "nested")


def test_rejects_symlinked_assets_outside_the_module_web_root(temporary_asset_package):
    module, web_path = temporary_asset_package({})
    outside_path = web_path.parent / "outside"
    outside_path.mkdir()
    (outside_path / "secret.js").write_bytes(b"outside module web root")
    link_path = web_path / "escaped"
    _link_directory(link_path, outside_path)

    with pytest.raises(ModuleAssetNotFound):
        read_module_asset(module, "escaped/secret.js")


def test_rejects_a_web_root_symlinked_outside_the_module_package(temporary_asset_package):
    module, web_path = temporary_asset_package({})
    outside_path = web_path.parent.parent / "outside_web"
    outside_path.mkdir()
    (outside_path / "index.js").write_bytes(b"outside module package")
    web_path.rmdir()
    _link_directory(web_path, outside_path)

    with pytest.raises(ModuleAssetNotFound):
        read_module_asset(module, "index.js")


def test_does_not_leak_resource_path_for_missing_asset(alpha_module):
    with pytest.raises(ModuleAssetNotFound) as error:
        read_module_asset(alpha_module, "missing.js")

    assert str(FIXTURE_PARENT) not in str(error.value)


def test_rejects_oversized_module_asset_before_serving(temporary_asset_package, monkeypatch):
    module, _ = temporary_asset_package({"large.js": b"12345"})
    monkeypatch.setattr(resources_module, "_MAX_MODULE_ASSET_BYTES", 4)

    with pytest.raises(ModuleAssetNotFound):
        read_module_asset(module, "large.js")
