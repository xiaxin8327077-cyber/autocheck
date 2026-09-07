/* 登录超时原账号重新认证状态机与全屏遮罩。
 *
 * 平台能力：会话过期后不离开当前页面，固定原账号只输入密码重新认证，
 * 成功后由调用方（主应用）自动重试一次被前置鉴权拒绝的请求。
 * 设计：docs/superpowers/specs/2026-09-04-session-expiry-reauthentication-design.md
 *
 * 状态机：idle | reauthenticating | exitPending | discarding | terminal
 * - terminal 为终止态：禁止任何新的登录恢复/注销流程，迟到回调一律失效。
 * - exitPending 为受控退出等待态：认证/应用会话在途时点击退出不立即导航，
 *   等待认证结果确定；未建立会话直接退出，已建立会话转 discarding 注销，
 *   注销成功后才完成退出，失败保持阻塞并提供“重试退出”。
 * - discarding 期间 recover() 阻塞在单例 discardPromise 上，注销完成统一取消。
 * - 认证尝试带生命周期令牌（attempt），退出/销毁/转注销后旧回调失效；
 *   迟到但已成功建立的会话会被安全注销，而不是被忽略或应用。
 * - destroy() 返回清理 Promise：认证在途期间建立会话的注销失败必须反映在
 *   清理结果上（reject），不得静默吞掉；无在途会话时正常完成。
 *
 * 本脚本只管理状态机与遮罩交互，不包含任何业务页面逻辑，也不保存密码。
 */
(function (globalScope) {
  "use strict";

  class AuthRecoveryCancelledError extends Error {
    constructor(message = "authentication recovery cancelled") {
      super(message);
      this.name = "AuthRecoveryCancelledError";
    }
  }

  const OVERLAY_ID = "authRecoveryOverlay";
  const USERNAME_ID = "authRecoveryUsername";
  const PASSWORD_ID = "authRecoveryPassword";
  const EXIT_ID = "authRecoveryExit";
  const SUBMIT_ID = "authRecoverySubmit";
  const TITLE_ID = "authRecoveryTitle";
  const ERROR_ID = "authRecoveryError";
  const EXIT_LABEL = "退出系统";
  const RETRY_EXIT_LABEL = "重试退出";
  const SUBMIT_LABEL = "重新登录";

  function createAuthRecovery(options) {
    const doc =
      options.documentRef ||
      (typeof document !== "undefined" ? document : null);

    let recoveryPromise = null;
    let resolveRecovery = null;
    let rejectRecovery = null;
    let originalUser = null;
    let state = "idle"; // idle | reauthenticating | exitPending | discarding | terminal
    let discardPayload = null;
    let discardPromise = null;
    let rejectDiscard = null;
    let discardInFlight = false;
    let submitting = false;
    // 认证/应用会话是否在途：退出点击不得把“请求可能被中断”当作“会话未建立”。
    let authInFlight = false;
    let applyingSession = false;
    // 受控退出（exitPending）：等待在途认证结果后再决定注销或退出。
    let pendingExit = false;
    let exitDiscardPayload = null;
    // destroy 清理结果可观察：认证在途建立会话的注销失败必须 reject 清理 Promise。
    let pendingAuthAttempt = -1;
    let lateDiscardError = null; // 跨 resetState 保留，由 destroy 消费
    const terminalDiscardTasks = new Set();
    // 在途认证请求的 Promise，用于 destroy 等待实际 settle 时机。
    let authSettlement = null;
    let attempt = 0;
    let els = null;

    let eventsBound = false;

    function cancelledError() {
      const error = new AuthRecoveryCancelledError();
      // 供 Promise 等待者识别的标记；不改变错误类型与语义。
      error._isRecoveryCancelled = true;
      return error;
    }

    function rejectedCancelled() {
      const rejected = Promise.reject(cancelledError());
      rejected.catch(() => {});
      return rejected;
    }

    function buildOverlay() {
      const overlay = doc.createElement("div");
      overlay.id = OVERLAY_ID;
      overlay.className = "auth-recovery-overlay";
      overlay.hidden = true;

      const section = doc.createElement("section");
      section.setAttribute("role", "dialog");
      section.setAttribute("aria-modal", "true");
      section.setAttribute("aria-labelledby", TITLE_ID);
      section.className = "auth-recovery-card";

      const title = doc.createElement("h2");
      title.id = TITLE_ID;
      title.className = "auth-recovery-title";
      title.textContent = "登录状态已过期";

      const description = doc.createElement("p");
      description.className = "auth-recovery-description";
      description.textContent =
        "为保护当前操作，请重新验证身份。验证成功后将继续当前操作。";

      const accountRow = doc.createElement("div");
      accountRow.className = "auth-recovery-account";
      const accountLabel = doc.createElement("span");
      accountLabel.className = "auth-recovery-account-label";
      accountLabel.textContent = "账号";
      const username = doc.createElement("span");
      username.id = USERNAME_ID;
      username.className = "auth-recovery-username";
      accountRow.appendChild(accountLabel);
      accountRow.appendChild(username);

      const password = doc.createElement("input");
      password.id = PASSWORD_ID;
      password.type = "password";
      password.className = "auth-recovery-password";
      password.setAttribute("autocomplete", "current-password");
      password.setAttribute("placeholder", "请输入密码");

      const error = doc.createElement("p");
      error.id = ERROR_ID;
      error.className = "auth-recovery-error";
      error.setAttribute("role", "alert");
      error.hidden = true;

      const actions = doc.createElement("div");
      actions.className = "auth-recovery-actions";
      const exitButton = doc.createElement("button");
      exitButton.id = EXIT_ID;
      exitButton.type = "button";
      exitButton.className = "auth-recovery-exit";
      exitButton.textContent = EXIT_LABEL;
      const submitButton = doc.createElement("button");
      submitButton.id = SUBMIT_ID;
      submitButton.type = "submit";
      submitButton.className = "auth-recovery-submit";
      submitButton.textContent = SUBMIT_LABEL;
      actions.appendChild(exitButton);
      actions.appendChild(submitButton);

      section.appendChild(title);
      section.appendChild(description);
      section.appendChild(accountRow);
      section.appendChild(password);
      section.appendChild(error);
      section.appendChild(actions);
      overlay.appendChild(section);
      return overlay;
    }

    function onPasswordKeydown(event) {
      if (event && event.key === "Enter") {
        if (event.preventDefault) event.preventDefault();
        onSubmit(event);
      }
    }

    function onOverlayClick(event) {
      // Esc 与背景点击不关闭遮罩：显式拦截但不执行任何关闭动作。
      if (event && event.preventDefault) event.preventDefault();
    }

    function unbindEvents() {
      const elements = els;
      if (elements) {
        if (elements.exit && elements.exit.removeEventListener) {
          elements.exit.removeEventListener("click", onExit);
        }
        if (elements.submit && elements.submit.removeEventListener) {
          elements.submit.removeEventListener("click", onSubmit);
        }
        if (elements.password && elements.password.removeEventListener) {
          elements.password.removeEventListener("keydown", onPasswordKeydown);
        }
        if (elements.overlay && elements.overlay.removeEventListener) {
          elements.overlay.removeEventListener("click", onOverlayClick);
        }
      }
      eventsBound = false;
    }

    function ensureOverlay() {
      if (els) return els;
      if (!doc || !doc.getElementById) return null;
      let overlay = doc.getElementById(OVERLAY_ID);
      if (!overlay && doc.createElement && doc.body) {
        overlay = buildOverlay();
        doc.body.appendChild(overlay);
      }
      if (!overlay) return null;
      els = {
        overlay,
        username: doc.getElementById(USERNAME_ID),
        password: doc.getElementById(PASSWORD_ID),
        exit: doc.getElementById(EXIT_ID),
        submit: doc.getElementById(SUBMIT_ID),
        error: doc.getElementById(ERROR_ID),
      };
      if (!eventsBound && state !== "terminal") {
        eventsBound = true;
        if (els.exit && els.exit.addEventListener) els.exit.addEventListener("click", onExit);
        if (els.submit && els.submit.addEventListener) els.submit.addEventListener("click", onSubmit);
        if (els.password && els.password.addEventListener) {
          els.password.addEventListener("keydown", onPasswordKeydown);
        }
        if (overlay.addEventListener) overlay.addEventListener("click", onOverlayClick);
      }
      return els;
    }

    function setMessage(text) {
      const elements = ensureOverlay();
      if (!elements || !elements.error) return;
      if (text) {
        elements.error.textContent = text;
        elements.error.hidden = false;
      } else {
        elements.error.textContent = "";
        elements.error.hidden = true;
      }
    }

    function setAppInert(inert) {
      try {
        const body = doc && doc.body;
        if (!body || !body.children) return;
        const elements = els;
        for (const child of body.children) {
          if (elements && child === elements.overlay) continue;
          if (inert) {
            if (child.setAttribute) child.setAttribute("inert", "");
            if (child.setAttribute) child.setAttribute("aria-hidden", "true");
          } else {
            if (child.removeAttribute) child.removeAttribute("inert");
            if (child.removeAttribute) child.removeAttribute("aria-hidden");
          }
        }
      } catch (_error) {
        // inert 仅为可访问性增强，失败不影响恢复流程。
      }
    }

    function openOverlayReauthenticating() {
      if (state === "terminal") return;
      const elements = ensureOverlay();
      if (!elements) return;
      state = "reauthenticating";
      elements.username.textContent = originalUser ? String(originalUser.username || "") : "";
      elements.password.value = "";
      elements.password.disabled = false;
      elements.submit.disabled = false;
      elements.exit.disabled = false;
      elements.exit.textContent = EXIT_LABEL;
      setMessage("");
      elements.overlay.hidden = false;
      setAppInert(true);
      if (elements.password.focus) elements.password.focus();
    }

    function openOverlayDiscarding() {
      if (state === "terminal") return;
      const elements = ensureOverlay();
      if (!elements) return;
      state = "discarding";
      elements.username.textContent = originalUser ? String(originalUser.username || "") : "";
      elements.password.value = "";
      elements.password.disabled = true;
      elements.submit.disabled = true;
      elements.exit.disabled = false;
      elements.exit.textContent = RETRY_EXIT_LABEL;
      setMessage("");
      elements.overlay.hidden = false;
      setAppInert(true);
    }

    // 受控退出等待态：认证结果未确定前不导航，遮罩保持不透明阻塞。
    function openOverlayWaitingExit() {
      if (state === "terminal") return;
      const elements = ensureOverlay();
      if (!elements) return;
      state = "exitPending";
      elements.username.textContent = originalUser ? String(originalUser.username || "") : "";
      elements.password.value = "";
      elements.password.disabled = true;
      elements.submit.disabled = true;
      elements.exit.disabled = true;
      elements.exit.textContent = EXIT_LABEL;
      setMessage("");
      elements.overlay.hidden = false;
      setAppInert(true);
    }

    function closeOverlay() {
      const elements = els;
      if (elements && elements.overlay) {
        elements.overlay.hidden = true;
        if (elements.password) elements.password.value = "";
      }
      setAppInert(false);
    }

    function captureOriginalUser() {
      try {
        const user = options.getCurrentUser ? options.getCurrentUser() : null;
        originalUser = Object.freeze(Object.assign({}, user || {}));
      } catch (_error) {
        originalUser = Object.freeze({});
      }
      return originalUser;
    }

    function resetState(nextState = "idle") {
      recoveryPromise = null;
      resolveRecovery = null;
      rejectRecovery = null;
      discardPayload = null;
      discardPromise = null;
      rejectDiscard = null;
      discardInFlight = false;
      submitting = false;
      authInFlight = false;
      applyingSession = false;
      pendingExit = false;
      exitDiscardPayload = null;
      pendingAuthAttempt = -1;
      authSettlement = null;
      state = nextState;
    }

    function recover() {
      // 终止态：禁止新的恢复，立即取消。
      if (state === "terminal") return rejectedCancelled();
      if (recoveryPromise) return recoveryPromise;
      // discarding：等待者阻塞在单例注销 Promise 上，注销完成时统一取消。
      if (state === "discarding") {
        if (discardPromise) return discardPromise;
        return rejectedCancelled();
      }
      captureOriginalUser();
      recoveryPromise = new Promise((resolve, reject) => {
        resolveRecovery = resolve;
        rejectRecovery = reject;
      });
      // 避免未捕获 rejection 警告：调用方都会 await 该 Promise。
      recoveryPromise.catch(() => {});
      openOverlayReauthenticating();
      return recoveryPromise;
    }

    function identityMatches(payload) {
      const user = payload && payload.user;
      if (!user || !originalUser) return false;
      if (String(user.id) !== String(originalUser.id)) return false;
      if (String(user.username) !== String(originalUser.username)) return false;
      if (!payload.csrf_token) return false;
      return true;
    }

    // 迟到但已成功建立的会话必须安全注销，不能仅忽略。
    function discardLateSession(payload) {
      const usable = payload && payload.csrf_token && payload.user;
      if (!usable) return;
      if (state === "discarding") {
        discardPayload = payload;
        if (!discardInFlight) attemptDiscard();
        return;
      }
      // 已终止（例如 destroy 之后）：无法再阻塞页面，但注销结果必须可观察——
      // 失败记录进清理链，由 destroy() 返回的清理 Promise 反映，不得静默吞掉。
      const task = Promise.resolve()
        .then(() => (options.discardSession ? options.discardSession(payload) : undefined))
        .catch((error) => {
          if (!lateDiscardError) {
            lateDiscardError = error instanceof Error ? error : new Error(String(error));
          }
        });
      terminalDiscardTasks.add(task);
      task.then(() => terminalDiscardTasks.delete(task));
    }

    function completeRecovery(myAttempt, payload) {
      if (myAttempt !== attempt || state !== "reauthenticating") {
        discardLateSession(payload);
        return;
      }
      const resolve = resolveRecovery;
      closeOverlay();
      resetState();
      if (resolve) resolve();
    }

    function settleCancelled() {
      if (state === "terminal") return;
      attempt += 1;
      const reject = rejectRecovery;
      const discardReject = rejectDiscard;
      closeOverlay();
      resetState("terminal");
      try {
        if (options.exitSession) options.exitSession();
      } catch (_error) {
        // 退出回调失败不阻止状态清理。
      }
      const error = cancelledError();
      if (reject) reject(error);
      if (discardReject) discardReject(error);
    }

    function friendlyMessage(error) {
      const message = error && error.message ? String(error.message) : "";
      if (message && message !== "authentication recovery cancelled") return message;
      return "账号或密码验证失败";
    }

    // 受控退出入口：先让当前认证尝试失效并进入等待态，不立即导航；
    // 认证结果确定后再收口：未建立会话直接退出，已建立会话转注销流程。
    function beginControlledExit() {
      if (state !== "reauthenticating" || pendingExit) return;
      pendingExit = true;
      attempt += 1;
      if (authInFlight || applyingSession) {
        openOverlayWaitingExit();
        return;
      }
      if (exitDiscardPayload) {
        const payload = exitDiscardPayload;
        exitDiscardPayload = null;
        submitting = false;
        startDiscard(payload);
      }
      // 其余情况（认证已结算并成功应用、或结果在退出前已丢失）：
      // 等待该路径的既有收口逻辑释放等待者，不在此强行导航。
    }

    // 受控退出收口：payload 携带已建立会话的凭据则注销，否则直接完成退出。
    function routePendingExitResult(payload) {
      if (!pendingExit) return;
      if (payload && payload.csrf_token && payload.user) {
        submitting = false;
        startDiscard(payload);
        return;
      }
      submitting = false;
      settleCancelled();
    }

    function handleAuthSuccess(payload, myAttempt) {
      if (myAttempt !== attempt || state !== "reauthenticating") {
        // 受控退出等待中的本次在途结果：转由状态机管理，不得 fire-and-forget。
        if (pendingExit && state === "exitPending" && myAttempt === pendingAuthAttempt) {
          pendingAuthAttempt = -1;
          authInFlight = false;
          routePendingExitResult(payload);
          return;
        }
        discardLateSession(payload);
        return;
      }
      if (!identityMatches(payload)) {
        startDiscard(payload);
        return;
      }
      authInFlight = false;
      applyingSession = true;
      return Promise.resolve()
        .then(() => (options.applySession ? options.applySession(payload) : undefined))
        .then(() => {
          applyingSession = false;
          if (pendingExit) {
            // 会话已被应用（本地状态与通知中心已接管），迟到成功不得忽略：
            // 用响应凭据走受控注销收口，不应用等待者结果。
            pendingAuthAttempt = -1;
            routePendingExitResult(payload);
            return;
          }
          completeRecovery(myAttempt, payload);
        })
        .catch(() => {
          applyingSession = false;
          if (pendingExit) {
            pendingAuthAttempt = -1;
            routePendingExitResult(payload);
            return;
          }
          if (myAttempt !== attempt || state !== "reauthenticating") {
            discardLateSession(payload);
            return;
          }
          startDiscard(payload);
        });
    }

    function handleAuthFailure(error, myAttempt) {
      if (error instanceof AuthRecoveryCancelledError) return;
      if (myAttempt !== attempt || state !== "reauthenticating") {
        // 受控退出等待中的本次在途请求失败：认证端点自身报错、未产生新会话，
        // 此时才完成退出。注意：不依赖 AbortController/导航中断推断“服务端未建立会话”。
        if (pendingExit && state === "exitPending" && myAttempt === pendingAuthAttempt) {
          pendingAuthAttempt = -1;
          authInFlight = false;
          routePendingExitResult(null);
        }
        return;
      }
      authInFlight = false;
      submitting = false;
      const elements = els;
      if (elements) {
        if (elements.submit) elements.submit.disabled = false;
        if (elements.password) {
          elements.password.value = "";
          elements.password.disabled = false;
          if (elements.password.focus) elements.password.focus();
        }
      }
      setMessage(friendlyMessage(error));
    }

    function onSubmit(event) {
      if (event && event.preventDefault) event.preventDefault();
      if (state !== "reauthenticating" || submitting) return;
      const elements = els;
      if (!elements || !elements.password) return;
      const password = elements.password.value;
      if (!password) {
        if (elements.password.focus) elements.password.focus();
        return;
      }
      submitting = true;
      authInFlight = true;
      pendingAuthAttempt = attempt;
      if (elements.submit) elements.submit.disabled = true;
      setMessage("");
      const username = originalUser ? String(originalUser.username || "") : "";
      const myAttempt = attempt;
      const chain = Promise.resolve()
        .then(() => options.authenticate({ username, password }))
        .then((payload) => handleAuthSuccess(payload, myAttempt))
        .catch((error) => {
          handleAuthFailure(error, myAttempt);
        });
      // destroy 用该 Promise 判定“在途认证是否已 settle（含 apply 链与迟到注销注册）”。
      authSettlement = chain;
      chain.then(() => {
        if (authSettlement === chain) authSettlement = null;
      });
    }

    function startDiscard(payload) {
      attempt += 1;
      pendingAuthAttempt = -1;
      authInFlight = false;
      applyingSession = false;
      discardPayload = payload;
      submitting = false;
      if (!discardPromise) {
        discardPromise = new Promise((_resolve, reject) => {
          rejectDiscard = reject;
        });
        discardPromise.catch(() => {});
      }
      openOverlayDiscarding();
      attemptDiscard();
    }

    function recordDiscardFailure(error) {
      if (!lateDiscardError) {
        lateDiscardError = error instanceof Error ? error : new Error(String(error));
      }
    }

    function attemptDiscard() {
      if (discardInFlight || state !== "discarding") return;
      const myAttempt = attempt;
      const payload = discardPayload;
      discardInFlight = true;
      // 在途注销同样登记进清理追踪集合：destroy() 之后注销失败必须可观察，
      // 不得因状态机进入终止态而静默忽略。
      const chain = Promise.resolve()
        .then(() => (options.discardSession ? options.discardSession(payload) : undefined))
        .then(() => {
          discardInFlight = false;
          if (myAttempt !== attempt || state !== "discarding") {
            // destroy 之后成功：最新事实是会话已注销，清理无风险。
            lateDiscardError = null;
            return;
          }
          lateDiscardError = null;
          settleCancelled();
        })
        .catch((error) => {
          discardInFlight = false;
          if (myAttempt !== attempt || state !== "discarding") {
            // destroy 之后迟到失败：会话是否仍存在不可确认，
            // 记录风险供 destroy() 清理结果 reject，不得静默忽略。
            recordDiscardFailure(error);
            return;
          }
          // 仍可“重试退出”：风险尚未定论，不记录（成功后才清除记录）。
          setMessage("退出失败，请重试");
          const elements = els;
          if (elements && elements.exit) {
            elements.exit.disabled = false;
            elements.exit.textContent = RETRY_EXIT_LABEL;
          }
        });
      terminalDiscardTasks.add(chain);
      chain.then(() => terminalDiscardTasks.delete(chain));
    }

    function onExit() {
      if (state === "discarding") {
        // 重试退出：门闩保证不会并行注销。
        attemptDiscard();
        return;
      }
      if (state === "reauthenticating") {
        // 认证在途时先收口到等待结果，不立即导航；空闲时行为与既有约定一致。
        if (authInFlight || applyingSession || submitting) {
          beginControlledExit();
          return;
        }
        settleCancelled();
      }
    }

    function discardUnexpectedSession(payload) {
      if (state === "terminal") {
        discardLateSession(payload);
        return rejectedCancelled();
      }
      if (state === "discarding") {
        // 共享同一次注销；新 payload 代表服务端最新会话，刷新注销凭据。
        if (payload && payload.csrf_token && payload.user) discardPayload = payload;
        if (discardPromise) return discardPromise;
        return rejectedCancelled();
      }
      if (recoveryPromise && rejectRecovery) {
        const reject = rejectRecovery;
        recoveryPromise = null;
        resolveRecovery = null;
        rejectRecovery = null;
        reject(cancelledError());
      }
      if (!originalUser) captureOriginalUser();
      startDiscard(payload);
      return discardPromise;
    }

    function isRecovering() {
      return (
        state === "reauthenticating" ||
        state === "exitPending" ||
        state === "discarding" ||
        recoveryPromise !== null ||
        discardPromise !== null
      );
    }

    // 返回清理 Promise：拆卸仍立即完成；若拆卸时有认证/应用会话在途，
    // 迟到结果建立会话的注销失败必须反映为清理 reject，而不是静默吞掉。
    // 不导航、不阻止拆卸，保持既有调用方（忽略返回值）兼容。
    // 使用 authSettlement Promise 追踪在途认证请求的实际完成时机，而非轮询。
    function destroy() {
      const trackedSettlement = authSettlement; // 捕获当前在途认证的 Promise
      attempt += 1;
      const reject = rejectRecovery;
      const discardReject = rejectDiscard;
      const elements = els;
      if (elements && elements.password) elements.password.value = "";
      if (elements && elements.exit) elements.exit.textContent = EXIT_LABEL;
      closeOverlay();
      resetState("terminal");
      unbindEvents();
      // destroy 只拆卸不导航：不调用 exitSession。
      const error = cancelledError();
      if (reject) reject(error);
      if (discardReject) discardReject(error);
      let cleanup;
      const sessionRisk = () => {
        const cleanupError = cancelledError();
        cleanupError.cause = lateDiscardError;
        return cleanupError;
      };
      if (trackedSettlement) {
        // 等待在途认证请求 settle（含迟到注销任务注册），再检查是否有未处理的注销失败。
        cleanup = trackedSettlement
          .catch(() => {})
          .then(() => Promise.allSettled(Array.from(terminalDiscardTasks)))
          .then(() => {
            if (lateDiscardError) throw sessionRisk();
          });
      } else if (lateDiscardError) {
        cleanup = Promise.reject(sessionRisk());
      } else if (terminalDiscardTasks.size) {
        cleanup = Promise.allSettled(Array.from(terminalDiscardTasks)).then(() => {
          if (lateDiscardError) throw sessionRisk();
        });
      } else {
        cleanup = Promise.resolve();
      }
      // 调用方可忽略返回值：内部挂 catch 防 unhandled rejection，
      // await 返回值的调用方仍可观察 reject 结果。
      cleanup.catch(() => {});
      return cleanup;
    }

    return Object.freeze({
      recover,
      discardUnexpectedSession,
      isRecovering,
      destroy,
    });
  }

  globalScope.AutoCheckAuthRecovery = { createAuthRecovery, AuthRecoveryCancelledError };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { createAuthRecovery, AuthRecoveryCancelledError };
  }
})(typeof window !== "undefined" ? window : globalThis);
