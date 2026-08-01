(() => {
  function createModuleHost({
    documentRef = window.document,
    locationRef = window.location,
    windowRef = typeof window === "undefined" ? null : window,
    importModule = (url) => import(url),
    stylesheetTimeoutMs = 5000,
  } = {}) {
    const state = {
      platform: null,
      modules: new Map(),
      routes: new Map(),
      instances: new Map(),
      activeModuleId: "",
      activeRoute: "",
      initialized: false,
    };
    const failures = new Map();
    const styleElements = new Map();
    const eventListeners = new Map();
    const navigationListeners = new Map();
    let initializePromise = null;
    let lifecycleQueue = Promise.resolve();
    let lifecycleVersion = 0;
    let hashListener = null;

    function enqueue(operation) {
      const pending = lifecycleQueue.then(operation, operation);
      lifecycleQueue = pending.catch(() => undefined);
      return pending;
    }

    function pageHost() {
      return documentRef?.getElementById("modulePageHost") || null;
    }

    function moduleRoutes(module) {
      return Array.isArray(module.navigation) ? module.navigation : [];
    }

    function removeElement(element) {
      element?.remove?.();
    }

    function diagnostics() {
      const host = pageHost();
      if (!host) return null;
      let area = host.querySelector?.("[data-module-host-diagnostic]");
      if (!area) {
        area = documentRef.createElement("section");
        area.className = "module-host-diagnostics";
        area.dataset.moduleHostDiagnostic = "true";
        area.setAttribute("aria-live", "polite");
        host.appendChild(area);
      }
      return area;
    }

    function recordModuleIssue(moduleId, message) {
      const area = diagnostics();
      if (!area) return;
      const item = documentRef.createElement("p");
      item.className = "module-host-diagnostic";
      item.dataset.moduleHostIssue = moduleId;
      item.textContent = `模块 ${moduleId}：${message}`;
      area.appendChild(item);
    }

    function showModuleError(moduleId, message) {
      const host = pageHost();
      if (!host) return;
      hideModuleRoots();
      removeElement(host.querySelector?.("[data-module-host-error]"));
      const panel = documentRef.createElement("section");
      panel.className = "module-host-error";
      panel.dataset.moduleHostError = moduleId;
      panel.setAttribute("role", "alert");
      panel.textContent = `模块加载失败：${message}`;
      host.appendChild(panel);
      host.hidden = false;
      recordModuleIssue(moduleId, message);
    }

    function clearModuleError() {
      removeElement(pageHost()?.querySelector?.("[data-module-host-error]"));
    }

    function hideModuleRoots() {
      state.instances.forEach(({ root }) => {
        root.hidden = true;
      });
    }

    function setLegacyVisibility(hidden) {
      documentRef?.querySelectorAll?.(".page").forEach((page) => {
        page.hidden = hidden;
      });
      documentRef?.querySelectorAll?.(".nav-item[data-page], .top-nav-item[data-page]").forEach((item) => {
        item.classList?.remove("active");
        item.removeAttribute?.("aria-current");
      });
    }

    function setModuleNavigationActive(route) {
      ["moduleSideNavigation", "moduleTopNavigation"].forEach((id) => {
        const mount = documentRef?.getElementById(id);
        mount?.querySelectorAll?.("[data-module-route]").forEach((item) => {
          const active = item.dataset.moduleRoute === route;
          item.classList?.toggle("active", active);
          if (active) item.setAttribute?.("aria-current", "page");
          else item.removeAttribute?.("aria-current");
        });
      });
    }

    function setModulePageState(moduleId) {
      const root = documentRef?.documentElement;
      if (!root) return;
      root.dataset.page = `module-${moduleId}`;
    }

    function clearModulePageState() {
      const root = documentRef?.documentElement;
      if (root) delete root.dataset.page;
    }

    function updateHash(route) {
      const nextHash = `#${route}`;
      if (locationRef && locationRef.hash !== nextHash) locationRef.hash = nextHash;
    }

    function validatePlatform(platform) {
      return ["api", "user", "notify", "confirm", "legacyNavigate"].every(
        (name) => typeof platform?.[name] === "function",
      );
    }

    function validateInstance(instance) {
      return ["mount", "activate", "deactivate", "unmount"].every(
        (name) => typeof instance?.[name] === "function",
      );
    }

    function loadStyle(module) {
      if (!module.frontend_style || !documentRef?.head) return Promise.resolve(null);
      const link = documentRef.createElement("link");
      link.rel = "stylesheet";
      link.href = module.frontend_style;
      link.dataset.moduleStyle = module.id;
      styleElements.set(module.id, link);
      return new Promise((resolve, reject) => {
        let settled = false;
        const timeout = setTimeout(() => finish(new Error("模块样式加载超时")), stylesheetTimeoutMs);
        const cleanup = () => {
          clearTimeout(timeout);
          link.removeEventListener?.("load", onLoad);
          link.removeEventListener?.("error", onError);
        };
        const finish = (error) => {
          if (settled) return;
          settled = true;
          cleanup();
          if (error) {
            removeStyle(module.id);
            reject(error);
            return;
          }
          resolve(link);
        };
        const onLoad = () => finish(null);
        const onError = () => finish(new Error("模块样式加载失败"));
        link.addEventListener?.("load", onLoad);
        link.addEventListener?.("error", onError);
        try {
          documentRef.head.appendChild(link);
        } catch (error) {
          finish(error);
        }
      });
    }

    function removeStyle(moduleId) {
      removeElement(styleElements.get(moduleId));
      styleElements.delete(moduleId);
    }

    function moduleEventBus(moduleId) {
      const requireModuleEvent = (eventName) => {
        const event = String(eventName || "");
        if (!event.startsWith(`${moduleId}:`)) {
          throw new Error(`module events must use the ${moduleId}: namespace`);
        }
        return event;
      };
      return Object.freeze({
        emit(eventName, detail) {
          const event = requireModuleEvent(eventName);
          [...(eventListeners.get(event) || [])].forEach((listener) => {
            try {
              listener(detail);
            } catch (_) {
              recordModuleIssue(moduleId, "事件订阅处理失败");
            }
          });
        },
        on(eventName, listener) {
          const event = requireModuleEvent(eventName);
          if (typeof listener !== "function") throw new Error("module event listener must be a function");
          const listeners = eventListeners.get(event) || new Set();
          listeners.add(listener);
          eventListeners.set(event, listeners);
          return () => listeners.delete(listener);
        },
      });
    }

    async function invokeLifecycle(lifecycleState, phase, callback, route = "") {
      const previous = lifecycleState.frame;
      const frame = { phase, route, navigation: null };
      lifecycleState.frame = frame;
      try {
        return { value: await callback(), navigation: frame.navigation };
      } finally {
        lifecycleState.frame = previous;
      }
    }

    function scheduleLegacyNavigation(intent) {
      const currentQueue = lifecycleQueue;
      currentQueue
        .then(() => {
          if (!state.initialized || intent.version !== lifecycleVersion) return undefined;
          return state.platform?.legacyNavigate(intent.route);
        })
        .catch(() => recordModuleIssue("system", "传统页面导航失败"));
    }

    function createContext(module, root, lifecycleState) {
      const context = {
        root,
        api: state.platform.api,
        user: state.platform.user,
        notify: state.platform.notify,
        confirm: state.platform.confirm,
        navigate: async (route) => {
          const routeName = String(route || "");
          const frame = lifecycleState.frame;
          if (frame) {
            if (frame.phase === "mount" || frame.phase === "activate") {
              if (frame.phase === "activate" && frame.route === routeName) return true;
              lifecycleState.acceptNavigation = false;
              frame.navigation = { route: routeName, version: ++lifecycleVersion };
              return state.routes.has(routeName);
            }
            return false;
          }
          if (!lifecycleState.acceptNavigation || state.activeModuleId !== module.id) return false;
          if (await activate(routeName)) return true;
          await state.platform.legacyNavigate(routeName);
          return false;
        },
        events: moduleEventBus(module.id),
      };
      return Object.freeze(context);
    }

    function createRoot(module) {
      const host = pageHost();
      if (!host) throw new Error("module page host is unavailable");
      const root = documentRef.createElement("section");
      root.className = "auto-check-module";
      root.dataset.module = module.id;
      root.hidden = true;
      host.appendChild(root);
      return root;
    }

    function createNavigationItem(entry, className) {
      const button = documentRef.createElement("button");
      button.type = "button";
      button.className = className;
      button.dataset.moduleRoute = entry.route;
      button.dataset.moduleNavigation = entry.id;
      button.textContent = entry.label;
      return button;
    }

    function renderNavigation() {
      const side = documentRef?.getElementById("moduleSideNavigation");
      const top = documentRef?.getElementById("moduleTopNavigation");
      if (!side || !top) return;
      side.replaceChildren?.();
      top.replaceChildren?.();
      [...state.routes.entries()]
        .map(([route, moduleId]) => ({ route, module: state.modules.get(moduleId) }))
        .flatMap(({ route, module }) => moduleRoutes(module)
          .filter((entry) => entry.route === route)
          .map((entry) => ({ ...entry, module })))
        .sort((left, right) => Number(left.order || 0) - Number(right.order || 0))
        .forEach((entry) => {
          side.appendChild(createNavigationItem(entry, "nav-item module-nav-item"));
          top.appendChild(createNavigationItem(entry, "top-nav-item module-top-nav-item"));
        });
    }

    function bindNavigation() {
      ["moduleSideNavigation", "moduleTopNavigation"].forEach((id) => {
        const mount = documentRef?.getElementById(id);
        if (!mount || navigationListeners.has(mount)) return;
        mount.dataset.moduleHostBound = "true";
        const listener = (event) => {
          const target = event.target?.closest?.("[data-module-route]");
          if (!target || (mount.contains && !mount.contains(target))) return;
          event.preventDefault();
          activate(target.dataset.moduleRoute);
        };
        mount.addEventListener("click", listener);
        navigationListeners.set(mount, listener);
      });
    }

    function removeNavigationListeners() {
      navigationListeners.forEach((listener, mount) => {
        mount.removeEventListener?.("click", listener);
        delete mount.dataset.moduleHostBound;
      });
      navigationListeners.clear();
    }

    async function deactivateNow({ restoreLegacy = true } = {}) {
      const activeId = state.activeModuleId;
      const active = state.instances.get(activeId);
      if (active) {
        active.lifecycleState.acceptNavigation = false;
        try {
          const instance = active.instance;
          await invokeLifecycle(active.lifecycleState, "deactivate", () => instance.deactivate());
        } catch (_) {
          recordModuleIssue(activeId, "停用失败");
        }
      }
      hideModuleRoots();
      clearModuleError();
      const host = pageHost();
      if (host) host.hidden = true;
      state.activeModuleId = "";
      state.activeRoute = "";
      setModuleNavigationActive("");
      if (restoreLegacy) {
        clearModulePageState();
        setLegacyVisibility(false);
      }
    }

    async function activateNow(route, version, { syncHash = true } = {}, redirectTrail = []) {
      const routeName = String(route || "");
      const moduleId = state.routes.get(routeName);
      if (!moduleId) return false;
      if (redirectTrail.includes(routeName)) {
        failures.set(moduleId, "模块导航形成循环");
        showModuleError(moduleId, "模块导航形成循环");
        return true;
      }
      if (state.activeModuleId === moduleId && state.activeRoute === routeName && !pageHost()?.hidden) {
        const current = state.instances.get(moduleId);
        if (current) current.lifecycleState.acceptNavigation = true;
        if (syncHash) updateHash(routeName);
        return true;
      }
      if (state.activeModuleId) await deactivateNow({ restoreLegacy: false });
      const failed = failures.get(moduleId);
      if (failed) {
        setLegacyVisibility(true);
        setModulePageState(moduleId);
        setModuleNavigationActive(routeName);
        showModuleError(moduleId, failed);
        state.activeModuleId = moduleId;
        state.activeRoute = routeName;
        if (syncHash) updateHash(routeName);
        return true;
      }
      const record = state.instances.get(moduleId);
      if (!record) {
        showModuleError(moduleId, "模块未成功挂载");
        return true;
      }
      try {
        clearModuleError();
        setLegacyVisibility(true);
        hideModuleRoots();
        record.root.hidden = false;
        pageHost().hidden = false;
        setModulePageState(moduleId);
        setModuleNavigationActive(routeName);
        const instance = record.instance;
        const activation = await invokeLifecycle(
          record.lifecycleState,
          "activate",
          () => instance.activate(route),
          routeName,
        );
        const redirectedRoute = activation.navigation;
        if (redirectedRoute && redirectedRoute.route !== routeName) {
          try {
            await invokeLifecycle(
              record.lifecycleState,
              "deactivate",
              () => instance.deactivate(),
            );
          } catch (_) {
            recordModuleIssue(moduleId, "导航切换停用失败");
          }
          record.root.hidden = true;
          if (state.routes.has(redirectedRoute.route)) {
            return activateNow(
              redirectedRoute.route,
              redirectedRoute.version,
              { syncHash: true },
              [...redirectTrail, routeName],
            );
          }
          hideModuleRoots();
          const host = pageHost();
          if (host) host.hidden = true;
          state.activeModuleId = "";
          state.activeRoute = "";
          setModuleNavigationActive("");
          clearModulePageState();
          setLegacyVisibility(false);
          scheduleLegacyNavigation(redirectedRoute);
          return true;
        }
        if (version !== lifecycleVersion) {
          try {
            await invokeLifecycle(
              record.lifecycleState,
              "deactivate",
              () => instance.deactivate(),
            );
          } catch (_) {
            recordModuleIssue(moduleId, "过期激活停用失败");
          }
          record.root.hidden = true;
          return true;
        }
        state.activeModuleId = moduleId;
        state.activeRoute = routeName;
        record.lifecycleState.acceptNavigation = true;
        if (syncHash) updateHash(routeName);
      } catch (_) {
        if (version !== lifecycleVersion) {
          record.root.hidden = true;
          return true;
        }
        failures.set(moduleId, "模块运行时发生异常");
        showModuleError(moduleId, "模块运行时发生异常");
        state.activeModuleId = moduleId;
        state.activeRoute = routeName;
        if (syncHash) updateHash(routeName);
      }
      return true;
    }

    async function activate(route, options) {
      const version = ++lifecycleVersion;
      const active = state.instances.get(state.activeModuleId);
      if (active) active.lifecycleState.acceptNavigation = false;
      return enqueue(() => activateNow(route, version, options));
    }

    async function deactivate() {
      lifecycleVersion += 1;
      const active = state.instances.get(state.activeModuleId);
      if (active) active.lifecycleState.acceptNavigation = false;
      return enqueue(() => deactivateNow());
    }

    function legacyRouteIsAlreadyActive(route) {
      const root = documentRef?.documentElement;
      const host = pageHost();
      return !state.activeModuleId
        && host?.hidden !== false
        && String(root?.dataset?.page || "") === route;
    }

    async function handleHashChange() {
      const route = String(locationRef?.hash || "").replace(/^#/, "");
      if (!state.routes.has(route) && legacyRouteIsAlreadyActive(route)) return;
      if (await activate(route, { syncHash: false })) return;
      await deactivate();
      await state.platform?.legacyNavigate(route || "report-navigation");
    }

    function bindHashChange() {
      if (!windowRef?.addEventListener || hashListener) return;
      hashListener = () => {
        handleHashChange().catch(() => {
          recordModuleIssue("system", "地址导航失败");
        });
      };
      windowRef.addEventListener("hashchange", hashListener);
    }

    function removeHashChange() {
      if (!hashListener) return;
      windowRef?.removeEventListener?.("hashchange", hashListener);
      hashListener = null;
    }

    async function initializeNow() {
      let payload;
      let mountedNavigation = null;
      try {
        payload = await state.platform.api("/api/system/modules");
      } catch (_) {
        recordModuleIssue("system", "模块清单加载失败");
        return false;
      }
      const modules = Array.isArray(payload?.modules) ? payload.modules : [];
      modules.forEach((module) => {
        if (!module?.id || state.modules.has(module.id)) return;
        state.modules.set(module.id, module);
        moduleRoutes(module).forEach((entry) => {
          if (!entry?.route) return;
          if (state.routes.has(entry.route)) {
            recordModuleIssue(module.id, `路由 ${entry.route} 已由 ${state.routes.get(entry.route)} 注册`);
            return;
          }
          state.routes.set(entry.route, module.id);
        });
      });
      for (const module of state.modules.values()) {
        let instance = null;
        let root = null;
        const lifecycleState = { frame: null, acceptNavigation: false };
        try {
          await loadStyle(module);
          const namespace = await importModule(module.frontend_entry);
          instance = namespace?.default || namespace;
          if (!validateInstance(instance)) throw new Error("模块生命周期接口不完整");
          root = createRoot(module);
          const context = createContext(module, root, lifecycleState);
          const mounted = await invokeLifecycle(
            lifecycleState,
            "mount",
            () => instance.mount(context),
          );
          if (mounted.navigation) mountedNavigation = mounted.navigation;
          state.instances.set(module.id, { instance, root, context, lifecycleState });
        } catch (_) {
          failures.set(module.id, "模块资源未能加载");
          if (instance) {
            try {
              await invokeLifecycle(lifecycleState, "unmount", () => instance.unmount());
            } catch (_) {
              recordModuleIssue(module.id, "失败模块卸载失败");
            }
          }
          removeElement(root);
          removeStyle(module.id);
          recordModuleIssue(module.id, "资源加载或挂载失败");
        }
      }
      renderNavigation();
      bindNavigation();
      bindHashChange();
      state.initialized = true;
      const route = mountedNavigation?.route || String(locationRef?.hash || "").replace(/^#/, "");
      const version = mountedNavigation?.version || ++lifecycleVersion;
      if (await activateNow(route, version)) return true;
      if (mountedNavigation) {
        scheduleLegacyNavigation(mountedNavigation);
        return true;
      }
      return false;
    }

    async function initialize(platform) {
      if (!validatePlatform(platform)) {
        recordModuleIssue("system", "平台接口不完整");
        return false;
      }
      if (state.initialized) return activate(String(locationRef?.hash || "").replace(/^#/, ""));
      if (initializePromise) return initializePromise;
      state.platform = platform;
      initializePromise = enqueue(initializeNow).finally(() => {
        initializePromise = null;
      });
      return initializePromise;
    }

    async function unmountNow() {
      await deactivateNow();
      for (const [moduleId, record] of state.instances) {
        try {
          const instance = record.instance;
          await invokeLifecycle(record.lifecycleState, "unmount", () => instance.unmount());
        } catch (_) {
          recordModuleIssue(moduleId, "卸载失败");
        }
        removeElement(record.root);
        removeStyle(moduleId);
      }
      state.modules.clear();
      state.routes.clear();
      state.instances.clear();
      failures.clear();
      styleElements.forEach((link) => removeElement(link));
      styleElements.clear();
      eventListeners.clear();
      removeNavigationListeners();
      pageHost()?.replaceChildren?.();
      documentRef?.getElementById("moduleSideNavigation")?.replaceChildren?.();
      documentRef?.getElementById("moduleTopNavigation")?.replaceChildren?.();
      removeHashChange();
      state.activeModuleId = "";
      state.activeRoute = "";
      state.initialized = false;
      state.platform = null;
    }

    async function unmount() {
      lifecycleVersion += 1;
      state.instances.forEach((record) => {
        record.lifecycleState.acceptNavigation = false;
      });
      return enqueue(unmountNow);
    }

    async function reload() {
      const platform = state.platform;
      await unmount();
      return initialize(platform);
    }

    return Object.freeze({ initialize, activate, deactivate, reload, unmount });
  }

  if (typeof window !== "undefined") window.AutoCheckModuleHost = createModuleHost();
  if (typeof module !== "undefined" && module.exports) module.exports = { createModuleHost };
})();
