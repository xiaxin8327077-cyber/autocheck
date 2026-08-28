/* 系统通知中心 — 独立状态机、API、SSE、降级轮询、弹窗和交互 */
(function () {
  "use strict";

  const state = {
    started: false,
    userId: "",
    csrfToken: "",
    filter: "unread",
    items: [],
    unreadCount: 0,
    nextCursor: null,
    loading: false,
    eventSource: null,
    reconnectFailures: 0,
    pollTimer: null,
    liveToastIds: new Set(),
    visibleToasts: [],
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  function getBell() {
    return document.querySelector("[data-notification-bell]");
  }

  function getBadge() {
    return document.querySelector("[data-notification-badge]");
  }

  function getPanel() {
    return document.querySelector("[data-notification-panel]");
  }

  function getList() {
    return document.querySelector("[data-notification-list]");
  }

  function getEmpty() {
    return document.querySelector("[data-notification-empty]");
  }

  function getToastRegion() {
    return document.querySelector("[data-notification-toast-region]");
  }

  function getError() {
    return document.querySelector("[data-notification-error]");
  }

  function getUnreadText() {
    return document.querySelector("[data-notification-unread-text]");
  }

  function renderBadge(count) {
    const badge = getBadge();
    const bell = getBell();
    if (!badge || !bell) return;
    const normalized = Math.max(0, Number(count) || 0);
    badge.hidden = normalized === 0;
    badge.textContent = count > 99 ? "99+" : String(count);
    bell.setAttribute("aria-label", normalized ? `通知，${normalized}条未读` : "通知，无未读");
  }

  async function apiRequest(url, options) {
    const opts = Object.assign({ credentials: "same-origin" }, options || {});
    if (opts.body && typeof opts.body !== "string") {
      opts.body = JSON.stringify(opts.body);
      opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    }
    const response = await fetch(url, opts);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "请求失败");
    }
    return data;
  }

  async function loadFirstPage() {
    if (state.loading) return;
    state.loading = true;
    try {
      const data = await apiRequest("/api/notifications?filter=" + state.filter + "&limit=20");
      state.items = data.items || [];
      state.unreadCount = data.unread_count || 0;
      state.nextCursor = data.next_cursor || null;
      renderList();
      renderBadge(state.unreadCount);
    } catch (e) {
      showError();
    } finally {
      state.loading = false;
    }
  }

  async function loadMore() {
    if (state.loading || !state.nextCursor) return;
    state.loading = true;
    try {
      const data = await apiRequest("/api/notifications?filter=" + state.filter + "&limit=20&cursor=" + encodeURIComponent(state.nextCursor));
      const newItems = data.items || [];
      state.items = state.items.concat(newItems);
      state.unreadCount = data.unread_count || state.unreadCount;
      state.nextCursor = data.next_cursor || null;
      renderList();
      renderBadge(state.unreadCount);
    } catch (e) {
      // ignore load more errors
    } finally {
      state.loading = false;
    }
  }

  function getLoadMore() {
    return document.querySelector("[data-notification-load-more]");
  }

  function renderList() {
    const list = getList();
    const empty = getEmpty();
    const loadMore = getLoadMore();
    if (!list) return;
    list.innerHTML = "";
    if (state.items.length === 0) {
      if (empty) empty.hidden = false;
      if (loadMore) loadMore.hidden = true;
      return;
    }
    if (empty) empty.hidden = true;
    if (loadMore) loadMore.hidden = true;
    state.items.forEach((item) => {
      const el = document.createElement("div");
      el.className = "notification-item" + (item.is_read ? "" : " notification-item--unread");
      el.setAttribute("data-notification-id", item.id);
      const title = document.createElement("div");
      title.className = "notification-item-title";
      if (!item.is_read) {
        const dot = document.createElement("span");
        dot.className = "notification-unread-dot";
        const label = document.createElement("span");
        label.className = "notification-unread-label";
        label.textContent = "未读";
        title.appendChild(dot);
        title.appendChild(label);
        title.appendChild(document.createTextNode(" "));
      }
      title.appendChild(document.createTextNode(item.title));
      const period = item.action && item.action.query && item.action.query.period;
      if (period) {
        const tag = document.createElement("span");
        tag.className = "notification-period-tag";
        tag.textContent = period;
        title.appendChild(document.createTextNode(" "));
        title.appendChild(tag);
      }
      const content = document.createElement("div");
      content.className = "notification-item-content";
      content.textContent = item.content;
      const time = document.createElement("div");
      time.className = "notification-item-time";
      time.textContent = formatTime(item.created_at);
      if (item.is_read && item.read_at) {
        const sep = document.createElement("span");
        sep.className = "notification-time-sep";
        sep.textContent = " · ";
        const readLabel = document.createElement("span");
        readLabel.className = "notification-read-label";
        readLabel.textContent = "已于" + formatTime(item.read_at) + "阅读";
        time.appendChild(sep);
        time.appendChild(readLabel);
      }
      const meta = document.createElement("div");
      meta.className = "notification-item-meta";
      el.appendChild(title);
      el.appendChild(content);
      el.appendChild(time);
      el.appendChild(meta);
      el.addEventListener("click", () => handleViewAction(item));
      list.appendChild(el);
    });
  }

  async function handleViewAction(item) {
    try {
      const data = await apiRequest(`/api/notifications/${item.id}/read`, {
        method: "POST",
        headers: { "X-CSRF-Token": state.csrfToken },
      });
      state.unreadCount = data.unread_count || 0;
      renderBadge(state.unreadCount);
      const idx = state.items.findIndex((i) => i.id === item.id);
      if (idx >= 0) {
        state.items[idx].is_read = true;
        state.items[idx].read_at = data.notification.read_at;
      }
      renderList();
    } catch (e) {
      // Still allow navigation even if mark read fails
    }
    if (item.action && item.action.type === "navigate" && item.action.route) {
      if (typeof window.handleReportNavTodoAction === "function") {
        window.handleReportNavTodoAction(item.action.route, item.action.query);
      }
    }
  }


  function showError() {
    const err = getError();
    if (err) err.hidden = false;
  }

  function hideError() {
    const err = getError();
    if (err) err.hidden = true;
  }

  function openPanel() {
    const panel = getPanel();
    if (!panel) return;
    panel.hidden = false;
    const bell = getBell();
    if (bell) bell.setAttribute("aria-expanded", "true");
    loadFirstPage();
  }

  function closePanel() {
    const panel = getPanel();
    if (!panel) return;
    panel.hidden = true;
    const bell = getBell();
    if (bell) bell.setAttribute("aria-expanded", "false");
  }

  function togglePanel() {
    const panel = getPanel();
    if (!panel) return;
    if (panel.hidden) {
      openPanel();
    } else {
      closePanel();
    }
  }

  function showLiveToast(event) {
    if (!event.notification) return;
    const id = event.notification.id;
    if (state.liveToastIds.has(id)) return;
    state.liveToastIds.add(id);
    const region = getToastRegion();
    if (!region) return;
    const toast = document.createElement("div");
    toast.className = "notification-toast";
    toast.setAttribute("role", "alert");
    const title = document.createElement("div");
    title.className = "notification-toast-title";
    title.textContent = event.notification.title;
    const content = document.createElement("div");
    content.className = "notification-toast-content";
    content.textContent = event.notification.content;
    const actions = document.createElement("div");
    actions.className = "notification-toast-actions";
    const viewBtn = document.createElement("button");
    viewBtn.type = "button";
    viewBtn.className = "notification-toast-view";
    viewBtn.textContent = "查看";
    viewBtn.addEventListener("click", () => {
      handleViewAction(event.notification);
      removeToast(toast);
    });
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "notification-toast-close";
    closeBtn.textContent = "×";
    closeBtn.addEventListener("click", () => removeToast(toast));
    actions.appendChild(viewBtn);
    actions.appendChild(closeBtn);
    toast.appendChild(title);
    toast.appendChild(content);
    toast.appendChild(actions);
    if (state.visibleToasts.length >= 3) {
      const old = state.visibleToasts.shift();
      if (old && old.parentNode) old.parentNode.removeChild(old);
    }
    state.visibleToasts.push(toast);
    region.appendChild(toast);
    const timer = setTimeout(() => removeToast(toast), 6000);
    toast._timer = timer;
  }

  function removeToast(toast) {
    if (toast._timer) clearTimeout(toast._timer);
    const idx = state.visibleToasts.indexOf(toast);
    if (idx >= 0) state.visibleToasts.splice(idx, 1);
    if (toast.parentNode) toast.parentNode.removeChild(toast);
  }

  function startEventSource() {
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
    const es = new EventSource("/api/notifications/stream");
    state.eventSource = es;
    es.addEventListener("notification", (e) => {
      try {
        const data = JSON.parse(e.data);
        state.unreadCount = data.unread_count || state.unreadCount;
        renderBadge(state.unreadCount);
        if (data.notification) {
          const exists = state.items.find((i) => i.id === data.notification.id);
          if (!exists) {
            state.items.unshift(data.notification);
            renderList();
          }
          showLiveToast({ notification: data.notification, unread_count: data.unread_count });
        }
      } catch (_) {}
    });
    es.onopen = () => {
      state.reconnectFailures = 0;
      clearPollingTimer();
      loadFirstPage();
    };
    es.onerror = () => {
      state.reconnectFailures++;
      if (state.reconnectFailures >= 3) {
        es.close();
        startPolling();
      }
    };
  }

  function closeEventSource() {
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
  }

  function startPolling() {
    if (state.pollTimer) return;
    state.pollTimer = setInterval(() => {
      loadFirstPage();
    }, 60000);
  }

  function clearPollingTimer() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  async function clearAll() {
    try {
      await apiRequest("/api/notifications", {
        method: "DELETE",
        headers: { "X-CSRF-Token": state.csrfToken },
      });
      state.items = [];
      state.unreadCount = 0;
      state.nextCursor = null;
      renderBadge(0);
      renderList();
    } catch (e) {
      // ignore
    }
  }

  async function markAllRead() {
    try {
      const data = await apiRequest("/api/notifications/read-all", {
        method: "POST",
        headers: { "X-CSRF-Token": state.csrfToken },
      });
      state.unreadCount = 0;
      state.items.forEach((item) => { item.is_read = true; });
      renderBadge(0);
      renderList();
    } catch (e) {
      // ignore
    }
  }

  function handleFilterChange(filter) {
    state.filter = filter;
    state.nextCursor = null;
    state.items = [];
    document.querySelectorAll("[data-notification-filter]").forEach((btn) => {
      btn.setAttribute("aria-selected", btn.getAttribute("data-notification-filter") === filter ? "true" : "false");
    });
    loadFirstPage();
  }

  function bindEvents() {
    const bell = getBell();
    if (bell) {
      bell.addEventListener("click", (e) => {
        e.preventDefault();
        togglePanel();
      });
    }
    document.addEventListener("click", (e) => {
      const panel = getPanel();
      const bell = getBell();
      if (!panel || panel.hidden) return;
      if (panel.contains(e.target)) return;
      if (bell && bell.contains(e.target)) return;
      closePanel();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closePanel();
    });
    const clearBtn = document.querySelector("[data-notification-clear]");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => clearAll());
    }
    const readAllBtn = document.querySelector("[data-notification-read-all]");
    if (readAllBtn) {
      readAllBtn.addEventListener("click", () => markAllRead());
    }
    const retryBtn = document.querySelector("[data-notification-retry]");
    if (retryBtn) {
      retryBtn.addEventListener("click", () => {
        hideError();
        loadFirstPage();
      });
    }
    const loadMoreBtn = getLoadMore();
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener("click", () => loadMore());
    }
    const list = getList();
    if (list) {
      list.addEventListener("scroll", () => {
        if (list.scrollTop + list.clientHeight >= list.scrollHeight - 40) {
          loadMore();
        }
      });
    }
    const filterBtns = document.querySelectorAll("[data-notification-filter]");
    filterBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        handleFilterChange(btn.getAttribute("data-notification-filter"));
      });
    });
  }

  const start = async ({ user, csrfToken, api, handleAction, notify }) => {
    if (state.started) return;
    state.started = true;
    state.userId = user.id || "";
    state.csrfToken = csrfToken;
    bindEvents();
    startEventSource();
  };

  const stop = function () {
    if (!state.started) return;
    state.started = false;
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
    state.visibleToasts.forEach((t) => { if (t._timer) clearTimeout(t._timer); });
    state.visibleToasts = [];
    state.liveToastIds.clear();
    const region = getToastRegion();
    if (region) region.innerHTML = "";
    closePanel();
  };

  window.AutoCheckNotificationCenter = Object.freeze({ start, stop });
})();
