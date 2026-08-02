import { createApi } from "./api.js";
import { createState } from "./state.js";
import { createLedgerPage } from "./pages/ledger.js";

let instance = null;

export function mount(context) {
  if (!context?.root || typeof context.api !== "function" || typeof context.user !== "function"
      || typeof context.notify !== "function" || typeof context.confirm !== "function"
      || typeof context.navigate !== "function") {
    throw new Error("报表特殊处理模块缺少宿主能力");
  }
  const api = createApi(context);
  const state = createState();
  instance = {
    context,
    api,
    state,
    page: createLedgerPage({
      root: context.root,
      api,
      state,
      user: context.user(),
      notify: context.notify,
      confirm: context.confirm,
      navigate: context.navigate,
    }),
  };
}

export function activate(route) {
  if (!instance) throw new Error("报表特殊处理模块尚未挂载");
  return instance.page.activate(route);
}

export function deactivate() {
  instance?.page.deactivate();
}

export function unmount() {
  instance?.page.destroy();
  instance = null;
}

