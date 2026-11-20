export function isAbortError(error) {
  return error?.name === "AbortError" || error?.code === 20;
}

export function documentPreviewGap(candidate) {
  const message = candidate?.preview_error;
  return message && candidate.uncertainties?.includes(message) ? message : "";
}

export function errorMessage(error, fallback = "操作失败，请稍后重试") {
  const code = error?.payload?.error?.code || error?.code;
  const known = {
    VALIDATION_ERROR: "业务口径未确认、规则内容不完整或测试未通过",
    FORBIDDEN: "当前用户无权操作该资源",
    TASK_EXECUTOR_UNAVAILABLE: "后台执行位置已满或服务正在停止，请稍后重试",
    TASK_API_VERSION_MISMATCH: "后端尚未加载当前执行接口，请统一重启服务后刷新页面重试",
    TASK_EXECUTION_ERROR: "后台校验执行失败，请查看批次状态后重试",
    TASK_SELECTION_LIMIT: "当前筛选命中的规则过多，请缩小筛选范围后分批执行",
    CONFLICT_VERSION: "规则版本已变化，请重新读取详情并测试",
    RULE_DELETED: "规则已删除，请刷新校验列表",
    RULE_NOT_FOUND: "规则不存在，请刷新校验列表",
    MODEL_UNAVAILABLE: "模型连接不可用，请检查启用状态或稍后重试；仍可转手工继续",
    MODEL_TIMEOUT: "模型生成超时，请稍后重试或选择响应更快的模型；仍可转手工继续",
    MODEL_REQUEST_FAILED: "模型服务拒绝或未能完成请求，请检查模型服务状态后重试",
    MODEL_RESPONSE_INVALID: "模型返回内容不符合规则格式，请重试或转手工继续",
    MODEL_OUTPUT_LIMIT: "模型输出已达到长度上限，规则尚未完整生成；请重试或缩小本次校验范围",
    ANALYSIS_OUTPUT_LIMIT: "本次分析已用完输出额度，请缩小校验范围后重新分析",
    ANALYSIS_LIMIT_REACHED: "分析任务已达上限，请等待现有请求结束或稍后重试",
    ANALYSIS_FAILED: "本次分析未能完成，请重新分析或转手工继续",
    ANALYSIS_UNAVAILABLE: "分析服务已停止或重载，请刷新后重新分析",
    ANALYSIS_CONTEXT_CHANGED: "分析依据已更新，请按当前文档和业务口径重新分析。",
    PREVIEW_DATE_FIELD_REQUIRED: "还需选择记录所属的校验日期字段；已选口径已保留，无需重新分析",
    PROJECT_CONTEXT_REQUIRED: "请在「校验设置 → 文档快照」核对项目编号、项目名称及关联说明，再重新分析",
    PREVIEW_DATE_FIELD_INVALID: "所选校验日期不在文档日期字段中，请重新选择，不能用采集时间或业务事件日期冒充",
    SQL_POLICY_DENIED: "SQL 未通过只读安全检查",
    SOURCE_UNAVAILABLE: "数据源不可用，请检查配置后重试",
    MAPPING_DRIFT: "字段映射已变化，请重新读取表结构",
  };
  const message = known[code] || error?.payload?.error?.message || error?.message || fallback;
  const stage = { select_table: "选表阶段", generate_rule: "规则生成阶段", test_model: "可用性测试" }[error?.payload?.error?.stage];
  const reference = error?.payload?.error?.reference;
  const suffix = /^[a-f0-9]{12}$/.test(reference || "") ? `（错误编号 ${reference}）` : "";
  return `${stage ? `${stage}：` : ""}${message}${suffix}`;
}

function abortError() {
  const error = new Error("请求已取消");
  error.name = "AbortError";
  return error;
}

export function createRuntime({ notify }) {
  let mounted = true;
  let active = false;
  let generation = 0;
  let sequence = 0;
  const channelSequence = new Map();
  const channelControllers = new Map();
  const timers = new Map();
  const debounces = new Map();
  const listeners = new Set();

  function abortChannel(channel) {
    const controllers = channelControllers.get(channel);
    if (!controllers) return;
    controllers.forEach((controller) => controller.abort());
    controllers.clear();
    channelControllers.delete(channel);
  }

  function invalidate(channel) {
    channelSequence.set(channel, (channelSequence.get(channel) || 0) + 1);
    abortChannel(channel);
  }

  function next(channel) {
    invalidate(channel);
    return { channel, id: channelSequence.get(channel), generation, sequence: ++sequence };
  }

  function current(token) {
    return Boolean(token && mounted && active && token.generation === generation
      && channelSequence.get(token.channel) === token.id);
  }

  async function request(token, invoke) {
    if (!current(token)) throw abortError();
    const controller = new AbortController();
    let controllers = channelControllers.get(token.channel);
    if (!controllers) {
      controllers = new Set();
      channelControllers.set(token.channel, controllers);
    }
    controllers.add(controller);
    try {
      return await invoke(controller.signal);
    } finally {
      controllers.delete(controller);
      if (!controllers.size && channelControllers.get(token.channel) === controllers) {
        channelControllers.delete(token.channel);
      }
    }
  }

  function listen(target, type, handler, options) {
    const wrapped = async (event) => {
      if (!mounted || !active) return;
      try {
        await handler(event);
      } catch (error) {
        if (mounted && active && !isAbortError(error)) notify(errorMessage(error), "error");
      }
    };
    target.addEventListener(type, wrapped, options);
    const remove = () => {
      target.removeEventListener(type, wrapped, options);
      listeners.delete(remove);
    };
    listeners.add(remove);
    return remove;
  }

  function setTimer(callback, delay, key = null) {
    if (!mounted || !active) return null;
    const id = globalThis.setTimeout(() => {
      timers.delete(id);
      if (key && debounces.get(key) === id) debounces.delete(key);
      if (mounted && active) callback();
    }, delay);
    timers.set(id, key);
    if (key) debounces.set(key, id);
    return id;
  }

  function clearTimer(id) {
    if (id === null || id === undefined) return;
    globalThis.clearTimeout(id);
    const key = timers.get(id);
    timers.delete(id);
    if (key && debounces.get(key) === id) debounces.delete(key);
  }

  function debounce(key, callback, delay = 300) {
    clearTimer(debounces.get(key));
    return setTimer(callback, delay, key);
  }

  function clearDebounce(key) {
    clearTimer(debounces.get(key));
  }

  function stopAsync() {
    timers.forEach((_key, id) => globalThis.clearTimeout(id));
    timers.clear();
    debounces.clear();
    channelControllers.forEach((_controllers, channel) => abortChannel(channel));
    channelControllers.clear();
    channelSequence.forEach((value, channel) => channelSequence.set(channel, value + 1));
  }

  return {
    activate() {
      if (!mounted) return;
      stopAsync();
      generation += 1;
      active = true;
    },
    deactivate() {
      if (!mounted) return;
      active = false;
      generation += 1;
      stopAsync();
    },
    next,
    current,
    invalidate,
    request,
    listen,
    debounce,
    clearDebounce,
    setTimer,
    clearTimer,
    isActive: () => mounted && active,
    destroy() {
      if (!mounted) return;
      active = false;
      generation += 1;
      stopAsync();
      listeners.forEach((remove) => remove());
      listeners.clear();
      mounted = false;
    },
    snapshot() {
      return {
        mounted,
        active,
        generation,
        listeners: listeners.size,
        timers: timers.size,
        controllers: [...channelControllers.values()].reduce((sum, items) => sum + items.size, 0),
      };
    },
  };
}
