export function createState() {
  return {
    active: false,
    catalog: null,
    catalogAvailable: false,
    reportPeriod: "",
    activeProcessCode: "",
    filters: { status: "", keyword: "", handler_user_id: "" },
    records: [],
    summary: { by_report_process: [] },
    page: 1,
    pageSize: 10,
    total: 0,
    totalPages: 1,
    drawer: null,
    restoreFocus: null,
    locateRecordId: "",
    locateHighlight: false,
    locateOpenConfirm: false,
    todoConfirmHost: false,
  };
}

export function dataOf(response, fallback = null) {
  return response?.data ?? fallback;
}

export function defaultPeriod() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  const year = local.getUTCFullYear();
  const month = local.getUTCMonth(); // 0-based current month in local calendar via UTC fields of shifted date
  const lastDayPrevMonth = new Date(Date.UTC(year, month, 0));
  return lastDayPrevMonth.toISOString().slice(0, 10);
}

