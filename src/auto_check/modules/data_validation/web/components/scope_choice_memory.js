// A browser-local preference, never confirmation evidence for a rule.
function contextKey(userId, candidate, question) {
  if (!userId || !candidate?.source_id || !candidate.table_name || question?.remember_scope !== "active_status") return null;
  const role = question.options?.[0]?.selection?.table;
  const table = role === "base" ? candidate.table_name : role === "related" ? candidate.join?.table_name : null;
  if (!table || !question.options.every((option) => option.selection?.table === role)) return null;
  return `dv:last-scope:${JSON.stringify([String(userId), String(candidate.source_id), candidate.table_name, table, role, question.remember_scope])}`;
}

function fingerprint(selection) {
  return selection ? JSON.stringify([selection.table, selection.field, selection.op, selection.value]) : null;
}

function optionFingerprint(option) {
  return JSON.stringify([fingerprint(option.selection), option.label]);
}

export function readScopeChoice(userId, candidate, question, storage) {
  const key = contextKey(userId, candidate, question);
  if (!key) return null;
  try {
    const saved = (storage ?? globalThis.localStorage)?.getItem(key);
    return question.options.find((option) => optionFingerprint(option) === saved) || null;
  } catch {
    return null;
  }
}

export function rememberScopeChoice(userId, candidate, question, selection, storage) {
  const key = contextKey(userId, candidate, question);
  if (!key) return;
  const option = question.options.find((item) => fingerprint(item.selection) === fingerprint(selection));
  if (!option) return;
  try {
    (storage ?? globalThis.localStorage)?.setItem(key, optionFingerprint(option));
  } catch {
    // Storage can be unavailable, e.g. blocked by privacy settings.
  }
}
