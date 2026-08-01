# Auto Check 模块化扩展宿主实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一次性的模块发现、路由、权限、数据库迁移、前端加载和打包宿主，使后续普通业务模块原则上只需新增 `src/auto_check/modules/<module_id>/` 目录。

**Architecture:** 保持现有功能和公共入口不拆除，在平台层增加 `module_system` 功能包。后端扫描可信内置模块清单并注册独占 API，前端宿主读取授权模块清单后动态加载 ES Module；核心模块管理表仍通过人工增量 SQL 建立，业务模块使用自己的独立迁移版本。

**Tech Stack:** Python 3.12、现有 `http.server` 服务、SQLAlchemy 2.x、MySQL 应用数据库、原生 HTML/CSS/JavaScript ES Module、pytest、Node.js 静态语法检查、PyInstaller。

## Global Constraints

- 详细架构以 `docs/superpowers/specs/2026-07-31-modular-extension-architecture-design.md` 为准。
- `PLATFORM_API_VERSION` 首版固定为 `1`。
- 只加载随 Auto Check 源码和安装包发布的可信内置模块，不提供在线上传第三方插件。
- 不引入 React、Vue、Node.js 构建链或新的 Web 框架。
- 现有自动对数、人行导入、人行校验、流程工具、历史和报送导航行为必须保持不变。
- 现有核心应用数据库仍执行只读结构校验；`012_module_system.sql` 由部署人员执行，业务模块迁移由模块运行时执行。
- `CURRENT_APP_SCHEMA_VERSION` 保持 `1`，模块 schema 使用 `app_module_schema_versions` 独立管理。
- 模块 ID 只允许小写字母、数字和下划线；API、权限、事件、数据库表和 DOM 必须使用模块命名空间。
- 模块前端只能在 `.auto-check-module[data-module="<module_id>"]` 根节点内操作 DOM 和定义样式。
- 页面继续只保留当前亮色活力主题，主操作按钮和圆角继续使用现有主题变量。
- 本计划只建设模块宿主和测试夹具，不实现自定义报表业务。
- 实施时优先由子代理或后台线程运行测试，主会话负责检查结果和必要修正。
- 普通源码和前端改动完成后不自动运行 Windows 打包脚本，也不刷新 `dist/auto-check.exe`；只有用户明确要求打包时才执行。

---

## 文件职责总览

### 新增平台文件

| 文件 | 单一职责 |
|---|---|
| `src/auto_check/app/module_system/__init__.py` | 导出稳定的平台模块接口 |
| `src/auto_check/app/module_system/contracts.py` | 模块清单、请求、响应、状态和生命周期协议 |
| `src/auto_check/app/module_system/discovery.py` | 扫描模块包、读取清单、解析入口和依赖排序 |
| `src/auto_check/app/module_system/permissions.py` | 权限编码校验和当前角色默认授权 |
| `src/auto_check/app/module_system/routing.py` | 模块相对路由注册、匹配和分发 |
| `src/auto_check/app/module_system/services.py` | 带版本的模块公开服务注册和只读解析 |
| `src/auto_check/app/module_system/events.py` | 命名空间事件订阅、发布和订阅者故障隔离 |
| `src/auto_check/app/module_system/storage.py` | 模块状态、schema 版本和迁移历史持久化 |
| `src/auto_check/app/module_system/schema.py` | 加载、校验和执行模块独立 SQL 迁移 |
| `src/auto_check/app/module_system/resources.py` | 安全读取模块前端资源 |
| `src/auto_check/app/module_system/runtime.py` | 模块发现、启停、路由、资源和公开清单编排 |
| `src/auto_check/modules/__init__.py` | 内置业务模块扫描根包 |
| `src/auto_check/web/module_host.js` | 前端模块清单、导航、资源和生命周期宿主 |
| `src/auto_check/web/module_host.css` | 宿主根容器、加载和错误状态样式 |
| `sql/app_storage/mysql/012_module_system.sql` | 建立模块管理三张核心表 |

### 一次性修改的公共文件

| 文件 | 修改范围 |
|---|---|
| `src/auto_check/app/app_database.py` | 将三张模块管理表加入核心结构校验 |
| `src/auto_check/app/server.py` | 创建模块运行时、委派模块 API、提供模块资源并在退出时停止模块 |
| `src/auto_check/web/index.html` | 增加模块导航挂载点、模块页面根节点和宿主资源 |
| `src/auto_check/web/app.js` | 向宿主提供稳定桥接对象，并在页面启动和传统导航时调用宿主 |
| `scripts/package-windows.ps1` | 收集模块 Python 子包和数据资源 |
| `scripts/package-linux.sh` | 收集模块 Python 子包和数据资源 |
| `scripts/Dockerfile.linux-build` | 收集模块 Python 子包和数据资源 |
| `scripts/docker-build.sh` | 收集模块 Python 子包和数据资源 |
| `README.md` | 记录模块化能力和应用库增量 SQL |
| `docs/mysql-application-storage.zh-CN.md` | 更新应用库表结构和模块迁移规则 |
| `docs/deployment.zh-CN.md` | 增加 `012_module_system.sql` 部署步骤 |
| `docs/intranet-production-deployment.zh-CN.md` | 增加内网部署步骤 |

### 新增测试文件

| 文件 | 覆盖范围 |
|---|---|
| `tests/module_system/test_contracts.py` | 清单解析和字段约束 |
| `tests/module_system/test_discovery.py` | 自动发现、入口加载和依赖排序 |
| `tests/module_system/test_routing.py` | 路由冲突、参数、权限和响应 |
| `tests/module_system/test_collaboration.py` | 公开服务、版本检查和事件隔离 |
| `tests/module_system/test_schema.py` | 模块管理表和独立迁移 |
| `tests/module_system/test_runtime.py` | 生命周期、可选失败、启停和公开清单 |
| `tests/module_system/test_resources.py` | 模块资源和路径穿越防护 |
| `tests/module_system/test_server_integration.py` | 登录、CSRF、模块 API 和资源 HTTP 集成 |
| `tests/module_system/test_frontend_host.py` | 宿主脚本、DOM 作用域和前端生命周期 |
| `tests/module_system/test_packaging.py` | PyInstaller 模块收集参数 |
| `tests/fixtures/module_packages/` | 自动化测试使用的合法、依赖、冲突和失败模块 |

---

### Task 1: 定义模块清单和稳定协议

**Files:**

- Create: `src/auto_check/app/module_system/__init__.py`
- Create: `src/auto_check/app/module_system/contracts.py`
- Create: `src/auto_check/modules/__init__.py`
- Create: `tests/module_system/__init__.py`
- Create: `tests/module_system/test_contracts.py`

**Interfaces:**

- Produces: `PLATFORM_API_VERSION = 1`
- Produces: `ModuleManifest.from_mapping(payload: Mapping[str, object]) -> ModuleManifest`
- Produces: `NavigationDeclaration`
- Produces: `ModuleRequest`
- Produces: `ModuleHttpResponse.json()` and `ModuleHttpResponse.bytes()`
- Produces: `ModuleStatus`, `ModuleHealth`, `ModuleBootstrapContext`, `ModuleContext` and `AutoCheckModule`

- [ ] **Step 1: 编写清单解析失败测试**

```python
from __future__ import annotations

import pytest

from auto_check.app.module_system.contracts import ModuleManifest, ModuleManifestError


VALID_MANIFEST = {
    "id": "custom_reports",
    "name": "自定义报表",
    "version": "1.0.0",
    "platform_api": 1,
    "required": False,
    "backend_entry": "auto_check.modules.custom_reports.module:create_module",
    "api_prefix": "/api/modules/custom-reports",
    "frontend_entry": "/module-assets/custom_reports/index.js",
    "frontend_style": "/module-assets/custom_reports/styles.css",
    "navigation": [
        {
            "id": "custom-reports",
            "label": "自定义报表",
            "route": "custom-reports",
            "order": 60,
            "permission": "custom_reports.view",
        }
    ],
    "permissions": ["custom_reports.view", "custom_reports.design"],
    "dependencies": [],
    "schema_version": 0,
}


def test_manifest_parses_valid_payload():
    manifest = ModuleManifest.from_mapping(VALID_MANIFEST)

    assert manifest.id == "custom_reports"
    assert manifest.api_prefix == "/api/modules/custom-reports"
    assert manifest.navigation[0].permission == "custom_reports.view"
    assert manifest.schema_version == 0


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "Custom-Reports", "id"),
        ("platform_api", 2, "platform_api"),
        ("api_prefix", "/api/config", "api_prefix"),
        ("backend_entry", "missing_separator", "backend_entry"),
        ("permissions", ["other.view"], "permission"),
        ("schema_version", -1, "schema_version"),
    ],
)
def test_manifest_rejects_invalid_fields(field, value, message):
    payload = {**VALID_MANIFEST, field: value}

    with pytest.raises(ModuleManifestError, match=message):
        ModuleManifest.from_mapping(payload)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/module_system/test_contracts.py -q
```

Expected: FAIL，导入 `auto_check.app.module_system.contracts` 失败。

- [ ] **Step 3: 实现模块协议**

`contracts.py` 至少实现以下不可变协议：

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

PLATFORM_API_VERSION = 1


class ModuleManifestError(ValueError):
    pass


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ModuleManifestError(f"{key} must be a non-empty string")
    return value.strip()


def _required_int(payload: Mapping[str, object], key: str, *, minimum: int) -> int:
    value = payload.get(key)
    if type(value) is not int or value < minimum:
        raise ModuleManifestError(f"{key} must be an integer greater than or equal to {minimum}")
    return value


def _required_text_tuple(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ModuleManifestError(f"{key} must be a list of non-empty strings")
    normalized = tuple(item.strip() for item in value)
    if len(set(normalized)) != len(normalized):
        raise ModuleManifestError(f"{key} contains duplicate values")
    return normalized


class ModuleStatus(StrEnum):
    DISCOVERED = "discovered"
    LOADING = "loading"
    ENABLED = "enabled"
    DISABLED = "disabled"
    INCOMPATIBLE = "incompatible"
    MIGRATION_FAILED = "migration_failed"
    STARTUP_FAILED = "startup_failed"


@dataclass(frozen=True)
class NavigationDeclaration:
    id: str
    label: str
    route: str
    order: int
    permission: str


@dataclass(frozen=True)
class ModuleManifest:
    id: str
    name: str
    version: str
    platform_api: int
    required: bool
    backend_entry: str
    api_prefix: str
    frontend_entry: str
    frontend_style: str
    navigation: tuple[NavigationDeclaration, ...]
    permissions: tuple[str, ...]
    dependencies: tuple[str, ...]
    schema_version: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "ModuleManifest":
        module_id = _required_text(payload, "id")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", module_id):
            raise ModuleManifestError("id must use lowercase letters, digits, and underscores")
        version = _required_text(payload, "version")
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ModuleManifestError("version must use MAJOR.MINOR.PATCH")
        platform_api = _required_int(payload, "platform_api", minimum=1)
        if platform_api != PLATFORM_API_VERSION:
            raise ModuleManifestError(
                f"platform_api {platform_api} is incompatible with {PLATFORM_API_VERSION}"
            )
        api_prefix = _required_text(payload, "api_prefix")
        if not api_prefix.startswith("/api/modules/"):
            raise ModuleManifestError("api_prefix must start with /api/modules/")
        backend_entry = _required_text(payload, "backend_entry")
        if backend_entry.count(":") != 1:
            raise ModuleManifestError("backend_entry must use package.module:function")
        permissions = _required_text_tuple(payload, "permissions")
        if any(not item.startswith(f"{module_id}.") for item in permissions):
            raise ModuleManifestError("permission must use the module namespace")
        dependencies = _required_text_tuple(payload, "dependencies")
        if module_id in dependencies:
            raise ModuleManifestError("dependencies cannot contain the module itself")
        if any(not re.fullmatch(r"[a-z][a-z0-9_]*", item) for item in dependencies):
            raise ModuleManifestError("dependencies contain an invalid module id")
        navigation_payload = payload.get("navigation")
        if not isinstance(navigation_payload, list):
            raise ModuleManifestError("navigation must be a list")
        navigation = tuple(
            NavigationDeclaration(
                id=_required_text(item, "id"),
                label=_required_text(item, "label"),
                route=_required_text(item, "route"),
                order=_required_int(item, "order", minimum=0),
                permission=_required_text(item, "permission"),
            )
            for item in navigation_payload
            if isinstance(item, Mapping)
        )
        if len(navigation) != len(navigation_payload):
            raise ModuleManifestError("navigation items must be objects")
        if any(item.permission not in permissions for item in navigation):
            raise ModuleManifestError("navigation permission is not declared")
        if len({item.id for item in navigation}) != len(navigation):
            raise ModuleManifestError("navigation contains a duplicate id")
        if len({item.route for item in navigation}) != len(navigation):
            raise ModuleManifestError("navigation contains a duplicate route")
        frontend_entry = _required_text(payload, "frontend_entry")
        frontend_style = _required_text(payload, "frontend_style")
        resource_prefix = f"/module-assets/{module_id}/"
        if not frontend_entry.startswith(resource_prefix):
            raise ModuleManifestError("frontend_entry must use the module asset namespace")
        if not frontend_style.startswith(resource_prefix):
            raise ModuleManifestError("frontend_style must use the module asset namespace")
        required = payload.get("required")
        if not isinstance(required, bool):
            raise ModuleManifestError("required must be a boolean")
        return cls(
            id=module_id,
            name=_required_text(payload, "name"),
            version=version,
            platform_api=platform_api,
            required=required,
            backend_entry=backend_entry,
            api_prefix=api_prefix,
            frontend_entry=frontend_entry,
            frontend_style=frontend_style,
            navigation=navigation,
            permissions=permissions,
            dependencies=dependencies,
            schema_version=_required_int(payload, "schema_version", minimum=0),
        )


@dataclass(frozen=True)
class ModuleRequest:
    method: str
    path: str
    path_params: Mapping[str, str]
    query: Mapping[str, str]
    body: Mapping[str, Any] | None
    current_user: Mapping[str, Any]


@dataclass(frozen=True)
class ModuleHttpResponse:
    status: int
    body: Mapping[str, Any] | bytes
    content_type: str
    headers: tuple[tuple[str, str], ...] = ()

    @classmethod
    def json(cls, status: int, body: Mapping[str, Any]) -> "ModuleHttpResponse":
        return cls(status=status, body=body, content_type="application/json; charset=utf-8")

    @classmethod
    def bytes(
        cls,
        status: int,
        body: bytes,
        *,
        content_type: str,
        headers: tuple[tuple[str, str], ...] = (),
    ) -> "ModuleHttpResponse":
        return cls(status=status, body=body, content_type=content_type, headers=headers)


@dataclass(frozen=True)
class ModuleHealth:
    healthy: bool
    message: str = ""


@dataclass(frozen=True)
class ModuleBootstrapContext:
    application_database: Any
    config_path: Path
    temp_root: Path
    now: Callable[[], Any]


@dataclass(frozen=True)
class ModuleContext(ModuleBootstrapContext):
    services: Any
    events: Any
    logger: Any
    background_executor: Any


class AutoCheckModule(Protocol):
    manifest: ModuleManifest

    def register_routes(self, router: Any) -> None:
        """Register relative API routes."""

    def register_schema(self, registry: Any) -> None:
        """Register expected module-owned tables and columns."""

    def start(self, context: ModuleContext) -> None:
        """Start module-owned services and background work."""

    def stop(self) -> None:
        """Stop module-owned services and release subscriptions."""

    def health(self) -> ModuleHealth:
        """Return current module health without exposing secrets."""
```

实现时不得保留省略号；`from_mapping()` 必须显式校验：

- 必填字段完整。
- 模块 ID 正则为 `^[a-z][a-z0-9_]*$`。
- `platform_api == 1`。
- `api_prefix` 以 `/api/modules/` 开头。
- 前端资源分别位于 `/module-assets/<id>/` 下。
- 权限全部以 `<module_id>.` 开头。
- 导航 ID、路由和权限非空。
- 模块版本使用 `MAJOR.MINOR.PATCH`。
- 导航 ID 和路由在模块内不能重复。
- 依赖项必须是合法且不重复的模块 ID。
- 依赖不包含自身。
- schema 版本是非负整数且不接受布尔值。

- [ ] **Step 4: 运行协议测试**

Run:

```powershell
python -m pytest tests/module_system/test_contracts.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交协议**

```powershell
git add src/auto_check/app/module_system src/auto_check/modules tests/module_system
git commit -m "feat: define module extension contracts"
```

---

### Task 2: 实现模块自动发现和依赖排序

**Files:**

- Create: `src/auto_check/app/module_system/discovery.py`
- Create: `tests/module_system/test_discovery.py`
- Create: `tests/fixtures/module_packages/__init__.py`
- Create: `tests/fixtures/module_packages/alpha/__init__.py`
- Create: `tests/fixtures/module_packages/alpha/manifest.json`
- Create: `tests/fixtures/module_packages/alpha/module.py`
- Create: `tests/fixtures/module_packages/beta/__init__.py`
- Create: `tests/fixtures/module_packages/beta/manifest.json`
- Create: `tests/fixtures/module_packages/beta/module.py`
- Create: `tests/fixtures/module_packages/broken_optional/__init__.py`
- Create: `tests/fixtures/module_packages/broken_optional/manifest.json`
- Create: `tests/fixtures/module_packages/broken_optional/module.py`
- Create: `tests/fixtures/module_packages/broken_required/__init__.py`
- Create: `tests/fixtures/module_packages/broken_required/manifest.json`
- Create: `tests/fixtures/module_packages/broken_required/module.py`

**Interfaces:**

- Consumes: `ModuleManifest.from_mapping()`
- Produces: `DiscoveredModule(package_name, package_root, manifest)`
- Produces: `discover_modules(package_name: str) -> list[DiscoveredModule]`
- Produces: `sort_modules(modules) -> list[DiscoveredModule]`
- Produces: `load_module_factory(entry: str) -> Callable[[], AutoCheckModule]`

- [ ] **Step 1: 编写发现和排序测试**

```python
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from auto_check.app.module_system.discovery import (
    ModuleDiscoveryError,
    discover_modules,
    load_module_factory,
    sort_modules,
)


FIXTURE_PARENT = Path(__file__).resolve().parents[1] / "fixtures"


def test_discovers_direct_child_packages_and_sorts_dependencies(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))

    modules = discover_modules("module_packages")
    ordered = sort_modules([module for module in modules if module.manifest.id in {"alpha", "beta"}])

    assert [module.manifest.id for module in ordered] == ["alpha", "beta"]


def test_loads_declared_factory(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))

    factory = load_module_factory("module_packages.alpha.module:create_module")

    assert callable(factory)
    assert factory().manifest.id == "alpha"


def test_rejects_dependency_cycle(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    modules = discover_modules("module_packages")
    alpha = next(module for module in modules if module.manifest.id == "alpha")
    beta = next(module for module in modules if module.manifest.id == "beta")
    cycled_alpha = replace(alpha, manifest=replace(alpha.manifest, dependencies=("beta",)))

    with pytest.raises(ModuleDiscoveryError, match="循环依赖"):
        sort_modules([cycled_alpha, beta])
```

夹具清单全部使用 Task 1 的完整字段：

- `alpha`：API 前缀 `/api/modules/alpha`、权限 `alpha.view`、无依赖、schema 版本 0。
- `beta`：API 前缀 `/api/modules/beta`、权限 `beta.view`、依赖 `alpha`、schema 版本 0。
- `broken_optional`：`required=false`，工厂抛出 `RuntimeError("fixture startup failure")`。
- `broken_required`：`required=true`，工厂抛出同一个固定异常。

`alpha.module` 和 `beta.module` 返回实现 `AutoCheckModule` 的夹具类；`start()` 和 `stop()` 把 `<module_id>:start`、`<module_id>:stop` 写入测试注入的调用记录，`health()` 返回 `ModuleHealth(healthy=True)`。

- [ ] **Step 2: 运行发现测试确认失败**

Run:

```powershell
python -m pytest tests/module_system/test_discovery.py -q
```

Expected: FAIL，缺少 `discovery.py`。

- [ ] **Step 3: 实现发现器**

实现流程固定为：

```python
def discover_modules(package_name: str = "auto_check.modules") -> list[DiscoveredModule]:
    package = importlib.import_module(package_name)
    modules = []
    for item in sorted(pkgutil.iter_modules(package.__path__), key=lambda value: value.name):
        if not item.ispkg or item.name.startswith("_"):
            continue
        child_package = f"{package_name}.{item.name}"
        root = resources.files(child_package)
        manifest_path = root.joinpath("manifest.json")
        if not manifest_path.is_file():
            continue
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        modules.append(
            DiscoveredModule(
                package_name=child_package,
                package_root=root,
                manifest=ModuleManifest.from_mapping(payload),
            )
        )
    return modules
```

`sort_modules()` 使用稳定的拓扑排序：

- 缺少必需依赖时报错。
- 检测循环依赖。
- 同层模块按模块 ID 排序。
- 返回新的列表，不修改输入。

`load_module_factory()` 只接受 `package.module:function`，使用 `importlib.import_module()` 加载并确认目标可调用。

- [ ] **Step 4: 运行发现测试**

Run:

```powershell
python -m pytest tests/module_system/test_contracts.py tests/module_system/test_discovery.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交自动发现**

```powershell
git add src/auto_check/app/module_system/discovery.py tests/module_system/test_discovery.py tests/fixtures/module_packages
git commit -m "feat: discover built-in modules automatically"
```

---

### Task 3: 实现权限注册和模块相对路由

**Files:**

- Create: `src/auto_check/app/module_system/permissions.py`
- Create: `src/auto_check/app/module_system/routing.py`
- Create: `tests/module_system/test_routing.py`

**Interfaces:**

- Consumes: `ModuleManifest`, `ModuleRequest`, `ModuleHttpResponse`
- Produces: `default_permission_evaluator(user, permission) -> bool`
- Produces: `ModuleRouter(manifest, permission_evaluator)`
- Produces: `ModuleRouter.add(method, path, handler, *, permission, max_body_bytes)`
- Produces: `ModuleRouter.dispatch(request) -> ModuleHttpResponse | None`

- [ ] **Step 1: 编写路由和权限测试**

```python
import pytest

from auto_check.app.module_system.contracts import ModuleHttpResponse, ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouteConflict, ModuleRouter


ADMIN = {"id": "1", "role": "admin"}
USER = {"id": "2", "role": "user"}


def test_admin_has_all_module_permissions_and_user_has_view_only():
    assert default_permission_evaluator(ADMIN, "custom_reports.publish") is True
    assert default_permission_evaluator(USER, "custom_reports.view") is True
    assert default_permission_evaluator(USER, "custom_reports.publish") is False
    assert default_permission_evaluator(None, "custom_reports.view") is False


def test_router_matches_relative_path_and_decodes_parameter(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    router.add(
        "GET",
        "/templates/{template_id}",
        lambda request: ModuleHttpResponse.json(200, {"id": request.path_params["template_id"]}),
        permission="custom_reports.view",
        max_body_bytes=0,
    )

    response = router.dispatch(
        ModuleRequest(
            method="GET",
            path="/api/modules/custom-reports/templates/abc%201",
            path_params={},
            query={},
            body=None,
            current_user=USER,
        )
    )

    assert response is not None
    assert response.status == 200
    assert response.body == {"id": "abc 1"}


def test_router_returns_forbidden_before_handler(valid_manifest):
    called = False

    def handler(request):
        nonlocal called
        called = True
        return ModuleHttpResponse.json(200, {})

    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    router.add("POST", "/publish", handler, permission="custom_reports.publish", max_body_bytes=1024)

    response = router.dispatch(
        ModuleRequest("POST", "/api/modules/custom-reports/publish", {}, {}, {}, USER)
    )

    assert response.status == 403
    assert response.body == {"error": "permission denied"}
    assert called is False


def test_router_rejects_duplicate_method_and_path(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    handler = lambda request: ModuleHttpResponse.json(200, {})
    router.add("GET", "/templates", handler, permission="custom_reports.view", max_body_bytes=0)

    with pytest.raises(ModuleRouteConflict):
        router.add("GET", "/templates", handler, permission="custom_reports.view", max_body_bytes=0)
```

将 `valid_manifest` fixture 放入 `tests/module_system/conftest.py`，内容使用 Task 1 的合法清单。

- [ ] **Step 2: 运行路由测试确认失败**

Run:

```powershell
python -m pytest tests/module_system/test_routing.py -q
```

Expected: FAIL，缺少权限和路由实现。

- [ ] **Step 3: 实现权限和路由**

权限首版规则固定为：

```python
def default_permission_evaluator(
    current_user: Mapping[str, Any] | None,
    permission: str,
) -> bool:
    if not current_user:
        return False
    if str(current_user.get("role") or "") == "admin":
        return True
    return permission.endswith(".view")
```

路由实现要求：

- 注册路径必须以 `/` 开头但不能包含 `/api/`。
- 权限必须存在于清单 `permissions` 中。
- 路径参数只匹配单个 `/` 分段。
- 参数使用 `urllib.parse.unquote()` 解码。
- 未匹配时返回 `None`。
- 方法不匹配时返回 `405` 和允许的方法。
- 权限不足返回 `403`，不调用处理器。
- 处理器抛出 `ValueError` 返回 `400`。
- 其他异常返回带 `module_id` 和 `error_id` 的 `500`，不返回堆栈。

- [ ] **Step 4: 运行路由及协议测试**

Run:

```powershell
python -m pytest tests/module_system/test_contracts.py tests/module_system/test_routing.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交路由**

```powershell
git add src/auto_check/app/module_system/permissions.py src/auto_check/app/module_system/routing.py tests/module_system/conftest.py tests/module_system/test_routing.py
git commit -m "feat: add namespaced module routing"
```

---

### Task 4: 实现公开服务和事件总线

**Files:**

- Create: `src/auto_check/app/module_system/services.py`
- Create: `src/auto_check/app/module_system/events.py`
- Create: `tests/module_system/test_collaboration.py`
- Modify: `src/auto_check/app/module_system/contracts.py`

**Interfaces:**

- Produces: `ServiceRegistry.register(name, version, provider, owner)`
- Produces: `ServiceRegistry.resolve(name, minimum_version) -> object`
- Produces: `EventBus.subscribe(event_name, handler, owner) -> Subscription`
- Produces: `EventBus.publish(event_name, payload) -> EventDeliveryReport`
- Produces: `ModuleServices` and `ModuleEvents` 受限视图
- Produces: `ModuleTaskExecutor.submit(callable, *args, **kwargs) -> Future`
- Refines: `ModuleContext.services`, `ModuleContext.events`, `ModuleContext.logger` and `ModuleContext.background_executor`

- [ ] **Step 1: 编写公开服务和事件隔离测试**

```python
import pytest

from auto_check.app.module_system.events import EventBus
from auto_check.app.module_system.services import ServiceRegistry, ServiceVersionError


def test_service_registry_resolves_compatible_public_service():
    provider = object()
    registry = ServiceRegistry()
    registry.register("alpha.lookup", 2, provider, owner="alpha")

    assert registry.resolve("alpha.lookup", minimum_version=1) is provider


def test_service_registry_rejects_cross_namespace_registration():
    registry = ServiceRegistry()

    with pytest.raises(ValueError, match="namespace"):
        registry.register("beta.lookup", 1, object(), owner="alpha")


def test_service_registry_rejects_incompatible_version():
    registry = ServiceRegistry()
    registry.register("alpha.lookup", 1, object(), owner="alpha")

    with pytest.raises(ServiceVersionError, match="version"):
        registry.resolve("alpha.lookup", minimum_version=2)


def test_event_bus_isolates_failing_subscriber():
    calls = []
    bus = EventBus()
    bus.subscribe("alpha:published", lambda payload: calls.append(("first", payload)), owner="alpha")
    bus.subscribe(
        "alpha:published",
        lambda payload: (_ for _ in ()).throw(RuntimeError("fixture failure")),
        owner="beta",
    )
    bus.subscribe("alpha:published", lambda payload: calls.append(("third", payload)), owner="gamma")

    report = bus.publish("alpha:published", {"id": "1"})

    assert calls == [("first", {"id": "1"}), ("third", {"id": "1"})]
    assert report.delivered == 2
    assert report.failed == 1


def test_module_event_view_only_publishes_own_namespace():
    events = EventBus().for_module("alpha")

    with pytest.raises(ValueError, match="namespace"):
        events.publish("beta:changed", {})
```

- [ ] **Step 2: 运行协作接口测试确认失败**

Run:

```powershell
python -m pytest tests/module_system/test_collaboration.py -q
```

Expected: FAIL，缺少服务注册和事件总线。

- [ ] **Step 3: 实现服务注册和事件总线**

服务注册规则：

- 服务名正则为 `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`。
- 名称前缀必须等于 owner。
- 版本是正整数且不接受布尔值。
- 同名服务不能重复注册。
- `resolve()` 在版本不足时抛出 `ServiceVersionError`。
- 模块只能获得只读解析视图，不能替其他模块注册服务。

事件总线规则：

- 事件名正则为 `^(system|[a-z][a-z0-9_]*):[a-z][a-z0-9_]*$`。
- 模块只允许发布自己的命名空间；平台可以发布 `system:*`。
- 订阅者按注册顺序执行。
- 单个订阅者失败写入 `EventDeliveryReport.errors`，不阻断后续订阅者。
- `Subscription.close()` 必须移除订阅，模块停止时关闭其全部订阅。
- 事件负载先通过 `json.dumps()` 验证可序列化。

Task 1 已为 `ModuleContext` 预留以下字段；本任务用 `ModuleServices`、`ModuleEvents` 和后台执行器协议替换宽泛的 `Any` 类型：

```python
@dataclass(frozen=True)
class ModuleContext(ModuleBootstrapContext):
    services: ModuleServices
    events: ModuleEvents
    logger: logging.LoggerAdapter
    background_executor: ModuleTaskExecutor
```

`ModuleTaskExecutor` 协议定义 `submit()` 和 `shutdown(cancel_pending: bool)`；具体的有界线程执行器由 Task 8 的运行时创建。

- [ ] **Step 4: 运行协作接口及协议测试**

Run:

```powershell
python -m pytest tests/module_system/test_collaboration.py tests/module_system/test_contracts.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交协作接口**

```powershell
git add src/auto_check/app/module_system/services.py src/auto_check/app/module_system/events.py src/auto_check/app/module_system/contracts.py tests/module_system/test_collaboration.py
git commit -m "feat: add versioned module collaboration interfaces"
```

---

### Task 5: 建立模块管理核心表

**Files:**

- Create: `sql/app_storage/mysql/012_module_system.sql`
- Create: `tests/module_system/test_schema.py`
- Modify: `src/auto_check/app/app_database.py`
- Modify: `tests/test_app_database.py`
- Modify: `tests/test_user_interface_preferences.py`
- Modify: `tests/test_report_navigation_schema.py`

**Interfaces:**

- Produces: 核心表 `app_modules`
- Produces: 核心表 `app_module_schema_versions`
- Produces: 核心表 `app_module_migration_history`
- Preserves: `CURRENT_APP_SCHEMA_VERSION == 1`

- [ ] **Step 1: 编写核心 schema 失败测试**

```python
from pathlib import Path

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA


ROOT = Path(__file__).resolve().parents[2]
MODULE_SQL = ROOT / "sql" / "app_storage" / "mysql" / "012_module_system.sql"


def test_module_system_core_tables_are_part_of_expected_schema():
    assert CURRENT_APP_SCHEMA_VERSION == 1
    assert EXPECTED_APP_SCHEMA["app_modules"] >= {
        "module_id",
        "module_version",
        "enabled",
        "status",
        "last_error",
        "installed_at",
        "updated_at",
    }
    assert EXPECTED_APP_SCHEMA["app_module_schema_versions"] >= {
        "module_id",
        "schema_version",
        "applied_at",
        "checksum",
    }
    assert EXPECTED_APP_SCHEMA["app_module_migration_history"] >= {
        "id",
        "module_id",
        "from_version",
        "to_version",
        "status",
        "checksum",
        "started_at",
        "finished_at",
        "error_message",
    }
    assert len(EXPECTED_APP_SCHEMA) == 42


def test_module_system_sql_is_repeatable_and_does_not_change_core_version():
    sql = MODULE_SQL.read_text(encoding="utf-8")

    assert sql.count("CREATE TABLE IF NOT EXISTS") == 3
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    assert "INSERT INTO `app_schema_version`" not in sql
```

- [ ] **Step 2: 运行 schema 测试确认失败**

Run:

```powershell
python -m pytest tests/module_system/test_schema.py tests/test_app_database.py -q
```

Expected: FAIL，SQL 文件和三张表声明不存在。

- [ ] **Step 3: 编写增量 SQL 和核心结构声明**

`012_module_system.sql` 创建三张 InnoDB 表，使用 `utf8mb4`，并包含：

```sql
CREATE TABLE IF NOT EXISTS `app_modules` (
  `module_id` varchar(64) NOT NULL,
  `module_version` varchar(32) NOT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT 1,
  `status` varchar(32) NOT NULL,
  `last_error` text NULL,
  `installed_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`module_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

另外两张表严格使用设计文档字段；迁移历史 `id` 使用 `bigint AUTO_INCREMENT`，并为 `(module_id, started_at)` 建立索引。

在 `EXPECTED_APP_SCHEMA` 中加入三张表，但保持 `CURRENT_APP_SCHEMA_VERSION = 1`。同步把现有测试中的固定表数量 `39` 改为 `42`。

- [ ] **Step 4: 运行核心 schema 测试**

Run:

```powershell
python -m pytest tests/module_system/test_schema.py tests/test_app_database.py tests/test_user_interface_preferences.py tests/test_report_navigation_schema.py tests/test_sqlite_to_mysql_export.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交核心表**

```powershell
git add sql/app_storage/mysql/012_module_system.sql src/auto_check/app/app_database.py tests/module_system/test_schema.py tests/test_app_database.py tests/test_user_interface_preferences.py tests/test_report_navigation_schema.py
git commit -m "feat: add module system storage schema"
```

---

### Task 6: 实现模块状态存储和独立迁移

**Files:**

- Create: `src/auto_check/app/module_system/storage.py`
- Create: `src/auto_check/app/module_system/schema.py`
- Modify: `tests/module_system/test_schema.py`
- Create: `tests/fixtures/module_packages/alpha/migrations/001_initial.sql`
- Create: `tests/fixtures/module_packages/alpha/migrations/002_add_note.sql`

**Interfaces:**

- Consumes: `ApplicationDatabase.transaction()`
- Produces: `ModuleStateStore`
- Produces: `ModuleMigration(version, name, checksum, statements)`
- Produces: `load_module_migrations(package_name) -> tuple[ModuleMigration, ...]`
- Produces: `ModuleMigrationRunner.run(manifest, package_name) -> int`
- Produces: `ModuleSchemaRegistry.add(table_name, columns)` and `validate(connection)`

- [ ] **Step 1: 扩充迁移测试**

```python
def test_loads_numbered_module_migrations_with_checksums(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))

    migrations = load_module_migrations("module_packages.alpha")

    assert [item.version for item in migrations] == [1, 2]
    assert all(len(item.checksum) == 64 for item in migrations)
    assert migrations[0].statements == (
        "CREATE TABLE alpha_items (id bigint PRIMARY KEY)",
    )


def test_runner_applies_only_missing_versions_and_records_checksum(fake_module_database, alpha_manifest):
    runner = ModuleMigrationRunner(fake_module_database)

    version = runner.run(alpha_manifest, "module_packages.alpha")
    second_version = runner.run(alpha_manifest, "module_packages.alpha")

    assert version == 2
    assert second_version == 2
    assert fake_module_database.executed.count("CREATE TABLE alpha_items (id bigint PRIMARY KEY)") == 1
    assert fake_module_database.executed.count("ALTER TABLE alpha_items ADD COLUMN note text NULL") == 1


def test_runner_rejects_changed_applied_checksum(fake_module_database, alpha_manifest):
    fake_module_database.schema_versions["alpha"] = (1, "different-checksum")

    with pytest.raises(ModuleMigrationError, match="摘要"):
        ModuleMigrationRunner(fake_module_database).run(alpha_manifest, "module_packages.alpha")
```

迁移文件使用以下显式分隔符，不使用简单的分号拆分：

```sql
CREATE TABLE alpha_items (id bigint PRIMARY KEY)
-- module-statement-break
CREATE INDEX idx_alpha_items_id ON alpha_items (id)
```

本任务同时把测试夹具 `alpha/manifest.json` 的 `schema_version` 从 `0` 改为 `2`。`alpha.module.register_schema()` 注册：

```python
registry.add("alpha_items", {"id", "note"})
```

- [ ] **Step 2: 运行迁移测试确认失败**

Run:

```powershell
python -m pytest tests/module_system/test_schema.py -q
```

Expected: FAIL，缺少模块迁移加载器和存储。

- [ ] **Step 3: 实现状态存储和迁移器**

`ModuleStateStore` 使用参数化 SQL，必须实现以下签名：

- `load_enabled(module_id: str) -> bool | None`
- `save_discovered(manifest: ModuleManifest) -> None`
- `set_enabled(module_id: str, enabled: bool) -> None`
- `set_status(module_id: str, status: ModuleStatus, error: str = "") -> None`
- `load_schema_version(module_id: str) -> tuple[int, str] | None`
- `record_migration_started(module_id: str, migration: ModuleMigration) -> int`
- `record_migration_completed(history_id: int, migration: ModuleMigration) -> None`
- `record_migration_failed(history_id: int, error: str) -> None`

`ModuleMigrationRunner.run()` 固定执行：

1. 获取 `GET_LOCK('auto_check_module_<id>', 10)`。
2. 加载迁移文件并校验版本连续、目标版本和摘要。
3. 对每个缺失版本写入 running 历史。
4. 按 `-- module-statement-break` 分段执行非空 SQL。
5. 更新模块 schema 版本和 completed 历史。
6. 失败时另开事务记录 failed，并抛出脱敏异常。
7. `finally` 调用 `RELEASE_LOCK()`。

迁移 SQL 不输出到日志，异常信息去除连接串和超过 500 字符的内容。

`ModuleSchemaRegistry` 保存模块自己的预期表字段；模块迁移完成后从 `information_schema` 校验，但不把业务模块表加入全局 `EXPECTED_APP_SCHEMA`。

- [ ] **Step 4: 运行存储和迁移测试**

Run:

```powershell
python -m pytest tests/module_system/test_schema.py tests/test_app_database.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交模块迁移**

```powershell
git add src/auto_check/app/module_system/storage.py src/auto_check/app/module_system/schema.py tests/module_system/test_schema.py tests/fixtures/module_packages/alpha/migrations
git commit -m "feat: add isolated module migrations"
```

---

### Task 7: 实现模块资源读取和路径防护

**Files:**

- Create: `src/auto_check/app/module_system/resources.py`
- Create: `tests/module_system/test_resources.py`
- Create: `tests/fixtures/module_packages/alpha/web/index.js`
- Create: `tests/fixtures/module_packages/alpha/web/styles.css`

**Interfaces:**

- Consumes: `DiscoveredModule.package_name`
- Produces: `ModuleAsset(content: bytes, content_type: str, etag: str)`
- Produces: `read_module_asset(module, relative_path) -> ModuleAsset`

- [ ] **Step 1: 编写资源安全测试**

```python
from auto_check.app.module_system.resources import ModuleAssetNotFound, read_module_asset


def test_reads_packaged_module_javascript(alpha_module):
    asset = read_module_asset(alpha_module, "index.js")

    assert b"export function mount" in asset.content
    assert asset.content_type == "text/javascript; charset=utf-8"
    assert len(asset.etag) == 64


@pytest.mark.parametrize("path", ["../manifest.json", "%2e%2e/manifest.json", "/index.js", "nested/../../index.js"])
def test_rejects_module_asset_path_traversal(alpha_module, path):
    with pytest.raises(ModuleAssetNotFound):
        read_module_asset(alpha_module, path)


def test_rejects_unknown_extension(alpha_module):
    with pytest.raises(ModuleAssetNotFound):
        read_module_asset(alpha_module, "secret.bin")
```

- [ ] **Step 2: 运行资源测试确认失败**

Run:

```powershell
python -m pytest tests/module_system/test_resources.py -q
```

Expected: FAIL，缺少资源读取器。

- [ ] **Step 3: 实现资源读取器**

实现要求：

- URL 解码后拒绝绝对路径、空段、`.` 和 `..`。
- 只读取模块包 `web/` 下的文件。
- 允许扩展名：`.js`、`.css`、`.svg`、`.png`、`.jpg`、`.jpeg`、`.webp`、`.json`。
- 使用 `importlib.resources.files()`，兼容源码和 PyInstaller。
- `etag` 是文件内容 SHA-256。
- 不返回真实磁盘路径。
- 未找到、目录或非法扩展名统一抛出 `ModuleAssetNotFound`。

- [ ] **Step 4: 运行资源测试**

Run:

```powershell
python -m pytest tests/module_system/test_resources.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交资源服务**

```powershell
git add src/auto_check/app/module_system/resources.py tests/module_system/test_resources.py tests/fixtures/module_packages/alpha/web
git commit -m "feat: serve isolated module assets"
```

---

### Task 8: 实现模块运行时和生命周期

**Files:**

- Create: `src/auto_check/app/module_system/runtime.py`
- Create: `tests/module_system/test_runtime.py`
- Modify: `src/auto_check/app/module_system/__init__.py`

**Interfaces:**

- Consumes: `discover_modules()`, `sort_modules()`, `ModuleStateStore`, `ModuleMigrationRunner`, `ModuleRouter`
- Produces: `ModuleRuntime.build(context: ModuleBootstrapContext, package_name="auto_check.modules")`
- Produces: `ModuleRuntime.start()` and `stop()`
- Produces: `ModuleRuntime.dispatch(*, method, path, query, body, current_user, body_size=0) -> ModuleHttpResponse`
- Produces: `ModuleRuntime.read_asset(module_id, relative_path) -> ModuleAsset`
- Produces: `ModuleRuntime.public_modules(current_user) -> list[dict[str, object]]`
- Produces: `ModuleRuntime.admin_statuses(current_user) -> list[dict[str, object]]`
- Produces: `ModuleRuntime.set_enabled(module_id, enabled, current_user)`

- [ ] **Step 1: 编写生命周期测试**

```python
import pytest

from auto_check.app.module_system.runtime import ModuleStartupError


def test_runtime_starts_modules_in_dependency_order(runtime_factory):
    runtime, calls = runtime_factory(["alpha", "beta"])

    runtime.start()

    assert calls == ["alpha:start", "beta:start"]
    assert [item["id"] for item in runtime.public_modules({"role": "admin"})] == ["alpha", "beta"]


def test_optional_module_failure_does_not_block_healthy_modules(runtime_factory):
    runtime, calls = runtime_factory(["alpha", "broken_optional"])

    runtime.start()

    assert runtime.status("alpha").value == "enabled"
    assert runtime.status("broken_optional").value == "startup_failed"
    assert [item["id"] for item in runtime.public_modules({"role": "admin"})] == ["alpha"]


def test_required_module_failure_aborts_startup(runtime_factory):
    runtime, calls = runtime_factory(["broken_required"])

    with pytest.raises(ModuleStartupError, match="broken_required"):
        runtime.start()


def test_runtime_stops_enabled_modules_in_reverse_order(runtime_factory):
    runtime, calls = runtime_factory(["alpha", "beta"])
    runtime.start()
    calls.clear()

    runtime.stop()

    assert calls == ["beta:stop", "alpha:stop"]


def test_regular_user_only_receives_view_navigation(runtime_factory):
    runtime, calls = runtime_factory(["alpha"])
    runtime.start()

    modules = runtime.public_modules({"role": "user"})

    assert modules[0]["navigation"] == [
        {
            "id": "alpha",
            "label": "Alpha",
            "route": "alpha",
            "order": 10,
            "permission": "alpha.view",
        }
    ]


def test_admin_statuses_include_disabled_and_failed_modules(runtime_factory):
    runtime, calls = runtime_factory(["alpha", "broken_optional"])
    runtime.start()
    runtime.set_enabled("alpha", False, {"role": "admin"})

    statuses = runtime.admin_statuses({"role": "admin"})

    assert [(item["id"], item["status"]) for item in statuses] == [
        ("alpha", "disabled"),
        ("broken_optional", "startup_failed"),
    ]
```

- [ ] **Step 2: 运行运行时测试确认失败**

Run:

```powershell
python -m pytest tests/module_system/test_runtime.py -q
```

Expected: FAIL，缺少 `ModuleRuntime`。

- [ ] **Step 3: 实现运行时**

运行时记录：

```python
@dataclass
class LoadedModule:
    discovered: DiscoveredModule
    instance: AutoCheckModule | None = None
    router: ModuleRouter | None = None
    status: ModuleStatus = ModuleStatus.DISCOVERED
    error: str = ""
```

启动顺序固定为：

1. 自动发现并依赖排序。
2. 保存 discovered 状态。
3. 读取 `app_modules.enabled`；首次发现默认启用。
4. 跳过禁用模块。
5. 加载工厂并检查实例清单 ID 与文件清单一致。
6. 注册路由和模块 schema。
7. 执行模块迁移并校验 schema。
8. 为模块创建专属服务视图、事件视图、日志适配器和后台任务执行器。
9. 调用 `start(context)`。
10. 标记 enabled。

运行时拥有一个共享 `ServiceRegistry`、一个共享 `EventBus` 和一个 `ThreadPoolExecutor(max_workers=4)`。每个模块获得的 `ModuleContext`：

- `services` 只能注册当前模块命名空间的服务，但可以按显式依赖解析其他模块公开服务。
- `events` 只能发布当前模块命名空间事件，并记录当前模块创建的订阅。
- `logger` 使用 `logging.LoggerAdapter`，所有记录自动附加 `module_id`。
- `background_executor` 默认最多同时运行 2 个当前模块任务；超过限制抛出 `ModuleTaskLimitError`。
- 模块停止时取消尚未开始的任务、关闭订阅并注销该模块公开服务。

`public_modules()` 只返回 enabled 模块，并过滤当前用户无权访问的导航。公开字段固定为：

```python
{
    "id": manifest.id,
    "name": manifest.name,
    "version": manifest.version,
    "frontend_entry": manifest.frontend_entry,
    "frontend_style": manifest.frontend_style,
    "navigation": visible_navigation,
}
```

不得公开 `backend_entry`、包路径、迁移文件、内部错误堆栈或数据库信息。

`admin_statuses()` 只允许管理员调用，返回模块 ID、名称、版本、required、enabled、status、health 和最长 500 字符的脱敏错误摘要；不返回模块包路径和异常堆栈。

`set_enabled()` 仅允许管理员：

- 禁用：调用 `stop()`，标记 disabled，后续路由返回 404。
- 启用：重新执行加载、迁移、schema 校验和 `start()`。
- 必需模块不能禁用。

- [ ] **Step 4: 运行模块系统测试**

Run:

```powershell
python -m pytest tests/module_system/test_contracts.py tests/module_system/test_discovery.py tests/module_system/test_routing.py tests/module_system/test_collaboration.py tests/module_system/test_schema.py tests/module_system/test_resources.py tests/module_system/test_runtime.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交运行时**

```powershell
git add src/auto_check/app/module_system/runtime.py src/auto_check/app/module_system/__init__.py tests/module_system/test_runtime.py
git commit -m "feat: add module lifecycle runtime"
```

---

### Task 9: 接入 HTTP 服务、鉴权和 CSRF

**Files:**

- Modify: `src/auto_check/app/server.py`
- Create: `tests/module_system/test_server_integration.py`
- Modify: `tests/test_security.py`
- Modify: `tests/test_server.py`

**Interfaces:**

- Consumes: `ModuleRuntime`
- Produces: `GET /api/system/modules`
- Produces: `PUT /api/system/modules/{module_id}/state`
- Produces: `/api/modules/<module-path>`
- Produces: `GET /module-assets/<module_id>/<resource-path>`

- [ ] **Step 1: 编写 HTTP 集成失败测试**

```python
import http.client
import json


def _request(server, method, path, body=None, headers=None):
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    connection.request(
        method,
        path,
        body=payload,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    response = connection.getresponse()
    data = response.read()
    response_headers = {key.lower(): value for key, value in response.getheaders()}
    connection.close()
    return response.status, data, response_headers


def test_module_list_requires_login(module_server):
    status, data, headers = _request(module_server, "GET", "/api/system/modules")

    assert status == 401
    assert json.loads(data) == {"error": "login required"}


def test_authenticated_user_receives_visible_module_list(authenticated_module_server):
    server, auth_headers = authenticated_module_server
    status, data, headers = _request(server, "GET", "/api/system/modules", headers=auth_headers)

    assert status == 200
    assert json.loads(data)["modules"][0]["id"] == "alpha"


def test_module_mutation_requires_csrf(authenticated_module_server):
    server, auth_headers = authenticated_module_server
    status, data, headers = _request(
        server,
        "PUT",
        "/api/system/modules/alpha/state",
        {"enabled": False},
        {"Cookie": auth_headers["Cookie"], "X-CSRF-Token": ""},
    )

    assert status == 403


def test_module_api_uses_current_user(authenticated_module_server):
    server, auth_headers = authenticated_module_server
    status, data, headers = _request(
        server,
        "GET",
        "/api/modules/alpha/whoami",
        headers=auth_headers,
    )

    assert status == 200
    assert json.loads(data)["username"] == "admin"


def test_module_asset_blocks_traversal(module_server):
    status, data, headers = _request(
        module_server,
        "GET",
        "/module-assets/alpha/%2e%2e/manifest.json",
    )

    assert status == 404
```

`module_server` fixture 沿用 `tests/test_security.py` 的模式创建 `ThreadingHTTPServer`、`ApiRouter` 和 `AuthManager`，并注入测试模块运行时。`authenticated_module_server` 使用同一个 `AuthManager` 创建管理员会话，返回：

```python
{
    "Cookie": f"auto_check_session={session.session_id}",
    "X-CSRF-Token": session.csrf_token,
}
```

- [ ] **Step 2: 运行 HTTP 集成测试确认失败**

Run:

```powershell
python -m pytest tests/module_system/test_server_integration.py tests/test_security.py -q
```

Expected: FAIL，模块路径仍返回 404。

- [ ] **Step 3: 一次性接入服务**

修改 `ApiRouter.__init__()`：

```python
module_runtime: ModuleRuntime | None = None
```

缺省使用 `ModuleRuntime.empty()`，保证现有单元测试和调用方不触发文件扫描。

在 `AutoCheckRequestHandler` 中：

- `/api/system/modules` 和 `/api/modules/` 在登录、CSRF 校验后委派模块运行时。
- `GET /api/system/modules` 返回 `{"modules": [...]}`；管理员响应额外包含 `module_statuses`。
- GET 模块请求不读取请求体。
- POST、PUT、DELETE 最大读取现有 `MAX_UPLOAD_BYTES`，再由模块路由检查自己的 `max_body_bytes`。
- JSON 响应继续使用 `_send_json()`。
- bytes 响应设置模块返回的 `Content-Type` 和安全响应头，再调用 `_write_response_body()`。
- `/module-assets/` 只允许 GET，通过运行时读取资源，支持 `ETag` 和 `If-None-Match`。
- 不把模块路径交给现有 `_serve_static()`。

在 `run_server()` 中：

```python
module_context = ModuleBootstrapContext(
    application_database=application_database,
    config_path=resolved_config_path,
    temp_root=resolved_config_path.parent / "module-data",
    now=datetime.now,
)
module_runtime = ModuleRuntime.build(module_context)
module_runtime.start()
router = ApiRouter(
    config_path=resolved_config_path,
    application_database=application_database,
    module_runtime=module_runtime,
    start_field_mapping_auto_refresh=True,
)
```

模块运行时应在创建 `ThreadingHTTPServer` 之前启动，避免必需模块失败后留下监听端口；如果 HTTP 服务创建失败，仍由 `finally` 停止已经启动的模块。在 `finally` 中依次停止报送导航调度器、模块运行时、HTTP 服务并关闭应用数据库。

错误处理：

- 未登录：401。
- 普通用户修改模块状态：403。
- 模块不存在或禁用：404。
- 非法 JSON：400。
- 请求体超过模块限制：413。
- 模块异常：使用运行时生成的脱敏 500。

- [ ] **Step 4: 运行服务和安全测试**

Run:

```powershell
python -m pytest tests/module_system/test_server_integration.py tests/test_security.py tests/test_server.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交 HTTP 接入**

```powershell
git add src/auto_check/app/server.py tests/module_system/test_server_integration.py tests/test_security.py tests/test_server.py
git commit -m "feat: connect modules to authenticated HTTP host"
```

---

### Task 10: 建设前端模块宿主

**Files:**

- Create: `src/auto_check/web/module_host.js`
- Create: `src/auto_check/web/module_host.css`
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Create: `tests/module_system/test_frontend_host.py`
- Modify: `tests/test_web_static.py`

**Interfaces:**

- Consumes: `GET /api/system/modules`
- Produces: `window.AutoCheckModuleHost.initialize(platform) -> Promise<boolean>`
- Produces: `activate(route)`, `deactivate()`, `reload()`, `unmount()`
- Produces: module lifecycle context `{root, api, user, notify, confirm, navigate, events}`

- [ ] **Step 1: 编写前端结构和生命周期失败测试**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HOST_JS = ROOT / "src" / "auto_check" / "web" / "module_host.js"
HOST_CSS = ROOT / "src" / "auto_check" / "web" / "module_host.css"
INDEX_HTML = ROOT / "src" / "auto_check" / "web" / "index.html"
APP_JS = ROOT / "src" / "auto_check" / "web" / "app.js"


def test_module_host_has_stable_lifecycle_contract():
    script = HOST_JS.read_text(encoding="utf-8")

    for fragment in [
        "window.AutoCheckModuleHost",
        "function createModuleHost",
        "async function initialize",
        "async function activate",
        "async function deactivate",
        "async function unmount",
        'api("/api/system/modules")',
        "importModule(module.frontend_entry)",
        "instance.mount(context)",
        "instance.activate(route)",
        "instance.deactivate()",
        "instance.unmount()",
    ]:
        assert fragment in script


def test_module_host_is_loaded_once_before_app_bootstrap():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert html.count('src="/module_host.js') == 1
    assert html.index('src="/module_host.js') < html.index('src="/app.js')
    assert 'id="moduleSideNavigation"' in html
    assert 'id="moduleTopNavigation"' in html
    assert 'id="modulePageHost"' in html


def test_module_host_css_is_scoped():
    css = HOST_CSS.read_text(encoding="utf-8")

    assert ".auto-check-module" in css
    assert "\nbutton {" not in css
    assert "\ninput {" not in css
    assert "\ntable {" not in css


def test_legacy_app_exposes_only_explicit_platform_bridge():
    script = APP_JS.read_text(encoding="utf-8")

    assert "window.AutoCheckModuleHost.initialize({" in script
    assert "api," in script
    assert "user: () => ({ ...authState.user })" in script
    assert "notify: showToast" in script
    assert "confirm: showConfirm" in script
    assert "legacyNavigate: switchPage" in script
```

另外通过 Node.js 场景测试注入假的 `document`、`api` 和 `importModule`，断言：

- 两个导航挂载点生成同一模块入口。
- 初始 hash 属于模块时 `initialize()` 返回 `true`。
- 从模块切到传统页面调用 `deactivate()`。
- 加载失败只在 `modulePageHost` 显示错误，不抛出到全局。

- [ ] **Step 2: 运行前端测试确认失败**

Run:

```powershell
python -m pytest tests/module_system/test_frontend_host.py tests/test_web_static.py -q
```

Expected: FAIL，宿主文件和挂载点不存在。

- [ ] **Step 3: 实现前端宿主和一次性桥接**

`module_host.js` 使用 IIFE，在浏览器中只导出 `window.AutoCheckModuleHost`。IIFE 内部提供 `createModuleHost({ documentRef, locationRef, importModule })` 工厂；Node.js 测试通过 `module.exports = { createModuleHost }` 获取工厂，浏览器不会产生额外全局变量。内部状态固定为：

```javascript
const state = {
  platform: null,
  modules: new Map(),
  routes: new Map(),
  instances: new Map(),
  activeModuleId: "",
  activeRoute: "",
  initialized: false,
};
```

`initialize(platform)`：

1. 校验 `api`、`user`、`notify`、`confirm` 和 `legacyNavigate`。
2. 请求模块清单。
3. 为每个模块加载 CSS。
4. 使用可注入的 `importModule`，默认值为 `(url) => import(url)`。
5. 校验模块导出四个生命周期函数。
6. 调用 `mount(context)`。
7. 创建侧栏和顶部导航。
8. 如果当前 hash 属于模块则调用 `activate()` 并返回 `true`，否则返回 `false`。

模块上下文使用 `Object.freeze()`，事件名必须以当前模块 ID 开头。

在 `index.html` 中一次性加入：

```html
<div id="moduleSideNavigation"></div>
<div id="moduleTopNavigation"></div>
<section id="modulePageHost" class="auto-check-module-host" hidden></section>
<link rel="stylesheet" href="/module_host.css" />
<script src="/module_host.js"></script>
```

在 `app.js` 启动代码中：

```javascript
const moduleHandled = await window.AutoCheckModuleHost.initialize({
  api,
  user: () => ({ ...authState.user }),
  notify: showToast,
  confirm: showConfirm,
  legacyNavigate: switchPage,
});
if (!moduleHandled) {
  const savedPage = location.hash.slice(1);
  if (savedPage && document.getElementById("page-" + savedPage)) {
    await switchPage(savedPage, { forceHomeRefresh: savedPage === "home" });
  } else {
    await switchPage("report-navigation");
  }
}
```

在传统 `switchPage()` 开始时调用：

```javascript
await window.AutoCheckModuleHost?.deactivate();
```

宿主导航使用自己的事件委派，不修改启动时静态获取的 `navItems`。

- [ ] **Step 4: 运行前端测试和 Node.js 语法检查**

Run:

```powershell
python -m pytest tests/module_system/test_frontend_host.py tests/test_web_static.py -q
node --check src/auto_check/web/module_host.js
node --check src/auto_check/web/app.js
```

Expected: 全部 PASS，两个 Node.js 命令退出码为 0。

- [ ] **Step 5: 提交前端宿主**

```powershell
git add src/auto_check/web/module_host.js src/auto_check/web/module_host.css src/auto_check/web/index.html src/auto_check/web/app.js tests/module_system/test_frontend_host.py tests/test_web_static.py
git commit -m "feat: add dynamic frontend module host"
```

---

### Task 11: 验证真正的“只增加模块目录”

**Files:**

- Create: `tests/fixtures/dropin_modules/report_demo/__init__.py`
- Create: `tests/fixtures/dropin_modules/report_demo/manifest.json`
- Create: `tests/fixtures/dropin_modules/report_demo/module.py`
- Create: `tests/fixtures/dropin_modules/report_demo/migrations/001_initial.sql`
- Create: `tests/fixtures/dropin_modules/report_demo/web/index.js`
- Create: `tests/fixtures/dropin_modules/report_demo/web/styles.css`
- Create: `tests/module_system/test_dropin_module.py`
- Modify: `tests/module_system/conftest.py`

**Interfaces:**

- Consumes: 已完成的发现、迁移、HTTP 和前端宿主协议
- Produces: 一个只通过目录接入的测试模块

- [ ] **Step 1: 编写端到端验收测试**

```python
def test_dropin_module_needs_no_central_registration(dropin_runtime):
    runtime = dropin_runtime()

    runtime.start()

    modules = runtime.public_modules({"id": "1", "role": "admin"})
    assert [module["id"] for module in modules] == ["report_demo"]

    response = runtime.dispatch(
        method="GET",
        path="/api/modules/report-demo/health",
        query={},
        body=None,
        current_user={"id": "1", "username": "admin", "role": "admin"},
    )
    assert response.status == 200
    assert response.body == {"module": "report_demo", "status": "ok"}

    asset = runtime.read_asset("report_demo", "index.js")
    assert b"export function mount" in asset.content


def test_disabling_dropin_module_removes_api_navigation_and_tasks(dropin_runtime):
    runtime = dropin_runtime()
    runtime.start()

    runtime.set_enabled("report_demo", False, {"role": "admin"})

    assert runtime.public_modules({"role": "admin"}) == []
    assert runtime.dispatch(
        method="GET",
        path="/api/modules/report-demo/health",
        query={},
        body=None,
        current_user={"role": "admin"},
    ).status == 404
```

- [ ] **Step 2: 运行验收测试确认失败**

Run:

```powershell
python -m pytest tests/module_system/test_dropin_module.py -q
```

Expected: FAIL，pytest 报告 `dropin_runtime` fixture 不存在。

- [ ] **Step 3: 完成测试模块并只修正平台契约**

`report_demo` 只提供：

- `GET /health`
- 一张 `report_demo_items` 测试表
- 一个无业务内容的 ES Module 生命周期
- 作用域样式

`dropin_runtime` fixture 把 `tests/fixtures` 加入 `sys.path`，以 `dropin_modules` 作为发现根包，并注入测试应用数据库、固定时钟和临时模块目录。

测试模块不得加入 `src/auto_check/modules`，不得出现在正式导航中。为了使测试通过而修改平台时，只允许修改 `module_system/` 和对应测试；不得向 `server.py`、`app.js` 或 `index.html` 添加 `report_demo` 名称。

- [ ] **Step 4: 运行全部模块系统测试**

Run:

```powershell
python -m pytest tests/module_system -q
```

Expected: PASS。

- [ ] **Step 5: 提交 drop-in 验收**

```powershell
git add tests/fixtures/dropin_modules tests/module_system/conftest.py tests/module_system/test_dropin_module.py src/auto_check/app/module_system
git commit -m "test: prove directory-only module integration"
```

---

### Task 12: 适配 PyInstaller 模块收集

**Files:**

- Modify: `scripts/package-windows.ps1`
- Modify: `scripts/package-linux.sh`
- Modify: `scripts/Dockerfile.linux-build`
- Modify: `scripts/docker-build.sh`
- Modify: `scripts/build.ps1`
- Create: `tests/module_system/test_packaging.py`

**Interfaces:**

- Consumes: `auto_check.modules`
- Produces: PyInstaller 参数 `--collect-submodules auto_check.modules`
- Produces: PyInstaller 参数 `--collect-data auto_check.modules`

- [ ] **Step 1: 编写打包参数失败测试**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_FILES = [
    ROOT / "scripts" / "package-windows.ps1",
    ROOT / "scripts" / "package-linux.sh",
    ROOT / "scripts" / "Dockerfile.linux-build",
    ROOT / "scripts" / "docker-build.sh",
    ROOT / "scripts" / "build.ps1",
]


def test_all_pyinstaller_entrypoints_collect_module_code_and_data():
    for path in PACKAGE_FILES:
        content = path.read_text(encoding="utf-8")
        assert "collect-submodules" in content, path
        assert "auto_check.modules" in content, path
        assert "collect-data" in content, path
```

- [ ] **Step 2: 运行打包静态测试确认失败**

Run:

```powershell
python -m pytest tests/module_system/test_packaging.py -q
```

Expected: FAIL，现有脚本没有模块收集参数。

- [ ] **Step 3: 更新全部 PyInstaller 入口**

Windows 参数数组加入：

```powershell
"--collect-submodules", "auto_check.modules",
"--collect-data", "auto_check.modules",
```

Shell 和 Docker 命令加入：

```text
--collect-submodules auto_check.modules
--collect-data auto_check.modules
```

不得移除现有 `web`、`resources`、数据库驱动和压缩库参数。

- [ ] **Step 4: 运行打包静态测试**

Run:

```powershell
python -m pytest tests/module_system/test_packaging.py -q
```

Expected: PASS。

本任务不执行实际打包。只有用户明确要求生成可执行程序时，才运行 `scripts/package-windows.ps1` 并验证 `dist/auto-check.exe`。

- [ ] **Step 5: 提交打包适配**

```powershell
git add scripts/package-windows.ps1 scripts/package-linux.sh scripts/Dockerfile.linux-build scripts/docker-build.sh scripts/build.ps1 tests/module_system/test_packaging.py
git commit -m "build: collect modular extension packages"
```

---

### Task 13: 更新部署、存储和开发文档

**Files:**

- Modify: `README.md`
- Modify: `docs/mysql-application-storage.zh-CN.md`
- Modify: `docs/mysql-application-storage-progress.zh-CN.md`
- Modify: `docs/deployment.zh-CN.md`
- Modify: `docs/intranet-production-deployment.zh-CN.md`
- Modify: `docs/production-baseline-diff-audit-2026-07-24.zh-CN.md`
- Modify: `docs/production-release-file-checklist-2026-07-25.zh-CN.md`
- Modify: `src/auto_check/web/app.js`
- Create: `docs/module-development-guide.zh-CN.md`
- Create: `tests/module_system/test_documentation.py`

**Interfaces:**

- Consumes: 模块清单、目录、权限、迁移和测试协议
- Produces: 新模块开发者可以独立使用的接入指南

- [ ] **Step 1: 编写文档一致性失败测试**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_deployment_docs_include_module_schema_upgrade():
    for relative in [
        "README.md",
        "docs/mysql-application-storage.zh-CN.md",
        "docs/mysql-application-storage-progress.zh-CN.md",
        "docs/deployment.zh-CN.md",
        "docs/intranet-production-deployment.zh-CN.md",
        "docs/production-baseline-diff-audit-2026-07-24.zh-CN.md",
        "docs/production-release-file-checklist-2026-07-25.zh-CN.md",
    ]:
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert "012_module_system.sql" in content


def test_module_development_guide_defines_required_contracts():
    content = (ROOT / "docs/module-development-guide.zh-CN.md").read_text(encoding="utf-8")

    for fragment in [
        "manifest.json",
        "backend_entry",
        "api_prefix",
        "platform_api",
        "schema_version",
        "register_routes",
        "register_schema",
        "mount",
        "activate",
        "deactivate",
        "unmount",
        "-- module-statement-break",
        "python -m pytest tests/modules",
    ]:
        assert fragment in content
```

- [ ] **Step 2: 运行文档测试确认失败**

Run:

```powershell
python -m pytest tests/module_system/test_documentation.py -q
```

Expected: FAIL，部署文档和开发指南尚未更新。

- [ ] **Step 3: 更新文档**

文档必须明确：

- 应用数据库从 39 张表增加到 42 张表。
- `app_schema_version` 仍为 `1`。
- 生产升级必须先备份，再执行 `012_module_system.sql`。
- 模块业务表不加入全局 `EXPECTED_APP_SCHEMA`。
- 模块迁移文件发布后不可修改。
- 新模块只增加 `src/auto_check/modules/<module_id>/` 和对应测试。
- 平台内核修改必须单独评审。
- 模块 CSS、权限、API 和事件必须命名空间化。
- 模块是可信内置扩展，不是第三方插件沙箱。

`README.md` 详细记录模块化基础能力。`app.js` 当前版本更新日志只增加一条：

```html
<li>系统优化及BUG修复。</li>
```

如果当前版本已经存在完全相同条目，不重复添加。

- [ ] **Step 4: 运行文档和静态测试**

Run:

```powershell
python -m pytest tests/module_system/test_documentation.py tests/test_web_static.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交文档**

```powershell
git add README.md docs/mysql-application-storage.zh-CN.md docs/mysql-application-storage-progress.zh-CN.md docs/deployment.zh-CN.md docs/intranet-production-deployment.zh-CN.md docs/production-baseline-diff-audit-2026-07-24.zh-CN.md docs/production-release-file-checklist-2026-07-25.zh-CN.md docs/module-development-guide.zh-CN.md src/auto_check/web/app.js tests/module_system/test_documentation.py
git commit -m "docs: document modular extension workflow"
```

---

### Task 14: 全量验证和交付检查

**Files:**

- Verify: `src/auto_check/app/module_system/`
- Verify: `src/auto_check/web/module_host.js`
- Verify: `src/auto_check/web/module_host.css`
- Verify: `sql/app_storage/mysql/012_module_system.sql`
- Verify: `tests/module_system/`
- Verify: `README.md`
- Verify: `docs/module-development-guide.zh-CN.md`

**Interfaces:**

- Consumes: Tasks 1–13 全部产物
- Produces: 可供自定义报表模块使用的平台接口版本 1

- [ ] **Step 1: 运行模块系统测试**

由测试子代理或后台线程运行：

```powershell
python -m pytest tests/module_system -q
```

Expected: PASS。

- [ ] **Step 2: 运行相关回归测试**

```powershell
python -m pytest tests/test_app_database.py tests/test_server.py tests/test_security.py tests/test_web_static.py tests/test_user_interface_preferences.py tests/test_report_navigation_schema.py tests/test_sqlite_to_mysql_export.py -q
```

Expected: PASS。

- [ ] **Step 3: 运行仓库全量测试**

```powershell
python -m pytest -q
```

Expected: 全部 PASS，无 skipped 增长和 warning 激增。

- [ ] **Step 4: 检查 JavaScript、差异和模块边界**

```powershell
node --check src/auto_check/web/module_host.js
node --check src/auto_check/web/app.js
git diff --check
rg -n "report_demo|custom_reports" src/auto_check/app/server.py src/auto_check/web/app.js src/auto_check/web/index.html
```

Expected:

- 两个 Node.js 检查退出码为 0。
- `git diff --check` 无实际 whitespace error。
- 公共入口中不存在测试模块或自定义报表业务名称。

- [ ] **Step 5: 人工验收源码运行**

在已执行 `012_module_system.sql` 的测试应用库上启动源码：

```powershell
python -m auto_check
```

检查：

- 现有页面正常打开。
- 无模块时导航和现有页面不发生变化。
- 合法模块启用后动态显示导航。
- 模块页面进入、离开和刷新正常。
- 禁用模块后其他页面继续可用。
- 非管理员不能修改模块状态。
- 模块加载失败只显示模块错误。

Expected: 所有检查通过。

- [ ] **Step 6: 检查提交范围**

```powershell
git status --short
git log --oneline -12
```

确认没有纳入工作区中与本项目无关的用户文件。未经用户明确要求，不运行打包、不提交最终整合提交、不推送远端。

---

## 实施完成后的下一步

模块宿主通过 Task 14 验收后，另行创建自定义报表模块实施计划。该计划只能在以下目录增加业务实现：

```text
src/auto_check/modules/custom_reports/
tests/modules/custom_reports/
docs/custom-report-*.zh-CN.md
```

如果自定义报表开发仍需要修改 `server.py`、`app.js`、`styles.css`、`index.html` 或其他业务模块内部文件，应先判定为平台协议缺口，单独评审平台变更，不能把修改混入报表业务提交。
