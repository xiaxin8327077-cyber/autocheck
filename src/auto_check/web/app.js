/* ===== Dom refs ===== */
const navItems = document.querySelectorAll(".nav-item[data-page]");
const topNav = document.querySelector(".top-nav");
const topNavItems = document.querySelectorAll(".top-nav-item[data-page]");
const navGroupToggles = document.querySelectorAll("[data-nav-group-toggle]");
const mainContent = document.querySelector(".main-content");
const pages = document.querySelectorAll(".page");
const runBtn = document.getElementById("runBtn");
const stopRunBtn = document.getElementById("stopRunBtn");
const runDate = document.getElementById("runDate");
const statusText = document.getElementById("statusText");
const topNavStatus = document.getElementById("topNavStatus");
const topDarkModeToggle = document.getElementById("topDarkModeToggle");
const sidebarDarkModeToggle = document.getElementById("sidebarDarkModeToggle");
const logoutButtons = document.querySelectorAll("[data-logout-btn]");
const reportNavPeriodSelect = document.getElementById("reportNavPeriodSelect");
const reportNavStatus = document.getElementById("reportNavStatus");
const reportNavStats = document.getElementById("reportNavStats");
const reportNavSchedules = document.getElementById("reportNavSchedules");
const reportNavBranches = document.getElementById("reportNavBranches");
const reportNavLastRun = document.getElementById("reportNavLastRun");
const reportNavFishboneSpine = document.getElementById("reportNavFishboneSpine");
const reportNavRefreshButton = document.getElementById("reportNavRefreshButton");
const reportNavRefreshCountdown = document.getElementById("reportNavRefreshCountdown");
const reportNavCardMaintenanceModal = document.getElementById("reportNavCardMaintenanceModal");
const reportNavCardMaintenanceTitle = document.getElementById("reportNavCardMaintenanceTitle");
const reportNavCardMaintenanceGrid = document.getElementById("reportNavCardMaintenanceGrid");
const reportNavCardMaintenanceClose = document.getElementById("reportNavCardMaintenanceClose");
const reportNavCardMaintenanceCancel = document.getElementById("reportNavCardMaintenanceCancel");
const reportNavCardMaintenanceSave = document.getElementById("reportNavCardMaintenanceSave");

const DEFAULT_VERSION = "v2.1";
const USER_AVATAR_SESSION_KEY = "autoCheckUserAvatarVariant";
const USER_AVATAR_GRADIENTS = [
  ["#6366f1", "#4338ca"],
  ["#f59e0b", "#d97706"],
  ["#10b981", "#047857"],
  ["#ec4899", "#be185d"],
  ["#0ea5e9", "#0369a1"],
  ["#8b5cf6", "#6d28d9"],
];
let statusRestoreTimer = null;

/* ===== Progress Bar Refs ===== */
const waveProgressContainer = document.getElementById("waveProgressContainer");
const waveProgressBar = document.getElementById("waveProgressBar");
const waveProgressText = document.getElementById("waveProgressText");
const waveStepName = document.getElementById("waveStepName");
const lastRunTime = document.getElementById("lastRunTime");
const runLogPanel = document.getElementById("runLogPanel");
const runLogList = document.getElementById("runLogList");
const runLogToggleBtn = document.getElementById("runLogToggleBtn");

/* ===== Steps definition ===== */
const reconcileSteps = [
  { name: "读取数据", percentage: 20 },
  { name: "验证数据完整性", percentage: 40 },
  { name: "自动分析差异", percentage: 70 },
  { name: "生成报告", percentage: 90 },
  { name: "完成", percentage: 100 }
];
const resultBody = document.getElementById("resultBody");
const keywordFilter = document.getElementById("keywordFilter");
const reasonFilter = document.getElementById("reasonFilter");
const statusFilter = document.getElementById("statusFilter");
const clearKeywordFilterBtn = document.getElementById("clearKeywordFilter");
const clearReasonFilterBtn = document.getElementById("clearReasonFilter");
const clearStatusFilterBtn = document.getElementById("clearStatusFilter");
const resultFilterHint = document.getElementById("resultFilterHint");
const prevPageBtn = document.getElementById("prevPage");
const nextPageBtn = document.getElementById("nextPage");
const pageCurrent = document.getElementById("pageCurrent");
const pageInfo = document.getElementById("pageInfo");
const exportBtn = document.getElementById("exportBtn");
const exportBtnLabel = exportBtn?.querySelector("[data-export-label]");
const exportProgress = document.getElementById("exportProgress");
const exportProgressText = document.getElementById("exportProgressText");
const jumpPage = document.getElementById("jumpPage");
const historyBody = document.getElementById("historyBody");
const historyReportFilter = document.getElementById("historyReportFilter");
const historyExecutorFilter = document.getElementById("historyExecutorFilter");
const clearHistoryReportFilterBtn = document.getElementById("clearHistoryReportFilter");
const clearHistoryExecutorFilterBtn = document.getElementById("clearHistoryExecutorFilter");
const historyRefreshBtn = document.getElementById("historyRefreshBtn");
const historyPageInfo = document.getElementById("historyPageInfo");
const historyPrevPageBtn = document.getElementById("historyPrevPage");
const historyNextPageBtn = document.getElementById("historyNextPage");
const historyPageCurrent = document.getElementById("historyPageCurrent");
const historyJumpPage = document.getElementById("historyJumpPage");
const refreshInfoBtn = document.getElementById("refreshInfoBtn");
const sysInfoFeedback = document.getElementById("sysInfoFeedback");
const userTableBody = document.getElementById("userTableBody");
const userSearch = document.getElementById("userSearch");
const userRoleFilter = document.getElementById("userRoleFilter");
const userStatusFilter = document.getElementById("userStatusFilter");
const userPrevPage = document.getElementById("userPrevPage");
const userNextPage = document.getElementById("userNextPage");
const userPageInfo = document.getElementById("userPageInfo");
const userModal = document.getElementById("userModal");
const userModalTitle = document.getElementById("userModalTitle");
const userModalClose = document.getElementById("userModalClose");
const userModalCancel = document.getElementById("userModalCancel");
const userModalSave = document.getElementById("userModalSave");
const userModalStatus = document.getElementById("userModalStatus");
const userId = document.getElementById("userId");
const userUsername = document.getElementById("userUsername");
const userDisplayNameInput = document.getElementById("userDisplayName");
const userRole = document.getElementById("userRole");
const userEnabled = document.getElementById("userEnabled");
const userEnabledSwitch = document.getElementById("userEnabledSwitch");
const userPassword = document.getElementById("userPassword");
const chartDateSelect = document.getElementById("chartDateSelect");
const trendQuickBtns = document.querySelectorAll(".trend-quick-btn");
const pbcZipFile = document.getElementById("pbcZipFile");
const pbcUploadArea = document.getElementById("pbcUploadArea");
const pbcUploadProgress = document.getElementById("pbcUploadProgress");
const pbcUploadProgressText = document.getElementById("pbcUploadProgressText");
const pbcUploadProgressPercent = document.getElementById("pbcUploadProgressPercent");
const pbcUploadProgressFill = document.getElementById("pbcUploadProgressFill");
const pbcFileList = document.getElementById("pbcFileList");
const pbcFileListBody = document.getElementById("pbcFileListBody");
const pbcDataSource = document.getElementById("pbcDataSource");
const pbcTargetTable = document.getElementById("pbcTargetTable");
const pbcRecentTables = document.getElementById("pbcRecentTables");
const pbcImportMode = document.getElementById("pbcImportMode");
const pbcLoadMappingsBtn = document.getElementById("pbcLoadMappingsBtn");
const pbcMappingList = document.getElementById("pbcMappingList");
const pbcMappingCount = document.getElementById("pbcMappingCount");
const pbcColumnNotice = document.getElementById("pbcColumnNotice");
const pbcImportLog = document.getElementById("pbcImportLog");
const pbcProgressIcon = document.getElementById("pbcProgressIcon");
const pbcProgressTitle = document.getElementById("pbcProgressTitle");
const pbcProgressSubtitle = document.getElementById("pbcProgressSubtitle");
const pbcProgressFill = document.getElementById("pbcProgressFill");
const pbcProgressPercent = document.getElementById("pbcProgressPercent");
const pbcCompleteDesc = document.getElementById("pbcCompleteDesc");
const pbcCompleteStats = document.getElementById("pbcCompleteStats");
const pbcPrevBtn = document.getElementById("pbcPrevBtn");
const pbcUploadSummary = document.getElementById("pbcUploadSummary");
const pbcClearFilesBtn = document.getElementById("pbcClearFilesBtn");
const pbcNextBtn = document.getElementById("pbcNextBtn");
const pbcRetryBtn = document.getElementById("pbcRetryBtn");
const pbcFinishBtn = document.getElementById("pbcFinishBtn");
const pbcModalOverlay = document.getElementById("pbcModalOverlay");
const pbcModalClose = document.getElementById("pbcModalClose");
const toolCardPbc = document.getElementById("toolCardPbc");
const pbcStepsContainer = document.getElementById("pbcSteps");
const pbcModalFooter = document.getElementById("pbcModalFooter");
const toolCardDbValidation = document.getElementById("toolCardDbValidation");
const toolCardFlow = document.getElementById("toolCardFlow");
const dbValidationModalOverlay = document.getElementById("dbValidationModalOverlay");
const dbValidationModalClose = document.getElementById("dbValidationModalClose");
const dbValidationCloseBtn = document.getElementById("dbValidationCloseBtn");
const dbValidationPublicInfoCheck = document.getElementById("dbValidationPublicInfoCheck");
const dbValidationTemplateCheck = document.getElementById("dbValidationTemplateCheck");
const dbValidationHistoryBtn = document.getElementById("dbValidationHistoryBtn");
const dbValidationHistoryOverlay = document.getElementById("dbValidationHistoryOverlay");
const dbValidationHistoryClose = document.getElementById("dbValidationHistoryClose");
const dbValidationHistoryBody = document.getElementById("dbValidationHistoryBody");
const dbValidationReportDate = document.getElementById("dbValidationReportDate");
const dbValidationTableList = document.getElementById("dbValidationTableList");
const dbValidationSelectAllTablesBtn = document.getElementById("dbValidationSelectAllTablesBtn");
const dbValidationProgressIcon = document.getElementById("dbValidationProgressIcon");
const dbValidationProgressTitle = document.getElementById("dbValidationProgressTitle");
const dbValidationProgressSubtitle = document.getElementById("dbValidationProgressSubtitle");
const dbValidationProgressFill = document.getElementById("dbValidationProgressFill");
const dbValidationProgressPercent = document.getElementById("dbValidationProgressPercent");
const dbValidationLog = document.getElementById("dbValidationLog");
const dbValidationStats = document.getElementById("dbValidationStats");
const dbValidationStatus = document.getElementById("dbValidationStatus");
const dbValidationStartBtn = document.getElementById("dbValidationStartBtn");
const dbValidationDownloadBtn = document.getElementById("dbValidationDownloadBtn");
const dbValidationRulesDocBtn = document.getElementById("dbValidationRulesDocBtn");
const dbValidationDetailSource = document.getElementById("dbValidationDetailSource");
const dbValidationDetailSysManageId = document.getElementById("dbValidationDetailSysManageId");
const dbValidationDetailClassificationId = document.getElementById("dbValidationDetailClassificationId");
const dbValidationPublicInfoSource = document.getElementById("dbValidationPublicInfoSource");
const dbValidationPublicInfoSysManageId = document.getElementById("dbValidationPublicInfoSysManageId");
const dbValidationPublicInfoClassificationId = document.getElementById("dbValidationPublicInfoClassificationId");
const dbValidationTemplateSource = document.getElementById("dbValidationTemplateSource");
const dbValidationTemplateSysManageId = document.getElementById("dbValidationTemplateSysManageId");
const dbValidationTemplateClassificationId = document.getElementById("dbValidationTemplateClassificationId");
const dbValidationMetadataSource = document.getElementById("dbValidationMetadataSource");
const dbValidationBaseinfoTable = document.getElementById("dbValidationBaseinfoTable");
const dbValidationFieldInfoTable = document.getElementById("dbValidationFieldInfoTable");
const dbValidationPublicInfoTable = document.getElementById("dbValidationPublicInfoTable");
const dbValidationSettingsStatus = document.getElementById("dbValidationSettingsStatus");
const saveDbValidationSettingsBtn = document.getElementById("saveDbValidationSettingsBtn");
const dbValidationRefreshFieldMappingBtn = document.getElementById("dbValidationRefreshFieldMappingBtn");
const flowModalOverlay = document.getElementById("flowModalOverlay");
const flowModalClose = document.getElementById("flowModalClose");
const flowProgressIcon = document.getElementById("flowProgressIcon");
const flowProgressTitle = document.getElementById("flowProgressTitle");
const flowProgressSubtitle = document.getElementById("flowProgressSubtitle");
const flowProgressFill = document.getElementById("flowProgressFill");
const flowProgressPercent = document.getElementById("flowProgressPercent");
const flowLog = document.getElementById("flowLog");
const flowStatus = document.getElementById("flowStatus");
const flowStartBtn = document.getElementById("flowStartBtn");
const flowCancelBtn = document.getElementById("flowCancelBtn");
const flowBgRunBtn = document.getElementById("flowBgRunBtn");
const flowHistoryBtn = document.getElementById("flowHistoryBtn");
const flowHistoryOverlay = document.getElementById("flowHistoryOverlay");
const flowHistoryClose = document.getElementById("flowHistoryClose");
const flowHistoryBody = document.getElementById("flowHistoryBody");
const flowSource = document.getElementById("flowSource");
const flowExecuteUrl = document.getElementById("flowExecuteUrl");
const flowFlowTable = document.getElementById("flowFlowTable");
const flowTaskTable = document.getElementById("flowTaskTable");
const flowPollInterval = document.getElementById("flowPollInterval");
const flowStepTimeout = document.getElementById("flowStepTimeout");
const flowChainSettingsList = document.getElementById("flowChainSettingsList");
const addFlowChainBtn = document.getElementById("addFlowChainBtn");
const saveFlowSettingsBtn = document.getElementById("saveFlowSettingsBtn");
const flowSettingsStatus = document.getElementById("flowSettingsStatus");
const flowChainEditorOverlay = document.getElementById("flowChainEditorOverlay");
const flowChainEditorClose = document.getElementById("flowChainEditorClose");
const flowChainEditorTitle = document.getElementById("flowChainEditorTitle");
const flowChainEditorName = document.getElementById("flowChainEditorName");
const flowChainEditorEnabled = document.getElementById("flowChainEditorEnabled");
const flowDefinitionSearch = document.getElementById("flowDefinitionSearch");
const flowManualFlowId = document.getElementById("flowManualFlowId");
const addManualFlowBtn = document.getElementById("addManualFlowBtn");
const flowDefinitionLimitHint = document.getElementById("flowDefinitionLimitHint");
const flowDefinitionRefreshBtn = document.getElementById("flowDefinitionRefreshBtn");
const flowDefinitionTable = document.getElementById("flowDefinitionTable");
const flowSelectedStepList = document.getElementById("flowSelectedStepList");
const flowChainEditorStatus = document.getElementById("flowChainEditorStatus");
const flowChainEditorCancel = document.getElementById("flowChainEditorCancel");
const flowChainEditorSave = document.getElementById("flowChainEditorSave");
const flowChainList = document.getElementById("flowChainList");
const flowChainSelectionSummary = document.getElementById("flowChainSelectionSummary");
const flowChainSelectedCount = document.querySelector(".flow-chain-selected-count");

let results = [];
let historyRuns = [];
let selectedHistory = null;
let selectedHistoryId = "";
let currentPage = 1;
let historyCurrentPage = 1;
let PAGE_SIZE = 10;
let runJobId = null;
let runPollTimer = null;
let activeRunConflictPollTimer = null;
let latestRunAt = "";
let latestRunExecutor = "";
let hasReconciled = false;
let resultEmptyState = "";
let hideLastRunTimeForNoSourceData = false;
let selectedChartDate = "";
let renderChartAnimId = null;
let renderTrendAnimId = null;
let homeChartsNeedThemeRefresh = false;
let homeChartsResizeTimer = null;
const HOME_CHARTS_RESIZE_DEBOUNCE_MS = 160;
const HOME_CHARTS_LOW_EFFECTS_RESIZE_DEBOUNCE_MS = 320;
let resultListLoadingTimer = null;
let trendQuickFilter = "6m";
let trendDateStart = "";
let trendDateEnd = "";
let homeResultListFilterLabel = "";
let resultRestoreHistoryMeta = null;
const LATEST_RESULTS_SNAPSHOT_KEY = "autoCheckLatestResults";
const RESULT_EMPTY_SOURCE = "source-empty";
let pbcUploadId = "";
let pbcColumns = [];
let pbcFiles = [];
let pbcMappings = [];
let pbcTableColumns = [];
let pbcDataSources = [];
let pbcPollTimer = null;
let dbValidationDataSources = [];
let dbValidationTables = [];
let dbValidationPollTimer = null;
let dbValidationDownloadUrl = "";
let flowSettings = null;
let flowDataSources = [];
let flowPollTimer = null;
let flowCurrentJobId = "";
let flowEditingChainIndex = -1;
let flowCurrentChainInfo = null;
let flowDefinitions = [];
let flowDefinitionsLoaded = false;
let flowSearchTimer = null;
let flowDefinitionSearchItems = [];
let flowChainEditorSelectedSteps = [];
// 多流程链批量执行状态
let selectedFlowChainIds = [];
let isFlowExecuting = false;
let currentExecutingChainIndex = 0;
let flowChainExecutionResults = []; // 收集多流程链执行结果
const BEIJING_TIME_ZONE = "Asia/Shanghai";
const BEIJING_DATE_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  timeZone: BEIJING_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
const BEIJING_DATE_TIME_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  timeZone: BEIJING_TIME_ZONE,
  hourCycle: "h23",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

function beijingParts(date = new Date(), formatter = BEIJING_DATE_TIME_FORMATTER) {
  return formatter.formatToParts(date).reduce((acc, part) => {
    if (part.type !== "literal") acc[part.type] = part.value;
    return acc;
  }, {});
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function formatBeijingDate(date = new Date()) {
  const parts = beijingParts(date, BEIJING_DATE_FORMATTER);
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function formatBeijingDateTime(date = new Date()) {
  const parts = beijingParts(date);
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`;
}

function formatBeijingTime(date = new Date()) {
  const parts = beijingParts(date);
  return `${parts.hour}:${parts.minute}:${parts.second}`;
}

function beijingMonthDays(year, month) {
  return new Date(Date.UTC(Number(year), Number(month), 0)).getUTCDate();
}

function shiftBeijingDate({ months = 0, years = 0 } = {}, date = new Date()) {
  const parts = beijingParts(date, BEIJING_DATE_FORMATTER);
  const monthIndex = Number(parts.month) - 1 + Number(months) + Number(years) * 12;
  const target = new Date(Date.UTC(Number(parts.year), monthIndex, 1));
  const year = target.getUTCFullYear();
  const month = target.getUTCMonth() + 1;
  const day = Math.min(Number(parts.day), beijingMonthDays(year, month));
  return `${year}-${pad2(month)}-${pad2(day)}`;
}

function beijingFileTimestamp(date = new Date()) {
  return formatBeijingDateTime(date).replace(/[-:\s]/g, "");
}
// Initialize trend date start to 6 months ago
(() => { trendDateStart = shiftBeijingDate({ months: -6 }); })();
const DEFAULT_SETTINGS = {
  sessionExpireHours: "8",
  pageSize: "10",
  combinationLimit: "50",
  autoRefreshHome: "false",
  visualEffects: "true",
  theme: "space-tech",
  darkMode: "false",
};
let defaultSettings = { ...DEFAULT_SETTINGS };
let serverDefaultSettings = { ...DEFAULT_SETTINGS };
let managedUsers = [];
let userQuickFilter = "all";
let userCurrentPage = 1;
let usersLoaded = false;
let usersLoading = false;
const USER_PAGE_SIZE = 10;
const authState = { csrfToken: "", user: null };
let reportNavigationPayload = null;
let reportNavigationLoading = false;
const REPORT_NAV_REFRESH_COOLDOWN_SECONDS = 300;
let reportNavigationRefreshCooldownUntil = 0;
let reportNavigationRefreshTimer = null;
let reportNavigationRefreshBusy = false;
let reportNavigationRefreshRemoteRunning = false;
const THEME_ACTIVE_USER_KEY = "autoCheckThemeUserKey";
const THEME_KEY_BASE = "autoCheckTheme";
const DARK_MODE_KEY_BASE = "autoCheckDarkMode";
const MAIN_ENTRY_ANIMATION_KEY = "autoCheckMainEntryAnimation";

function consumeMainEntryAnimationFlag() {
  try {
    const shouldPlay = sessionStorage.getItem(MAIN_ENTRY_ANIMATION_KEY) === "login";
    sessionStorage.removeItem(MAIN_ENTRY_ANIMATION_KEY);
    return shouldPlay;
  } catch (_) {
    return false;
  }
}

function revealAuthenticatedApp() {
  const shouldAnimate = consumeMainEntryAnimationFlag();
  if (shouldAnimate && visualEffectsEnabled() && !window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) {
    document.documentElement.classList.add("main-entry-animate");
    window.setTimeout(() => {
      document.documentElement.classList.remove("main-entry-animate");
    }, 720);
  }
  document.documentElement.classList.remove("auth-pending");
}

async function ensureAuthenticated() {
  const response = await fetch("/api/auth/status");
  const payload = await response.json();
  if (!response.ok || !payload.authenticated) {
    window.location.href = "/login.html";
    throw new Error("login required");
  }
  resetInterfaceRadiusForAuthChange();
  authState.csrfToken = payload.csrf_token || "";
  authState.user = payload.user || null;
  document.documentElement.dataset.role = authState.user?.role === "admin" ? "admin" : "user";
  await loadInterfaceRadiusPreference({ silent: true });
  activateThemeUserStorage();
  applySavedUserTheme();
  updateCurrentUsername();
  applyRoleAccess();
  revealAuthenticatedApp();
  return payload;
}

function getSavedSettings() {
  try {
    return JSON.parse(localStorage.getItem("autoCheckSettings") || "{}");
  } catch (_) {
    return {};
  }
}

function normalizeTheme(theme) {
  return ["light", "space-tech"].includes(theme) ? theme : "space-tech";
}

function normalizeDarkMode(darkMode) {
  return darkMode === true || darkMode === "true" ? "true" : "false";
}

function currentThemeUserKey() {
  const user = authState.user || {};
  const id = String(user.id || "").trim();
  if (id) return `id:${id}`;
  const username = String(user.username || "").trim().toLowerCase();
  if (username) return `username:${username}`;
  try {
    return localStorage.getItem(THEME_ACTIVE_USER_KEY) || "";
  } catch (_) {
    return "";
  }
}

function themeStorageKey(baseKey) {
  const userKey = currentThemeUserKey();
  return userKey ? `${baseKey}:${userKey}` : baseKey;
}

function activateThemeUserStorage() {
  const userKey = currentThemeUserKey();
  if (!userKey) return;
  try {
    const activeUserKey = localStorage.getItem(THEME_ACTIVE_USER_KEY) || "";
    if (!activeUserKey) {
      const legacyTheme = localStorage.getItem(THEME_KEY_BASE);
      const legacyDarkMode = localStorage.getItem(DARK_MODE_KEY_BASE);
      if (legacyTheme && !localStorage.getItem(`${THEME_KEY_BASE}:${userKey}`)) {
        localStorage.setItem(`${THEME_KEY_BASE}:${userKey}`, legacyTheme);
      }
      if (legacyDarkMode && !localStorage.getItem(`${DARK_MODE_KEY_BASE}:${userKey}`)) {
        localStorage.setItem(`${DARK_MODE_KEY_BASE}:${userKey}`, legacyDarkMode);
      }
    }
    localStorage.setItem(THEME_ACTIVE_USER_KEY, userKey);
  } catch (_) {
    // Ignore storage quota or private browsing failures.
  }
}

function getSavedTheme() {
  try {
    const saved = localStorage.getItem(themeStorageKey(THEME_KEY_BASE)) || "";
    return saved || (authState.user ? "" : (localStorage.getItem(THEME_KEY_BASE) || ""));
  } catch (_) {
    return "";
  }
}

function getSavedDarkMode() {
  try {
    const saved = localStorage.getItem(themeStorageKey(DARK_MODE_KEY_BASE)) || "";
    return saved || (authState.user ? "" : (localStorage.getItem(DARK_MODE_KEY_BASE) || ""));
  } catch (_) {
    return "";
  }
}

function saveUserThemePreference(keyBase, value) {
  try {
    localStorage.setItem(themeStorageKey(keyBase), value);
    const userKey = currentThemeUserKey();
    if (userKey) localStorage.setItem(THEME_ACTIVE_USER_KEY, userKey);
  } catch (_) {
    // Ignore storage quota or private browsing failures.
  }
}

function withSavedUserTheme(settings = {}) {
  const savedTheme = getSavedTheme();
  const savedDarkMode = getSavedDarkMode();
  return normalizeClientSettings({
    ...settings,
    ...(savedTheme ? { theme: savedTheme } : {}),
    ...(savedDarkMode ? { darkMode: savedDarkMode } : {}),
  });
}

function applySavedUserTheme() {
  const savedTheme = getSavedTheme();
  const savedDarkMode = getSavedDarkMode();
  if (savedTheme) {
    defaultSettings.theme = normalizeTheme(savedTheme);
    applyTheme(defaultSettings.theme);
  }
  if (savedDarkMode) {
    defaultSettings.darkMode = normalizeDarkMode(savedDarkMode);
    applyDarkMode(defaultSettings.darkMode);
  }
}

// Interface radius start
const DEFAULT_INTERFACE_RADIUS_PX = 4;
const MIN_INTERFACE_RADIUS_PX = 1;
const MAX_INTERFACE_RADIUS_PX = 15;
const INTERFACE_RADIUS_LOAD_TIMEOUT_MS = 2500;
const interfaceRadiusSlider = document.getElementById("interfaceRadiusSlider");
const interfaceRadiusValue = document.getElementById("interfaceRadiusValue");
const interfaceSettingsStatus = document.getElementById("interfaceSettingsStatus");
const saveInterfaceSettingsBtn = document.getElementById("saveInterfaceSettingsBtn");
const resetInterfaceSettingsBtn = document.getElementById("resetInterfaceSettingsBtn");
const interfaceRadiusState = {
  savedRadiusPx: DEFAULT_INTERFACE_RADIUS_PX,
  draftRadiusPx: DEFAULT_INTERFACE_RADIUS_PX,
  loaded: false,
  loadFailed: false,
  saving: false,
  statusText: "已保存",
  loadRequestId: 0,
  saveRequestId: 0,
  authRevision: 0,
  editRevision: 0,
  serverMutationRevision: 0,
};

function normalizeInterfaceRadius(radiusPx) {
  if (
    Number.isInteger(radiusPx)
    && radiusPx >= MIN_INTERFACE_RADIUS_PX
    && radiusPx <= MAX_INTERFACE_RADIUS_PX
  ) {
    return radiusPx;
  }
  return DEFAULT_INTERFACE_RADIUS_PX;
}

function applyInterfaceRadius(radiusPx) {
  const normalizedRadiusPx = normalizeInterfaceRadius(radiusPx);
  document.documentElement.style.setProperty("--ui-radius", `${normalizedRadiusPx}px`);
  return normalizedRadiusPx;
}

function readInterfaceRadiusPayload(payload) {
  const radiusPx = payload?.settings?.radius_px;
  if (
    !Number.isInteger(radiusPx)
    || radiusPx < MIN_INTERFACE_RADIUS_PX
    || radiusPx > MAX_INTERFACE_RADIUS_PX
  ) {
    throw new Error("界面圆角响应无效");
  }
  return radiusPx;
}

function syncInterfaceRadiusDirtyStatus() {
  interfaceRadiusState.statusText = (
    interfaceRadiusState.draftRadiusPx === interfaceRadiusState.savedRadiusPx
      ? "已保存"
      : "正在预览，尚未保存"
  );
  return interfaceRadiusState.statusText;
}

function renderInterfaceRadiusPreference() {
  if (interfaceRadiusSlider) {
    interfaceRadiusSlider.value = String(interfaceRadiusState.draftRadiusPx);
    interfaceRadiusSlider.disabled = interfaceRadiusState.saving;
  }
  if (interfaceRadiusValue) {
    interfaceRadiusValue.textContent = `${interfaceRadiusState.draftRadiusPx}px`;
  }
  if (interfaceSettingsStatus) {
    interfaceSettingsStatus.textContent = interfaceRadiusState.statusText;
  }
  if (saveInterfaceSettingsBtn) {
    saveInterfaceSettingsBtn.disabled = interfaceRadiusState.saving;
    saveInterfaceSettingsBtn.classList.toggle("loading", interfaceRadiusState.saving);
    saveInterfaceSettingsBtn.textContent = interfaceRadiusState.saving ? "保存中..." : "保存界面设置";
  }
  if (resetInterfaceSettingsBtn) {
    resetInterfaceSettingsBtn.disabled = interfaceRadiusState.saving;
  }
}

function resetInterfaceRadiusForAuthChange() {
  interfaceRadiusState.loadRequestId += 1;
  interfaceRadiusState.saveRequestId += 1;
  interfaceRadiusState.authRevision += 1;
  interfaceRadiusState.editRevision += 1;
  interfaceRadiusState.serverMutationRevision += 1;
  interfaceRadiusState.savedRadiusPx = DEFAULT_INTERFACE_RADIUS_PX;
  interfaceRadiusState.draftRadiusPx = DEFAULT_INTERFACE_RADIUS_PX;
  interfaceRadiusState.loaded = false;
  interfaceRadiusState.loadFailed = false;
  interfaceRadiusState.saving = false;
  interfaceRadiusState.statusText = "已保存";
  applyInterfaceRadius(DEFAULT_INTERFACE_RADIUS_PX);
  renderInterfaceRadiusPreference();
  return interfaceRadiusState.authRevision;
}

function captureInterfaceRadiusPreference() {
  return {
    savedRadiusPx: interfaceRadiusState.savedRadiusPx,
    draftRadiusPx: interfaceRadiusState.draftRadiusPx,
    loaded: interfaceRadiusState.loaded,
    loadFailed: interfaceRadiusState.loadFailed,
    statusText: interfaceRadiusState.statusText,
  };
}

function restoreInterfaceRadiusPreference(snapshot, expectedAuthRevision) {
  if (expectedAuthRevision !== interfaceRadiusState.authRevision) return false;
  interfaceRadiusState.loadRequestId += 1;
  interfaceRadiusState.saveRequestId += 1;
  interfaceRadiusState.authRevision += 1;
  interfaceRadiusState.editRevision += 1;
  interfaceRadiusState.serverMutationRevision += 1;
  interfaceRadiusState.savedRadiusPx = snapshot.savedRadiusPx;
  interfaceRadiusState.draftRadiusPx = snapshot.draftRadiusPx;
  interfaceRadiusState.loaded = snapshot.loaded;
  interfaceRadiusState.loadFailed = snapshot.loadFailed;
  interfaceRadiusState.saving = false;
  interfaceRadiusState.statusText = snapshot.statusText;
  applyInterfaceRadius(snapshot.draftRadiusPx);
  renderInterfaceRadiusPreference();
  return true;
}

async function loadInterfaceRadiusPreference({ silent = false } = {}) {
  if (interfaceRadiusState.saving) return false;
  const requestId = ++interfaceRadiusState.loadRequestId;
  const editRevision = interfaceRadiusState.editRevision;
  const mutationRevision = interfaceRadiusState.serverMutationRevision;
  const hadUnsavedDraft = (
    interfaceRadiusState.draftRadiusPx !== interfaceRadiusState.savedRadiusPx
  );
  const abortController = new AbortController();
  const timeoutId = setTimeout(() => abortController.abort(), INTERFACE_RADIUS_LOAD_TIMEOUT_MS);
  try {
    const payload = await api("/api/settings/interface", { signal: abortController.signal });
    if (
      requestId !== interfaceRadiusState.loadRequestId
      || mutationRevision !== interfaceRadiusState.serverMutationRevision
    ) {
      return false;
    }
    const radiusPx = readInterfaceRadiusPayload(payload);
    interfaceRadiusState.savedRadiusPx = radiusPx;
    interfaceRadiusState.loaded = true;
    interfaceRadiusState.loadFailed = false;
    if (!hadUnsavedDraft && editRevision === interfaceRadiusState.editRevision) {
      interfaceRadiusState.draftRadiusPx = radiusPx;
      applyInterfaceRadius(radiusPx);
    }
    syncInterfaceRadiusDirtyStatus();
    renderInterfaceRadiusPreference();
    return true;
  } catch (error) {
    if (
      requestId !== interfaceRadiusState.loadRequestId
      || mutationRevision !== interfaceRadiusState.serverMutationRevision
    ) {
      return false;
    }
    const editedDuringRequest = editRevision !== interfaceRadiusState.editRevision;
    const preserveDraft = hadUnsavedDraft || editedDuringRequest;
    if (!interfaceRadiusState.loaded) {
      interfaceRadiusState.savedRadiusPx = DEFAULT_INTERFACE_RADIUS_PX;
      if (preserveDraft) {
        syncInterfaceRadiusDirtyStatus();
      } else {
        interfaceRadiusState.draftRadiusPx = DEFAULT_INTERFACE_RADIUS_PX;
        applyInterfaceRadius(DEFAULT_INTERFACE_RADIUS_PX);
        interfaceRadiusState.statusText = "加载失败，当前使用默认 4px";
      }
    } else if (editedDuringRequest) {
      syncInterfaceRadiusDirtyStatus();
    } else {
      interfaceRadiusState.statusText = `加载失败，继续使用 ${interfaceRadiusState.draftRadiusPx}px`;
    }
    interfaceRadiusState.loadFailed = true;
    renderInterfaceRadiusPreference();
    if (!silent) showToast(`界面设置加载失败: ${error.message}`, "error");
    return false;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function saveInterfaceRadiusPreference() {
  if (interfaceRadiusState.saving) return false;
  const requestId = ++interfaceRadiusState.saveRequestId;
  const authRevision = interfaceRadiusState.authRevision;
  interfaceRadiusState.serverMutationRevision += 1;
  const mutationRevision = interfaceRadiusState.serverMutationRevision;
  const isCurrentRequest = () => (
    requestId === interfaceRadiusState.saveRequestId
    && authRevision === interfaceRadiusState.authRevision
    && mutationRevision === interfaceRadiusState.serverMutationRevision
  );
  interfaceRadiusState.saving = true;
  renderInterfaceRadiusPreference();
  try {
    const payload = await api("/api/settings/interface", {
      method: "POST",
      body: JSON.stringify({ radius_px: interfaceRadiusState.draftRadiusPx }),
    });
    if (!isCurrentRequest()) return false;
    const savedRadiusPx = readInterfaceRadiusPayload(payload);
    interfaceRadiusState.savedRadiusPx = savedRadiusPx;
    interfaceRadiusState.draftRadiusPx = savedRadiusPx;
    interfaceRadiusState.loaded = true;
    interfaceRadiusState.loadFailed = false;
    interfaceRadiusState.statusText = "保存成功";
    applyInterfaceRadius(savedRadiusPx);
    return true;
  } catch (error) {
    if (!isCurrentRequest()) return false;
    interfaceRadiusState.statusText = "保存失败";
    showToast(`界面设置保存失败: ${error.message}`, "error");
    return false;
  } finally {
    if (isCurrentRequest()) {
      interfaceRadiusState.saving = false;
      renderInterfaceRadiusPreference();
    }
  }
}

function discardUnsavedInterfaceRadius() {
  interfaceRadiusState.loadRequestId += 1;
  const changed = interfaceRadiusState.draftRadiusPx !== interfaceRadiusState.savedRadiusPx;
  interfaceRadiusState.draftRadiusPx = interfaceRadiusState.savedRadiusPx;
  applyInterfaceRadius(interfaceRadiusState.savedRadiusPx);
  syncInterfaceRadiusDirtyStatus();
  renderInterfaceRadiusPreference();
  return changed;
}

interfaceRadiusSlider?.addEventListener("input", () => {
  if (interfaceRadiusState.saving) return;
  interfaceRadiusState.editRevision += 1;
  interfaceRadiusState.draftRadiusPx = normalizeInterfaceRadius(Number(interfaceRadiusSlider.value));
  applyInterfaceRadius(interfaceRadiusState.draftRadiusPx);
  syncInterfaceRadiusDirtyStatus();
  renderInterfaceRadiusPreference();
});

resetInterfaceSettingsBtn?.addEventListener("click", () => {
  if (interfaceRadiusState.saving) return;
  interfaceRadiusState.editRevision += 1;
  interfaceRadiusState.draftRadiusPx = DEFAULT_INTERFACE_RADIUS_PX;
  applyInterfaceRadius(interfaceRadiusState.draftRadiusPx);
  syncInterfaceRadiusDirtyStatus();
  renderInterfaceRadiusPreference();
});

saveInterfaceSettingsBtn?.addEventListener("click", saveInterfaceRadiusPreference);
// Interface radius end

function updateSpaceTopNavFrost() {
  if (!topNav) return;
  const scrollOffset = Math.max(window.scrollY, mainContent?.scrollTop || 0);
  const activePage = Array.from(pages).find(
    (page) => window.getComputedStyle(page).display !== "none"
  );
  const navBottom = topNav.getBoundingClientRect().bottom;
  const contentTop = activePage?.getBoundingClientRect().top ?? Number.POSITIVE_INFINITY;
  // Only frost the nav once scrolled content actually reaches the nav edge.
  const shouldFrost = scrollOffset > 1 && contentTop < navBottom;
  document.documentElement.classList.toggle("space-nav-over-content", shouldFrost);
}

function syncThemeBootCache() {
  try {
    const themeKey = themeStorageKey(THEME_KEY_BASE);
    const darkModeKey = themeStorageKey(DARK_MODE_KEY_BASE);
    if (!localStorage.getItem(themeKey)) {
      localStorage.setItem(themeKey, defaultSettings.theme);
    }
    if (!localStorage.getItem(darkModeKey)) {
      localStorage.setItem(darkModeKey, defaultSettings.darkMode);
    }
  } catch (_) {
    // Ignore storage quota or private browsing failures.
  }
}

function normalizeClientSettings(settings = {}) {
  const rawCombinationLimit = parseInt(settings.combinationLimit || DEFAULT_SETTINGS.combinationLimit, 10);
  const combinationLimit = Number.isFinite(rawCombinationLimit) ? Math.min(Math.max(rawCombinationLimit, 1), 500) : 50;
  const rawPageSize = parseInt(settings.pageSize || DEFAULT_SETTINGS.pageSize, 10);
  const pageSize = Number.isFinite(rawPageSize) ? Math.min(Math.max(rawPageSize, 1), 500) : 10;
  const rawSessionExpireHours = parseInt(settings.sessionExpireHours || DEFAULT_SETTINGS.sessionExpireHours, 10);
  const sessionExpireHours = Number.isFinite(rawSessionExpireHours) ? Math.min(Math.max(rawSessionExpireHours, 1), 168) : 8;
  return {
    sessionExpireHours: String(sessionExpireHours),
    pageSize: String(pageSize),
    combinationLimit: String(combinationLimit),
    autoRefreshHome: String(settings.autoRefreshHome) === "true" ? "true" : "false",
    visualEffects: String(settings.visualEffects) === "false" ? "false" : "true",
    theme: normalizeTheme(settings.theme || DEFAULT_SETTINGS.theme),
    darkMode: normalizeDarkMode(settings.darkMode),
  };
}

function serverSettingsToClient(settings = {}) {
  return normalizeClientSettings({
    sessionExpireHours: settings.session_expire_hours,
    pageSize: settings.page_size,
    combinationLimit: settings.combination_limit,
    autoRefreshHome: settings.auto_refresh_home,
    visualEffects: settings.visual_effects === false ? "false" : "true",
    theme: settings.theme,
    darkMode: settings.dark_mode,
  });
}

function clientSettingsToServer(settings) {
  const normalized = normalizeClientSettings(settings);
  return {
    session_expire_hours: parseInt(normalized.sessionExpireHours, 10),
    page_size: parseInt(normalized.pageSize, 10),
    combination_limit: parseInt(normalized.combinationLimit, 10),
    auto_refresh_home: normalized.autoRefreshHome === "true",
    visual_effects: normalized.visualEffects !== "false",
    theme: normalized.theme,
    dark_mode: normalized.darkMode === "true",
  };
}

async function loadDefaultSettings() {
  const data = await api("/api/settings/defaults");
  serverDefaultSettings = serverSettingsToClient(data.settings || {});
  defaultSettings = withSavedUserTheme(serverDefaultSettings);
  const legacySettings = getSavedSettings();
  if (Object.keys(legacySettings).length) {
    const migratedSettings = normalizeClientSettings({
      ...serverDefaultSettings,
      ...legacySettings,
      theme: serverDefaultSettings.theme,
      darkMode: serverDefaultSettings.darkMode,
    });
    const saved = await api("/api/settings/defaults", {
      method: "POST",
      body: JSON.stringify(clientSettingsToServer(migratedSettings)),
    });
    serverDefaultSettings = serverSettingsToClient(saved.settings || {});
    defaultSettings = withSavedUserTheme(serverDefaultSettings);
    localStorage.removeItem("autoCheckSettings");
  }
  syncThemeBootCache();
  applyVisualEffectsSetting();
  return data;
}

function shouldAutoRefreshHome() {
  return defaultSettings.autoRefreshHome === "true";
}

function visualEffectsEnabled() {
  return defaultSettings.visualEffects !== "false";
}

function applyVisualEffectsSetting() {
  document.documentElement.dataset.visualEffects = visualEffectsEnabled() ? "on" : "off";
}

/* ===== Navigation ===== */
const smartReconcilePages = new Set(["home", "auto-check", "history"]);

function setNavGroupOpen(group, open) {
  if (!group) return;
  group.classList.toggle("open", open);
  group.querySelector("[data-nav-group-toggle]")?.setAttribute("aria-expanded", open ? "true" : "false");
}

function syncNavGroupState(name) {
  const active = smartReconcilePages.has(name);
  document.querySelectorAll('[data-nav-group="smart-reconcile"]').forEach((group) => {
    group.classList.toggle("active", active);
    group.querySelector("[data-nav-group-toggle]")?.classList.toggle("active", active);
  });
}

function syncNavState(name) {
  [...navItems, ...topNavItems].forEach((item) => {
    item.classList.toggle("active", item.dataset.page === name);
  });
  syncNavGroupState(name);
}

function applySettingsRoleAccess() {
  const isAdmin = authState.user?.role === "admin";
  document.querySelectorAll(".admin-action").forEach((button) => {
    button.disabled = !isAdmin;
    button.title = isAdmin ? "" : "普通用户不可执行该操作";
  });
}

function applyRoleAccess() {
  const isAdmin = authState.user?.role === "admin";
  document.documentElement.dataset.role = isAdmin ? "admin" : "user";
  document.querySelectorAll(".admin-only").forEach((item) => {
    item.hidden = !isAdmin;
  });
  applySettingsRoleAccess();
  const currentPageName = document.documentElement.getAttribute("data-page") || location.hash.slice(1);
  if (!isAdmin && currentPageName === "users") {
    switchPage("report-navigation");
  }
}

async function loadPageSection(label, loader) {
  try {
    return await loader();
  } catch (error) {
    console.error(`${label}加载失败`, error);
    return null;
  }
}

async function loadToolsPageData() {
  await Promise.all([
    loadPageSection("PBC导入配置", loadPbcImportSettings),
    loadPageSection("逐笔校验配置", loadDbValidationSettings),
    loadPageSection("流程执行配置", loadFlowSettings),
  ]);
}

async function loadSettingsPageData() {
  await Promise.all([
    loadPageSection("系统信息", loadSystemInfo),
    loadPageSection("界面设置", () => loadInterfaceRadiusPreference({ silent: false })),
    loadPageSection("数据源配置", loadConfigList),
    loadPageSection("逐笔校验配置", loadDbValidationSettings),
    loadPageSection("流程执行配置", loadFlowSettings),
    loadPageSection("业务字段配置", loadReconcileSchemaSettings),
  ]);
  applySettingsRoleAccess();
}

[...navItems, ...topNavItems].forEach((item) => {
  item.addEventListener("click", (e) => {
    e.preventDefault();
    document.querySelectorAll(".top-nav-group.open").forEach((group) => setNavGroupOpen(group, false));
    switchPage(item.dataset.page);
    if (item.classList.contains("top-nav-subitem") && e.detail > 0) item.blur();
  });
});

navGroupToggles.forEach((toggle) => {
  toggle.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const group = toggle.closest("[data-nav-group]");
    if (!group) return;
    if (group.classList.contains("nav-group")) {
      setNavGroupOpen(group, !group.classList.contains("open"));
      return;
    }
    if (group.classList.contains("top-nav-group")) {
      document.querySelectorAll(".top-nav-group.open").forEach((item) => setNavGroupOpen(item, false));
      switchPage("home");
      if (event.detail > 0) toggle.blur();
    }
  });
});

document.addEventListener("click", (event) => {
  document.querySelectorAll(".top-nav-group").forEach((group) => {
    if (!group.contains(event.target)) {
      setNavGroupOpen(group, false);
      if (group.contains(document.activeElement)) document.activeElement.blur();
    }
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  document.querySelectorAll(".top-nav-group").forEach((group) => {
    setNavGroupOpen(group, false);
    if (group.contains(document.activeElement)) document.activeElement.blur();
  });
});

async function switchPage(name, options = {}) {
  const previousPage = document.documentElement.getAttribute("data-page") || "";
  if (name === "users" && authState.user?.role !== "admin") {
    showToast("普通用户无权访问用户管理", "error");
    name = "report-navigation";
  }
  if (previousPage === "settings" && name !== "settings") discardUnsavedInterfaceRadius();
  document.documentElement.setAttribute('data-page', name);
  syncNavState(name);
  const nextHash = `#${name}`;
  if (location.hash !== nextHash) location.hash = name;
  if (name === "history") loadHistoryList(true);
  if (name === "tools") loadToolsPageData();
  if (name === "settings") loadSettingsPageData();
  if (name === "users") await loadUsers();
  if (name === "report-navigation") await loadReportNavigation();
  if (name === "home" && (options.forceHomeRefresh || shouldAutoRefreshHome() || homeChartsNeedThemeRefresh)) {
    homeChartsNeedThemeRefresh = false;
    renderHomeStats(); renderChart(); renderTrendChart();
  }
  if (name === "auto-check" && previousPage !== "auto-check") showResultListReturnLoading();
}

function captureScrollPosition() {
  const windowX = window.scrollX;
  const windowY = window.scrollY;
  const mainScrollTop = mainContent?.scrollTop || 0;
  const mainScrollLeft = mainContent?.scrollLeft || 0;
  return () => {
    requestAnimationFrame(() => {
      if (mainContent) {
        mainContent.scrollTop = mainScrollTop;
        mainContent.scrollLeft = mainScrollLeft;
      }
      window.scrollTo(windowX, windowY);
      updateSpaceTopNavFrost();
    });
  };
}

/* ===== API ===== */
function formatApiErrorMessage(message) {
  const raw = String(message || "");
  if (raw.includes("password must be at least 6 characters and include a letter")) {
    return "密码长度至少 6 位，且需包含至少 1 个字母。";
  }
  return raw;
}

async function api(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (method !== "GET" && authState.csrfToken) {
    headers["X-CSRF-Token"] = authState.csrfToken;
  }
  const r = await fetch(path, { ...options, headers });
  const p = await r.json();
  if (r.status === 401) {
    window.location.href = "/login.html";
    throw new Error("login required");
  }
  if (!r.ok) {
    const error = new Error(formatApiErrorMessage(p.error || `请求失败: ${r.status}`));
    error.status = r.status;
    error.payload = p;
    throw error;
  }
  return p;
}

const REPORT_NAV_CARD_STYLES = {
  report_forms: { color: "blue", icon: "▣", unit: "套" },
  supplement_tasks: { color: "green", icon: "✓", unit: "个" },
  data_governance: { color: "orange", icon: "!", unit: "个" },
  special_governance: { color: "red", icon: "◎", unit: "个" },
};
const REPORT_NAV_MAINTENANCE_PERIODS = [
  ["week", "本周"],
  ["month", "本月"],
  ["quarter", "本季度"],
  ["year", "本年"],
];
const REPORT_NAV_MAINTAINABLE_CARDS = new Set(["data_governance", "special_governance"]);

function reportNavigationDateText(value) {
  const match = String(value || "").match(/^\d{4}-(\d{2})-(\d{2})$/);
  if (!match) return "待配置";
  return `${Number(match[1])}月${Number(match[2])}日`;
}

function reportNavigationRate(card) {
  const value = Number(card?.completion_rate || 0);
  return Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
}

function renderReportNavigationCards(cards) {
  if (!reportNavStats) return;
  reportNavStats.innerHTML = (cards || []).map((card) => {
    const style = REPORT_NAV_CARD_STYLES[card.card_code] || REPORT_NAV_CARD_STYLES.report_forms;
    const rate = reportNavigationRate(card);
    const maintainable = authState.user?.role === "admin" && REPORT_NAV_MAINTAINABLE_CARDS.has(card.card_code);
    const interaction = maintainable
      ? ` data-maintenance-card="${escapeHtml(card.card_code || "")}" role="button" tabindex="0"`
      : "";
    return `
      <article class="report-nav-stat-card ${style.color}${maintainable ? " maintainable" : ""}" data-report-nav-card="${escapeHtml(card.card_code || "")}"${interaction}>
        <div class="report-nav-stat-top">
          <div class="report-nav-stat-icon" aria-hidden="true">${style.icon}</div>
          <div class="report-nav-stat-heading">
            <span>${escapeHtml(card.name || "")}</span>
            <strong>${Number(card.total_count || 0)}<small>${style.unit}</small></strong>
          </div>
        </div>
        <div class="report-nav-stat-progress-row"><span>完成率</span><i><b style="width:${rate}%"></b></i><em>${rate.toFixed(rate % 1 ? 1 : 0)}%</em></div>
        <div class="report-nav-stat-tags"><span class="up">已完成 ${Number(card.completed_count || 0)}</span><span class="warn">未完成 ${Number(card.incomplete_count || 0)}</span></div>
      </article>`;
  }).join("");
}

function closeReportNavigationCardMaintenance() {
  if (!reportNavCardMaintenanceModal || reportNavCardMaintenanceModal.hidden) return;
  reportNavCardMaintenanceModal.classList.add("closing");
  setTimeout(() => {
    reportNavCardMaintenanceModal.hidden = true;
    reportNavCardMaintenanceModal.classList.remove("closing");
    reportNavCardMaintenanceModal.dataset.cardCode = "";
  }, 200);
}

function openReportNavigationCardMaintenance(cardCode) {
  if (
    authState.user?.role !== "admin"
    || !REPORT_NAV_MAINTAINABLE_CARDS.has(cardCode)
    || !reportNavCardMaintenanceModal
    || !reportNavCardMaintenanceGrid
  ) return;
  const card = (reportNavigationPayload?.cards || []).find((item) => item.card_code === cardCode);
  const values = reportNavigationPayload?.card_maintenance?.[cardCode] || {};
  reportNavCardMaintenanceTitle.textContent = `维护${card?.name || "治理统计"}`;
  reportNavCardMaintenanceGrid.innerHTML = `
    <span class="report-nav-card-maintenance-header">统计周期</span>
    <span class="report-nav-card-maintenance-header">已完成</span>
    <span class="report-nav-card-maintenance-header">未完成</span>
    ${REPORT_NAV_MAINTENANCE_PERIODS.map(([period, label]) => {
      const row = values[period] || {};
      return `<strong>${label}</strong>
        <input class="prompt-input" type="number" min="0" step="1" inputmode="numeric" data-maintenance-period="${period}" data-maintenance-count="completed_count" value="${Number(row.completed_count || 0)}" aria-label="${label}已完成数量" />
        <input class="prompt-input" type="number" min="0" step="1" inputmode="numeric" data-maintenance-period="${period}" data-maintenance-count="incomplete_count" value="${Number(row.incomplete_count || 0)}" aria-label="${label}未完成数量" />`;
    }).join("")}`;
  reportNavCardMaintenanceModal.dataset.cardCode = cardCode;
  reportNavCardMaintenanceModal.hidden = false;
  setTimeout(() => reportNavCardMaintenanceGrid.querySelector("input")?.focus(), 0);
}

reportNavCardMaintenanceClose?.addEventListener("click", closeReportNavigationCardMaintenance);
reportNavCardMaintenanceCancel?.addEventListener("click", closeReportNavigationCardMaintenance);
reportNavCardMaintenanceModal?.addEventListener("click", (event) => {
  if (event.target === reportNavCardMaintenanceModal) closeReportNavigationCardMaintenance();
});

reportNavCardMaintenanceSave?.addEventListener("click", async () => {
  const cardCode = reportNavCardMaintenanceModal?.dataset.cardCode || "";
  if (!REPORT_NAV_MAINTAINABLE_CARDS.has(cardCode) || reportNavCardMaintenanceSave.disabled) return;
  const values = {};
  for (const [period] of REPORT_NAV_MAINTENANCE_PERIODS) {
    const completedInput = reportNavCardMaintenanceGrid.querySelector(`[data-maintenance-period="${period}"][data-maintenance-count="completed_count"]`);
    const incompleteInput = reportNavCardMaintenanceGrid.querySelector(`[data-maintenance-period="${period}"][data-maintenance-count="incomplete_count"]`);
    const completedCount = Number(completedInput?.value);
    const incompleteCount = Number(incompleteInput?.value);
    if (
      !Number.isInteger(completedCount)
      || !Number.isInteger(incompleteCount)
      || completedCount < 0
      || incompleteCount < 0
    ) {
      showToast("已完成和未完成数量必须为不小于 0 的整数", "error");
      return;
    }
    values[period] = {
      completed_count: completedCount,
      incomplete_count: incompleteCount,
    };
  }
  reportNavCardMaintenanceSave.disabled = true;
  try {
    await api(`/api/report-navigation/cards/${encodeURIComponent(cardCode)}`, {
      method: "POST",
      body: JSON.stringify({ values }),
    });
    closeReportNavigationCardMaintenance();
    await loadReportNavigation();
    showToast("治理统计已保存", "success");
  } catch (error) {
    showToast(`治理统计保存失败：${error.message}`, "error");
  } finally {
    reportNavCardMaintenanceSave.disabled = false;
  }
});

reportNavStats?.addEventListener("click", (event) => {
  const card = event.target.closest("[data-maintenance-card]");
  if (card) openReportNavigationCardMaintenance(card.dataset.maintenanceCard);
});

reportNavStats?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const card = event.target.closest("[data-maintenance-card]");
  if (!card) return;
  event.preventDefault();
  openReportNavigationCardMaintenance(card.dataset.maintenanceCard);
});

function reportNavigationScheduleName(process) {
  const labels = {
    pbc_central: "人行大集中报送",
    pbc_template: "资管产品模板、逐笔",
    jr_1104: "1104",
    full_elements: "全要素",
    citic_registration: "中信登",
    east5: "East5",
    five_articles: "五篇大文章",
  };
  return labels[process.process_code] || process.process_name || process.process_code;
}

function renderReportNavigationSchedules(processes, reportMonth) {
  if (!reportNavSchedules) return;
  const groups = [
    ["人行", new Set(["pbc_central", "pbc_template"])],
    ["金监", new Set(["jr_1104", "full_elements", "citic_registration", "east5", "five_articles"])],
  ];
  reportNavSchedules.innerHTML = groups.map(([groupName, codes]) => {
    const items = processes.filter((process) => codes.has(process.process_code));
    if (!items.length) return "";
    const itemByCode = new Map(items.map((process) => [process.process_code, process]));
    const groupRows = groupName === "金监"
      ? [["jr_1104", "full_elements"], ["citic_registration", "east5", "five_articles"]]
      : [["pbc_central"], ["pbc_template"]];
    const renderItem = (process) => {
      const editable = process.schedule_editable && process.report_date;
      const title = editable ? "双击修改报送日期" : "";
      return `<span class="report-nav-schedule-item"><b>${escapeHtml(reportNavigationScheduleName(process))}</b><span class="report-nav-schedule-separator">：</span><time data-schedule-process="${escapeHtml(process.process_code)}" data-report-month="${escapeHtml(reportMonth)}" data-report-date="${escapeHtml(process.report_date || "")}" class="${editable ? "editable" : ""}" title="${title}">${escapeHtml(reportNavigationDateText(process.report_date))}</time></span>`;
    };
    const rows = groupRows.map((rowCodes) => rowCodes
      .map((code) => itemByCode.get(code))
      .filter(Boolean)
      .map(renderItem)
      .join(""))
      .filter(Boolean)
      .map((row) => `<span class="report-nav-schedule-row">${row}</span>`)
      .join("");
    const rowsClass = groupName === "金监" ? "regulator" : "pbc";
    return `<div class="report-nav-batch"><strong>${groupName}</strong><p class="report-nav-schedule-rows ${rowsClass}">${rows}</p></div>`;
  }).join("");
}

function updateReportNavigationRefreshButton() {
  if (!reportNavRefreshButton) return;
  const remainingSeconds = Math.max(0, Math.ceil((reportNavigationRefreshCooldownUntil - Date.now()) / 1000));
  const disabled = reportNavigationRefreshBusy || reportNavigationRefreshRemoteRunning || remainingSeconds > 0;
  reportNavRefreshButton.disabled = disabled;
  if (reportNavigationRefreshBusy || reportNavigationRefreshRemoteRunning) {
    reportNavRefreshButton.title = "统计刷新中";
  } else if (remainingSeconds > 0) {
    const minutes = Math.floor(remainingSeconds / 60);
    const seconds = remainingSeconds % 60;
    reportNavRefreshButton.title = `请等待 ${minutes}:${String(seconds).padStart(2, "0")} 后再次刷新`;
  } else {
    reportNavRefreshButton.title = "立即刷新";
  }
  if (reportNavRefreshCountdown) {
    const minutes = Math.floor(remainingSeconds / 60);
    const seconds = remainingSeconds % 60;
    reportNavRefreshCountdown.textContent = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    reportNavRefreshCountdown.hidden = remainingSeconds <= 0;
  }
  if (remainingSeconds === 0 && reportNavigationRefreshTimer) {
    clearInterval(reportNavigationRefreshTimer);
    reportNavigationRefreshTimer = null;
  }
}

function renderReportNavigationRefreshIssues(issues = []) {
  const rows = issues.map((issue) => {
    const location = [issue.process_name, issue.step_name].filter(Boolean).join(" / ") || issue.step_code || "未知步骤";
    const reason = issue.error_message || "未返回具体错误原因";
    return `<li><strong>${escapeHtml(location)}</strong><span>${escapeHtml(reason)}</span></li>`;
  }).join("");
  return `<div class="report-nav-refresh-issues">
    <p>本次刷新有 ${issues.length} 个步骤统计异常，请根据以下信息检查数据源、表和字段配置。</p>
    <ul class="report-nav-refresh-issue-list">${rows}</ul>
  </div>`;
}

function setReportNavigationRefreshCooldown(seconds) {
  const cooldownSeconds = Math.max(0, Number(seconds) || 0);
  reportNavigationRefreshCooldownUntil = Date.now() + cooldownSeconds * 1000;
  if (reportNavigationRefreshTimer) clearInterval(reportNavigationRefreshTimer);
  reportNavigationRefreshTimer = cooldownSeconds > 0
    ? setInterval(updateReportNavigationRefreshButton, 1000)
    : null;
  updateReportNavigationRefreshButton();
}

function renderReportNavigationStep(step, reportMonth) {
  const completed = step.status === "completed";
  const stateClass = completed ? "completed" : (step.status === "error" ? "error" : "pending");
  const actionable = step.manual_completion_allowed && (step.manual_completed || !completed);
  const actionClass = actionable ? " interactive" : "";
  let actionAttributes = "";
  if (actionable) {
    const manualAction = step.manual_completed ? "manual-cancel" : "manual-complete";
    const label = step.manual_completed ? "撤销手工完成" : "标记完成";
    actionAttributes = ` data-step-code="${escapeHtml(step.step_code)}" data-manual-action="${manualAction}" data-report-month="${escapeHtml(reportMonth)}" role="button" tabindex="0" aria-label="${label}：${escapeHtml(step.step_name || "")}"`;
  }
  const message = step.error_message || step.status_message || "";
  return `<p class="report-nav-step ${stateClass}${actionClass}"${actionAttributes} title="${escapeHtml(message)}"><span>${escapeHtml(step.step_name || "")}</span></p>`;
}

function reportNavigationPanelWidth(steps = []) {
  const longestStepLength = steps.reduce(
    (longest, step) => Math.max(longest, Array.from(String(step.step_name || "")).length),
    0,
  );
  return Math.min(340, Math.max(250, longestStepLength * 12 + 56));
}

function reportNavigationSpineProgress(processes = []) {
  if (!processes.length) return 0;
  let completedPrefixCount = 0;
  for (const process of processes) {
    if (process.status !== "completed") break;
    completedPrefixCount += 1;
  }
  if (completedPrefixCount === 0) return 0;
  if (completedPrefixCount === processes.length) return 100;
  return ((completedPrefixCount - 0.5) / processes.length) * 100;
}

function renderReportNavigationProcesses(payload) {
  if (!reportNavBranches) return;
  const month = Number(String(payload.report_month || "").slice(5, 7));
  const processes = (payload.processes || []).filter((process) => {
    if (process.process_code === "five_articles") return [1, 4, 7, 10].includes(month);
    return true;
  });
  const panelHiddenProcessCodes = new Set(["full_elements", "east5", "five_articles"]);
  const spineProgress = reportNavigationSpineProgress(processes);
  const allProcessesCompleted = processes.length > 0
    && processes.every((process) => process.status === "completed");
  reportNavBranches.closest(".report-nav-fishbone")?.classList.toggle("all-done", allProcessesCompleted);
  reportNavFishboneSpine?.style.setProperty("--report-nav-spine-progress", `${spineProgress}%`);
  reportNavBranches.style.setProperty("--report-nav-branch-count", String(Math.max(processes.length, 1)));
  reportNavBranches.innerHTML = processes.map((process, index) => {
    const done = process.status === "completed";
    const side = index % 2 === 0 ? "top" : "bottom";
    const steps = process.steps || [];
    const showPanel = steps.length > 0 && !panelHiddenProcessCodes.has(process.process_code);
    const panelClass = showPanel ? "" : " no-panel";
    const panelWidth = reportNavigationPanelWidth(steps);
    const panel = showPanel ? `
      <div class="report-nav-branch-panel" style="--report-nav-panel-width: ${panelWidth}px">
        <div class="report-nav-panel-status">${done ? "DONE · " : "进度 · "}${Number(process.completed_steps || 0)}/${Number(process.total_steps || steps.length)}</div>
        ${steps.map((step) => renderReportNavigationStep(step, payload.report_month)).join("")}
        ${done && process.completed_at ? `<div class="report-nav-done-meta">✓ 完成于 ${escapeHtml(process.completed_at)}</div>` : ""}
      </div>` : "";
    const noPanelCompletion = !showPanel && done && process.completed_at
      ? `<div class="report-nav-no-panel-done-meta">完成于 ${escapeHtml(process.completed_at)}</div>`
      : "";
    return `<div class="report-nav-branch ${side}${done ? " done" : ""}${panelClass}">
      <div class="report-nav-branch-line"></div><div class="report-nav-branch-node"></div>
      <div class="report-nav-branch-label">${done ? "<span>✓</span>" : ""}${escapeHtml(process.process_name || "")}</div>
      ${noPanelCompletion}
      ${panel}
    </div>`;
  }).join("");
}

function renderReportNavigation(payload) {
  reportNavigationPayload = payload;
  renderReportNavigationCards(payload.cards || []);
  const month = Number(String(payload.report_month || "").slice(5, 7));
  const processes = (payload.processes || []).filter((process) => {
    if (process.process_code === "five_articles") return [1, 4, 7, 10].includes(month);
    return true;
  });
  renderReportNavigationSchedules(processes, payload.report_month || "");
  renderReportNavigationProcesses({ ...payload, processes });
  const refreshState = payload.manual_refresh || {};
  reportNavigationRefreshRemoteRunning = Boolean(refreshState.running);
  setReportNavigationRefreshCooldown(Number(refreshState.retry_after_seconds || 0));
  if (reportNavLastRun) {
    const run = payload.last_run;
    reportNavLastRun.textContent = run
      ? `最近更新：${run.finished_at || run.started_at || "--"}${run.status === "failed" ? "（失败）" : ""}`
      : "等待定时任务首次统计";
  }
  if (reportNavStatus) {
    const failed = payload.last_run?.status === "failed";
    reportNavStatus.classList.toggle("error", failed);
    reportNavStatus.classList.toggle("ready", Boolean(payload.last_run) && !failed);
    reportNavStatus.textContent = failed
      ? "最近一次统计失败，当前保留显示上次成功快照，请检查任务日志。"
      : (payload.last_run ? "" : "尚无统计快照，页面将在定时任务完成后自动显示结果。");
  }
}

async function loadReportNavigation() {
  if (reportNavigationLoading) return;
  reportNavigationLoading = true;
  const period = reportNavPeriodSelect?.value || "month";
  if (reportNavStatus) {
    reportNavStatus.classList.remove("ready", "error");
    reportNavStatus.textContent = "正在读取最新统计结果…";
  }
  try {
    const payload = await api(`/api/report-navigation/dashboard?period=${encodeURIComponent(period)}`);
    renderReportNavigation(payload);
  } catch (error) {
    if (reportNavStatus) {
      reportNavStatus.classList.add("error");
      reportNavStatus.textContent = `统计结果读取失败：${error.message}`;
    }
  } finally {
    reportNavigationLoading = false;
  }
}

reportNavPeriodSelect?.addEventListener("change", () => loadReportNavigation());

reportNavRefreshButton?.addEventListener("click", async () => {
  if (reportNavRefreshButton.disabled || reportNavigationRefreshBusy) return;
  reportNavigationRefreshBusy = true;
  reportNavigationRefreshRemoteRunning = false;
  reportNavRefreshButton.classList.add("refreshing");
  updateReportNavigationRefreshButton();
  try {
    const result = await api("/api/report-navigation/refresh", {
      method: "POST",
      body: JSON.stringify({}),
    });
    setReportNavigationRefreshCooldown(
      Number(result.retry_after_seconds ?? result.cooldown_seconds ?? REPORT_NAV_REFRESH_COOLDOWN_SECONDS),
    );
    await loadReportNavigation();
    if (result.status === "partial") {
      const issues = result.issues || [];
      if (issues.length) {
        showInfo("报送导航统计异常", renderReportNavigationRefreshIssues(issues), { closeOnBackdrop: false });
      } else {
        showToast(result.error_message || "刷新完成，但部分步骤统计异常", "error");
      }
    } else {
      showToast("报送导航统计已刷新", "success");
    }
  } catch (error) {
    const retryAfterSeconds = Number(error.payload?.retry_after_seconds || 0);
    if (retryAfterSeconds > 0) setReportNavigationRefreshCooldown(retryAfterSeconds);
    showToast(`报送导航刷新失败：${error.message}`, "error");
    await loadReportNavigation();
  } finally {
    reportNavigationRefreshBusy = false;
    reportNavRefreshButton.classList.remove("refreshing");
    updateReportNavigationRefreshButton();
  }
});

reportNavSchedules?.addEventListener("dblclick", async (event) => {
  const target = event.target.closest("time[data-schedule-process]");
  if (!target?.classList.contains("editable") || authState.user?.role !== "admin") return;
  const nextDate = await showPrompt("修改报送日期", "请选择新的报送日期", {
    type: "date",
    defaultValue: target.dataset.reportDate || "",
    placeholder: "YYYY-MM-DD",
  });
  if (!nextDate || nextDate === target.dataset.reportDate) return;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(nextDate)) {
    showToast("请输入 YYYY-MM-DD 格式的日期", "error");
    return;
  }
  const confirmed = await showConfirm("修改报送日期", `确认将报送日期修改为 ${nextDate} 吗？`);
  if (!confirmed) return;
  try {
    const result = await api(`/api/report-navigation/schedules/${encodeURIComponent(target.dataset.scheduleProcess)}`, {
      method: "POST",
      body: JSON.stringify({ report_month: target.dataset.reportMonth, report_date: nextDate }),
    });
    if (result.statistics_status === "failed") {
      showToast(`报送日期已更新，但状态重算失败：${result.statistics_error || "未知错误"}`, "error");
    } else if (result.statistics_status === "skipped") {
      showToast("报送日期已更新，当前已有统计任务执行中，请稍后刷新查看最新状态", "warning");
    } else {
      showToast("报送日期已更新，流程状态已重新统计", "success");
    }
    await loadReportNavigation();
  } catch (error) {
    showToast(error.message, "error");
  }
});

async function handleReportNavigationManualAction(stepRow) {
  if (!stepRow || stepRow.classList.contains("busy") || authState.user?.role !== "admin") return;
  const isCancel = stepRow.dataset.manualAction === "manual-cancel";
  const confirmed = await showConfirm(
    isCancel ? "撤销手工完成" : "标记步骤完成",
    isCancel ? "撤销后将恢复该步骤最近一次自动统计状态，确认继续吗？" : "确认将该步骤手工标记为已完成吗？",
  );
  if (!confirmed) return;
  stepRow.classList.add("busy");
  stepRow.setAttribute("aria-disabled", "true");
  try {
    await api(`/api/report-navigation/steps/${encodeURIComponent(stepRow.dataset.stepCode)}/${stepRow.dataset.manualAction}`, {
      method: "POST",
      body: JSON.stringify({ report_month: stepRow.dataset.reportMonth }),
    });
    showToast(isCancel ? "已恢复自动统计状态" : "已标记完成", "success");
    await loadReportNavigation();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    stepRow.classList.remove("busy");
    stepRow.removeAttribute("aria-disabled");
  }
}

reportNavBranches?.addEventListener("click", (event) => {
  const stepRow = event.target.closest(".report-nav-step[data-manual-action]");
  handleReportNavigationManualAction(stepRow);
});

reportNavBranches?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const stepRow = event.target.closest(".report-nav-step[data-manual-action]");
  if (!stepRow) return;
  event.preventDefault();
  handleReportNavigationManualAction(stepRow);
});

async function encryptPasswordForTransport(password) {
  return window.autoCheckCrypto.encryptPasswordForTransport(password, () => api("/api/auth/key"));
}

async function logout() {
  const confirmed = await showConfirm("退出登录", "确认退出当前账号并返回登录页吗？");
  if (!confirmed) return;
  const interfaceRadiusSnapshot = captureInterfaceRadiusPreference();
  const logoutAuthRevision = resetInterfaceRadiusForAuthChange();
  try {
    await api("/api/auth/logout", { method: "POST", body: JSON.stringify({}) });
  } catch (error) {
    if (restoreInterfaceRadiusPreference(interfaceRadiusSnapshot, logoutAuthRevision)) {
      showToast(error.message, "error");
    }
    return;
  }
  if (logoutAuthRevision !== interfaceRadiusState.authRevision) return;
  authState.csrfToken = "";
  try { sessionStorage.removeItem(USER_AVATAR_SESSION_KEY); } catch (_) {}
  window.location.href = "/login.html";
}

document.querySelectorAll("[data-logout-btn]").forEach((button) => {
  button.addEventListener("click", logout);
});

function updateCurrentUsername() {
  const username = authState.user?.username || "admin";
  const displayName = userDisplayName(authState.user);
  const initial = userAvatarInitial(displayName || username);
  const [from, to] = currentUserAvatarGradient();
  document.querySelectorAll("[data-current-username]").forEach((item) => {
    const nameText = item.querySelector("[data-current-username-text]");
    if (nameText) nameText.textContent = displayName;
    const avatar = item.querySelector("[data-current-user-avatar]");
    if (avatar) {
      avatar.textContent = initial;
      avatar.style.setProperty("--avatar-from", from);
      avatar.style.setProperty("--avatar-to", to);
    }
    item.title = `${displayName} (${username})`;
  });
}

function userDisplayName(user) {
  return String(user?.display_name || user?.username || "").trim() || "admin";
}

function userAvatarInitial(value) {
  const text = String(value || "").trim();
  return (Array.from(text)[0] || "A").toUpperCase();
}

function currentUserAvatarGradient() {
  let index = -1;
  try {
    index = Number(sessionStorage.getItem(USER_AVATAR_SESSION_KEY));
    if (!Number.isInteger(index) || index < 0 || index >= USER_AVATAR_GRADIENTS.length) {
      index = Math.floor(Math.random() * USER_AVATAR_GRADIENTS.length);
      sessionStorage.setItem(USER_AVATAR_SESSION_KEY, String(index));
    }
  } catch (_) {
    index = Math.floor(Math.random() * USER_AVATAR_GRADIENTS.length);
  }
  return USER_AVATAR_GRADIENTS[index] || USER_AVATAR_GRADIENTS[0];
}

function userDisplayRole(role) {
  return role === "admin" ? "管理员" : "普通用户";
}

function userDisplayStatus(user) {
  return user.enabled === false ? "已停用" : "已启用";
}

function isInitialAdminAccount(user) {
  return String(user?.username || "").toLowerCase() === "admin";
}

function isDelegatedAdminSession() {
  return authState.user?.role === "admin" && !isInitialAdminAccount(authState.user);
}

function currentUserCanEditUser(user) {
  return !(isDelegatedAdminSession() && (user?.role || "user") === "admin");
}

function editingUserFromModal() {
  const editingId = userId?.value || "";
  return managedUsers.find((user) => user.id === editingId) || null;
}

function filteredUsers() {
  const keyword = (userSearch?.value || "").trim().toLowerCase();
  const role = userQuickFilter === "admin" || userQuickFilter === "user" ? userQuickFilter : (userRoleFilter?.value || "");
  const status = userQuickFilter === "enabled" || userQuickFilter === "disabled" ? userQuickFilter : (userStatusFilter?.value || "");
  return managedUsers.filter((user) => {
    const normalizedRole = user.role || "user";
    const enabled = user.enabled !== false;
    const displayName = userDisplayName(user);
    const hitKeyword = !keyword
      || String(user.username || "").toLowerCase().includes(keyword)
      || displayName.toLowerCase().includes(keyword)
      || userDisplayRole(normalizedRole).toLowerCase().includes(keyword)
      || normalizedRole.includes(keyword);
    const hitRole = !role || normalizedRole === role;
    const hitStatus = !status || (status === "enabled" ? enabled : !enabled);
    return hitKeyword && hitRole && hitStatus;
  });
}

function renderUserStats() {
  const total = managedUsers.length;
  const adminCount = managedUsers.filter((user) => user.role === "admin").length;
  const regularCount = total - adminCount;
  const enabledCount = managedUsers.filter((user) => user.enabled !== false).length;
  const disabledCount = total - enabledCount;
  const totalEl = document.getElementById("userStatTotal");
  const adminEl = document.getElementById("userStatAdmin");
  const enabledEl = document.getElementById("userStatEnabled");
  const disabledEl = document.getElementById("userStatDisabled");
  const adminHint = document.getElementById("userStatAdminHint");
  const enabledHint = document.getElementById("userStatEnabledHint");
  if (totalEl) totalEl.textContent = String(total);
  if (adminEl) adminEl.textContent = String(adminCount);
  if (enabledEl) enabledEl.textContent = String(enabledCount);
  if (disabledEl) disabledEl.textContent = String(disabledCount);
  if (adminHint) adminHint.textContent = `占比 ${total ? Math.round((adminCount / total) * 1000) / 10 : 0}%`;
  if (enabledHint) enabledHint.textContent = `活跃率 ${total ? Math.round((enabledCount / total) * 1000) / 10 : 0}%`;
  const counts = {
    userFilterAllCount: total,
    userFilterAdminCount: adminCount,
    userFilterUserCount: regularCount,
    userFilterEnabledCount: enabledCount,
    userFilterDisabledCount: disabledCount,
  };
  Object.entries(counts).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.textContent = String(value);
  });
}

function setUserQuickFilter(filter) {
  userQuickFilter = filter || "all";
  userCurrentPage = 1;
  if (userRoleFilter) userRoleFilter.value = userQuickFilter === "admin" || userQuickFilter === "user" ? userQuickFilter : "";
  if (userStatusFilter) userStatusFilter.value = userQuickFilter === "enabled" || userQuickFilter === "disabled" ? userQuickFilter : "";
  document.querySelectorAll("[data-user-filter]").forEach((button) => {
    button.classList.toggle("active", button.dataset.userFilter === userQuickFilter);
  });
  renderUsers();
}

function paginatedUsers(users) {
  const pageCount = Math.max(1, Math.ceil(users.length / USER_PAGE_SIZE));
  userCurrentPage = Math.min(Math.max(1, userCurrentPage), pageCount);
  const start = (userCurrentPage - 1) * USER_PAGE_SIZE;
  return users.slice(start, start + USER_PAGE_SIZE);
}

function updateUserPagination(total) {
  const pageCount = Math.max(1, Math.ceil(total / USER_PAGE_SIZE));
  userCurrentPage = Math.min(Math.max(1, userCurrentPage), pageCount);
  if (userPageInfo) userPageInfo.textContent = `共 ${total} 条 · 第 ${userCurrentPage}/${pageCount} 页`;
  if (userPrevPage) userPrevPage.disabled = userCurrentPage <= 1;
  if (userNextPage) userNextPage.disabled = userCurrentPage >= pageCount;
}

function renderUsers() {
  if (!userTableBody) return;
  renderUserStats();
  const allUsers = filteredUsers();
  updateUserPagination(allUsers.length);
  const users = paginatedUsers(allUsers);
  if (!users.length) {
    userTableBody.innerHTML = '<tr><td colspan="6" class="empty">暂无用户数据</td></tr>';
    return;
  }
  userTableBody.innerHTML = users.map((user) => {
    const role = user.role || "user";
    const enabled = user.enabled !== false;
    const isInitialAdmin = user.username === "admin";
    const canEdit = currentUserCanEditUser(user);
    const toggleDisabled = isInitialAdmin || !canEdit;
    const deleteDisabled = isInitialAdmin || !canEdit;
    const isCurrentUser = user.id && user.id === authState.user?.id;
    const displayName = userDisplayName(user);
    const initials = String(displayName || user.username || "?").slice(0, 2).toUpperCase();
    const roleIcon = role === "admin" ? "🛡️" : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M5 20a7 7 0 0 1 14 0"/></svg>';
    const adminLockedTitle = "委派管理员不可操作管理员用户";
    return `<tr>
      <td>
        <div class="user-cell">
          <span class="user-avatar-wrap">
            <span class="user-avatar ${isCurrentUser ? "is-online" : ""}">${escapeHtml(initials)}</span>
            ${isCurrentUser ? '<span class="user-avatar-status" title="在线"></span>' : ""}
          </span>
          <div class="user-name-stack">
            <span class="user-name-line">
              <strong>${escapeHtml(displayName)}</strong>
              ${isCurrentUser ? '<span class="current-user-badge">我</span>' : ""}
            </span>
            <small>${escapeHtml(user.username || "")}</small>
          </div>
        </div>
      </td>
      <td><span class="role-badge role-badge--${escapeHtml(role)}"><span class="role-badge-icon">${roleIcon}</span>${escapeHtml(userDisplayRole(role))}</span></td>
      <td><span class="user-status-badge ${enabled ? "enabled" : "disabled"}">${escapeHtml(userDisplayStatus(user))}</span></td>
      <td>${escapeHtml(formatDisplayTime(user.created_at || ""))}</td>
      <td>${escapeHtml(user.last_login_at ? formatDisplayTime(user.last_login_at) : "-")}</td>
      <td class="user-actions-cell">
        <div class="user-actions">
          <button class="user-icon-action edit-user" data-id="${escapeHtml(user.id || "")}" title="${canEdit ? "编辑" : adminLockedTitle}" ${canEdit ? "" : "disabled"}>✏️</button>
          <button class="user-icon-action toggle-user" data-id="${escapeHtml(user.id || "")}" title="${isInitialAdmin ? "初始管理员不可停用" : (!canEdit ? adminLockedTitle : (enabled ? "停用" : "启用"))}" ${toggleDisabled ? "disabled" : ""}>${enabled ? "⏸️" : "▶️"}</button>
          <button class="user-icon-action delete-user" data-id="${escapeHtml(user.id || "")}" title="${isInitialAdmin ? "初始管理员不可删除" : (!canEdit ? adminLockedTitle : "删除")}" ${deleteDisabled ? "disabled" : ""}>🗑️</button>
        </div>
      </td>
    </tr>`;
  }).join("");
}

function renderUsersLoading() {
  if (!userTableBody) return;
  if (userPageInfo) userPageInfo.textContent = "加载中...";
  if (userPrevPage) userPrevPage.disabled = true;
  if (userNextPage) userNextPage.disabled = true;
  const rows = Array.from({ length: Math.min(USER_PAGE_SIZE, 6) }, () => `
    <tr class="user-loading-row">
      <td><span class="user-skeleton user-skeleton-name"></span><span class="user-skeleton user-skeleton-sub"></span></td>
      <td><span class="user-skeleton user-skeleton-pill"></span></td>
      <td><span class="user-skeleton user-skeleton-pill"></span></td>
      <td><span class="user-skeleton user-skeleton-time"></span></td>
      <td><span class="user-skeleton user-skeleton-time"></span></td>
      <td><span class="user-skeleton user-skeleton-actions"></span></td>
    </tr>
  `);
  userTableBody.innerHTML = rows.join("");
}

function syncUserRoleCards() {
  const currentRole = userRole?.value || "user";
  const editingUser = editingUserFromModal();
  const roleLocked = isInitialAdminAccount(editingUser);
  const adminChoiceDisabled = roleLocked || isDelegatedAdminSession();
  document.querySelectorAll("[data-user-role-card]").forEach((card) => {
    const selected = card.dataset.userRoleCard === currentRole;
    const disabled = card.dataset.userRoleCard === "admin" ? adminChoiceDisabled : roleLocked;
    card.classList.toggle("selected", selected);
    card.classList.toggle("disabled", disabled);
    card.setAttribute("aria-disabled", disabled ? "true" : "false");
    card.title = disabled ? (roleLocked ? "初始管理员角色不可修改" : "委派管理员不可创建或设置管理员") : "";
    const input = card.querySelector('input[name="userRoleChoice"]');
    if (input) {
      input.checked = selected;
      input.disabled = disabled;
    }
  });
}

function syncUserEnabledSwitch() {
  const enabled = userEnabled?.value !== "false";
  const editingUser = editingUserFromModal();
  const locked = isInitialAdminAccount(editingUser);
  if (!userEnabledSwitch) return;
  userEnabledSwitch.classList.toggle("on", enabled);
  userEnabledSwitch.disabled = locked;
  userEnabledSwitch.setAttribute("aria-pressed", enabled ? "true" : "false");
  userEnabledSwitch.title = locked ? "初始管理员不可禁用" : "";
  userEnabledSwitch.closest(".user-enable-row")?.classList.toggle("disabled", locked);
}

async function loadUsers({ force = false } = {}) {
  if (authState.user?.role !== "admin" || !userTableBody) return;
  if (usersLoading) return;
  if (!usersLoaded || force) {
    renderUsersLoading();
  } else {
    renderUsers();
  }
  usersLoading = true;
  try {
    const payload = await api("/api/users");
    managedUsers = payload.users || [];
    usersLoaded = true;
    renderUsers();
  } catch (error) {
    userTableBody.innerHTML = `<tr><td colspan="6" class="empty">${escapeHtml(error.message)}</td></tr>`;
  } finally {
    usersLoading = false;
  }
}

function openUserModal(user = null) {
  if (!userModal) return;
  if (user && !currentUserCanEditUser(user)) {
    showToast("委派管理员不可编辑管理员用户", "warning");
    return;
  }
  const isEdit = Boolean(user);
  userId.value = user?.id || "";
  userUsername.value = user?.username || "";
  const displayNameValue = isEdit ? userDisplayName(user) : "";
  if (userDisplayNameInput) {
    userDisplayNameInput.value = displayNameValue;
    userDisplayNameInput.defaultValue = displayNameValue;
  }
  userUsername.readOnly = isEdit;
  userRole.value = isDelegatedAdminSession() ? "user" : (user?.role || "user");
  userEnabled.value = isInitialAdminAccount(user) ? "true" : (user?.enabled === false ? "false" : "true");
  userPassword.value = "";
  userPassword.placeholder = isEdit ? "留空则不修改密码" : "请输入至少 6 位且包含字母的密码";
  userModalTitle.textContent = isEdit ? "编辑用户" : "新建用户";
  userModalStatus.textContent = "";
  syncUserRoleCards();
  syncUserEnabledSwitch();
  userModal.hidden = false;
  if (!isEdit) {
    requestAnimationFrame(() => {
      if (!userId.value && userDisplayNameInput) userDisplayNameInput.value = "";
    });
  }
}

function closeUserModal() {
  if (!userModal) return;
  userModal.hidden = true;
}

function userFriendlyError(message = "") {
  const text = String(message || "");
  if (text.includes("username contains unsupported characters")) {
    return "用户名仅支持英文字母、数字、下划线(_)、中横线(-)和点(.)，不支持中文、空格及其他特殊字符；中文姓名请填写在用户姓名。";
  }
  return text || "操作失败";
}

async function saveUser() {
  if (!userModalSave) return;
  const editingId = userId.value;
  const rawPassword = userPassword.value;
  const editingUser = editingUserFromModal();
  const payload = {
    username: userUsername.value.trim(),
    display_name: userDisplayNameInput?.value.trim() || "",
    role: userRole.value,
    enabled: userEnabled.value === "true",
  };
  if (isDelegatedAdminSession()) {
    payload.role = "user";
  }
  if (isInitialAdminAccount(editingUser)) {
    payload.role = "admin";
    payload.enabled = true;
  }
  if (!payload.username) {
    userModalStatus.textContent = "请填写用户名";
    return;
  }
  if (!editingId || rawPassword) {
    payload.password_encrypted = await encryptPasswordForTransport(rawPassword);
  }
  userModalSave.disabled = true;
  userModalStatus.textContent = "保存中...";
  try {
    if (editingId) {
      const targetUserId = editingId;
      const updatePayload = { username: payload.username, display_name: payload.display_name, role: payload.role, enabled: payload.enabled };
      await api(`/api/users/${encodeURIComponent(targetUserId)}`, {
        method: "PUT",
        body: JSON.stringify(updatePayload),
      });
      if (rawPassword) {
        await api(`/api/users/${encodeURIComponent(targetUserId)}/reset-password`, {
          method: "POST",
          body: JSON.stringify({ password_encrypted: payload.password_encrypted }),
        });
      }
      if (targetUserId === authState.user?.id) {
        authState.user = { ...authState.user, display_name: payload.display_name || payload.username };
        updateCurrentUsername();
      }
    } else {
      await api("/api/users", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    closeUserModal();
    showToast("用户已保存", "success");
    await loadUsers();
  } catch (error) {
    userModalStatus.textContent = userFriendlyError(error.message);
  } finally {
    userModalSave.disabled = false;
  }
}

async function resetUserPassword(targetUser) {
  const nextPassword = await showPrompt("重置密码", `请输入 ${targetUser.username} 的新密码（至少 6 位且包含字母）`, {
    type: "password",
    autocomplete: "new-password",
  });
  if (!nextPassword) return;
  const password_encrypted = await encryptPasswordForTransport(nextPassword);
  try {
    const userId = targetUser.id;
    await api(`/api/users/${encodeURIComponent(userId)}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ password_encrypted }),
    });
    showToast("密码已重置", "success");
    await loadUsers();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function deleteUser(targetUser) {
  if (targetUser.username === "admin") {
    showToast("初始管理员不可删除", "warning");
    return;
  }
  const confirmed = await showConfirm("删除用户", `确定删除用户 ${targetUser.username} 吗？`);
  if (!confirmed) return;
  try {
    const userId = targetUser.id;
    await api(`/api/users/${encodeURIComponent(userId)}`, { method: "DELETE" });
    showToast("用户已删除", "success");
    await loadUsers();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function toggleUserEnabled(targetUser) {
  if (targetUser.username === "admin") {
    showToast("初始管理员不可停用", "warning");
    return;
  }
  const nextEnabled = targetUser.enabled === false;
  const confirmed = await showConfirm(nextEnabled ? "启用用户" : "停用用户", `确认${nextEnabled ? "启用" : "停用"}用户 ${targetUser.username} 吗？`);
  if (!confirmed) return;
  try {
    const userId = targetUser.id;
    await api(`/api/users/${encodeURIComponent(userId)}`, {
      method: "PUT",
      body: JSON.stringify({ enabled: nextEnabled }),
    });
    showToast(nextEnabled ? "用户已启用" : "用户已停用", "success");
    await loadUsers();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function escapeCsvValue(value) {
  const text = String(value ?? "");
  const formulaPrefixPattern = /^[=+\-@]/;
  const safeText = formulaPrefixPattern.test(text.trimStart()) ? `'${text}` : text;
  return `"${safeText.replace(/"/g, '""')}"`;
}

function exportUsers() {
  const users = filteredUsers();
  const headers = ["用户姓名", "用户账号", "角色", "状态", "创建时间", "最近登录时间"];
  const rows = users.map((user) => [
    userDisplayName(user),
    user.username || "",
    userDisplayRole(user.role || "user"),
    userDisplayStatus(user),
    formatDisplayTime(user.created_at || ""),
    user.last_login_at ? formatDisplayTime(user.last_login_at) : "-",
  ]);
  const csv = [headers, ...rows]
    .map((row) => row.map(escapeCsvValue).join(","))
    .join("\n");
  const blob = new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `users-${formatBeijingDate()}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

document.querySelectorAll("[data-new-user-btn]").forEach((button) => {
  button.addEventListener("click", () => openUserModal());
});
document.querySelectorAll("[data-export-users-btn]").forEach((button) => {
  button.addEventListener("click", exportUsers);
});
userModalClose?.addEventListener("click", closeUserModal);
userModalCancel?.addEventListener("click", closeUserModal);
userModalSave?.addEventListener("click", () => saveUser().catch((error) => { userModalStatus.textContent = userFriendlyError(error.message); }));
document.querySelectorAll('input[name="userRoleChoice"]').forEach((input) => {
  input.addEventListener("change", () => {
    if (!userRole || input.disabled) return;
    userRole.value = input.value;
    syncUserRoleCards();
  });
});
userEnabledSwitch?.addEventListener("click", () => {
  if (!userEnabled || userEnabledSwitch.disabled) return;
  userEnabled.value = userEnabled.value === "false" ? "true" : "false";
  syncUserEnabledSwitch();
});
[userSearch, userRoleFilter, userStatusFilter].forEach((control) => {
  control?.addEventListener("input", () => { userCurrentPage = 1; renderUsers(); });
  control?.addEventListener("change", () => { userCurrentPage = 1; renderUsers(); });
});
userPrevPage?.addEventListener("click", () => {
  userCurrentPage -= 1;
  renderUsers();
});
userNextPage?.addEventListener("click", () => {
  userCurrentPage += 1;
  renderUsers();
});
document.querySelectorAll("[data-user-filter]").forEach((button) => {
  button.addEventListener("click", () => setUserQuickFilter(button.dataset.userFilter || "all"));
});
userTableBody?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-id]");
  if (!button) return;
  const targetUser = managedUsers.find((user) => user.id === button.dataset.id);
  if (!targetUser) return;
  if (button.classList.contains("edit-user")) openUserModal(targetUser);
  if (button.classList.contains("toggle-user")) toggleUserEnabled(targetUser);
  if (button.classList.contains("delete-user")) deleteUser(targetUser);
});

function setStatus(t) {
  const nextText = String(t || "");
  const statusChanged = statusText.textContent !== nextText;
  statusText.textContent = nextText;
  if (statusChanged) {
    statusText.classList.remove("status-msg-enter");
    void statusText.offsetWidth;
    statusText.classList.add("status-msg-enter");
  }

  if (topNavStatus) {
    const topStatusChanged = topNavStatus.textContent !== nextText;
    topNavStatus.textContent = nextText;
    topNavStatus.title = nextText;
    topNavStatus.classList.toggle("top-nav-status--notice", nextText !== DEFAULT_VERSION);
    if (topStatusChanged) {
      topNavStatus.classList.remove("status-msg-enter");
      void topNavStatus.offsetWidth;
      topNavStatus.classList.add("status-msg-enter");
    }
  }

  clearTimeout(statusRestoreTimer);
  statusRestoreTimer = setTimeout(() => {
    statusText.textContent = DEFAULT_VERSION;
    if (topNavStatus) {
      topNavStatus.textContent = DEFAULT_VERSION;
      topNavStatus.title = DEFAULT_VERSION;
      topNavStatus.classList.remove("top-nav-status--notice");
    }
  }, 30000);
}

function formatClockTime() {
  return formatBeijingTime();
}

/* ===== Wave Progress Bar ===== */
let progressAnimationId = null;
let progressRetainTimer = null;

const PROGRESS_RETAIN_MS = 2 * 60 * 1000;

function setWaveProgress(percentage, stepName) {
  const clampedPct = Math.min(Math.max(percentage, 0), 100);
  const displayPct = clampedPct.toFixed(0);
  
  waveProgressBar.style.width = clampedPct + "%";
  waveProgressText.textContent = displayPct + "%";
  if (stepName) {
    waveStepName.textContent = stepName;
  }
}

function showWaveProgress() {
  if (progressRetainTimer) {
    clearTimeout(progressRetainTimer);
    progressRetainTimer = null;
  }
  if (lastRunTime.textContent && !resultRestoreHistoryMeta && !hideLastRunTimeForNoSourceData) lastRunTime.hidden = false;
  waveProgressContainer.hidden = false;
  setWaveProgress(0, reconcileSteps[0].name);
}

function hideWaveProgress() {
  waveProgressContainer.classList.add("run-progress-exit");
  setTimeout(() => {
    waveProgressContainer.hidden = true;
    waveProgressContainer.classList.remove("run-progress-exit");
    lastRunTime.hidden = Boolean(resultRestoreHistoryMeta) || hideLastRunTimeForNoSourceData;
  }, 500);
  if (progressAnimationId) {
    clearInterval(progressAnimationId);
    progressAnimationId = null;
  }
  if (progressRetainTimer) {
    clearTimeout(progressRetainTimer);
    progressRetainTimer = null;
  }
}

function retainProgress() {
  if (progressRetainTimer) {
    clearTimeout(progressRetainTimer);
  }
  progressRetainTimer = setTimeout(() => {
    hideWaveProgress();
    progressRetainTimer = null;
  }, PROGRESS_RETAIN_MS);
}

function animateProgressTo(targetPct, duration = 1500) {
  return new Promise((resolve) => {
    const startPct = parseFloat(waveProgressBar.style.width) || 0;
    const startTime = Date.now();
    
    if (progressAnimationId) {
      clearInterval(progressAnimationId);
    }
    
    progressAnimationId = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const currentPct = startPct + (targetPct - startPct) * easeOutCubic(progress);
      
      setWaveProgress(currentPct);
      
      if (progress >= 1) {
        clearInterval(progressAnimationId);
        progressAnimationId = null;
        resolve();
      }
    }, 16);
  });
}

function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

function formatLastRunTime() {
  return formatBeijingDateTime();
}

function formatDisplayTime(value) {
  if (!value) return "";
  return String(value).replace("T", " ");
}

function normalizeExecutorDisplayName(value, fallback = "未知执行人") {
  const text = String(value || "").trim();
  if (text && text !== "-") return text;
  return fallback;
}

function setLastRunTime(value, executorName = "") {
  const displayTime = formatDisplayTime(value || "");
  if (!displayTime) return;
  hideLastRunTimeForNoSourceData = false;
  latestRunAt = displayTime;
  latestRunExecutor = normalizeExecutorDisplayName(executorName || latestRunExecutor);
  const executor = latestRunExecutor;
  lastRunTime.textContent = `最近执行：${executor}  ${latestRunAt}`;
  lastRunTime.hidden = false;
}

function buildRunCompletionNotice(resultCount, history = {}) {
  return `执行完成，差异 ${resultCount} 条，对比上次新增差异 ${formatHistoryDiffCount(history, "added_count")}，减少差异 ${formatHistoryDiffCount(history, "removed_count")}`;
}

function buildRunCompletionLogMessage(notice, history = {}) {
  const baselineRunAt = formatDisplayTime(history.baseline_run_at || "");
  return `${notice}。上次执行时间 ${baselineRunAt || "无"}`;
}

function saveLatestResultsSnapshot(extra = {}) {
  if (!Array.isArray(results) || (!results.length && !hasReconciled)) return;
  try {
    localStorage.setItem(LATEST_RESULTS_SNAPSHOT_KEY, JSON.stringify({
      results,
      runDate: runDate.value || "",
      runAt: extra.runAt || latestRunAt || "",
      executorName: normalizeExecutorDisplayName(extra.executorName || latestRunExecutor, ""),
      hasReconciled,
      savedAt: formatBeijingDateTime(),
    }));
  } catch (_) {
    // Large result sets can exceed browser storage; history API remains the source of truth.
  }
}

function restoreLatestResultsSnapshot() {
  try {
    const payload = JSON.parse(localStorage.getItem(LATEST_RESULTS_SNAPSHOT_KEY) || "{}");
    if (!Array.isArray(payload.results)) return false;
    results = payload.results;
    if (payload.runDate) runDate.value = payload.runDate;
    hasReconciled = Boolean(payload.hasReconciled);
    resultEmptyState = "";
    clearResultHistoryRestoreState();
    currentPage = 1;
    renderResults();
    if (payload.runAt) setLastRunTime(payload.runAt, payload.executorName || "");
    return true;
  } catch (_) {
    return false;
  }
}

function clearLatestResultsSnapshot() {
  try {
    localStorage.removeItem(LATEST_RESULTS_SNAPSHOT_KEY);
  } catch (_) {
    // Ignore storage failures.
  }
}

function getCombinationLimit() {
  const parsed = parseInt(defaultSettings.combinationLimit || "50", 10);
  if (!Number.isFinite(parsed)) return 50;
  return Math.min(Math.max(parsed, 1), 500);
}

function resetRunLogs() {
  if (!runLogPanel || !runLogList) return;
  runLogPanel.classList.remove("collapsed");
  runLogToggleBtn?.setAttribute("aria-expanded", "true");
  runLogList.innerHTML = "";
  runLogPanel.hidden = true;
}

function renderRunLogs(logs = []) {
  if (!runLogPanel || !runLogList) return;
  if (!logs.length && runLogPanel.hidden) return;
  runLogPanel.hidden = false;
  runLogList.innerHTML = logs.map((log) => (
    `<div class="run-log-line"><span class="run-log-time">${escapeHtml(log.time || "")}</span><span>${escapeHtml(log.message || "")}</span></div>`
  )).join("");
  runLogList.scrollTop = runLogList.scrollHeight;
}

function appendRunLog(message) {
  if (!runLogPanel || !runLogList) return;
  runLogPanel.hidden = false;
  const line = document.createElement("div");
  line.className = "run-log-line";
  line.innerHTML = `<span class="run-log-time">${escapeHtml(formatClockTime())}</span><span>${escapeHtml(message)}</span>`;
  runLogList.appendChild(line);
  runLogList.scrollTop = runLogList.scrollHeight;
}

function setRunningUi(isRunning) {
  runBtn.disabled = isRunning;
  runBtn.classList.toggle("loading", isRunning);
  if (stopRunBtn) {
    stopRunBtn.hidden = !isRunning;
    stopRunBtn.disabled = false;
  }
}

/* ===== Formatting ===== */
function formatMoney(v) {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(String(v));
  if (!Number.isFinite(n)) return String(v);
  return n.toLocaleString("zh-CN", { maximumFractionDigits: 8 });
}

function escapeHtml(v) {
  return String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

/* ===== Custom Selects ===== */
const customSelectStates = new WeakMap();
const customDateStates = new WeakMap();
let customSelectObserver = null;
let customSelectRaf = 0;
const CUSTOM_INPUT_TYPES = new Set(["text", "search", "number", "date", "password", "email", "tel", "url"]);
const CUSTOM_DATE_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

function customSelectText(select) {
  return select.selectedOptions?.[0]?.textContent || select.options?.[select.selectedIndex]?.textContent || "";
}

function customSelectMeasure(select, shell) {
  const rect = select.getBoundingClientRect();
  const style = window.getComputedStyle(select);
  const width = rect.width || parseFloat(style.width) || 0;
  const height = rect.height || parseFloat(style.height) || 32;
  shell.style.setProperty("--select-width", width > 0 ? `${width}px` : "100%");
  shell.style.setProperty("--select-height", `${Math.max(height, 1)}px`);
  shell.style.setProperty("--select-font-size", style.fontSize || "13px");
  shell.style.setProperty("--select-font-weight", style.fontWeight || "400");
}

function customInputMeasure(input, shell) {
  const rect = input.getBoundingClientRect();
  const style = window.getComputedStyle(input);
  const width = rect.width || parseFloat(style.width) || 0;
  const height = rect.height || parseFloat(style.height) || parseFloat(style.minHeight) || 32;
  shell.style.setProperty("--input-width", width > 0 ? `${width}px` : "100%");
  shell.style.setProperty("--input-height", `${Math.max(height, 1)}px`);
  shell.style.setProperty("--input-font-size", style.fontSize || "13px");
  shell.style.setProperty("--input-font-weight", style.fontWeight || "400");
}

function closeCustomSelect(select) {
  const state = customSelectStates.get(select);
  if (!state) return;
  state.shell.classList.remove("custom-select-open");
  state.trigger.setAttribute("aria-expanded", "false");
  state.dropdown.hidden = true;
}

function closeOtherCustomSelects(currentSelect = null) {
  document.querySelectorAll("select.custom-select-native").forEach((select) => {
    if (select !== currentSelect) closeCustomSelect(select);
  });
}

function parseCustomDateValue(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]) - 1;
  const day = Number(match[3]);
  const date = new Date(year, month, day);
  if (date.getFullYear() !== year || date.getMonth() !== month || date.getDate() !== day) return null;
  return date;
}

function formatCustomDateValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function closeCustomDatePicker(input) {
  const state = customDateStates.get(input);
  if (!state) return;
  state.shell.classList.remove("custom-date-open");
  state.dropdown.hidden = true;
}

function closeOtherCustomDatePickers(currentInput = null) {
  document.querySelectorAll("input.custom-date-input").forEach((input) => {
    if (input !== currentInput) closeCustomDatePicker(input);
  });
}

function syncCustomSelect(select) {
  const state = customSelectStates.get(select);
  if (!state) return;
  state.trigger.textContent = customSelectText(select);
  state.trigger.classList.toggle("is-placeholder", !state.trigger.textContent);
  state.trigger.disabled = select.disabled;
  state.shell.classList.toggle("custom-select-disabled", select.disabled);
  state.dropdown.innerHTML = "";
  [...select.options].forEach((option, index) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "custom-select-option";
    item.innerHTML = `<span class="custom-select-option-text" title="${escapeHtml(option.textContent || "")}">${escapeHtml(option.textContent || "")}</span>`;
    item.dataset.value = option.value;
    item.setAttribute("role", "option");
    item.setAttribute("aria-selected", option.selected ? "true" : "false");
    item.disabled = option.disabled;
    if (option.selected) item.classList.add("active");
    item.addEventListener("click", () => {
      if (option.disabled) return;
      select.selectedIndex = index;
      select.dispatchEvent(new Event("input", { bubbles: true }));
      select.dispatchEvent(new Event("change", { bubbles: true }));
      syncCustomSelect(select);
      closeCustomSelect(select);
    });
    state.dropdown.appendChild(item);
  });
}

function positionCustomSelectDropdown(select) {
  const state = customSelectStates.get(select);
  if (!state) return;
  const rect = state.shell.getBoundingClientRect();
  const viewportGap = 16;
  const dropdownGap = 8;
  const dropdownWidth = Math.min(Math.max(rect.width + 24, rect.width), window.innerWidth - viewportGap * 2);
  const availableBelow = window.innerHeight - rect.bottom - viewportGap - dropdownGap;
  const availableAbove = rect.top - viewportGap - dropdownGap;
  const openAbove = availableBelow < 160 && availableAbove > availableBelow;
  const maxHeight = Math.max(120, Math.min(320, openAbove ? availableAbove : availableBelow));
  const left = Math.min(Math.max(viewportGap, rect.left), Math.max(viewportGap, window.innerWidth - viewportGap - dropdownWidth));
  const top = openAbove
    ? Math.max(viewportGap, rect.top - dropdownGap - maxHeight)
    : Math.min(rect.bottom + dropdownGap, window.innerHeight - viewportGap - maxHeight);
  state.dropdown.style.left = `${Math.round(left)}px`;
  state.dropdown.style.top = `${Math.round(top)}px`;
  state.dropdown.style.width = `${Math.round(dropdownWidth)}px`;
  state.dropdown.style.maxHeight = `${maxHeight}px`;
}

function openCustomSelect(select) {
  const state = customSelectStates.get(select);
  if (!state || select.disabled) return;
  closeOtherCustomSelects(select);
  closeOtherCustomDatePickers();
  syncCustomSelect(select);
  positionCustomSelectDropdown(select);
  state.dropdown.hidden = false;
  state.shell.classList.add("custom-select-open");
  state.trigger.setAttribute("aria-expanded", "true");
}

function toggleCustomSelect(select) {
  const state = customSelectStates.get(select);
  if (!state) return;
  if (state.dropdown.hidden) openCustomSelect(select);
  else closeCustomSelect(select);
}

function enhanceCustomSelect(select) {
  if (!select || customSelectStates.has(select) || select.closest(".custom-select-shell")) return;
  const shell = document.createElement("div");
  shell.className = `custom-select-shell ${select.className || ""}`.trim();
  customSelectMeasure(select, shell);

  select.parentNode.insertBefore(shell, select);
  shell.appendChild(select);
  select.classList.add("custom-select-native");
  select.setAttribute("tabindex", "-1");

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "custom-select-trigger";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");
  shell.appendChild(trigger);

  const dropdown = document.createElement("div");
  dropdown.className = "custom-select-dropdown";
  dropdown.setAttribute("role", "listbox");
  dropdown.hidden = true;
  document.body.appendChild(dropdown);

  customSelectStates.set(select, { shell, trigger, dropdown });
  syncCustomSelect(select);

  trigger.addEventListener("click", (event) => {
    event.preventDefault();
    toggleCustomSelect(select);
  });
  trigger.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " " || event.key === "ArrowDown") {
      event.preventDefault();
      openCustomSelect(select);
    } else if (event.key === "Escape") {
      closeCustomSelect(select);
    }
  });
  select.addEventListener("change", () => syncCustomSelect(select));

  new MutationObserver(() => {
    syncCustomSelect(select);
  }).observe(select, { childList: true, subtree: true, attributes: true, attributeFilter: ["selected", "disabled", "label", "value"] });
}

function positionCustomDateDropdown(input) {
  const state = customDateStates.get(input);
  if (!state) return;
  const rect = state.shell.getBoundingClientRect();
  const viewportGap = 16;
  const dropdownGap = 8;
  const dropdownWidth = Math.min(248, window.innerWidth - viewportGap * 2);
  const dropdownHeight = 292;
  const availableBelow = window.innerHeight - rect.bottom - viewportGap - dropdownGap;
  const availableAbove = rect.top - viewportGap - dropdownGap;
  const openAbove = availableBelow < dropdownHeight && availableAbove > availableBelow;
  const left = Math.min(Math.max(viewportGap, rect.left), Math.max(viewportGap, window.innerWidth - viewportGap - dropdownWidth));
  const top = openAbove
    ? Math.max(viewportGap, rect.top - dropdownGap - dropdownHeight)
    : Math.min(rect.bottom + dropdownGap, window.innerHeight - viewportGap - dropdownHeight);
  state.dropdown.style.left = `${Math.round(left)}px`;
  state.dropdown.style.top = `${Math.round(top)}px`;
  state.dropdown.style.width = `${Math.round(dropdownWidth)}px`;
}

function renderCustomDatePicker(input) {
  const state = customDateStates.get(input);
  if (!state) return;
  const selectedDate = parseCustomDateValue(input.value);
  const today = new Date();
  if (!Number.isInteger(state.viewYear) || !Number.isInteger(state.viewMonth)) {
    const baseDate = selectedDate || today;
    state.viewYear = baseDate.getFullYear();
    state.viewMonth = baseDate.getMonth();
  }
  const firstDay = new Date(state.viewYear, state.viewMonth, 1);
  const startOffset = (firstDay.getDay() + 6) % 7;
  const gridStart = new Date(state.viewYear, state.viewMonth, 1 - startOffset);
  const todayValue = formatCustomDateValue(today);
  const selectedValue = selectedDate ? formatCustomDateValue(selectedDate) : "";
  const cells = Array.from({ length: 42 }, (_, index) => {
    const date = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + index);
    const value = formatCustomDateValue(date);
    const muted = date.getMonth() !== state.viewMonth ? " muted" : "";
    const active = value === selectedValue ? " active" : "";
    const current = value === todayValue ? " today" : "";
    return `<button type="button" class="custom-date-day${muted}${active}${current}" data-date="${value}">${date.getDate()}</button>`;
  }).join("");
  state.dropdown.innerHTML = `
    <div class="custom-date-head">
      <button type="button" class="custom-date-nav" data-date-nav="prev" aria-label="上个月">‹</button>
      <strong>${state.viewYear}年${state.viewMonth + 1}月</strong>
      <button type="button" class="custom-date-nav" data-date-nav="next" aria-label="下个月">›</button>
    </div>
    <div class="custom-date-weekdays">${CUSTOM_DATE_WEEKDAYS.map((day) => `<span>${day}</span>`).join("")}</div>
    <div class="custom-date-days">${cells}</div>
    <div class="custom-date-actions">
      <button type="button" data-date-action="clear">清除</button>
      <button type="button" data-date-action="today">今天</button>
    </div>
  `;
}

function setCustomDateValue(input, value) {
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function openCustomDatePicker(input) {
  const state = customDateStates.get(input);
  if (!state || input.disabled) return;
  closeOtherCustomSelects();
  closeOtherCustomDatePickers(input);
  const selectedDate = parseCustomDateValue(input.value) || new Date();
  state.viewYear = selectedDate.getFullYear();
  state.viewMonth = selectedDate.getMonth();
  renderCustomDatePicker(input);
  positionCustomDateDropdown(input);
  state.dropdown.hidden = false;
  state.shell.classList.add("custom-date-open");
}

function toggleCustomDatePicker(input) {
  const state = customDateStates.get(input);
  if (!state) return;
  if (state.dropdown.hidden) openCustomDatePicker(input);
  else closeCustomDatePicker(input);
}

function enhanceCustomDateInput(input, shell) {
  input.type = "text";
  input.inputMode = "none";
  input.autocomplete = "off";
  input.readOnly = true;
  input.classList.add("custom-date-input");
  input.setAttribute("aria-haspopup", "dialog");

  const dropdown = document.createElement("div");
  dropdown.className = "custom-date-dropdown";
  dropdown.hidden = true;
  document.body.appendChild(dropdown);
  customDateStates.set(input, { shell, dropdown, viewYear: null, viewMonth: null });

  input.addEventListener("click", () => toggleCustomDatePicker(input));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeCustomDatePicker(input);
    } else if (event.key === "Enter" || event.key === " " || event.key === "ArrowDown") {
      event.preventDefault();
      openCustomDatePicker(input);
    }
  });
  dropdown.addEventListener("click", (event) => {
    event.stopPropagation();
    const nav = event.target.closest("[data-date-nav]");
    const day = event.target.closest("[data-date]");
    const action = event.target.closest("[data-date-action]");
    const state = customDateStates.get(input);
    if (!state) return;
    if (nav) {
      const delta = nav.dataset.dateNav === "prev" ? -1 : 1;
      const next = new Date(state.viewYear, state.viewMonth + delta, 1);
      state.viewYear = next.getFullYear();
      state.viewMonth = next.getMonth();
      renderCustomDatePicker(input);
      positionCustomDateDropdown(input);
      return;
    }
    if (day) {
      setCustomDateValue(input, day.dataset.date || "");
      closeCustomDatePicker(input);
      return;
    }
    if (action?.dataset.dateAction === "today") {
      setCustomDateValue(input, formatCustomDateValue(new Date()));
      closeCustomDatePicker(input);
      return;
    }
    if (action?.dataset.dateAction === "clear") {
      setCustomDateValue(input, "");
      closeCustomDatePicker(input);
    }
  });
}

function shouldEnhanceCustomInput(input) {
  if (!input || input.classList.contains("custom-input-native") || input.closest(".custom-input-shell")) return false;
  const type = (input.getAttribute("type") || "text").toLowerCase();
  return CUSTOM_INPUT_TYPES.has(type) && !input.hidden;
}

function enhanceCustomInput(input) {
  if (!shouldEnhanceCustomInput(input)) return;
  const type = (input.getAttribute("type") || "text").toLowerCase();
  const shell = document.createElement("div");
  shell.className = `custom-input-shell ${input.className || ""}`.trim();
  if (type === "date") shell.classList.add("custom-date-shell");
  customInputMeasure(input, shell);

  input.parentNode.insertBefore(shell, input);
  shell.appendChild(input);
  input.classList.add("custom-input-native");
  if (type === "date") enhanceCustomDateInput(input, shell);

}

function enhanceCustomSelects(root = document) {
  root.querySelectorAll?.("select:not(.custom-select-native)").forEach(enhanceCustomSelect);
}

function enhanceCustomInputs(root = document) {
  root.querySelectorAll?.("input:not(.custom-input-native)").forEach(enhanceCustomInput);
}

function enhanceCustomControls(root = document) {
  enhanceCustomSelects(root);
  enhanceCustomInputs(root);
}

function scheduleCustomSelectEnhancement() {
  if (customSelectRaf) return;
  customSelectRaf = requestAnimationFrame(() => {
    customSelectRaf = 0;
    enhanceCustomControls();
  });
}

function initializeCustomSelects() {
  enhanceCustomControls();
  if (!customSelectObserver) {
    customSelectObserver = new MutationObserver(scheduleCustomSelectEnhancement);
    customSelectObserver.observe(document.body, { childList: true, subtree: true });
  }
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".custom-select-shell") && !event.target.closest(".custom-select-dropdown")) {
      closeOtherCustomSelects();
    }
    if (!event.target.closest(".custom-date-shell") && !event.target.closest(".custom-date-dropdown")) {
      closeOtherCustomDatePickers();
    }
  });
  window.addEventListener("resize", () => { closeOtherCustomSelects(); closeOtherCustomDatePickers(); });
  window.addEventListener("scroll", (event) => {
    const target = event.target;
    if (target && typeof target.closest === "function" && target.closest(".custom-select-dropdown")) return;
    closeOtherCustomSelects();
    closeOtherCustomDatePickers();
  }, true);
}

/* ===== Filtering ===== */
function differenceReasonMatchesFilter(differenceReason, selectedReason) {
  if (!selectedReason) return true;
  return String(differenceReason || "")
    .split(/\s*\+\s*/)
    .map((part) => part.trim())
    .includes(selectedReason);
}

function resultMatchesReasonFilter(item, selectedReason) {
  if (!selectedReason) return true;
  if (String(selectedReason) === "home-status:unresolved") {
    return homeResultCountsAsUnresolved(item);
  }
  if (String(selectedReason).startsWith("home-category:")) {
    return homeResultCategory(item).key === String(selectedReason).slice("home-category:".length);
  }
  return differenceReasonMatchesFilter(item.difference_reason, selectedReason);
}

function filteredResults() {
  const kw = keywordFilter.value.trim().toLowerCase();
  const reason = reasonFilter.value, status = statusFilter.value;
  return results.filter((item) => {
    const code = String(item.project_code || "").toLowerCase();
    const name = String(item.project_name || "").toLowerCase();
    const hit = !kw || code.includes(kw) || name.includes(kw);
    return hit && resultMatchesReasonFilter(item, reason) && (!status || item.match_status === status);
  });
}

function getPageItems() {
  const f = filteredResults();
  const t = f.length, tp = Math.max(1, Math.ceil(t / PAGE_SIZE));
  if (currentPage > tp) currentPage = tp;
  return { pageItems: f.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE), total: t, totalPages: tp };
}

function historyRestoreHintText(meta = resultRestoreHistoryMeta, total = results.length) {
  if (!meta) return "";
  const reportDate = meta.runDate || "--";
  const runAtText = formatDisplayTime(meta.runAt || "") || "--";
  return `结果列表已恢复到历史数据：报告期${reportDate} 执行时间 ${runAtText}，共 ${formatMoney(total)} 条。`;
}

function setResultHistoryRestoreState(run = {}, total = results.length) {
  resultRestoreHistoryMeta = {
    runDate: run.run_date || "",
    runAt: run.run_at || "",
    total,
  };
  homeResultListFilterLabel = "";
  if (lastRunTime) lastRunTime.hidden = true;
}

function clearResultHistoryRestoreState() {
  resultRestoreHistoryMeta = null;
}

function setFilterClearButtonVisible(button, visible) {
  if (!button) return;
  button.classList.toggle("is-visible", Boolean(visible));
  button.tabIndex = visible ? 0 : -1;
}

function updateFilterClearButtons() {
  setFilterClearButtonVisible(clearKeywordFilterBtn, keywordFilter?.value.trim());
  setFilterClearButtonVisible(clearReasonFilterBtn, reasonFilter?.value);
  setFilterClearButtonVisible(clearStatusFilterBtn, statusFilter?.value);
  setFilterClearButtonVisible(clearHistoryReportFilterBtn, historyReportFilter?.value);
  setFilterClearButtonVisible(clearHistoryExecutorFilterBtn, historyExecutorFilter?.value);
}

function updateResultFilterHint(total = filteredResults().length) {
  if (!resultFilterHint) return;
  if (resultRestoreHistoryMeta) {
    resultFilterHint.hidden = false;
    resultFilterHint.innerHTML = `${escapeHtml(historyRestoreHintText(resultRestoreHistoryMeta, resultRestoreHistoryMeta.total))}<button type="button" class="result-filter-clear" id="restoreLatestResults">回到最新结果</button>`;
    return;
  }
  if (!homeResultListFilterLabel) {
    resultFilterHint.hidden = true;
    resultFilterHint.innerHTML = "";
    return;
  }
  resultFilterHint.hidden = false;
  resultFilterHint.innerHTML = `结果列表已筛选 ${escapeHtml(homeResultListFilterLabel)} 数据，共 ${escapeHtml(total)} 条，<button type="button" class="result-filter-clear" id="clearHomeResultFilter">取消筛选</button>`;
}

function updatePagination() {
  const { total, totalPages } = getPageItems();
  pageInfo.textContent = total ? `共 ${total} 条，第 ${currentPage} / ${totalPages} 页` : "暂无数据";
  pageCurrent.textContent = total ? currentPage : "-";
  prevPageBtn.disabled = currentPage <= 1;
  nextPageBtn.disabled = currentPage >= totalPages;
  updateResultFilterHint(total);
  updateFilterClearButtons();
}

/* ===== Render ===== */
function renderStatusBadge(s) {
  if (s === "已解释") return `<span class="status-badge status-badge--good">已解释</span>`;
  if (s === "候选不唯一") return `<span class="status-badge status-badge--warn">候选不唯一</span>`;
  if (s === "组合候选过多") return `<span class="status-badge status-badge--warn">组合候选过多</span>`;
  return `<span class="status-badge status-badge--bad">未解释</span>`;
}

function renderSourceNoDataRow() {
  const selectedDate = escapeHtml(runDate?.value || "所选日期");
  return `<tr><td colspan="9"><div class="no-source-panel" id="noSourcePanel"><div class="no-source-illustration" aria-hidden="true"><svg class="no-source-svg" viewBox="0 0 220 180" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="noSourceCardGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#eef8ff"/><stop offset="100%" stop-color="#ffffff"/></linearGradient><linearGradient id="noSourceAccentGrad" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#22c3d6"/><stop offset="100%" stop-color="#3b82f6"/></linearGradient></defs><circle class="no-source-orbit no-source-orbit--outer" cx="110" cy="88" r="72"/><circle class="no-source-orbit no-source-orbit--inner" cx="110" cy="88" r="54"/><g class="no-source-card"><rect x="62" y="34" width="96" height="112" rx="14" fill="url(#noSourceCardGrad)" stroke="#b7d7e8" stroke-width="2"/><rect x="62" y="34" width="96" height="28" rx="14" fill="#dff5fb"/><path d="M62 58 H158" stroke="#b7d7e8" stroke-width="2"/><path class="no-source-scan" d="M76 82 H144" stroke="url(#noSourceAccentGrad)" stroke-width="5" stroke-linecap="round"/><path d="M76 102 H128" stroke="#c7d7e5" stroke-width="5" stroke-linecap="round"/><path d="M76 122 H138" stroke="#d7e3ed" stroke-width="5" stroke-linecap="round"/><circle class="no-source-dot no-source-dot--one" cx="84" cy="48" r="4" fill="#22c3d6"/><circle class="no-source-dot no-source-dot--two" cx="100" cy="48" r="4" fill="#3b82f6"/><circle class="no-source-dot no-source-dot--three" cx="116" cy="48" r="4" fill="#f59e0b"/></g><path class="no-source-wave" d="M54 150 C82 136 100 164 126 150 S168 138 184 152" fill="none" stroke="#22c3d6" stroke-width="4" stroke-linecap="round"/></svg></div><div class="no-source-text"><h3 class="no-source-title">报表对应日期无数据</h3><p class="no-source-sub">未查询到 ${selectedDate} 的报表记录，本次不写入历史</p></div></div></td></tr>`;
}

function renderResults() {
  const { pageItems, total } = getPageItems();
  if (!total) {
    if (resultEmptyState === RESULT_EMPTY_SOURCE) {
      resultBody.innerHTML = renderSourceNoDataRow();
    } else if (hasReconciled) {
      resultBody.innerHTML = '<tr><td colspan="9"><div class="success-panel" id="successPanel"><div class="success-illustration"><svg class="success-svg" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="circleGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#25676e"/><stop offset="100%" stop-color="#abeaf2"/></linearGradient><filter id="glow"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs><circle cx="100" cy="100" r="88" fill="none" stroke="url(#circleGrad)" stroke-width="3" class="success-ring-outer"/><circle cx="100" cy="100" r="78" fill="none" stroke="#abeaf2" stroke-width="1.5" class="success-ring-inner" opacity="0.5"/><circle cx="100" cy="100" r="60" fill="#e6f4ea" class="success-bg-circle"/><path d="M80 102 L94 116 L122 84" fill="none" stroke="#25676e" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" class="success-check"/></svg></div><div class="success-text"><h3 class="success-title">恭喜！数据完全正确</h3><p class="success-sub">本次核对未发现任何差异数据</p></div></div></td></tr>';
      launchConfetti();
    } else {
      resultBody.innerHTML = '<tr><td colspan="9" class="empty">暂无结果</td></tr>';
    }
    updatePagination(); return;
  }
  resultBody.innerHTML = pageItems.map((item, i) => {
    const diff = Number(item.difference), gi = (currentPage - 1) * PAGE_SIZE + i;
    return `<tr class="result-main-row" data-result-index="${gi}" title="点击展开/收回详情">
      <td><button class="expand-btn" data-index="${gi}">+</button></td>
      <td class="result-project-code">${escapeHtml(item.project_code)}</td>
      <td>${escapeHtml(item.project_name)}</td>
      <td class="money-cell">${formatMoney(item.valuation_asset_total)}</td>
      <td class="money-cell">${formatMoney(item.asset_total)}</td>
      <td class="money-cell">${formatMoney(item.liability_equity_total)}</td>
      <td class="money-cell ${diff ? "money-cell--error" : ""}">${formatMoney(item.difference)}</td>
      <td>${escapeHtml(item.difference_reason || "")}</td>
      <td style="text-align:center">${renderStatusBadge(item.match_status)}</td>
    </tr>
    <tr class="detail-row" data-detail="${gi}" hidden><td colspan="9">${renderDetails(item.display_details || [])}</td></tr>`;
  }).join("");
  updatePagination();
}

function renderResultListLoading() {
  resultBody.innerHTML = `<tr class="result-loading-row"><td colspan="9">
    <span class="loading-spinner result-loading-spinner" aria-hidden="true"></span>
    <span>正在加载执行结果列表...</span>
  </td></tr>`;
}

function showResultListReturnLoading() {
  if (!resultBody || !results.length) return;
  if (resultListLoadingTimer) clearTimeout(resultListLoadingTimer);
  renderResultListLoading();
  resultListLoadingTimer = setTimeout(() => {
    resultListLoadingTimer = null;
    renderResults();
  }, RESULT_LIST_LOADING_MS);
}

function displayDetailLabel(label) {
  return label === "zf_detail 资产合计" ? "资负报表资产合计" : label;
}

function renderDetails(ds) {
  if (!ds.length) return '<div class="detail">无明细</div>';
  return `<div class="detail">${ds.map((s) => {
    const rows = (s.rows || []).map((r) => `<div class="detail-item"><span>${escapeHtml(displayDetailLabel(r.label))}</span><strong>${escapeHtml(r.value)}</strong></div>`).join("");
    const tbl = s.table ? `<table class="detail-table"><thead><tr>${s.table.headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead><tbody>${(s.table.rows || []).map((r) => `<tr>${r.map((c) => `<td class="money-cell">${escapeHtml(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>` : "";
    return `<div class="detail-block"><div class="detail-heading"><strong>${escapeHtml(s.title)}</strong></div><div class="detail-content">${rows}${tbl}</div></div>`;
  }).join("")}</div>`;
}

/* ===== Confetti Celebration ===== */
let confettiFired = false;
function launchConfetti() {
  if (confettiFired) return;
  confettiFired = true;
  const panel = document.getElementById("successPanel");
  if (!panel) { confettiFired = false; return; }
  const rect = panel.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2 - 60;
  const colors = ["#25676e", "#abeaf2", "#137333", "#ceead6", "#ffb74d", "#f06292", "#64b5f6", "#a1887f"];
  const particles = [];
  const count = 80;

  for (let i = 0; i < count; i++) {
    const el = document.createElement("div");
    el.className = "confetti-particle";
    const angle = Math.random() * Math.PI * 2;
    const distance = 120 + Math.random() * 200;
    const size = 5 + Math.random() * 8;
    el.style.cssText = `
      position:fixed; left:${cx}px; top:${cy}px;
      width:${size}px; height:${size * (0.5 + Math.random())}px;
      background:${colors[Math.floor(Math.random() * colors.length)]};
      border-radius:${Math.random() > 0.5 ? "2px" : "50%"};
      pointer-events:none; z-index:999;
      opacity:1;
      transform:translate(-50%,-50%) rotate(${Math.random() * 360}deg);
    `;
    document.body.appendChild(el);
    const dx = Math.cos(angle) * distance;
    const dy = Math.sin(angle) * distance - 60;
    const rot = 360 + Math.random() * 720;
    const duration = 800 + Math.random() * 1200;
    el.animate([
      { transform: "translate(-50%,-50%) rotate(0deg)", opacity: 1 },
      { transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) rotate(${rot}deg)`, opacity: 0 }
    ], { duration, easing: "cubic-bezier(.15,.7,.5,1)", fill: "forwards" });
    particles.push({ el, duration });
  }
  setTimeout(() => particles.forEach(p => p.el.remove()), 2200);
}

/* ===== Export ===== */
function buildDetailText(item) {
  if (typeof window.buildExportDetailText !== "function") return "";
  return window.buildExportDetailText(item);
}

function buildProcessingScriptText(item) {
  if (typeof window.buildProcessingScript !== "function") return "";
  return window.buildProcessingScript(item);
}

function specificReasonText(item) {
  const finalSection = (item.display_details || []).find((detail) => detail.title === "最终判断结果");
  const row = (finalSection?.rows || []).find((candidate) => candidate.label === "具体原因");
  return row?.value || "";
}

function remarkText(item) {
  const reasonParts = String(item.difference_reason || "")
    .split(/\s*\+\s*/)
    .filter(Boolean);
  if (reasonParts.length <= 1) return "";
  const status = String(item.match_status || "");
  const baseParts = reasonParts.filter((reason) => reason !== "暂无法确定");
  const assetParts = baseParts.filter((reason) => reason.startsWith("资产"));
  const receivedTrustParts = baseParts.filter((reason) => reason.startsWith("实收本金"));
  const liabilityEquityParts = baseParts.filter((reason) => reason.startsWith("负债及权益"));
  const quoteReasons = (parts) => parts.map((reason) => `“${reason}”`).join("、");
  if (reasonParts.includes("暂无法确定")) {
    const baseReason = baseParts.join("、") || "原差异类型";
    if (reasonParts.includes("资产缺失")) {
      return `资产端存在多组候选资产均可解释差额，当前无法唯一确认具体缺失资产，因此在“${baseReason}”基础上追加“暂无法确定”；请查看候选组合明细。`;
    }
    if (reasonParts.includes("资产重复")) {
      return `资产端存在多组候选资产均可解释差额，当前无法唯一确认具体重复资产，因此在“${baseReason}”基础上追加“暂无法确定”；请查看候选组合明细。`;
    }
    if (liabilityEquityParts.length) {
      return `负债及权益端存在多组候选科目均可解释差额，当前无法唯一确认具体科目，因此在“${baseReason}”基础上追加“暂无法确定”；请查看候选组合明细。`;
    }
    return `当前差异存在多组候选结果，无法唯一确认具体原因，因此在“${baseReason}”基础上追加“暂无法确定”；请查看候选组合明细。`;
  }
  if (assetParts.length && receivedTrustParts.length && liabilityEquityParts.length) {
    if (status === "已解释") {
      return `资产端差额先由${quoteReasons(assetParts)}解释，修正资产端后仍存在剩余差额；其中${quoteReasons(receivedTrustParts)}解释实收本金部分，剩余部分由${quoteReasons(liabilityEquityParts)}解释，因此展示为组合差异类型。`;
    }
    return `资产端差额可归入${quoteReasons(assetParts)}，修正资产端后仍存在剩余差额；其中${quoteReasons(receivedTrustParts)}解释实收本金部分，但${quoteReasons(liabilityEquityParts)}未能完整解释剩余差额，因此展示为组合差异类型且状态为${status || "未解释"}。`;
  }
  if (assetParts.length && receivedTrustParts.length) {
    if (status === "已解释") {
      return `资产端差额已由${quoteReasons(assetParts)}解释，修正资产端后仍存在剩余差额，剩余部分由${quoteReasons(receivedTrustParts)}解释，因此展示为组合差异类型。`;
    }
    return `资产端差额可归入${quoteReasons(assetParts)}，但修正资产端后仍存在剩余差额，${quoteReasons(receivedTrustParts)}未能完整解释，因此展示为组合差异类型且状态为${status || "未解释"}。`;
  }
  if (assetParts.length && liabilityEquityParts.length) {
    if (status === "已解释") {
      return `资产端差额已由${quoteReasons(assetParts)}解释，修正资产端后仍存在剩余差额，剩余部分由${quoteReasons(liabilityEquityParts)}解释，因此展示为组合差异类型。`;
    }
    return `资产端差额可归入${quoteReasons(assetParts)}，但修正资产端后仍存在剩余差额，${quoteReasons(liabilityEquityParts)}未能完整解释，因此展示为组合差异类型且状态为${status || "未解释"}。`;
  }
  if (receivedTrustParts.length && liabilityEquityParts.length) {
    if (status === "已解释") {
      return `${quoteReasons(receivedTrustParts)}解释实收本金差额后仍存在剩余差额，剩余部分由${quoteReasons(liabilityEquityParts)}解释，因此展示为组合差异类型。`;
    }
    return `${quoteReasons(receivedTrustParts)}可解释部分差额，但剩余差额在${quoteReasons(liabilityEquityParts)}未能完整解释，因此展示为组合差异类型且状态为${status || "未解释"}。`;
  }
  if (status === "已解释") {
    return `多个核对层面的差异共同解释本项目差额，因此展示为组合差异类型。`;
  }
  return `本项目存在多个核对层面的差异，其中仍有部分差额未能完整解释，因此展示为组合差异类型且状态为${status || "未解释"}。`;
}

const EXPORT_COLUMNS = [
  { header: "项目编号", width: 110, style: "Text", type: "string" },
  { header: "项目名称", width: 180, style: "ProjectName", type: "string" },
  { header: "资产合计（估值表）", width: 120, style: "Money", type: "number" },
  { header: "资产合计", width: 110, style: "Money", type: "number" },
  { header: "负债及权益合计", width: 120, style: "Money", type: "number" },
  { header: "差异金额", width: 110, style: "Money", type: "number" },
  { header: "差异类型", width: 180, style: "Text", type: "string" },
  { header: "具体原因", width: 180, style: "SpecificReason", type: "string" },
  { header: "匹配状态", width: 80, style: "Text", type: "string" },
  { header: "差异原因详情", width: 360, style: "Detail", type: "string" },
  { header: "处理脚本", width: 360, style: "Script", type: "string" },
  { header: "备注", width: 220, style: "SpecificReason", type: "string" },
];
const RESULT_LIST_LOADING_MS = 180;
const XLSX_STYLE_IDS = {
  Title: 1,
  Header: 2,
  Text: 3,
  ProjectName: 4,
  Money: 5,
  Detail: 6,
  Script: 7,
  SpecificReason: 8,
};

function escapeXml(value) {
  return String(value ?? "")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function escapeExcelSingleLineText(value) {
  return String(value ?? "").replace(/\s*(?:\r\n?|\n)\s*/g, " ");
}

function waitForExportUiFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}

function setExportState(exporting, message = "") {
  if (exportBtn) {
    exportBtn.disabled = Boolean(exporting);
    exportBtn.classList.toggle("loading", Boolean(exporting));
  }
  if (exportBtnLabel) exportBtnLabel.textContent = exporting ? "导出中" : "导出";
  if (exportProgress) exportProgress.hidden = !exporting;
  if (exportProgressText) exportProgressText.textContent = message || "准备导出...";
}

function updateExportProgress(message) {
  if (exportProgressText) exportProgressText.textContent = message;
  setStatus(message);
}

function columnWidthToXlsxWidth(pixelWidth) {
  return Math.max(8, Math.round((Number(pixelWidth) || 80) / 7 * 100) / 100);
}

function excelColumnName(index) {
  let n = index + 1;
  let name = "";
  while (n > 0) {
    const remainder = (n - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

function excelStringCell(value, styleName, rowIndex, columnIndex) {
  const ref = `${excelColumnName(columnIndex)}${rowIndex}`;
  const text = escapeXml(value);
  return `<c r="${ref}" s="${XLSX_STYLE_IDS[styleName]}" t="inlineStr"><is><t xml:space="preserve">${text}</t></is></c>`;
}

function excelNumberCell(value, styleName, rowIndex, columnIndex) {
  const n = Number(String(value ?? "").replace(/,/g, ""));
  if (!Number.isFinite(n)) return excelStringCell(value, "Text", rowIndex, columnIndex);
  const ref = `${excelColumnName(columnIndex)}${rowIndex}`;
  const displayed = styleName === "Money" ? Number(n.toFixed(2)) : n;
  return `<c r="${ref}" s="${XLSX_STYLE_IDS[styleName]}"><v>${displayed}</v></c>`;
}

function excelCell(value, column, rowIndex, columnIndex) {
  if (column.type === "number") return excelNumberCell(value, column.style, rowIndex, columnIndex);
  return excelStringCell(value, column.style, rowIndex, columnIndex);
}

function xlsxContentTypesXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>`;
}

function xlsxRootRelsXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>`;
}

function xlsxWorkbookXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="自动对数结果" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>`;
}

function xlsxWorkbookRelsXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`;
}

function xlsxStylesXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>
  <fonts count="3">
    <font><sz val="11"/><name val="Arial"/></font>
    <font><b/><sz val="12"/><name val="Arial"/></font>
    <font><b/><sz val="11"/><name val="Arial"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFEEF3F6"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border/>
    <border>
      <left style="thin"><color rgb="FFCCCCCC"/></left>
      <right style="thin"><color rgb="FFCCCCCC"/></right>
      <top style="thin"><color rgb="FFCCCCCC"/></top>
      <bottom style="thin"><color rgb="FFCCCCCC"/></bottom>
    </border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="9">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" applyFont="1"><alignment horizontal="left" vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="2" borderId="1" applyFont="1" applyFill="1" applyBorder="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" applyBorder="1"><alignment horizontal="center" vertical="top"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" applyBorder="1"><alignment horizontal="center" vertical="top" wrapText="1"/></xf>
    <xf numFmtId="164" fontId="0" fillId="0" borderId="1" applyNumberFormat="1" applyBorder="1"><alignment horizontal="right" vertical="top"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" applyBorder="1"><alignment horizontal="left" vertical="top"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" applyBorder="1"><alignment horizontal="left" vertical="top"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" applyBorder="1"><alignment horizontal="left" vertical="top"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`;
}

function xlsxWorksheetXml(rows, title) {
  const lastColumn = excelColumnName(EXPORT_COLUMNS.length - 1);
  const columns = EXPORT_COLUMNS.map((column, index) => {
    const col = index + 1;
    return `<col min="${col}" max="${col}" width="${columnWidthToXlsxWidth(column.width)}" customWidth="1"/>`;
  }).join("");
  const titleRow = `<row r="1" ht="24" customHeight="1">${excelStringCell(title, "Title", 1, 0)}</row>`;
  const headerCells = EXPORT_COLUMNS.map((column, index) => excelStringCell(column.header, "Header", 2, index)).join("");
  const headerRow = `<row r="2" ht="30" customHeight="1">${headerCells}</row>`;
  const bodyRows = rows.map((row, rowOffset) => {
    const rowIndex = rowOffset + 3;
    const cells = row.map((value, columnIndex) => excelCell(value, EXPORT_COLUMNS[columnIndex], rowIndex, columnIndex)).join("");
    return `<row r="${rowIndex}">${cells}</row>`;
  }).join("");
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>
  <dimension ref="A1:${lastColumn}${rows.length + 2}"/>
  <sheetViews>
    <sheetView workbookViewId="0">
      <pane ySplit="2" topLeftCell="A3" activePane="bottomLeft" state="frozen"/>
      <selection pane="bottomLeft" activeCell="A3" sqref="A3"/>
    </sheetView>
  </sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <cols>${columns}</cols>
  <sheetData>${titleRow}${headerRow}${bodyRows}</sheetData>
  <mergeCells count="1"><mergeCell ref="A1:${lastColumn}1"/></mergeCells>
</worksheet>`;
}

function xlsxCorePropertiesXml() {
  const now = new Date().toISOString();
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>监管智核</dc:creator>
  <cp:lastModifiedBy>监管智核</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">${now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">${now}</dcterms:modified>
</cp:coreProperties>`;
}

function xlsxAppPropertiesXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>监管智核</Application>
</Properties>`;
}

function crc32(bytes) {
  let crc = -1;
  for (let i = 0; i < bytes.length; i += 1) {
    crc = (crc >>> 8) ^ CRC32_TABLE[(crc ^ bytes[i]) & 0xff];
  }
  return (crc ^ -1) >>> 0;
}

const CRC32_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i += 1) {
    let c = i;
    for (let j = 0; j < 8; j += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[i] = c >>> 0;
  }
  return table;
})();

function xlsxDosDateTime(date = new Date()) {
  const year = Math.max(1980, date.getFullYear());
  const dosTime = (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2);
  const dosDate = ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
  return { dosDate, dosTime };
}

function appendZipUint16(parts, value) {
  parts.push(value & 0xff, (value >>> 8) & 0xff);
}

function appendZipUint32(parts, value) {
  parts.push(value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff);
}

function buildZip(files) {
  const encoder = new TextEncoder();
  const chunks = [];
  const centralDirectory = [];
  let offset = 0;
  const { dosDate, dosTime } = xlsxDosDateTime();
  files.forEach((file) => {
    const nameBytes = encoder.encode(file.name);
    const dataBytes = encoder.encode(file.content);
    const crc = crc32(dataBytes);
    const localHeader = [];
    appendZipUint32(localHeader, 0x04034b50);
    appendZipUint16(localHeader, 20);
    appendZipUint16(localHeader, 0x0800);
    appendZipUint16(localHeader, 0);
    appendZipUint16(localHeader, dosTime);
    appendZipUint16(localHeader, dosDate);
    appendZipUint32(localHeader, crc);
    appendZipUint32(localHeader, dataBytes.length);
    appendZipUint32(localHeader, dataBytes.length);
    appendZipUint16(localHeader, nameBytes.length);
    appendZipUint16(localHeader, 0);
    chunks.push(new Uint8Array(localHeader), nameBytes, dataBytes);
    const centralHeader = [];
    appendZipUint32(centralHeader, 0x02014b50);
    appendZipUint16(centralHeader, 20);
    appendZipUint16(centralHeader, 20);
    appendZipUint16(centralHeader, 0x0800);
    appendZipUint16(centralHeader, 0);
    appendZipUint16(centralHeader, dosTime);
    appendZipUint16(centralHeader, dosDate);
    appendZipUint32(centralHeader, crc);
    appendZipUint32(centralHeader, dataBytes.length);
    appendZipUint32(centralHeader, dataBytes.length);
    appendZipUint16(centralHeader, nameBytes.length);
    appendZipUint16(centralHeader, 0);
    appendZipUint16(centralHeader, 0);
    appendZipUint16(centralHeader, 0);
    appendZipUint16(centralHeader, 0);
    appendZipUint32(centralHeader, 0);
    appendZipUint32(centralHeader, offset);
    centralDirectory.push(new Uint8Array(centralHeader), nameBytes);
    offset += localHeader.length + nameBytes.length + dataBytes.length;
  });
  const centralDirectoryOffset = offset;
  const centralDirectorySize = centralDirectory.reduce((total, chunk) => total + chunk.length, 0);
  const endRecord = [];
  appendZipUint32(endRecord, 0x06054b50);
  appendZipUint16(endRecord, 0);
  appendZipUint16(endRecord, 0);
  appendZipUint16(endRecord, files.length);
  appendZipUint16(endRecord, files.length);
  appendZipUint32(endRecord, centralDirectorySize);
  appendZipUint32(endRecord, centralDirectoryOffset);
  appendZipUint16(endRecord, 0);
  return new Blob([...chunks, ...centralDirectory, new Uint8Array(endRecord)], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

function buildExcelWorkbookBlob(rows, title) {
  return buildZip([
    { name: "[Content_Types].xml", content: xlsxContentTypesXml() },
    { name: "_rels/.rels", content: xlsxRootRelsXml() },
    { name: "docProps/core.xml", content: xlsxCorePropertiesXml() },
    { name: "docProps/app.xml", content: xlsxAppPropertiesXml() },
    { name: "xl/workbook.xml", content: xlsxWorkbookXml() },
    { name: "xl/_rels/workbook.xml.rels", content: xlsxWorkbookRelsXml() },
    { name: "xl/styles.xml", content: xlsxStylesXml() },
    { name: "xl/worksheets/sheet1.xml", content: xlsxWorksheetXml(rows, title) },
  ]);
}

function exportRowsForExcel(data) {
  const reasonOrder = new Map();
  return data
    .map((item, originalIndex) => {
      const reason = item.difference_reason || "";
      if (!reasonOrder.has(reason)) reasonOrder.set(reason, reasonOrder.size);
      return { item, originalIndex, reasonIndex: reasonOrder.get(reason) };
    })
    .sort((left, right) => {
      const reasonDelta = left.reasonIndex - right.reasonIndex;
      return reasonDelta || left.originalIndex - right.originalIndex;
    })
    .map((entry) => entry.item);
}

async function exportToExcel() {
  if (exportBtn?.disabled) return;
  const data = exportRowsForExcel(filteredResults());
  if (!data.length) {
    setStatus("无数据可导出");
    showToast("无数据可导出", "warning");
    return;
  }
  setExportState(true, "准备导出...");
  try {
    await waitForExportUiFrame();
    updateExportProgress(`正在整理 ${data.length} 条结果...`);
    const ds = runDate.value || formatBeijingDate();
    const rows = data.map((item) => {
      return [
        item.project_code,
        item.project_name,
        item.valuation_asset_total,
        item.asset_total,
        item.liability_equity_total,
        item.difference,
        item.difference_reason || "",
        specificReasonText(item),
        item.match_status,
        buildDetailText(item),
        escapeExcelSingleLineText(buildProcessingScriptText(item)),
        remarkText(item) || "无",
      ];
    });
    await waitForExportUiFrame();
    updateExportProgress("正在生成 Excel 文件...");
    const blob = buildExcelWorkbookBlob(rows, `自动对数结果 — ${ds}`);
    if (!blob.size) throw new Error("生成的导出文件为空");
    const url = URL.createObjectURL(blob);
    try {
      updateExportProgress("正在启动浏览器下载...");
      const a = document.createElement("a");
      a.href = url;
      a.style.display = "none";
      const ts = beijingFileTimestamp();
      a.download = `自动对数_${ds}_${ts}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } finally {
      URL.revokeObjectURL(url);
    }
    setStatus(`已导出 ${data.length} 条`);
    showToast(`已导出 ${data.length} 条结果`, "success");
  } catch (error) {
    const message = error?.message || "未知错误";
    setStatus(`导出失败：${message}`);
    showToast(`导出失败：${message}`, "error");
  } finally {
    setExportState(false);
  }
}

exportBtn.addEventListener("click", exportToExcel);

/* ===== Auto-check Run ===== */
const RUN_CONFLICT_MESSAGE = "对数任务正在执行，请等待当前任务完成后再开始。";

function handleRunStartError(error) {
  const message = error?.message || "执行失败";
  if (message.includes("正在执行") || message.includes("当前任务完成")) {
    const activeJob = error?.payload?.active_job || {};
    const executor = userDisplayName(activeJob.executor || {});
    appendRunLog("您的执行失败，原因：有正在执行的任务");
    appendRunLog(`${executor}用户正在执行中`);
    pollActiveRunConflict(activeJob.id, executor);
    showToast(message, "warning");
  }
  return message;
}

function pollActiveRunConflict(jobId, executorName) {
  if (!jobId) return;
  if (activeRunConflictPollTimer) clearInterval(activeRunConflictPollTimer);
  const poll = async () => {
    try {
      const payload = await api(`/api/run/status/${encodeURIComponent(jobId)}`);
      const job = payload.job || {};
      if (["completed", "failed", "cancelled"].includes(job.status)) {
        clearInterval(activeRunConflictPollTimer);
        activeRunConflictPollTimer = null;
        appendRunLog(`${executorName || "当前"}用户执行完成，您可再次执行。`);
      }
    } catch (_) {
      clearInterval(activeRunConflictPollTimer);
      activeRunConflictPollTimer = null;
    }
  };
  activeRunConflictPollTimer = setInterval(poll, 1200);
  poll();
}

runBtn.addEventListener("click", async () => {
  if (!runDate.value) { setStatus("请选择日期"); return; }
  clearResultHistoryRestoreState();
  homeResultListFilterLabel = "";
  hasReconciled = false;
  resultEmptyState = "";
  hideLastRunTimeForNoSourceData = false;
  confettiFired = false;
  setRunningUi(true);
  setStatus("执行中");
  showWaveProgress();
  resetRunLogs();
  
  try {
    const payload = await api("/api/run/start", {
      method: "POST",
      body: JSON.stringify({ date: runDate.value, max_combination_rows: getCombinationLimit() })
    });
    runJobId = payload.job_id;
    await pollRunJob(runJobId);
  } catch (e) { 
    const message = handleRunStartError(e);
    if (progressAnimationId) {
      clearInterval(progressAnimationId);
      progressAnimationId = null;
    }
    setStatus(message);
    setWaveProgress(100, "执行失败");
    waveProgressText.textContent = "失败";
    retainProgress();
  }
  finally {
    setRunningUi(false);
    runJobId = null;
  }
});

async function pollRunJob(jobId) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finishPolling = () => {
      if (runPollTimer) clearInterval(runPollTimer);
      runPollTimer = null;
    };
    const poll = async () => {
      if (settled) return;
      try {
        const payload = await api(`/api/run/status/${encodeURIComponent(jobId)}`);
        if (settled) return;
        const job = payload.job || {};
        renderRunLogs(job.logs || []);
        setWaveProgress(job.progress || 0, job.step || "执行中");
        if (job.status === "completed") {
          settled = true;
          finishPolling();
          const h = job.history || {};
          const noSourceData = Boolean(h.no_source_data);
          hasReconciled = !noSourceData;
          resultEmptyState = noSourceData ? RESULT_EMPTY_SOURCE : "";
          results = job.results || [];
          currentPage = 1;
          const currentPageName = document.documentElement.getAttribute("data-page") || "";
          const restoreScroll = currentPageName === "auto-check" ? captureScrollPosition() : null;
          renderResults();
          restoreScroll?.();
          if (noSourceData) {
            hideLastRunTimeForNoSourceData = true;
            if (lastRunTime) lastRunTime.hidden = true;
            const noDataMessage = h.message || "报表对应日期无数据";
            setStatus(noDataMessage);
          if (currentPageName !== "auto-check") await switchPage("auto-check");
          retainProgress();
          resolve();
          return;
        }
        hideLastRunTimeForNoSourceData = false;
        const completionNotice = buildRunCompletionNotice(results.length, h);
        setStatus(completionNotice);
        appendRunLog(buildRunCompletionLogMessage(completionNotice, h));
        if (currentPageName !== "auto-check") await switchPage("auto-check");
          const executorFallback = job.executor?.display_name || job.executor?.username || authState.user?.display_name || authState.user?.username || "未知执行人";
          const executor = historyExecutorName(h, executorFallback);
          setLastRunTime(h.run_at || job.finished_at || formatLastRunTime(), executor);
          saveLatestResultsSnapshot({ runAt: h.run_at || job.finished_at || latestRunAt, executorName: executor });
          retainProgress();
          resolve();
          return;
        }
        if (job.status === "cancelled") {
          settled = true;
          finishPolling();
          setStatus("执行已终止");
          setWaveProgress(job.progress || 0, "已终止");
          waveProgressText.textContent = "停止";
          retainProgress();
          resolve();
          return;
        }
        if (job.status === "failed") {
          settled = true;
          finishPolling();
          reject(new Error(job.error || "执行失败"));
        }
      } catch (e) {
        if (settled) return;
        settled = true;
        finishPolling();
        reject(e);
      }
    };
    finishPolling();
    runPollTimer = setInterval(poll, 1000);
    poll();
  });
}

stopRunBtn?.addEventListener("click", async () => {
  if (!runJobId) return;
  stopRunBtn.disabled = true;
  setStatus("正在停止执行");
  setWaveProgress(parseFloat(waveProgressBar.style.width) || 0, "停止中");
  try {
    await api("/api/run/cancel", { method: "POST", body: JSON.stringify({ job_id: runJobId }) });
  } catch (e) {
    setStatus(e.message);
    stopRunBtn.disabled = false;
  }
});

runLogToggleBtn?.addEventListener("click", () => {
  if (!runLogPanel) return;
  const collapsed = runLogPanel.classList.toggle("collapsed");
  runLogToggleBtn.setAttribute("aria-expanded", String(!collapsed));
});

prevPageBtn.addEventListener("click", () => { if (currentPage > 1) { currentPage--; renderResults(); } });
nextPageBtn.addEventListener("click", () => { const { totalPages } = getPageItems(); if (currentPage < totalPages) { currentPage++; renderResults(); } });
jumpPage.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); const n = parseInt(jumpPage.value); const { totalPages } = getPageItems(); if (n >= 1 && n <= totalPages) { currentPage = n; renderResults(); } jumpPage.value = ""; }
});
function clearResultFilterControl(control) {
  if (!control) return;
  control.value = "";
  if (control.tagName === "SELECT") syncCustomSelect(control);
  homeResultListFilterLabel = "";
  currentPage = 1;
  renderResults();
}

function clearHistoryFilterControl(control) {
  if (!control) return;
  control.value = "";
  if (control.tagName === "SELECT") syncCustomSelect(control);
  historyCurrentPage = 1;
  renderHistoryList();
}

for (const f of [keywordFilter, reasonFilter, statusFilter]) f.addEventListener("input", () => {
  homeResultListFilterLabel = "";
  currentPage = 1;
  renderResults();
});
clearKeywordFilterBtn?.addEventListener("click", () => clearResultFilterControl(keywordFilter));
clearReasonFilterBtn?.addEventListener("click", () => clearResultFilterControl(reasonFilter));
clearStatusFilterBtn?.addEventListener("click", () => clearResultFilterControl(statusFilter));
async function restoreLatestResultsToResultList() {
  const restored = await loadLatestHistoryResults();
  if (!restored) {
    setStatus("暂无最新结果可还原");
    showToast("暂无最新结果可还原", "warning");
    return;
  }
  await switchPage("auto-check");
  setStatus("结果列表已还原到最新结果");
  showToast("结果列表已还原到最新结果", "success");
}

resultFilterHint?.addEventListener("click", async (event) => {
  if (event.target.closest("#restoreLatestResults")) {
    await restoreLatestResultsToResultList();
    return;
  }
  if (!event.target.closest("#clearHomeResultFilter")) return;
  keywordFilter.value = "";
  reasonFilter.value = "";
  statusFilter.value = "";
  homeResultListFilterLabel = "";
  syncCustomSelect(reasonFilter);
  syncCustomSelect(statusFilter);
  currentPage = 1;
  renderResults();
  setStatus("已取消筛选");
});
function hasSelectedResultText() {
  const selection = window.getSelection?.();
  if (!selection || selection.isCollapsed) return false;
  return Boolean(selection.toString().trim());
}

resultBody.addEventListener("click", (e) => {
  const btn = e.target.closest(".expand-btn");
  const mainRow = e.target.closest(".result-main-row");
  if (!btn && !mainRow) return;
  if (!btn && hasSelectedResultText()) return;
  const index = btn?.dataset.index || mainRow?.dataset.resultIndex;
  const row = resultBody.querySelector(`[data-detail="${index}"]`);
  if (!row) return;
  const currentBtn = btn || mainRow?.querySelector(".expand-btn");
  const wasHidden = row.hidden;
  resultBody.querySelectorAll(".detail-row").forEach((detailRow) => {
    if (detailRow === row) return;
    detailRow.hidden = true;
  });
  resultBody.querySelectorAll(".result-main-row").forEach((otherRow) => {
    if (otherRow === mainRow) return;
    otherRow.classList.remove("is-expanded");
  });
  resultBody.querySelectorAll(".expand-btn").forEach((otherBtn) => {
    if (otherBtn === currentBtn) return;
    otherBtn.textContent = "+";
  });
  row.hidden = !wasHidden;
  mainRow?.classList.toggle("is-expanded", wasHidden);
  if (currentBtn) currentBtn.textContent = row.hidden ? "+" : "-";
});

/* ===== History ===== */
async function loadHistoryList(resetPage = false) {
  if (!historyBody) return;
  if (resetPage) historyCurrentPage = 1;
  renderHistoryLoading();
  try {
    const payload = await api("/api/history");
    historyRuns = payload.history || [];
    updateHistoryExecutorOptions();
    renderHistoryList();
  } catch (e) {
    historyBody.innerHTML = `<tr><td colspan="${historyColumnCount()}" class="empty">${escapeHtml(e.message)}</td></tr>`;
    updateHistoryPagination();
  }
}

function getHistoryPageItems() {
  const sorted = getFilteredHistoryRuns().sort(compareHistoryRunsDesc);
  const total = sorted.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (historyCurrentPage > totalPages) historyCurrentPage = totalPages;
  return {
    pageItems: sorted.slice((historyCurrentPage - 1) * PAGE_SIZE, historyCurrentPage * PAGE_SIZE),
    total,
    totalPages,
  };
}

function compareHistoryRunsDesc(a, b) {
  const dateCmp = (b.run_date || "").localeCompare(a.run_date || "");
  if (dateCmp !== 0) return dateCmp;
  return (b.run_at || "").localeCompare(a.run_at || "");
}

function compareHistoryRunsByRunAtDesc(a, b) {
  const runAtCmp = (b.run_at || "").localeCompare(a.run_at || "");
  if (runAtCmp !== 0) return runAtCmp;
  return (b.run_date || "").localeCompare(a.run_date || "");
}

function updateHistoryPagination() {
  if (!historyPageInfo || !historyPageCurrent || !historyPrevPageBtn || !historyNextPageBtn) return;
  const { total, totalPages } = getHistoryPageItems();
  historyPageInfo.textContent = total ? `共 ${total} 条，第 ${historyCurrentPage} / ${totalPages} 页` : "暂无数据";
  historyPageCurrent.textContent = total ? historyCurrentPage : "-";
  historyPrevPageBtn.disabled = historyCurrentPage <= 1;
  historyNextPageBtn.disabled = historyCurrentPage >= totalPages;
  if (historyJumpPage && !total) historyJumpPage.value = "";
  updateFilterClearButtons();
}

function renderHistoryLoading() {
  if (!historyBody) return;
  historyBody.innerHTML = `
    <tr class="history-loading-row">
      <td colspan="${historyColumnCount()}">
        <span class="loading-spinner history-loading-spinner" aria-hidden="true"></span>
        <span>加载核对历史...</span>
      </td>
    </tr>`;
  if (historyPageInfo) historyPageInfo.textContent = "正在加载...";
  if (historyPageCurrent) historyPageCurrent.textContent = "-";
  if (historyPrevPageBtn) historyPrevPageBtn.disabled = true;
  if (historyNextPageBtn) historyNextPageBtn.disabled = true;
  if (historyJumpPage) historyJumpPage.value = "";
}

function historyExecutorName(run, fallback = "未知执行人") {
  return normalizeExecutorDisplayName(run?.executor_name || run?.executor_username || fallback, fallback);
}

function formatHistorySourceName(run) {
  const dws = String(run?.dws_source_name || "").trim();
  const biz = String(run?.config_name || "").trim();
  if (dws && biz) return `${dws} | ${biz}`;
  return biz || dws || "-";
}

function canManageHistory() {
  return authState.user?.role === "admin";
}

function canSeeHistorySource() {
  return authState.user?.role === "admin";
}

function historyColumnCount() {
  return canSeeHistorySource() ? 9 : 8;
}

function historyBaselineText(run = {}) {
  if (!run?.baseline_id) return "无";
  const baselineRunAt = formatDisplayTime(run.baseline_run_at || "");
  return baselineRunAt ? `${baselineRunAt}执行的同报告期记录` : "同报告期记录";
}

function historyHasBaseline(run = {}) {
  return Boolean(run?.baseline_id || run?.baseline_run_at);
}

function formatHistoryDiffCount(run = {}, field = "", options = {}) {
  if (!historyHasBaseline(run)) return "-";
  const text = formatMoney(run?.[field] ?? 0);
  return options.unit === false ? text : `${text} 条`;
}

function historyDiffItems(run = {}, field = "") {
  return historyHasBaseline(run) ? (run?.[field] || []) : [];
}

function renderHistoryList() {
  const { pageItems, total } = getHistoryPageItems();
  if (!total) {
    selectedHistory = null;
    selectedHistoryId = "";
    const emptyText = isHistoryFilterActive() ? "暂无符合条件的历史记录" : "暂无历史记录";
    historyBody.innerHTML = `<tr><td colspan="${historyColumnCount()}" class="empty">${emptyText}</td></tr>`;
    updateHistoryPagination();
    return;
  }
  historyBody.innerHTML = pageItems.map((run) => {
    const explained = (run.status_counts || {})["已解释"] || 0;
    const sourceCell = canSeeHistorySource()
      ? `<td class="admin-only">${escapeHtml(formatHistorySourceName(run))}</td>`
      : "";
    const deleteAction = canManageHistory()
      ? `<button class="btn-outline btn-xs btn-danger delete-history" data-id="${escapeHtml(run.id)}">删除</button>`
      : "";
    return `<tr class="history-main-row" data-history-id="${escapeHtml(run.id)}">
      <td>${escapeHtml(run.run_date)}</td>
      <td>${escapeHtml(formatDisplayTime(run.run_at))}</td>
      <td>${escapeHtml(historyExecutorName(run))}</td>
      ${sourceCell}
      <td class="money-cell">${formatMoney(run.total_count)}</td>
      <td class="money-cell">${formatMoney(explained)}</td>
      <td class="money-cell history-added">${escapeHtml(formatHistoryDiffCount(run, "added_count", { unit: false }))}</td>
      <td class="money-cell history-removed">${escapeHtml(formatHistoryDiffCount(run, "removed_count", { unit: false }))}</td>
      <td class="history-actions">
        <button class="btn-outline btn-xs view-history" data-id="${escapeHtml(run.id)}">查看</button>
        ${deleteAction}
      </td>
    </tr>`;
  }).join("");
  updateHistoryPagination();
}

async function loadHistoryDetail(id) {
  selectedHistory = null;
  selectedHistoryId = String(id || "");
  const payload = await api(`/api/history/${encodeURIComponent(id)}`);
  selectedHistory = payload.history;
  selectedHistoryId = String(selectedHistory?.id || id || "");
  return selectedHistory;
}

async function showHistoryDetailModal(id) {
  showInfo("历史详情", renderHistoryDetailLoading(id), { modalClass: "modal-info--history-detail", closeOnBackdrop: false });
  try {
    const history = await loadHistoryDetail(id);
    showInfo("历史详情", renderHistoryDetailContent(history), { modalClass: "modal-info--history-detail", closeOnBackdrop: false });
    document.querySelector("#infoBody .restore-history-detail")?.addEventListener("click", async () => {
      await restoreHistoryRun(history);
      document.getElementById("infoClose")?.click();
    });
    return history;
  } catch (e) {
    selectedHistory = null;
    selectedHistoryId = "";
    showInfo("历史详情", `<p class="history-empty">${escapeHtml(e.message || "历史详情加载失败")}</p>`, {
      modalClass: "modal-info--history-detail",
      closeOnBackdrop: false,
    });
    throw e;
  }
}

function renderHistoryDetailContent(run) {
  return `
    <div class="history-detail-card">
      <div class="history-detail">
    <div class="history-summary-grid">
      ${historySummaryItem("报告期", run.run_date)}
      ${historySummaryItem("执行人", historyExecutorName(run))}
      ${historySummaryItem("执行时间", run.run_at)}
      ${historySummaryItem("基准记录", historyBaselineText(run))}
    </div>
    ${historyDetailCounts(run)}
    ${historySection("本次新增差异", historyDiffItems(run, "added_results"))}
    ${historySection("本次减少差异", historyDiffItems(run, "removed_results"))}
    ${historySection("本次完整核对结果", run.results || [])}
      </div>
      <div class="history-detail-footer">
        <button type="button" class="btn-primary btn-sm restore-history-detail" data-id="${escapeHtml(run.id || "")}">恢复到结果页</button>
      </div>
    </div>
  `;
}

function renderHistoryDetailLoading(id) {
  return `
    <div class="history-detail-card" data-loading-id="${escapeHtml(id || "")}">
      <div class="history-detail">
        <div class="history-detail-loading">
          <span class="loading-spinner history-loading-spinner" aria-hidden="true"></span>
          <span>正在加载历史详情...</span>
        </div>
      </div>
    </div>`;
}

function historySummaryItem(label, value) {
  return `<div class="history-summary-item"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function historyDetailCounts(run) {
  return `<div class="history-detail-counts">
    ${historyCountItem("本次新增差异", historyHasBaseline(run) ? (run.added_results || []) : null)}
    ${historyCountItem("本次减少差异", historyHasBaseline(run) ? (run.removed_results || []) : null)}
    ${historyCountItem("本次完整核对结果", run.results || [])}
  </div>`;
}

function historyCountItem(label, items) {
  if (items === null) {
    return `<div class="history-count-item"><span>${escapeHtml(label)}</span><strong>-</strong></div>`;
  }
  return `<div class="history-count-item"><span>${escapeHtml(label)}</span><strong>${formatMoney(items.length)} 条</strong></div>`;
}

function historySection(title, items) {
  if (!items.length) return "";
  const sectionClass = `${title === "本次完整核对结果" ? " history-section--full-results" : ""}${items.length > 10 ? " history-section--scroll" : ""}`;
  return `<div class="history-section${sectionClass}">
    <div class="history-section-title">${escapeHtml(title)} <span>${items.length} 条</span></div>
    <div class="history-section-table">${historyResultTable(items)}</div>
  </div>`;
}

function historyResultTable(items) {
  if (!items.length) return '<div class="history-empty">无</div>';
  return `<table class="detail-table history-result-table">
    <thead><tr><th>项目编号</th><th>项目名称</th><th>差异金额</th><th>差异类型</th><th>状态</th></tr></thead>
    <tbody>${items.map((item) => `<tr>
      <td>${escapeHtml(item.project_code)}</td>
      <td>${escapeHtml(item.project_name)}</td>
      <td class="money-cell">${formatMoney(item.difference)}</td>
      <td>${escapeHtml(item.difference_reason || "")}</td>
      <td>${escapeHtml(item.match_status || "")}</td>
    </tr>`).join("")}</tbody>
  </table>`;
}

historyRefreshBtn?.addEventListener("click", () => loadHistoryList(true));
historyReportFilter?.addEventListener("change", () => {
  historyCurrentPage = 1;
  renderHistoryList();
});
historyExecutorFilter?.addEventListener("change", () => {
  historyCurrentPage = 1;
  renderHistoryList();
});
clearHistoryReportFilterBtn?.addEventListener("click", () => clearHistoryFilterControl(historyReportFilter));
clearHistoryExecutorFilterBtn?.addEventListener("click", () => clearHistoryFilterControl(historyExecutorFilter));
chartDateSelect?.addEventListener("change", () => {
  selectedChartDate = chartDateSelect.value;
  renderChart();
});

// Trend filter quick buttons
trendQuickBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    trendQuickBtns.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const range = btn.dataset.range;
    trendQuickFilter = range;
    if (range === "all") { trendDateStart = ""; trendDateEnd = ""; }
    else if (range === "3m") { trendDateStart = shiftBeijingDate({ months: -3 }); trendDateEnd = ""; }
    else if (range === "6m") { trendDateStart = shiftBeijingDate({ months: -6 }); trendDateEnd = ""; }
    else if (range === "1y") { trendDateStart = shiftBeijingDate({ years: -1 }); trendDateEnd = ""; }
    else if (range === "2y") { trendDateStart = shiftBeijingDate({ years: -2 }); trendDateEnd = ""; }
    renderTrendChart();
  });
});
historyPrevPageBtn?.addEventListener("click", () => {
  if (historyCurrentPage > 1) {
    historyCurrentPage--;
    renderHistoryList();
  }
});
historyNextPageBtn?.addEventListener("click", () => {
  const { totalPages } = getHistoryPageItems();
  if (historyCurrentPage < totalPages) {
    historyCurrentPage++;
    renderHistoryList();
  }
});
historyJumpPage?.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  const { totalPages } = getHistoryPageItems();
  const page = Math.max(1, Math.min(totalPages, parseInt(historyJumpPage.value || "1", 10) || 1));
  historyCurrentPage = page;
  historyJumpPage.value = "";
  renderHistoryList();
});
async function restoreHistoryRun(run) {
  if (!run) return;
  hasReconciled = false;
  resultEmptyState = "";
  results = run.results || [];
  runDate.value = run.run_date || runDate.value;
  keywordFilter.value = ""; reasonFilter.value = ""; statusFilter.value = "";
  syncCustomSelect(reasonFilter);
  syncCustomSelect(statusFilter);
  setResultHistoryRestoreState(run, results.length);
  currentPage = 1; renderResults(); await switchPage("auto-check");
  setStatus(historyRestoreHintText(resultRestoreHistoryMeta, results.length));
  showToast("结果列表已恢复到历史数据", "info");
}

historyBody?.addEventListener("click", async (e) => {
  const button = e.target.closest("button[data-id]"); if (!button) return;
  const id = button.dataset.id;
  try {
    if (button.classList.contains("view-history")) {
      await showHistoryDetailModal(id);
      setStatus("已加载历史详情");
    } else if (button.classList.contains("delete-history")) {
      if (!canManageHistory()) {
        setStatus("普通用户无权删除历史记录");
        return;
      }
      const confirmed = await showConfirm("删除历史记录", "确定删除这条历史记录吗？");
      if (!confirmed) return;
      await api("/api/history", { method: "DELETE", body: JSON.stringify({ id }) });
      if ((selectedHistory && selectedHistory.id === id) || selectedHistoryId === String(id || "")) {
        selectedHistory = null;
        selectedHistoryId = "";
      }
      await loadHistoryList();
      setStatus("历史记录已删除");
    }
  } catch (err) { setStatus(err.message); }
});

async function loadLatestHistoryResults() {
  try {
    const payload = await api("/api/history");
    const runs = payload.history || [];
    if (!runs.length) return;
    const latest = [...runs].sort(compareHistoryRunsByRunAtDesc)[0];
    if (!latest?.id) return;
    const detailPayload = await api(`/api/history/${encodeURIComponent(latest.id)}`);
    const latestHistory = detailPayload.history;
    clearResultHistoryRestoreState();
    homeResultListFilterLabel = "";
    keywordFilter.value = "";
    reasonFilter.value = "";
    statusFilter.value = "";
    syncCustomSelect(reasonFilter);
    syncCustomSelect(statusFilter);
    results = latestHistory.results || [];
    resultEmptyState = "";
    runDate.value = latestHistory.run_date || runDate.value;
    currentPage = 1;
    renderResults();
    if (latestHistory.run_at) setLastRunTime(latestHistory.run_at, historyExecutorName(latestHistory));
    saveLatestResultsSnapshot({ runAt: latestHistory.run_at || latestRunAt, executorName: historyExecutorName(latestHistory) });
    return true;
  } catch (_) {
    return false;
  }
}

/* ===== Config Management ===== */
const configToggle = document.getElementById("configToggle");
const configBody = document.getElementById("configBody");
const configList = document.getElementById("configList");
const collapseArrow = document.getElementById("collapseArrow");
const newConfigBtn = document.getElementById("newConfigBtn");
const configModal = document.getElementById("configModal");
const modalTitle = document.getElementById("modalTitle");
const modalClose = document.getElementById("modalClose");
const modalStatus = document.getElementById("modalStatus");
const modalSaveBtn = document.getElementById("modalSaveBtn");
const modalTestBtn = document.getElementById("modalTestBtn");
const reconcileSchemaForm = document.getElementById("reconcileSchemaForm");
const saveReconcileSchemaBtn = document.getElementById("saveReconcileSchemaBtn");
const initReconcileSchemaFromFileBtn = document.getElementById("initReconcileSchemaFromFileBtn");
const reconcileSchemaStatus = document.getElementById("reconcileSchemaStatus");

let editingId = null;
let allConfigs = [];
let activeReconcileBusinessSourceName = "";
let modalTestRequestToken = 0;
let reconcileSchemaState = { version: 1, strict: true, tables: {} };
let reconcileSchemaDataSources = [];
let reconcileSchemaColumnCache = {};

const RECONCILE_SCHEMA_TABLES = [
  {
    key: "zf_detail",
    name: "资负明细",
    fields: [
      ["check_date", "核对日期", "caldate"],
      ["project_code", "项目内码", "projinnercode"],
      ["project_name", "项目名称", "projname"],
      ["asset_total", "资产总计", "a0001"],
      ["liability_equity_total", "负债和权益总计", "d0000"],
      ["received_trust_balance", "实收信托余额", "c1000"],
    ],
  },
  {
    key: "fa_account_balance",
    name: "FA 科目余额",
    fields: [
      ["project_code", "项目代码", "c_projcode"],
      ["balance_date", "余额日期", "d_balancedate"],
      ["account_code", "科目代码", "c_accountcode"],
      ["account_name", "科目名称", "c_accountname"],
      ["balance", "余额", "f_balance"],
    ],
  },
  {
    key: "fa_valuation",
    name: "FA 估值表",
    fields: [
      ["project_code", "项目代码", "c_projcode"],
      ["valuation_date", "估值日期", "d_valuationdate"],
      ["account_code", "科目代码", "c_accountcode"],
      ["account_name", "科目名称", "c_accountname"],
      ["market_value", "市值/余额", "f_marketvalue"],
    ],
  },
  {
    key: "am_pact_asset",
    name: "AM 合同标的",
    fields: [
      ["project_code", "项目代码", "c_projcode"],
      ["close_date", "截止日期", "d_cldate"],
      ["asset_name", "标的名称", "c_udlyasset"],
      ["stock_code", "标的代码", "c_stockcode"],
      ["pact_id", "合同编号", "c_pactid"],
      ["spv_type", "SPV 类型", "c_spv_type"],
      ["asset_type", "标的类型", "c_assettype"],
      ["data_source", "合同来源", "c_datasource"],
    ],
  },
  {
    key: "am_project_invest",
    name: "AM 项目投资",
    fields: [
      ["project_code", "项目代码", "c_projcode"],
      ["close_date", "截止日期", "d_cldate"],
      ["pact_id", "合同编号", "c_pactid"],
      ["invest_balance", "投资余额", "f_acbalance"],
      ["contract_start_date", "合同开始日", "d_bdate"],
    ],
  },
  {
    key: "ta_pact_detail",
    name: "TA 合同明细",
    fields: [
      ["project_code", "项目代码", "c_projcode"],
      ["close_date", "截止日期", "d_cldate"],
      ["share_amount", "份额", "f_shareamt"],
      ["all_income", "累计收益", "f_alltincom"],
    ],
  },
  {
    key: "ta_survamt_dm",
    name: "TA 合同存量日表",
    fields: [
      ["check_date", "核对日期", "tpm_date"],
      ["project_code", "项目代码", "tpm_tcmpcode"],
      ["pact_id", "合同编号", "tpm_pactid"],
      ["client_name", "客户名称", "tpm_clientname"],
      ["client_kind", "客户类型", "tpm_clientkind_tusp"],
      ["client_kind_index", "客户类型序号", "tpm_clientkindex"],
      ["spv_type", "SPV 类型", "tpm_spvtype"],
      ["ht_income", "衡泰收益", "tpm_htincome"],
      ["share_amount", "份额", "tpm_shareamt"],
    ],
  },
  {
    key: "fa_security_balance_dm",
    name: "FA 证券余额日表",
    fields: [
      ["project_code", "项目代码", "sbm_projcode"],
      ["check_date", "核对日期", "sbm_cacldate"],
      ["stock_code", "证券代码", "sbm_stockcode"],
      ["security_name", "证券名称", "sbm_sename"],
      ["bond_category", "债券分类", "sbm_seclas_h2024"],
      ["stock_equity_category", "股票/股权分类", "sbm_gpgqtype_h"],
      ["fund_type", "基金类型", "sbm_fundtype"],
      ["balance_cost", "成本余额", "sbm_balamoney_cost"],
      ["balance_fair", "公允价值余额", "sbm_balamoney_fair"],
      ["balance_interest", "利息余额", "sbm_balamoney_inte"],
    ],
  },
  {
    key: "dm_project_invest",
    name: "AM 项目投资日表",
    fields: [
      ["project_code", "项目代码", "pin_projcode"],
      ["close_date", "截止日期", "pin_cldate"],
      ["pact_id", "合同编号", "pin_mpactid"],
      ["invest_balance", "投资余额", "pin_acbalance"],
      ["equity_invest_type", "股权投资类型", "pin_gqtype_h"],
    ],
  },
  {
    key: "dm_spv_project_invest",
    name: "AM SPV 项目投资日表",
    fields: [
      ["project_code", "项目代码", "svd_projcode"],
      ["close_date", "截止日期", "svd_cldate"],
      ["pact_id", "合同编号", "svd_mpactid"],
      ["asset_type", "资产类型", "svd_assettype"],
      ["balance_cost", "成本余额", "svd_balamoney_cost"],
      ["balance_interest", "利息余额", "svd_balamoney_inte"],
      ["balance_fair", "公允价值余额", "svd_balamoney_fair"],
    ],
  },
  {
    key: "property_right_contract",
    name: "财产权合同信息",
    fields: [
      ["project_code", "项目代码", "pjdw_projcode"],
      ["pact_id", "合同编号", "pin_mpactid"],
      ["invest_balance", "投资余额", "pin_acbalance"],
    ],
  },
  {
    key: "pledge_back",
    name: "回购质押表",
    fields: [
      ["project_code", "项目代码", "project_code"],
      ["subject_code", "科目/标的代码", "subcode"],
      ["buyback_money", "回购金额", "buyback_money"],
      ["expenses", "费用", "expenses"],
    ],
  },
  {
    key: "ta_asset_share_duration",
    name: "资产份额期间表",
    fields: [
      ["check_date", "核对日期", "caldate"],
      ["project_code", "项目代码", "c_projectcode"],
      ["asset_share", "资产份额", "f_assetshare"],
    ],
  },
  ...["2_1_2", "2_1_4", "2_1_5", "2_1_5_2", "2_1_6", "2_1_8", "2_1_9"].map((suffix) => ({
    key: `report_detail_${suffix}`,
    name: `报表 ${suffix.split("_").join(".")} 明细`,
    fields: [["check_date", "核对日期", "caldate"]],
  })),
];

const RECONCILE_SCHEMA_DEFAULT_TABLES = {
  zf_detail: "zf_detail_2024",
  fa_account_balance: "fa_accountbalance_dws",
  fa_valuation: "fa_valuationreport_dws",
  am_pact_asset: "am_pactasset_dws",
  am_project_invest: "am_projinvest_dws",
  ta_pact_detail: "ta_pact_detail_dws",
  ta_survamt_dm: "dm.ta_pact_survamt_day_zgxg_dm",
  fa_security_balance_dm: "dm.fa_security_balance_zgxg_dm",
  dm_project_invest: "dm.am_projinvest_zgxg_dm",
  dm_spv_project_invest: "dm.am_projinvest_spv_zgxg_dm",
  property_right_contract: "zgxg_zhbs.ccqxx",
  pledge_back: "ass_man_reg.ex_pledge_back",
  ta_asset_share_duration: "currency_report_duration",
  report_detail_2_1_2: "currency_report_24.currency_detail_project_2_1_2",
  report_detail_2_1_4: "currency_report_24.currency_detail_project_2_1_4",
  report_detail_2_1_5: "currency_report_24.currency_detail_project_2_1_5",
  report_detail_2_1_5_2: "currency_report_24.currency_detail_project_2_1_5_2",
  report_detail_2_1_6: "currency_report_24.currency_detail_project_2_1_6",
  report_detail_2_1_8: "currency_report_24.currency_detail_project_2_1_8",
  report_detail_2_1_9: "currency_report_24.currency_detail_project_2_1_9",
};

configToggle.addEventListener("click", () => {
  if (!configToggle.classList.contains("collapsible")) return;
  configBody.hidden = !configBody.hidden;
  if (collapseArrow) collapseArrow.style.transform = configBody.hidden ? "rotate(0deg)" : "rotate(180deg)";
  if (!configBody.hidden) loadConfigList();
});

function resetModalTestConnectionState() {
  modalTestRequestToken += 1;
  if (modalTestBtn) modalTestBtn.disabled = false;
}

function closeConfigModal() {
  resetModalTestConnectionState();
  configModal.classList.add("closing");
  setTimeout(() => {
    configModal.hidden = true;
    configModal.classList.remove("closing");
  }, 200);
}

modalClose.addEventListener("click", closeConfigModal);
newConfigBtn?.addEventListener("click", () => openModal(null));
document.getElementById("mdSourceType")?.addEventListener("change", () => {
  syncDataSourceSchemaVisibility("mdSource");
  syncDataSourcePortForType("mdSource", { force: true });
});

function syncDataSourceSchemaVisibility(prefix) {
  const type = document.getElementById(prefix + "Type")?.value || "";
  const schemaField = document.getElementById(prefix + "SchemaField");
  const schemaInput = document.getElementById(prefix + "Schema");
  const isPostgres = type === "postgresql";
  if (schemaField) schemaField.hidden = !isPostgres;
  if (!isPostgres && schemaInput) schemaInput.value = "";
}

function defaultPortForDataSourceType(type) {
  return String(type || "").toLowerCase() === "mysql" ? 3306 : 5432;
}

function parseHostWithOptionalPort(rawHost = "") {
  const text = String(rawHost || "").trim();
  if (!text) return { host: "", port: 0 };
  const colonIdx = text.lastIndexOf(":");
  if (colonIdx > 0) {
    return {
      host: text.slice(0, colonIdx),
      port: parseInt(text.slice(colonIdx + 1), 10) || 0,
    };
  }
  return { host: text, port: 0 };
}

function syncDataSourcePortForType(prefix, options = {}) {
  const type = document.getElementById(prefix + "Type")?.value || "postgresql";
  const hostInput = document.getElementById(prefix + "Host");
  if (!hostInput) return;
  const { host, port } = parseHostWithOptionalPort(hostInput.value);
  const nextPort = defaultPortForDataSourceType(type);
  if (!options.force && port) return;
  hostInput.value = `${host || "127.0.0.1"}:${nextPort}`;
}

function openModal(config) {
  resetModalTestConnectionState();
  editingId = config ? config.id : null;
  modalTitle.textContent = config ? "编辑数据源" : "新建数据源";
  modalStatus.textContent = "";
  if (config) {
    document.getElementById("modalName").value = config.name;
    fillDs("mdSource", config);
  } else {
    document.getElementById("modalName").value = "";
    fillDs("mdSource", { db_type: "postgresql", host: "127.0.0.1", port: 5432, database: "", schema: "", username: "", password: "" });
  }
  configModal.classList.remove("closing");
  configModal.hidden = false;
}

function fillDs(prefix, ds) {
  const host = ds.host ? `${ds.host}${ds.port ? ":" + ds.port : ""}` : "";
  document.getElementById(prefix + "Type").value = ds.db_type || "";
  document.getElementById(prefix + "Host").value = host;
  document.getElementById(prefix + "Db").value = ds.database || "";
  document.getElementById(prefix + "Schema").value = ds.schema || "";
  document.getElementById(prefix + "User").value = ds.username || "";
  document.getElementById(prefix + "Pwd").value = ds.password || "";
  syncDataSourceSchemaVisibility(prefix);
  syncDataSourcePortForType(prefix, { force: false });
}

function readDs(prefix) {
  const rawHost = document.getElementById(prefix + "Host").value.trim();
  const passwordValue = document.getElementById(prefix + "Pwd").value;
  const { host, port } = parseHostWithOptionalPort(rawHost);
  return {
    db_type: document.getElementById(prefix + "Type").value,
    host: host,
    port: port,
    database: document.getElementById(prefix + "Db").value.trim(),
    schema: document.getElementById(prefix + "Type").value === "postgresql" ? document.getElementById(prefix + "Schema").value.trim() : "",
    username: document.getElementById(prefix + "User").value.trim(),
    password_value: passwordValue,
  };
}

function readModal() {
  return {
    id: editingId || "",
    name: document.getElementById("modalName").value.trim(),
    ...readDs("mdSource"),
  };
}

async function encryptDataSourcePasswordsForTransport(config) {
  const payload = JSON.parse(JSON.stringify(config));
  const passwordValue = payload.password_value || "";
  delete payload.password_value;
  delete payload.password;
  if (passwordValue) {
    payload.password_encrypted = await encryptPasswordForTransport(passwordValue);
  }
  return payload;
}

async function loadConfigList() {
  try {
    const data = await api("/api/configs");
    allConfigs = sortConfigsForDisplay(data.data_sources || data.configs || []);
    renderConfigList();
    if (!runDate.value) {
      try { const d = await api("/api/config"); if (d.default_run_date && !runDate.value) runDate.value = d.default_run_date; } catch (_) {}
    }
  } catch (e) { configList.innerHTML = '<p class="placeholder-text">加载失败</p>'; }
}

function sortConfigsForDisplay(configs) {
  return [...configs].sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "zh-CN"));
}

function renderConfigList() {
  if (!allConfigs.length) {
    configList.innerHTML = '<p class="placeholder-text">暂无数据源配置</p>';
    return;
  }
  const configs = sortConfigsForDisplay(allConfigs);
  configList.innerHTML = configs.map((c) => `
    <div class="config-item">
      <span class="config-item-name">${escapeHtml(c.name)}</span>
      <span class="config-item-info">${escapeHtml(c.db_type || "")}/${escapeHtml(c.host || "")}:${escapeHtml(c.port || "")} | ${escapeHtml(c.database || "")}${c.schema ? ` / ${escapeHtml(c.schema)}` : ""}</span>
      <div class="config-item-actions">
        <button class="btn-outline btn-xs edit-cfg" data-id="${escapeHtml(c.id || "")}">编辑</button>
        <button class="btn-outline btn-xs btn-danger del-cfg" data-id="${escapeHtml(c.id || "")}">删除</button>
      </div>
    </div>
  `).join("");

  configList.querySelectorAll(".edit-cfg").forEach((b) => b.addEventListener("click", () => {
    const cfg = allConfigs.find((c) => c.id === b.dataset.id);
    if (cfg) openModal(cfg);
  }));
  configList.querySelectorAll(".del-cfg").forEach((b) => b.addEventListener("click", async () => {
    const cfg = allConfigs.find((c) => c.id === b.dataset.id);
    const confirmed = await showConfirm("删除数据源", `确定删除“${cfg?.name || b.dataset.id}”吗？`);
    if (!confirmed) return;
    try { await api("/api/configs", { method: "DELETE", body: JSON.stringify({ id: b.dataset.id }) }); loadConfigList(); setStatus("已删除"); } catch (e) { setStatus(e.message); }
  }));
}

function normalizeReconcileSchemaForForm(schema = {}) {
  return {
    version: schema.version || 1,
    strict: schema.strict !== false,
    tables: schema.tables && typeof schema.tables === "object" ? schema.tables : {},
  };
}

function reconcileSchemaSourceOptions(sourceRef = {}) {
  const sourceId = String(sourceRef.id || "").trim();
  const sourceName = String(sourceRef.name || "").trim();
  const matched = reconcileSchemaDataSources.find((item) => item.id === sourceId)
    || reconcileSchemaDataSources.find((item) => item.name === sourceName);
  const selectedId = matched?.id || sourceId;
  const options = ['<option value="">请选择数据源</option>'];
  if (selectedId && !reconcileSchemaDataSources.some((item) => item.id === selectedId)) {
    options.push(`<option value="${escapeHtml(selectedId)}" selected>${escapeHtml(sourceName || selectedId)}</option>`);
  }
  reconcileSchemaDataSources.forEach((item) => {
    const selected = item.id === selectedId ? " selected" : "";
    options.push(`<option value="${escapeHtml(item.id || "")}"${selected}>${escapeHtml(item.name || item.id || "")}</option>`);
  });
  return options.join("");
}

function reconcileSchemaFieldValue(tableConfig, fieldKey, defaultValue, optional = false) {
  const primary = optional ? tableConfig.optional_fields : tableConfig.fields;
  const fallback = optional ? tableConfig.fields : tableConfig.optional_fields;
  const value = primary && Object.prototype.hasOwnProperty.call(primary, fieldKey)
    ? primary[fieldKey]
    : fallback && Object.prototype.hasOwnProperty.call(fallback, fieldKey)
      ? fallback[fieldKey]
      : defaultValue;
  return String(value || "");
}

function reconcileSchemaDisplayNameValue(meta, tableConfig = {}) {
  return String(tableConfig.display_name || meta?.name || "");
}

function reconcileSchemaFieldRows(meta, tableConfig) {
  const requiredRows = meta.fields.map(([fieldKey, label, defaultValue]) => ({
    fieldKey,
    label,
    defaultValue,
    optional: false,
  }));
  const optionalRows = (meta.optionalFields || []).map(([fieldKey, label, defaultValue]) => ({
    fieldKey,
    label,
    defaultValue,
    optional: true,
  }));
  return [...requiredRows, ...optionalRows].map((field) => {
    const value = reconcileSchemaFieldValue(tableConfig, field.fieldKey, field.defaultValue, field.optional);
    return `
      <div class="reconcile-schema-field-row">
        <span class="reconcile-schema-field-name">
          <strong>${escapeHtml(field.label)}</strong>
          <small>${escapeHtml(field.fieldKey)}${field.optional ? " · 可选" : ""}</small>
        </span>
        <span
          class="reconcile-schema-field-combobox"
          data-field-key="${escapeHtml(field.fieldKey)}"
          data-field-optional="${field.optional ? "1" : "0"}"
        >
          <input
            class="setting-input reconcile-schema-field-search"
            value="${escapeHtml(value)}"
            placeholder="${escapeHtml(field.defaultValue || "")}"
            autocomplete="off"
            ${field.optional ? "" : "required"}
          />
          <span class="reconcile-schema-field-options" hidden></span>
        </span>
      </div>
    `;
  }).join("");
}

function renderReconcileSchemaForm(schema = {}, dataSources = reconcileSchemaDataSources) {
  if (!reconcileSchemaForm) return;
  reconcileSchemaState = normalizeReconcileSchemaForForm(schema);
  reconcileSchemaDataSources = sortConfigsForDisplay(Array.isArray(dataSources) ? dataSources : []);
  reconcileSchemaForm.innerHTML = RECONCILE_SCHEMA_TABLES.map((meta) => {
    const tableConfig = reconcileSchemaState.tables[meta.key] || {};
    const sourceRef = tableConfig.source_ref || {};
    const tableName = String(tableConfig.table || RECONCILE_SCHEMA_DEFAULT_TABLES[meta.key] || "");
    const displayName = reconcileSchemaDisplayNameValue(meta, tableConfig);
    return `
      <section class="reconcile-schema-table" data-reconcile-table-key="${escapeHtml(meta.key)}">
        <div class="reconcile-schema-table-head">
          <div class="reconcile-schema-table-title">
            <strong>${escapeHtml(displayName)}</strong>
            <span>${escapeHtml(meta.key)}</span>
          </div>
          <button type="button" class="btn-outline btn-xs reconcile-schema-toggle" data-key="${escapeHtml(meta.key)}">展开字段</button>
        </div>
        <div class="reconcile-schema-table-grid">
          <label class="setting-item">
            <span class="setting-label">数据源</span>
            <select class="setting-input reconcile-schema-source" data-key="${escapeHtml(meta.key)}" required>${reconcileSchemaSourceOptions(sourceRef)}</select>
          </label>
          <label class="setting-item">
            <span class="setting-label">标准中文名</span>
            <input class="setting-input reconcile-schema-display-name" data-key="${escapeHtml(meta.key)}" value="${escapeHtml(displayName)}" placeholder="${escapeHtml(meta.name)}" required />
          </label>
          <label class="setting-item">
            <span class="setting-label">物理表名</span>
            <input class="setting-input reconcile-schema-table-name" data-key="${escapeHtml(meta.key)}" value="${escapeHtml(tableName)}" placeholder="schema.table" required />
          </label>
          <div class="reconcile-schema-table-state" data-key="${escapeHtml(meta.key)}"></div>
        </div>
        <div class="reconcile-schema-fields" data-key="${escapeHtml(meta.key)}" hidden>
          <div class="reconcile-schema-field-toolbar">
            <span class="reconcile-schema-field-status" data-key="${escapeHtml(meta.key)}">聚焦字段后自动读取数据库字段并可下拉选择</span>
          </div>
          <div class="reconcile-schema-field-list">${reconcileSchemaFieldRows(meta, tableConfig)}</div>
        </div>
      </section>
    `;
  }).join("");
  RECONCILE_SCHEMA_TABLES.forEach((meta) => refreshReconcileSchemaTableStatus(meta.key));
  renderBusinessSettings();
}

function reconcileSchemaTableElement(key) {
  return reconcileSchemaForm?.querySelector(`.reconcile-schema-table[data-reconcile-table-key="${key}"]`) || null;
}

function refreshReconcileSchemaTableStatus(key) {
  const meta = RECONCILE_SCHEMA_TABLES.find((item) => item.key === key);
  const tableEl = reconcileSchemaTableElement(key);
  if (!meta || !tableEl) return;
  const sourceValue = tableEl.querySelector("select.reconcile-schema-source")?.value || "";
  const displayNameValue = readTrimmedControlValue(tableEl.querySelector("input.reconcile-schema-display-name"));
  const tableValue = readTrimmedControlValue(tableEl.querySelector("input.reconcile-schema-table-name"));
  const requiredInputs = [...tableEl.querySelectorAll('.reconcile-schema-field-combobox[data-field-optional="0"] input.reconcile-schema-field-search')];
  const filledRequired = requiredInputs.filter((input) => readTrimmedControlValue(input)).length;
  const status = tableEl.querySelector(".reconcile-schema-table-state");
  const incomplete = !sourceValue || !displayNameValue || !tableValue || filledRequired < requiredInputs.length;
  tableEl.classList.toggle("is-incomplete", incomplete);
  if (status) {
    status.textContent = incomplete
      ? `待完善：必填字段 ${filledRequired}/${requiredInputs.length}`
      : `已配置：必填字段 ${filledRequired}/${requiredInputs.length}`;
  }
}

function readTrimmedControlValue(control) {
  return String(control?.value ?? "").trim();
}

function reconcileSchemaFieldInput(tableEl, fieldKey) {
  return tableEl?.querySelector(`.reconcile-schema-field-combobox[data-field-key="${fieldKey}"] input.reconcile-schema-field-search`) || null;
}

function reconcileSchemaVisibleControl(control) {
  if (!control) return null;
  if (control.tagName === "SELECT") return customSelectStates.get(control)?.shell || control;
  return control.closest(".custom-input-shell") || control.closest(".custom-select-shell") || control;
}

function reconcileSchemaErrorHolder(control) {
  return control?.closest(".setting-item") || control?.closest(".reconcile-schema-field-combobox") || control?.parentElement || null;
}

function reconcileSchemaDirectErrorMessage(holder) {
  return [...(holder?.children || [])].find((child) => child.classList?.contains("reconcile-schema-error-message")) || null;
}

function clearReconcileSchemaRequiredError(control) {
  if (!control) return;
  control.classList.remove("reconcile-schema-required-error");
  control.removeAttribute("aria-invalid");
  if (control.dataset.requiredError) {
    delete control.dataset.requiredError;
    if (!control.classList.contains("is-invalid")) control.title = "";
  }
  const visibleControl = reconcileSchemaVisibleControl(control);
  if (visibleControl && visibleControl !== control) {
    visibleControl.classList.remove("reconcile-schema-required-error");
    visibleControl.removeAttribute("aria-invalid");
  }
  const holder = reconcileSchemaErrorHolder(control);
  reconcileSchemaDirectErrorMessage(holder)?.remove();
}

function clearReconcileSchemaRequiredErrors(scope = reconcileSchemaForm) {
  (scope?.querySelectorAll(".reconcile-schema-required-error") || []).forEach((control) => {
    clearReconcileSchemaRequiredError(control);
  });
  (scope?.querySelectorAll(".reconcile-schema-error-message") || []).forEach((message) => {
    message.remove();
  });
}

function markReconcileSchemaRequiredError(control, message) {
  if (!control) return;
  control.classList.add("reconcile-schema-required-error");
  control.setAttribute("aria-invalid", "true");
  control.dataset.requiredError = "1";
  control.title = message;
  const visibleControl = reconcileSchemaVisibleControl(control);
  if (visibleControl && visibleControl !== control) {
    visibleControl.classList.add("reconcile-schema-required-error");
    visibleControl.setAttribute("aria-invalid", "true");
  }
  const holder = reconcileSchemaErrorHolder(control);
  if (!holder) return;
  let messageEl = reconcileSchemaDirectErrorMessage(holder);
  if (!messageEl) {
    messageEl = document.createElement("span");
    messageEl.className = "reconcile-schema-error-message";
    holder.appendChild(messageEl);
  }
  messageEl.textContent = message;
}

function expandReconcileSchemaTable(key) {
  const fields = reconcileSchemaForm?.querySelector(`.reconcile-schema-fields[data-key="${key}"]`);
  const toggle = reconcileSchemaForm?.querySelector(`.reconcile-schema-toggle[data-key="${key}"]`);
  if (fields) fields.hidden = false;
  if (toggle) toggle.textContent = "收起字段";
}

function validateReconcileSchemaRequiredFields() {
  const missing = [];
  let firstControl = null;
  let firstKey = "";
  clearReconcileSchemaRequiredErrors(reconcileSchemaForm);

  const addMissing = (key, tableName, label, control) => {
    const message = `请填写${label}`;
    missing.push(`${tableName}：${label}`);
    markReconcileSchemaRequiredError(control, message);
    if (!firstControl) {
      firstControl = control;
      firstKey = key;
    }
  };

  RECONCILE_SCHEMA_TABLES.forEach((meta) => {
    const tableEl = reconcileSchemaTableElement(meta.key);
    if (!tableEl) return;
    const sourceSelect = tableEl.querySelector("select.reconcile-schema-source");
    const displayNameInput = tableEl.querySelector("input.reconcile-schema-display-name");
    const tableInput = tableEl.querySelector("input.reconcile-schema-table-name");
    if (!readTrimmedControlValue(sourceSelect)) addMissing(meta.key, meta.name, "数据源", sourceSelect);
    if (!readTrimmedControlValue(displayNameInput)) addMissing(meta.key, meta.name, "标准中文名", displayNameInput);
    if (!readTrimmedControlValue(tableInput)) addMissing(meta.key, meta.name, "物理表名", tableInput);
    (meta.fields || []).forEach(([fieldKey, label]) => {
      const input = reconcileSchemaFieldInput(tableEl, fieldKey);
      if (!readTrimmedControlValue(input)) addMissing(meta.key, meta.name, label, input);
    });
  });

  if (firstControl && firstKey) {
    expandReconcileSchemaTable(firstKey);
    window.setTimeout(() => {
      firstControl.scrollIntoView({ block: "center", behavior: "smooth" });
      firstControl.focus({ preventScroll: true });
    }, 0);
  }

  return { missing, firstControl, firstKey };
}

function filterReconcileColumnOptions(columns = [], query = "") {
  const keyword = String(query || "").trim().toLowerCase();
  const normalized = (columns || []).map((column) => ({
    name: String(column.name || "").trim(),
    comment: String(column.comment || "").trim(),
  })).filter((column) => column.name);
  if (!keyword) return normalized.slice(0, 80);
  return normalized.filter((column) => {
    return column.name.toLowerCase().includes(keyword) || column.comment.toLowerCase().includes(keyword);
  }).slice(0, 80);
}

function renderReconcileFieldOptions(combo, columns = [], query = "") {
  const list = combo?.querySelector(".reconcile-schema-field-options");
  if (!list) return;
  const matches = filterReconcileColumnOptions(columns, query);
  if (!columns.length) {
    list.hidden = true;
    list.innerHTML = "";
    return;
  }
  if (!matches.length) {
    list.hidden = false;
    list.innerHTML = '<span class="reconcile-schema-field-option is-empty">未匹配到字段，可继续手工输入</span>';
    return;
  }
  list.hidden = false;
  list.innerHTML = matches.map((column) => `
    <button type="button" class="reconcile-schema-field-option" data-value="${escapeHtml(column.name)}">
      <span class="reconcile-schema-field-option-name">${escapeHtml(column.name)}</span>
      <span class="reconcile-schema-field-option-comment">${escapeHtml(column.comment || "无备注")}</span>
    </button>
  `).join("");
}

function closeReconcileFieldOptions(scope = reconcileSchemaForm) {
  (scope?.querySelectorAll(".reconcile-schema-field-options") || []).forEach((list) => {
    list.hidden = true;
  });
}

function reconcileSchemaFieldOptionsOpen(combo) {
  const list = combo?.querySelector(".reconcile-schema-field-options");
  return Boolean(list && !list.hidden);
}

function openReconcileFieldOptionsForInput(input) {
  const combo = input?.closest(".reconcile-schema-field-combobox");
  const tableEl = input?.closest(".reconcile-schema-table");
  if (!combo || !tableEl) return false;
  const key = tableEl.dataset.reconcileTableKey || "";
  closeReconcileFieldOptions(reconcileSchemaForm);
  if (!tableEl._reconcileColumns?.length && !tableEl._reconcileColumnsLoading) {
    loadReconcileTableColumns(key, { openCombo: combo, query: input.value || "" });
    return true;
  }
  renderReconcileFieldOptions(combo, tableEl._reconcileColumns || [], input.value || "");
  return true;
}

function splitFrontendReconcileSchemaMissingItems(rawItem = "") {
  const item = String(rawItem || "").trim();
  const match = item.match(/^请完善表字段配置[:：]\s*(.+)$/);
  if (!match) return item ? [item] : [];
  const body = String(match[1] || "").trim();
  if (!body) return [item];
  const parts = body.split("、").map((part) => part.trim()).filter(Boolean);
  if (parts.length <= 1) return [item];
  return parts.map((part) => `请完善表字段配置：${part}`);
}

function parseReconcileSchemaErrorItem(rawItem = "") {
  const item = String(rawItem || "").trim();
  const fallback = {
    logicalTable: "-",
    physicalTable: "-",
    field: "-",
    issue: item || "配置错误",
    detail: item || "保存失败，请检查表字段配置。",
  };
  if (!item) return fallback;

  let match = item.match(/^请完善表字段配置[:：]\s*(.+?)[:：](.+)$/);
  if (match) {
    return {
      logicalTable: String(match[1] || "").trim() || "-",
      physicalTable: "-",
      field: String(match[2] || "").trim() || "-",
      issue: "字段未填写",
      detail: item,
    };
  }

  match = item.match(/^请完善表字段配置[:：]\s*(.+)$/);
  if (match) {
    return {
      logicalTable: "-",
      physicalTable: "-",
      field: String(match[1] || "").trim() || "-",
      issue: "字段未填写",
      detail: item,
    };
  }

  match = item.match(/^(.+?)\s+缺少物理表名$/);
  if (match) {
    return {
      logicalTable: match[1],
      physicalTable: "-",
      field: "-",
      issue: "物理表名未配置",
      detail: item,
    };
  }

  match = item.match(/^(.+?)\s+缺少字段配置[:：](.+)$/);
  if (match) {
    return {
      logicalTable: match[1],
      physicalTable: "-",
      field: String(match[2] || "").trim() || "-",
      issue: "字段未配置",
      detail: item,
    };
  }

  match = item.match(/^(.+?)\s+字段\s+([^=：:]+)=([^：:]+)[:：](.+)$/);
  if (match) {
    return {
      logicalTable: match[1],
      physicalTable: "-",
      field: `${String(match[3] || "").trim()}（${String(match[2] || "").trim()}）`,
      issue: "字段名不合法",
      detail: String(match[4] || item).trim(),
    };
  }

  match = item.match(/^(.+?)\s+(\S+)\s+缺少字段\s+(.+?)(?:[（(]([^）)]*)[）)])?$/);
  if (match) {
    const fieldName = String(match[3] || "").trim();
    const fieldKey = String(match[4] || "").trim();
    return {
      logicalTable: match[1],
      physicalTable: match[2],
      field: fieldKey ? `${fieldName}（${fieldKey}）` : fieldName,
      issue: "字段不存在",
      detail: item,
    };
  }

  match = item.match(/^(.+?)\s+(\S+)[:：](.+)$/);
  if (match) {
    return {
      logicalTable: match[1],
      physicalTable: match[2],
      field: "-",
      issue: "表或数据源错误",
      detail: String(match[3] || item).trim(),
    };
  }

  return fallback;
}

function formatReconcileSchemaSaveErrors(message = "") {
  const raw = String(message || "保存失败，请检查表字段配置。").trim() || "保存失败，请检查表字段配置。";
  const body = raw.replace(/^表字段配置校验失败[:：]\s*/, "");
  const items = body.split(/[；;]/)
    .flatMap(splitFrontendReconcileSchemaMissingItems)
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length ? items.map(parseReconcileSchemaErrorItem) : [parseReconcileSchemaErrorItem(raw)];
}

function showReconcileSchemaSaveError(message = "", title = "表字段配置保存失败") {
  const text = String(message || "保存失败，请检查表字段配置。").trim() || "保存失败，请检查表字段配置。";
  const rows = formatReconcileSchemaSaveErrors(text);
  const tableRows = rows.map((row, index) => `
    <tr>
      <td class="num">${escapeHtml(index + 1)}</td>
      <td title="${escapeHtml(row.logicalTable)}">${escapeHtml(row.logicalTable)}</td>
      <td title="${escapeHtml(row.physicalTable)}"><code>${escapeHtml(row.physicalTable)}</code></td>
      <td title="${escapeHtml(row.field)}"><code>${escapeHtml(row.field)}</code></td>
      <td title="${escapeHtml(row.issue)}">${escapeHtml(row.issue)}</td>
      <td title="${escapeHtml(row.detail)}">${escapeHtml(row.detail)}</td>
    </tr>
  `).join("");
  showInfo(title, `
    <div class="reconcile-schema-save-error">
      <p>保存时发现表或字段配置无法通过数据库校验，请按下表逐项处理。</p>
      <div class="reconcile-schema-save-error-table-wrap">
        <table class="reconcile-schema-save-error-table">
          <thead>
            <tr>
              <th class="num">#</th>
              <th>逻辑表</th>
              <th>物理表</th>
              <th>字段</th>
              <th>问题</th>
              <th>详情</th>
            </tr>
          </thead>
          <tbody>${tableRows}</tbody>
        </table>
      </div>
      <details>
        <summary>原始错误信息</summary>
        <pre>${escapeHtml(text)}</pre>
      </details>
    </div>
  `, {
    modalClass: "modal-info--reconcile-schema-error",
    closeOnBackdrop: false,
  });
}

function renderReconcileColumnOptions(tableEl, key, columns = [], options = {}) {
  if (!tableEl) return;
  tableEl._reconcileColumns = columns;
  const combos = [...tableEl.querySelectorAll(".reconcile-schema-field-combobox")];
  combos.forEach((combo, index) => {
    const input = combo.querySelector("input.reconcile-schema-field-search");
    const shouldOpen = combo === options.openCombo || Boolean(options.openFirst && index === 0);
    const query = shouldOpen && Object.prototype.hasOwnProperty.call(options, "query") ? options.query : input?.value || "";
    renderReconcileFieldOptions(combo, columns, query);
    const list = combo.querySelector(".reconcile-schema-field-options");
    if (list) list.hidden = !shouldOpen;
    if (shouldOpen && input && document.activeElement !== input) {
      input.focus();
    }
  });
}

function validateLoadedReconcileFields(tableEl, columns = []) {
  const names = new Set(columns.map((column) => String(column.name || "").toLowerCase()));
  const inputs = [...(tableEl?.querySelectorAll("input.reconcile-schema-field-search") || [])];
  let missingCount = 0;
  inputs.forEach((input) => {
    const value = readTrimmedControlValue(input);
    const missing = Boolean(value && names.size && !names.has(value.toLowerCase()));
    input.classList.toggle("is-invalid", missing);
    input.title = missing ? "当前读取的字段列表中没有这个字段，可确认后手动保留" : "";
    if (missing) missingCount += 1;
  });
  return missingCount;
}

async function loadReconcileTableColumns(key, options = {}) {
  const tableEl = reconcileSchemaTableElement(key);
  if (!tableEl) return;
  const status = tableEl.querySelector(".reconcile-schema-field-status");
  const sourceId = tableEl.querySelector("select.reconcile-schema-source")?.value || "";
  const tableName = readTrimmedControlValue(tableEl.querySelector("input.reconcile-schema-table-name"));
  if (!sourceId || !tableName) {
    if (status) status.textContent = "请先选择数据源并填写物理表名";
    return;
  }
  if (tableEl._reconcileColumnsLoading) {
    if (status) status.textContent = "字段读取中...";
    return;
  }
  const cacheKey = `${sourceId}::${tableName}`;
  if (reconcileSchemaColumnCache[cacheKey]) {
    renderReconcileColumnOptions(tableEl, key, reconcileSchemaColumnCache[cacheKey], options);
    const missing = validateLoadedReconcileFields(tableEl, reconcileSchemaColumnCache[cacheKey]);
    if (status) status.textContent = missing ? `已读取字段，${missing} 个字段需确认` : "已读取字段，可输入字段名或备注筛选";
    return;
  }
  if (status) status.textContent = "读取中...";
  tableEl._reconcileColumnsLoading = true;
  try {
    const payload = await api("/api/settings/reconcile-schema/columns", {
      method: "POST",
      body: JSON.stringify({ source_id: sourceId, table: tableName }),
    });
    const columns = payload.columns || [];
    reconcileSchemaColumnCache[cacheKey] = columns;
    renderReconcileColumnOptions(tableEl, key, columns, options);
    const missing = validateLoadedReconcileFields(tableEl, columns);
    if (status) status.textContent = missing ? `已读取 ${columns.length} 个字段，${missing} 个字段需确认` : `已读取 ${columns.length} 个字段，可输入字段名或备注筛选`;
  } catch (e) {
    if (status) status.textContent = e.message;
  } finally {
    tableEl._reconcileColumnsLoading = false;
  }
}

async function loadReconcileSchemaSettings() {
  if (!reconcileSchemaForm) return;
  try {
    const payload = await api("/api/settings/reconcile-schema");
    renderReconcileSchemaForm(payload.schema || {}, payload.data_sources || []);
    if (reconcileSchemaStatus) reconcileSchemaStatus.textContent = "";
  } catch (e) {
    if (reconcileSchemaStatus) reconcileSchemaStatus.textContent = e.message;
  }
}

function readReconcileSchemaForm() {
  const tables = { ...(reconcileSchemaState.tables || {}) };
  const requiredValidation = validateReconcileSchemaRequiredFields();
  if (requiredValidation.missing.length) {
    throw new Error(`请完善表字段配置：${requiredValidation.missing.join("、")}`);
  }
  RECONCILE_SCHEMA_TABLES.forEach((meta) => {
    const tableEl = reconcileSchemaTableElement(meta.key);
    if (!tableEl) return;
    const sourceSelect = tableEl.querySelector("select.reconcile-schema-source");
    const sourceId = sourceSelect?.value || "";
    const sourceName = sourceSelect?.selectedOptions?.[0]?.textContent?.trim() || sourceId;
    const displayName = readTrimmedControlValue(tableEl.querySelector("input.reconcile-schema-display-name")) || meta.name;
    const tableName = readTrimmedControlValue(tableEl.querySelector("input.reconcile-schema-table-name"));
    const existing = tables[meta.key] || {};
    const fields = { ...(existing.fields || {}) };
    const optionalFields = { ...(existing.optional_fields || {}) };
    (meta.fields || []).forEach(([fieldKey, label]) => {
      const input = reconcileSchemaFieldInput(tableEl, fieldKey);
      const value = readTrimmedControlValue(input);
      fields[fieldKey] = value;
      delete optionalFields[fieldKey];
    });
    (meta.optionalFields || []).forEach(([fieldKey]) => {
      const input = reconcileSchemaFieldInput(tableEl, fieldKey);
      const value = readTrimmedControlValue(input);
      if (value) optionalFields[fieldKey] = value;
      else delete optionalFields[fieldKey];
    });
    tables[meta.key] = {
      ...existing,
      source_ref: { id: sourceId, name: sourceName, match_by: "id_then_name" },
      table: tableName,
      display_name: displayName,
      fields,
      optional_fields: optionalFields,
    };
    refreshReconcileSchemaTableStatus(meta.key);
  });
  return {
    version: reconcileSchemaState.version || 1,
    strict: true,
    tables,
  };
}

function selectReconcileSchemaFieldOption(option) {
  const combo = option?.closest(".reconcile-schema-field-combobox");
  const tableEl = option?.closest(".reconcile-schema-table");
  const input = combo?.querySelector("input.reconcile-schema-field-search");
  if (!combo || !input) return false;
  input.value = option.dataset.value || "";
  clearReconcileSchemaRequiredError(input);
  closeReconcileFieldOptions(combo);
  const key = tableEl?.dataset.reconcileTableKey || "";
  if (tableEl) validateLoadedReconcileFields(tableEl, tableEl._reconcileColumns || []);
  if (key) refreshReconcileSchemaTableStatus(key);
  renderBusinessSettings();
  return true;
}

reconcileSchemaForm?.addEventListener("mousedown", (event) => {
  const option = event.target.closest(".reconcile-schema-field-option[data-value]");
  if (option) {
    event.preventDefault();
    selectReconcileSchemaFieldOption(option);
    return;
  }
  const fieldInput = event.target.closest("input.reconcile-schema-field-search");
  const combo = fieldInput?.closest(".reconcile-schema-field-combobox");
  if (fieldInput && document.activeElement === fieldInput && reconcileSchemaFieldOptionsOpen(combo)) {
    event.preventDefault();
    combo._reconcileSuppressNextInputClick = true;
    closeReconcileFieldOptions(combo);
  }
});

reconcileSchemaForm?.addEventListener("click", (event) => {
  const option = event.target.closest(".reconcile-schema-field-option[data-value]");
  if (option) {
    event.preventDefault();
    selectReconcileSchemaFieldOption(option);
    return;
  }
  const fieldInput = event.target.closest("input.reconcile-schema-field-search");
  const combo = fieldInput?.closest(".reconcile-schema-field-combobox");
  if (fieldInput && combo) {
    if (combo._reconcileSuppressNextInputClick) {
      combo._reconcileSuppressNextInputClick = false;
      return;
    }
    if (!reconcileSchemaFieldOptionsOpen(combo)) openReconcileFieldOptionsForInput(fieldInput);
    return;
  }
  const toggle = event.target.closest(".reconcile-schema-toggle");
  if (toggle) {
    const key = toggle.dataset.key || "";
    const fields = reconcileSchemaForm.querySelector(`.reconcile-schema-fields[data-key="${key}"]`);
    if (fields) {
      fields.hidden = !fields.hidden;
      toggle.textContent = fields.hidden ? "展开字段" : "收起字段";
    }
    return;
  }
  if (!event.target.closest(".reconcile-schema-field-combobox")) {
    closeReconcileFieldOptions(reconcileSchemaForm);
  }
});

reconcileSchemaForm?.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeReconcileFieldOptions(reconcileSchemaForm);
});

reconcileSchemaForm?.addEventListener("input", (event) => {
  const tableEl = event.target.closest(".reconcile-schema-table");
  const key = tableEl?.dataset.reconcileTableKey || "";
  const combo = event.target.closest(".reconcile-schema-field-combobox");
  if (event.target.matches?.("input.reconcile-schema-display-name, input.reconcile-schema-table-name, input.reconcile-schema-field-search") && readTrimmedControlValue(event.target)) {
    clearReconcileSchemaRequiredError(event.target);
  }
  if (event.target.matches?.("input.reconcile-schema-display-name") && tableEl) {
    const meta = reconcileMetaByKey(key);
    const title = tableEl.querySelector(".reconcile-schema-table-title strong");
    if (title) title.textContent = readTrimmedControlValue(event.target) || meta?.name || "";
  }
  if (combo && tableEl) {
    if (!tableEl._reconcileColumns?.length && !tableEl._reconcileColumnsLoading) {
      loadReconcileTableColumns(key, { openCombo: combo, query: event.target.value || "" });
    }
    renderReconcileFieldOptions(combo, tableEl._reconcileColumns || [], event.target.value || "");
    validateLoadedReconcileFields(tableEl, tableEl._reconcileColumns || []);
  }
  if (key) {
    refreshReconcileSchemaTableStatus(key);
    renderBusinessSettings();
  }
});

reconcileSchemaForm?.addEventListener("change", (event) => {
  const tableEl = event.target.closest(".reconcile-schema-table");
  const key = tableEl?.dataset.reconcileTableKey || "";
  if (event.target.matches?.("select.reconcile-schema-source") && readTrimmedControlValue(event.target)) {
    clearReconcileSchemaRequiredError(event.target);
  }
  if (key) {
    refreshReconcileSchemaTableStatus(key);
    renderBusinessSettings();
  }
});

reconcileSchemaForm?.addEventListener("focusin", (event) => {
  if (event.target.closest(".reconcile-schema-field-option")) return;
  if (!event.target.matches?.("input.reconcile-schema-field-search")) return;
  openReconcileFieldOptionsForInput(event.target);
});

document.addEventListener("click", (event) => {
  if (!reconcileSchemaForm || reconcileSchemaForm.contains(event.target)) return;
  closeReconcileFieldOptions(reconcileSchemaForm);
});

saveReconcileSchemaBtn?.addEventListener("click", async () => {
  if (reconcileSchemaStatus) reconcileSchemaStatus.textContent = "保存中...";
  if (saveReconcileSchemaBtn) saveReconcileSchemaBtn.disabled = true;
  try {
    const schema = readReconcileSchemaForm();
    const payload = await api("/api/settings/reconcile-schema", {
      method: "POST",
      body: JSON.stringify(schema),
    });
    renderReconcileSchemaForm(payload.schema || schema, reconcileSchemaDataSources);
    if (reconcileSchemaStatus) reconcileSchemaStatus.textContent = "已保存";
  } catch (e) {
    if (reconcileSchemaStatus) reconcileSchemaStatus.textContent = "保存失败，已打开错误详情";
    showReconcileSchemaSaveError(e.message);
  } finally {
    if (saveReconcileSchemaBtn) saveReconcileSchemaBtn.disabled = false;
  }
});

initReconcileSchemaFromFileBtn?.addEventListener("click", async () => {
  const confirmed = await showConfirm("初始化表字段配置", "将使用服务端 reconcile-schema.yaml 覆盖当前页面配置。是否继续？");
  if (!confirmed) return;
  if (reconcileSchemaStatus) reconcileSchemaStatus.textContent = "初始化中...";
  if (initReconcileSchemaFromFileBtn) initReconcileSchemaFromFileBtn.disabled = true;
  try {
    const payload = await api("/api/settings/reconcile-schema/init-from-file", { method: "POST", body: "{}" });
    renderReconcileSchemaForm(payload.schema || {}, reconcileSchemaDataSources);
    if (reconcileSchemaStatus) reconcileSchemaStatus.textContent = "已根据配置文件初始化";
  } catch (e) {
    if (reconcileSchemaStatus) reconcileSchemaStatus.textContent = "初始化失败，已打开错误详情";
    showReconcileSchemaSaveError(e.message, "表字段配置初始化失败");
  } finally {
    if (initReconcileSchemaFromFileBtn) initReconcileSchemaFromFileBtn.disabled = false;
  }
});

modalTestBtn.addEventListener("click", async () => {
  const requestToken = ++modalTestRequestToken;
  modalTestBtn.disabled = true; modalStatus.textContent = "测试中...";
  try {
    const modalConfig = readModal();
    const cfg = { ...modalConfig, editing_id: editingId || modalConfig.id };
    const p = await api("/api/test-connection", { method: "POST", body: JSON.stringify(await encryptDataSourcePasswordsForTransport(cfg)) });
    if (requestToken !== modalTestRequestToken || configModal.hidden) return;
    modalStatus.textContent = p.source?.ok ? "连接成功" : `连接失败：${p.source?.message || "未知错误"}`;
  } catch (e) {
    if (requestToken === modalTestRequestToken && !configModal.hidden) modalStatus.textContent = e.message;
  } finally {
    if (requestToken === modalTestRequestToken && !configModal.hidden) modalTestBtn.disabled = false;
  }
});

modalSaveBtn.addEventListener("click", async () => {
  const cfg = readModal();
  if (!cfg.name) { modalStatus.textContent = "请输入配置名称"; return; }
  modalSaveBtn.disabled = true; modalStatus.textContent = "保存中...";
  try {
    const current = allConfigs.find((c) => c.id === editingId);
    const body = { ...cfg, editing_id: editingId || cfg.id };
    if (current?.is_default) body.is_default = "true";
    await api("/api/configs", { method: "POST", body: JSON.stringify(await encryptDataSourcePasswordsForTransport(body)) });
    closeConfigModal();
    loadConfigList();
    setStatus("配置已保存");
  } catch (e) { modalStatus.textContent = e.message; }
  finally { modalSaveBtn.disabled = false; }
});

/* ===== Home Chart — Canvas Glass ===== */

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

function clampNumber(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function formatChartMonthDay(dateText = "") {
  const parts = String(dateText || "").split("-");
  if (parts.length < 3) return String(dateText || "");
  return `${Number(parts[1])}/${Number(parts[2])}`;
}

function formatChartRunAtLabel(runAt = "", fallbackDate = "") {
  const display = formatDisplayTime(runAt || "");
  const [datePart = fallbackDate, timePart = ""] = display.split(" ");
  const dateLabel = formatChartMonthDay(datePart || fallbackDate);
  const timeLabel = String(timePart || "").slice(0, 5);
  return [dateLabel, timeLabel].filter(Boolean).join(" ");
}

function formatChartNumber(value) {
  const n = Number(value || 0);
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function formatMetricChartNumber(metric = {}, value) {
  if (metric.integerValues) return String(Math.round(Number(value || 0)));
  return formatChartNumber(value);
}

function smoothCurveThrough(ctx, pts, tension = 0.35, bounds = null) {
  if (pts.length < 2) return;
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    const cp1x = p1.x + (p2.x - p0.x) * tension;
    let cp1y = p1.y + (p2.y - p0.y) * tension;
    const cp2x = p2.x - (p3.x - p1.x) * tension;
    let cp2y = p2.y - (p3.y - p1.y) * tension;
    if (bounds) {
      cp1y = clampNumber(cp1y, bounds.top, bounds.bottom);
      cp2y = clampNumber(cp2y, bounds.top, bounds.bottom);
    }
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
  }
}

function drawGlassChart(canvas, values, labels, animRef, showLabels = true, tooltipItems = []) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.parentElement.getBoundingClientRect();
  const w = rect.width, h = rect.height;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = w + "px";
  canvas.style.height = h + "px";
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const isSpace = document.documentElement.getAttribute("data-theme") === "space-tech";
  const isDark = document.documentElement.getAttribute("data-color-mode") === "dark";
  const lineColor = isSpace ? (isDark ? "#2563eb" : "#3b82f6") : "#25676e";
  const lineEnd = isSpace ? (isDark ? "#7c3aed" : "#8b5cf6") : "#abeaf2";
  const lineMid = isSpace ? "#06b6d4" : null;
  const areaColor = isSpace ? (isDark ? "rgba(37,99,235," : "rgba(59,130,246,") : "rgba(37,103,110,";
  const dotStroke = lineColor;
  const valColor = lineColor;

  let hoverPt = null;
  canvas.onmousemove = (e) => {
    const mx = e.offsetX, my = e.offsetY;
    let best = null, bestD = 20;
    for (const p of pts) {
      const d = Math.hypot(p.x - mx, p.y - my);
      if (d < bestD) { bestD = d; best = p; }
    }
    if (best !== hoverPt) { hoverPt = best; draw(); }
  };
  canvas.onmouseleave = () => { if (hoverPt) { hoverPt = null; draw(); } };

  const pad = { top: Math.round(h * 0.06), right: Math.round(w * 0.06), bottom: 18, left: Math.round(w * 0.08) };
  const pw = w - pad.left - pad.right;
  const ph = h - pad.top - pad.bottom;
  const maxVal = Math.max(...values, 1) * 1.12;

  const pts = values.map((v, i) => ({
    x: pad.left + (values.length > 1 ? (i / (values.length - 1)) * pw : pw / 2),
    y: pad.top + ph - (v / maxVal) * ph,
    v,
    label: labels[i],
    tooltip: tooltipItems[i] || null,
  }));

  if (animRef && animRef.cancel) animRef.cancel = true;
  let progress = visualEffectsEnabled() ? 0 : 1;
  let animId;
  let stopped = false;

  function draw() {
    if (animRef && animRef.cancel) { stopped = true; cancelAnimationFrame(animId); return; }
    ctx.clearRect(0, 0, w, h);

    // Grid
    ctx.strokeStyle = "rgba(37,103,110,0.1)";
    ctx.lineWidth = 0.8;
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + (i / 4) * ph;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();
    }

    // Y-axis labels
    ctx.fillStyle = "#74777c";
    ctx.font = "10px 'DM Sans','Microsoft YaHei',sans-serif";
    ctx.textAlign = "right";
    const ticks = [0, Math.round(maxVal / 2), Math.round(maxVal)];
    ticks.forEach((t) => {
      ctx.fillText(t, pad.left - 8, pad.top + ph - (t / maxVal) * ph + 4);
    });

    // Draw up to progress
    const n = Math.min(Math.floor(pts.length * progress) + 1, pts.length);
    const drawPts = pts.slice(0, Math.max(2, n));

    if (drawPts.length >= 2) {
      const curveBounds = { top: pad.top, bottom: pad.top + ph };
      // Area fill
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, areaColor + "0.22)");
      grad.addColorStop(1, areaColor + "0.02)");
      ctx.beginPath();
      smoothCurveThrough(ctx, drawPts, 0.35, curveBounds);
      ctx.lineTo(drawPts[drawPts.length - 1].x, pad.top + ph);
      ctx.lineTo(drawPts[0].x, pad.top + ph);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();

      // Line gradient
      const lineGrad = ctx.createLinearGradient(0, 0, w, 0);
      lineGrad.addColorStop(0, lineColor);
      if (lineMid) lineGrad.addColorStop(0.5, lineMid);
      lineGrad.addColorStop(1, lineEnd);
      ctx.beginPath();
      smoothCurveThrough(ctx, drawPts, 0.35, curveBounds);
      ctx.strokeStyle = lineGrad;
      ctx.lineWidth = 2.5;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.shadowColor = areaColor + "0.2)";
      ctx.shadowBlur = 6;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    // Data points (draw for all progress, including single point)
    if (drawPts.length >= 1) {
      drawPts.forEach((p, i) => {
        if (pts.length <= 2 || i % 2 === 0 || i === drawPts.length - 1) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, 4.5, 0, Math.PI * 2);
          ctx.fillStyle = "#fff";
          ctx.fill();
          ctx.strokeStyle = dotStroke;
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      });
    }

    // X-axis labels
    ctx.fillStyle = "rgba(116,119,124,0.7)";
    ctx.font = "11px 'DM Sans','Microsoft YaHei',sans-serif";
    ctx.textAlign = "center";
    labels.forEach((l, i) => {
      if (labels.length <= 8 || i % Math.ceil(labels.length / 8) === 0 || i === labels.length - 1) {
        ctx.fillText(l, pts[i].x, pad.top + ph + 16);
      }
    });

    // Value labels on all points
    if (progress >= 1 && showLabels) {
      ctx.fillStyle = valColor;
      ctx.font = "bold 12px 'Microsoft YaHei',sans-serif";
      ctx.textAlign = "center";
      pts.forEach((p) => {
        ctx.fillText(p.v, p.x, p.y - 14);
      });
    }

    // Hover tooltip
    if (progress >= 1 && hoverPt) {
      const p = hoverPt;
      const tooltip = p.tooltip || { title: p.label || "", lines: [`差异数: ${p.v}`] };
      const title = tooltip.title || p.label || "";
      const lines = Array.isArray(tooltip.lines) && tooltip.lines.length ? tooltip.lines : [`差异数: ${p.v}`];
      ctx.save();
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = isDark ? "rgba(148,163,184,0.45)" : "rgba(100,116,139,0.28)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(p.x, pad.top);
      ctx.lineTo(p.x, pad.top + ph);
      ctx.stroke();
      ctx.restore();

      ctx.font = "bold 12px 'Microsoft YaHei',sans-serif";
      const lineFont = "600 12px 'Microsoft YaHei',sans-serif";
      const widthParts = [ctx.measureText(title).width];
      ctx.font = lineFont;
      lines.forEach((line) => widthParts.push(ctx.measureText(String(line)).width));
      const tw = Math.max(96, Math.max(...widthParts) + 24);
      const th = 26 + lines.length * 18;
      const preferredX = p.x + 14 + tw <= w - pad.right ? p.x + 14 : p.x - tw - 14;
      const tx = Math.min(Math.max(preferredX, pad.left), w - pad.right - tw);
      const ty = Math.min(Math.max(p.y - th - 16, pad.top + 6), pad.top + ph - th - 6);
      ctx.fillStyle = isDark ? "rgba(15,23,42,0.94)" : "rgba(51,65,85,0.92)";
      roundRect(ctx, tx, ty, tw, th, 7);
      ctx.fill();
      ctx.fillStyle = "#fff";
      ctx.textAlign = "left";
      ctx.font = "bold 12px 'Microsoft YaHei',sans-serif";
      ctx.fillText(title, tx + 12, ty + 17);
      ctx.font = lineFont;
      lines.forEach((line, index) => {
        ctx.fillText(String(line), tx + 12, ty + 36 + index * 18);
      });
    }

    if (progress < 1) {
      progress += 0.04;
      animId = requestAnimationFrame(draw);
    } else {
      animId = null;
    }
  }

  draw();
  if (animRef) animRef.animId = animId;
}

function drawGlassMultiMetricChart(canvas, seriesList, labels, animRef, showLabels = true) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.parentElement.getBoundingClientRect();
  const w = rect.width, h = rect.height;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = w + "px";
  canvas.style.height = h + "px";
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const series = seriesList
    .map((item) => ({
      ...item,
      values: (item.values || []).map((value) => Number(value || 0)),
      maxVal: Math.max(...(item.values || []).map((value) => Number(value || 0)), 1),
    }))
    .filter((item) => item.values.length);
  if (!series.length) return;
  const sharedMaxVal = Math.max(...series.flatMap((metric) => metric.values), 1);
  series.forEach((metric) => { metric.maxVal = sharedMaxVal; });

  const pad = { top: Math.round(h * 0.06), right: Math.round(w * 0.11), bottom: 22, left: Math.round(w * 0.09) };
  const pw = w - pad.left - pad.right;
  const ph = h - pad.top - pad.bottom;
  const curveBounds = { top: pad.top, bottom: pad.top + ph };

  let hoverIndex = null;
  canvas.onmousemove = (event) => {
    const mx = event.offsetX;
    let bestIndex = null;
    let bestDistance = 28;
    labels.forEach((_, index) => {
      const x = pad.left + (labels.length > 1 ? (index / (labels.length - 1)) * pw : pw / 2);
      const distance = Math.abs(x - mx);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    });
    if (bestIndex !== hoverIndex) {
      hoverIndex = bestIndex;
      draw();
    }
  };
  canvas.onmouseleave = () => {
    if (hoverIndex !== null) {
      hoverIndex = null;
      draw();
    }
  };

  if (animRef && animRef.cancel) animRef.cancel = true;
  let progress = visualEffectsEnabled() ? 0 : 1;
  let animId;
  let stopped = false;

  function pointsFor(metric) {
    return metric.values.map((value, index) => ({
      x: pad.left + (metric.values.length > 1 ? (index / (metric.values.length - 1)) * pw : pw / 2),
      y: pad.top + ph - (value / metric.maxVal) * ph,
      value,
      label: labels[index],
    }));
  }

  function drawAxisLabels(metric, alignRight = false) {
    const ticks = [0, metric.maxVal / 2, metric.maxVal];
    ctx.fillStyle = "#74777c";
    ctx.font = "10px 'DM Sans','Microsoft YaHei',sans-serif";
    ctx.textAlign = alignRight ? "left" : "right";
    ticks.forEach((tick) => {
      const y = pad.top + ph - (tick / metric.maxVal) * ph + 4;
      const x = alignRight ? w - pad.right + 8 : pad.left - 8;
      ctx.fillText(formatMetricChartNumber(metric, tick), x, y);
    });
  }

  function drawTooltip() {
    if (hoverIndex === null || progress < 1) return;
    const lines = series.map((metric) => `${metric.name}: ${formatMetricChartNumber(metric, metric.values[hoverIndex])}${metric.suffix || ""}`);
    const title = labels[hoverIndex] || "";
    ctx.font = "12px 'Microsoft YaHei',sans-serif";
    const width = Math.max(ctx.measureText(title).width, ...lines.map((line) => ctx.measureText(line).width)) + 20;
    const height = 24 + lines.length * 18;
    const x = pad.left + (labels.length > 1 ? (hoverIndex / (labels.length - 1)) * pw : pw / 2);
    const tx = Math.min(Math.max(x, pad.left + width / 2), w - pad.right - width / 2);
    const ty = pad.top + 8;
    ctx.fillStyle = "rgba(15, 23, 42, 0.82)";
    roundRect(ctx, tx - width / 2, ty, width, height, 8);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.font = "bold 12px 'Microsoft YaHei',sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(title, tx - width / 2 + 10, ty + 17);
    ctx.font = "12px 'Microsoft YaHei',sans-serif";
    lines.forEach((line, index) => {
      ctx.fillText(line, tx - width / 2 + 10, ty + 37 + index * 18);
    });
  }

  function draw() {
    if (animRef && animRef.cancel) { stopped = true; cancelAnimationFrame(animId); return; }
    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = "rgba(37,103,110,0.1)";
    ctx.lineWidth = 0.8;
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + (i / 4) * ph;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();
    }

    drawAxisLabels(series[0], false);
    if (series[1]) drawAxisLabels(series[1], true);

    const drawCount = Math.min(Math.floor(labels.length * progress) + 1, labels.length);
    series.forEach((metric) => {
      const pts = pointsFor(metric);
      const drawPts = pts.slice(0, Math.max(2, drawCount));
      if (drawPts.length >= 2) {
        const grad = ctx.createLinearGradient(0, 0, w, 0);
        grad.addColorStop(0, metric.color);
        grad.addColorStop(1, metric.endColor || metric.color);
        ctx.beginPath();
        smoothCurveThrough(ctx, drawPts, 0.35, curveBounds);
        ctx.strokeStyle = grad;
        ctx.lineWidth = 2.4;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.shadowColor = metric.shadow || "rgba(59,130,246,0.18)";
        ctx.shadowBlur = 5;
        ctx.stroke();
        ctx.shadowBlur = 0;
      }
      drawPts.forEach((point, index) => {
        if (labels.length <= 8 || index % Math.ceil(labels.length / 8) === 0 || index === drawPts.length - 1) {
          ctx.beginPath();
          ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
          ctx.fillStyle = "#fff";
          ctx.fill();
          ctx.strokeStyle = metric.color;
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      });
      if (progress >= 1 && showLabels && labels.length <= 12) {
        ctx.fillStyle = metric.color;
        ctx.font = "bold 11px 'Microsoft YaHei',sans-serif";
        ctx.textAlign = "center";
        pts.forEach((point) => {
          ctx.fillText(formatMetricChartNumber(metric, point.value), point.x, point.y - 12);
        });
      }
    });

    ctx.fillStyle = "rgba(116,119,124,0.7)";
    ctx.font = "11px 'DM Sans','Microsoft YaHei',sans-serif";
    ctx.textAlign = "center";
    labels.forEach((label, index) => {
      if (labels.length <= 8 || index % Math.ceil(labels.length / 8) === 0 || index === labels.length - 1) {
        const x = pad.left + (labels.length > 1 ? (index / (labels.length - 1)) * pw : pw / 2);
        ctx.fillText(label, x, pad.top + ph + 18);
      }
    });

    if (hoverIndex !== null && progress >= 1) {
      const x = pad.left + (labels.length > 1 ? (hoverIndex / (labels.length - 1)) * pw : pw / 2);
      ctx.strokeStyle = "rgba(148, 163, 184, 0.35)";
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(x, pad.top);
      ctx.lineTo(x, pad.top + ph);
      ctx.stroke();
      ctx.setLineDash([]);
      drawTooltip();
    }

    if (progress < 1) {
      progress += 0.04;
      animId = requestAnimationFrame(draw);
    } else {
      animId = null;
    }
  }

  draw();
  if (animRef) animRef.animId = animId;
}

function cssRootValue(name, fallback = "") {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function trendFirstRunMetricStyle() {
  const isSpaceTheme = document.documentElement.getAttribute("data-theme") === "space-tech";
  if (isSpaceTheme) {
    return {
      color: "#3b82f6",
      endColor: "#06b6d4",
      shadow: "rgba(59,130,246,0.22)",
    };
  }
  return {
    color: cssRootValue("--secondary", "#25676e"),
    endColor: cssRootValue("--on-secondary-container", "#2a6b73"),
    shadow: "rgba(37,103,110,0.22)",
  };
}

function refreshHomeChartsForTheme() {
  if (document.documentElement.getAttribute("data-page") !== "home") {
    homeChartsNeedThemeRefresh = true;
    return;
  }
  homeChartsNeedThemeRefresh = false;
  renderChart();
  renderTrendChart();
}

async function getReconcileBusinessSourceName() {
  try {
    const payload = await api("/api/settings/reconcile-data-sources");
    const settings = payload.settings || {};
    const sources = payload.data_sources || [];
    const selected = sources.find((item) => item.id === settings.business_source_id);
    activeReconcileBusinessSourceName = selected?.name || "";
    return activeReconcileBusinessSourceName;
  } catch (_) {
    return activeReconcileBusinessSourceName || "";
  }
}

function setChartEmptyState(container, canvas, emptyEl, isEmpty, message = "") {
  if (!container) return;
  container.classList.toggle("chart-container--empty", isEmpty);
  if (canvas) canvas.hidden = isEmpty;
  if (emptyEl) {
    if (message) emptyEl.textContent = message;
    emptyEl.hidden = !isEmpty;
  }
}

function setChartLoadingState(container, isLoading) {
  if (!container) return;
  container.classList.toggle("chart-container--loading", isLoading);
  const indicator = container.querySelector(".chart-loading-indicator");
  if (indicator) indicator.hidden = !isLoading;
}

/* ===== Home Stats ===== */

const HOME_REASON_DEFS = [
  {
    key: "paidIn",
    label: "实收本金不一致",
    tone: "sys",
    match: (_text, item = {}) => homeSpecificReasonMatchesPaidIn(item),
  },
  {
    key: "targetCode",
    label: "标的代码不一致",
    tone: "data",
    match: (_text, item = {}) => homeSpecificReasonMatchesTargetCode(item),
  },
  {
    key: "assetLiability",
    label: "资产/负债权益差异",
    tone: "time",
    match: (text) => text.includes("资产") || text.includes("负债") || text.includes("权益"),
  },
];

const HOME_STAT_LABELS = {
  total: "总差异数",
  unresolved: "未解释",
  explained: "已解释",
  paidIn: "实收本金不一致",
  targetCode: "标的代码不一致",
  reportPeriod: "报告期",
  other: "其他待解释差异",
};

const HOME_STATUS_ORDER = ["已解释", "未解释", "候选不唯一", "组合候选过大"];
const HOME_REASON_TONES = ["sys", "data", "time", "other"];

let homeStatsState = {
  run: null,
  reportRuns: [],
  results: [],
  groups: {},
  counts: {},
  scopes: {},
};

function latestHomeRun(runs = []) {
  return [...runs].sort((a, b) => {
    const dateCompare = String(b.run_date || "").localeCompare(String(a.run_date || ""));
    if (dateCompare) return dateCompare;
    const timeCompare = String(b.run_at || "").localeCompare(String(a.run_at || ""));
    if (timeCompare) return timeCompare;
    return String(b.id || "").localeCompare(String(a.id || ""));
  })[0] || null;
}

function compareHomeRunTimeAsc(a = {}, b = {}) {
  const timeCompare = String(a.run_at || "").localeCompare(String(b.run_at || ""));
  if (timeCompare) return timeCompare;
  return String(a.id || "").localeCompare(String(b.id || ""));
}

function recentHomeRuns(runs = [], limit = 6) {
  const latestByDate = new Map();
  [...runs].sort((a, b) => {
    const dateCompare = String(b.run_date || "").localeCompare(String(a.run_date || ""));
    if (dateCompare) return dateCompare;
    const timeCompare = String(b.run_at || "").localeCompare(String(a.run_at || ""));
    if (timeCompare) return timeCompare;
    return String(b.id || "").localeCompare(String(a.id || ""));
  }).forEach((run) => {
    const key = run.run_date || run.run_at || run.id;
    if (key && !latestByDate.has(key)) latestByDate.set(key, run);
  });
  return [...latestByDate.values()].slice(0, limit);
}

function recentHomePeriodDates(runs = [], limit = 12) {
  const dates = new Set();
  [...runs].sort((a, b) => {
    const dateCompare = String(b.run_date || "").localeCompare(String(a.run_date || ""));
    if (dateCompare) return dateCompare;
    const timeCompare = String(b.run_at || "").localeCompare(String(a.run_at || ""));
    if (timeCompare) return timeCompare;
    return String(b.id || "").localeCompare(String(a.id || ""));
  }).forEach((run) => {
    if (run.run_date) dates.add(run.run_date);
  });
  return [...dates].slice(0, limit);
}

function homeRunsForPeriodDates(runs = [], dates = []) {
  const dateSet = new Set(dates);
  return [...runs]
    .filter((run) => dateSet.has(run.run_date))
    .sort((a, b) => {
      const dateCompare = String(b.run_date || "").localeCompare(String(a.run_date || ""));
      if (dateCompare) return dateCompare;
      const timeCompare = String(b.run_at || "").localeCompare(String(a.run_at || ""));
      if (timeCompare) return timeCompare;
      return String(b.id || "").localeCompare(String(a.id || ""));
    });
}

function firstHomeRunsForPeriodDates(runs = [], dates = []) {
  const firstByDate = new Map();
  homeRunsForPeriodDates(runs, dates).forEach((run) => {
    const current = firstByDate.get(run.run_date);
    if (!current || compareHomeRunTimeAsc(run, current) < 0) firstByDate.set(run.run_date, run);
  });
  return dates.map((date) => firstByDate.get(date)).filter(Boolean);
}

async function loadHomeRunDetail(summary = {}) {
  if (!summary?.id) return summary;
  try {
    const payload = await api(`/api/history/${encodeURIComponent(summary.id)}`);
    return payload.history || summary;
  } catch (_) {
    return summary;
  }
}

function homeReasonText(item = {}) {
  return [
    item.difference_reason,
    homeSpecificReasonText(item),
  ].filter(Boolean).join(" ");
}

function homeDetailReasonText(details = []) {
  const parts = [];
  (Array.isArray(details) ? details : []).forEach((detail) => {
    const data = detail?.data || {};
    ["specific_reason", "reason", "check_result", "reason_text", "basis"].forEach((field) => {
      if (data[field]) parts.push(data[field]);
    });
    ["rows", "refinement_rows"].forEach((field) => {
      (Array.isArray(data[field]) ? data[field] : []).forEach((row) => {
        ["specific_reason", "reason", "reason_text", "check_result", "type"].forEach((rowField) => {
          if (row?.[rowField]) parts.push(row[rowField]);
        });
      });
    });
  });
  return parts.filter(Boolean).join(" ");
}

function homeDisplayDetailReasonText(displayDetails = []) {
  const parts = [];
  (Array.isArray(displayDetails) ? displayDetails : []).forEach((section) => {
    (Array.isArray(section?.rows) ? section.rows : []).forEach((row) => {
      if (row?.label) parts.push(row.label);
      if (row?.value) parts.push(row.value);
    });
    (Array.isArray(section?.table?.rows) ? section.table.rows : []).forEach((row) => {
      (Array.isArray(row) ? row : []).forEach((cell) => {
        if (cell) parts.push(cell);
      });
    });
  });
  return parts.filter(Boolean).join(" ");
}

function homeSpecificReasonText(item = {}) {
  return [
    item.specific_reason,
    item.detail_reason,
    item.reason_detail,
    item.remark,
    specificReasonText(item),
    homeDetailReasonText(item.details),
    homeDisplayDetailReasonText(item.display_details),
  ].filter(Boolean).join(" ");
}

function normalizeHomeReasonText(text = "") {
  return String(text || "").toLowerCase().replace(/\s+/g, "");
}

function homeSpecificReasonMatchesPaidIn(item = {}) {
  const text = normalizeHomeReasonText(homeSpecificReasonText(item));
  return (
    text.includes("4001与c1000存在差异") ||
    text.includes("4001-c1000差额正好解释主差异") ||
    text.includes("4001-c1000差异正好解释主差异")
  );
}

function homeSpecificReasonMatchesTargetCode(item = {}) {
  const text = normalizeHomeReasonText(homeSpecificReasonText(item));
  return (
    text.includes("fa/am标的不一致") ||
    text.includes("fa与am标的不一致") ||
    text.includes("fa和am标的不一致")
  );
}

function homeTargetCodeMismatchTextMatches(value = "") {
  const text = normalizeHomeReasonText(value);
  return (
    text.includes("fa/am标的不一致") ||
    text.includes("fa与am标的不一致") ||
    text.includes("fa和am标的不一致")
  );
}

function homeTargetCodeMismatchCount(item = {}) {
  let count = 0;
  let faAmFallbackCount = 0;
  const details = Array.isArray(item.details) ? item.details : [];
  details.forEach((detail) => {
    if (detail?.kind === "fa_am") {
      faAmFallbackCount += 1;
      return;
    }
    const data = detail?.data || {};
    ["rows", "refinement_rows"].forEach((field) => {
      (Array.isArray(data[field]) ? data[field] : []).forEach((row) => {
        const rowText = [
          row?.specific_reason,
          row?.reason,
          row?.reason_text,
          row?.check_result,
          row?.type,
        ].filter(Boolean).join(" ");
        if (homeTargetCodeMismatchTextMatches(rowText)) count += 1;
      });
    });
  });
  if (count > 0) return count;
  if (faAmFallbackCount > 0) return faAmFallbackCount;

  const displayDetails = Array.isArray(item.display_details) ? item.display_details : [];
  displayDetails.forEach((section) => {
    (Array.isArray(section?.table?.rows) ? section.table.rows : []).forEach((row) => {
      const rowText = (Array.isArray(row) ? row : []).filter(Boolean).join(" ");
      if (homeTargetCodeMismatchTextMatches(rowText)) count += 1;
    });
  });
  if (count > 0) return count;

  return homeSpecificReasonMatchesTargetCode(item) ? 1 : 0;
}

function homeReasonCategoryFromItem(item = {}) {
  const text = homeReasonText(item);
  return HOME_REASON_DEFS.find((def) => def.match(text, item)) || {
    key: "other",
    label: "其他待解释差异",
    tone: "other",
  };
}

function updateHistoryExecutorOptions() {
  if (!historyExecutorFilter) return;
  const selectedValue = historyExecutorFilter.value;
  const executors = new Map();
  historyRuns.forEach((run) => {
    const name = historyExecutorName(run, "").trim();
    if (!name) return;
    executors.set(name.toLowerCase(), name);
  });
  const options = [...executors.values()].sort((a, b) => a.localeCompare(b, "zh-CN"));
  historyExecutorFilter.innerHTML = '<option value="">全部执行人</option>';
  options.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    historyExecutorFilter.appendChild(option);
  });
  historyExecutorFilter.value = options.includes(selectedValue) ? selectedValue : "";
  syncCustomSelect(historyExecutorFilter);
  updateFilterClearButtons();
}

function getHistoryFilterValues() {
  return {
    reportDate: String(historyReportFilter?.value || "").trim(),
    executor: String(historyExecutorFilter?.value || "").trim().toLowerCase(),
  };
}

function isHistoryFilterActive() {
  const filters = getHistoryFilterValues();
  return Boolean(filters.reportDate || filters.executor);
}

function getFilteredHistoryRuns() {
  const filters = getHistoryFilterValues();
  return historyRuns.filter((run) => {
    if (filters.reportDate && run.run_date !== filters.reportDate) return false;
    if (filters.executor) {
      const executorText = historyExecutorName(run, "").toLowerCase();
      if (executorText !== filters.executor) return false;
    }
    return true;
  });
}

function homeResultCategory(item = {}) {
  return homeReasonCategoryFromItem(item);
}

function homeStatusCountsFromResults(results = []) {
  return results.reduce((counts, item) => {
    const status = String(item.match_status || "未解释");
    counts[status] = (counts[status] || 0) + 1;
    return counts;
  }, {});
}

function homeResultCountsAsUnresolved(item = {}) {
  return ["未解释", "候选不唯一"].includes(String(item.match_status || ""));
}

function buildHomeResultGroups(results = []) {
  const groups = {
    total: [],
    unresolved: [],
    explained: [],
    paidIn: [],
    targetCode: [],
    assetLiability: [],
    other: [],
  };

  results.forEach((item) => {
    groups.total.push(item);
    if (item.match_status === "已解释") groups.explained.push(item);
    if (homeResultCountsAsUnresolved(item)) groups.unresolved.push(item);

    const category = homeResultCategory(item);
    if (!groups[category.key]) groups[category.key] = [];
    groups[category.key].push(item);
  });

  return groups;
}

function buildHomePeriodResults(runs = []) {
  return runs.flatMap((run) => {
    const runResults = Array.isArray(run.results) ? run.results : [];
    return runResults.map((item) => ({
      ...item,
      __homeRunDate: run.run_date || "",
      __homeRunAt: run.run_at || "",
      __homeRunId: run.id || "",
    }));
  });
}

function aggregateHomeStatusCounts(runs = []) {
  const counts = {};
  runs.forEach((run) => {
    Object.entries(run.status_counts || {}).forEach(([status, count]) => {
      counts[status] = (counts[status] || 0) + Number(count || 0);
    });
  });
  return counts;
}

function homeStatusCountsForRun(run = {}) {
  const results = Array.isArray(run.results) ? run.results : [];
  return results.length ? homeStatusCountsFromResults(results) : { ...(run.status_counts || {}) };
}

function buildHomeReasonSummary(run = {}) {
  const results = Array.isArray(run.results) ? run.results : [];
  const summary = {
    paidIn: 0,
    targetCode: 0,
    assetLiability: 0,
    other: 0,
  };

  if (results.length) {
    results.forEach((item) => {
      if (homeTargetCodeMismatchCount(item) > 0) {
        summary.targetCode += homeTargetCodeMismatchCount(item);
        return;
      }
      const category = homeReasonCategoryFromItem(item);
      summary[category.key] = (summary[category.key] || 0) + 1;
    });
    return summary;
  }

  Object.entries(run.reason_counts || {}).forEach(([reason, count]) => {
    summary.other += Number(count || 0);
  });
  return summary;
}

function homeDifferenceTypeParts(value = "") {
  const text = String(value || "").trim();
  if (!text) return ["未标注差异类型"];
  return text.split(/\s*\+\s*/).map((part) => part.trim()).filter(Boolean);
}

function buildHomeDifferenceTypeSummaryFromResults(results = []) {
  return results.reduce((summary, item) => {
    homeDifferenceTypeParts(item.difference_reason).forEach((type) => {
      summary[type] = (summary[type] || 0) + 1;
    });
    return summary;
  }, {});
}

function aggregateHomeDifferenceTypeSummary(runs = []) {
  const summary = {};
  runs.forEach((run) => {
    if (Array.isArray(run.results) && run.results.length) {
      const runSummary = buildHomeDifferenceTypeSummaryFromResults(run.results);
      Object.entries(runSummary).forEach(([type, count]) => {
        summary[type] = (summary[type] || 0) + Number(count || 0);
      });
      return;
    }
    Object.entries(run.reason_counts || {}).forEach(([type, count]) => {
      homeDifferenceTypeParts(type).forEach((part) => {
        summary[part] = (summary[part] || 0) + Number(count || 0);
      });
    });
  });
  return summary;
}

function homeDifferenceTypeSummaryForRun(run = {}) {
  const results = Array.isArray(run.results) ? run.results : [];
  if (results.length) return buildHomeDifferenceTypeSummaryFromResults(results);

  const summary = {};
  Object.entries(run.reason_counts || {}).forEach(([type, count]) => {
    homeDifferenceTypeParts(type).forEach((part) => {
      summary[part] = (summary[part] || 0) + Number(count || 0);
    });
  });
  return summary;
}

function homeSummaryTotal(summary = {}) {
  return Object.values(summary).reduce((sum, count) => sum + Number(count || 0), 0);
}

function formatHomeRoundedCount(value = 0) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? String(Math.round(number)) : "0";
}

const HOME_REPORT_PERIOD_MIN_FONT_SIZE = 16;
const HOME_REPORT_PERIOD_MAX_FONT_SIZE = 25;

function fitHomeReportPeriodValue() {
  const value = document.getElementById("homeStatReportPeriod");
  if (!value) return;
  let size = HOME_REPORT_PERIOD_MAX_FONT_SIZE;
  value.style.setProperty("--home-report-period-font-size", `${size}px`);
  if (!value.clientWidth) return;
  while (size > HOME_REPORT_PERIOD_MIN_FONT_SIZE && value.scrollWidth > value.clientWidth + 1) {
    size -= 1;
    value.style.setProperty("--home-report-period-font-size", `${size}px`);
  }
}

function setHomeStatText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
  if (id === "homeStatReportPeriod") fitHomeReportPeriodValue();
}

function scheduleHomeChartsResize() {
  if (homeChartsResizeTimer) window.clearTimeout(homeChartsResizeTimer);
  homeChartsResizeTimer = window.setTimeout(() => {
    homeChartsResizeTimer = null;
    if (document.documentElement.getAttribute("data-page") !== "home") return;
    renderChart();
    renderTrendChart();
  }, visualEffectsEnabled() ? HOME_CHARTS_RESIZE_DEBOUNCE_MS : HOME_CHARTS_LOW_EFFECTS_RESIZE_DEBOUNCE_MS);
}

function setHomeEmptyState() {
  homeStatsState = { run: null, reportRuns: [], results: [], groups: {}, counts: {} };
  [
    "homeStatTotalDiff",
    "homeStatUnresolved",
    "homeStatExplained",
    "homeStatPaidIn",
    "homeStatTargetCode",
    "homeStatReportPeriod",
    "homeStatReportRunAt",
    "homeStatTotalDiffDelta",
    "homeStatUnresolvedDelta",
    "homeStatExplainedDelta",
    "homeStatPaidInDelta",
    "homeStatTargetCodeDelta",
  ].forEach((id) => setHomeStatText(id, "--"));
  renderHomeStatDeltas({}, null, "较上期");
  const focusScope = document.getElementById("homeFocusScope");
  if (focusScope) focusScope.textContent = "暂无历史";
  const qualityRows = document.getElementById("homeQualityRows");
  if (qualityRows) qualityRows.innerHTML = '<p class="home-analysis-empty">等待首次核对后生成质量分布</p>';
  const reasonList = document.getElementById("homeReasonList");
  if (reasonList) reasonList.innerHTML = '<p class="home-analysis-empty">等待首次核对后统计差异类型</p>';
  const focusList = document.getElementById("homeFocusList");
  if (focusList) focusList.innerHTML = '<p class="home-analysis-empty">至少 2 期后分析高频项目</p>';
}

function renderHomeQualityRows(statusCounts = {}, total = 0, emptyText = "暂无匹配状态数据") {
  const list = document.getElementById("homeQualityRows");
  if (!list) return;
  const known = HOME_STATUS_ORDER
    .filter((status) => Number(statusCounts[status] || 0) > 0)
    .map((status) => ({ status, count: Number(statusCounts[status] || 0) }));
  const knownSet = new Set(HOME_STATUS_ORDER);
  const rest = Object.entries(statusCounts)
    .filter(([status, count]) => !knownSet.has(status) && Number(count || 0) > 0)
    .map(([status, count]) => ({ status, count: Number(count || 0) }))
    .sort((left, right) => right.count - left.count);
  const items = [...known, ...rest];

  if (!items.length) {
    list.innerHTML = `<p class="home-analysis-empty">${escapeHtml(emptyText)}</p>`;
    return;
  }

  list.innerHTML = items.map((item, index) => {
    const pct = total > 0 ? Math.round((item.count / total) * 1000) / 10 : 0;
    const tone = HOME_REASON_TONES[index % HOME_REASON_TONES.length];
    const countText = formatHomeRoundedCount(item.count);
    return `
      <div class="home-quality-row" title="${escapeHtml(`${item.status}：${countText} 条，占 ${pct.toFixed(1)}%`)}">
        <span>${escapeHtml(item.status)}</span>
        <div class="home-quality-track"><i class="home-quality-track--${escapeHtml(tone)}" style="width:${Math.min(100, pct)}%"></i></div>
        <strong>${escapeHtml(countText)} / ${escapeHtml(pct.toFixed(1))}%</strong>
      </div>
    `;
  }).join("");
}

function renderHomeReasonList(typeSummary, total, emptyText = "暂无差异类型数据") {
  const list = document.getElementById("homeReasonList");
  if (!list) return;
  const items = Object.entries(typeSummary || {})
    .map(([label, count], index) => ({
      label,
      count: Number(count || 0),
      tone: HOME_REASON_TONES[index % HOME_REASON_TONES.length],
    }))
    .filter((item) => item.count > 0)
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, "zh-Hans-CN"));

  if (!items.length) {
    list.innerHTML = `<p class="home-analysis-empty">${escapeHtml(emptyText)}</p>`;
    return;
  }

  list.innerHTML = items.map((item) => {
    const pct = total > 0 ? Math.round((item.count / total) * 1000) / 10 : 0;
    const countText = formatHomeRoundedCount(item.count);
    return `
      <div class="home-reason-item">
        <span class="home-reason-dot home-reason-dot--${escapeHtml(item.tone)}"></span>
        <div class="home-reason-main">
          <div class="home-reason-name">${escapeHtml(item.label)}</div>
          <div class="home-reason-bar"><i class="home-reason-bar--${escapeHtml(item.tone)}" style="width:${Math.min(100, pct)}%"></i></div>
        </div>
        <strong class="home-reason-count">${escapeHtml(countText)}</strong>
        <span class="home-reason-pct">${escapeHtml(pct.toFixed(1))}%</span>
      </div>
    `;
  }).join("");
}

function homeResultProjectCode(item = {}) {
  return item.project_code || item.project_id || item.product_code || item.code || "-";
}

function homeResultProjectName(item = {}) {
  return item.project_name || item.product_name || item.name || "-";
}

function homeResultSpecificReason(item = {}) {
  return item.specific_reason || item.detail_reason || item.reason_detail || item.remark || "-";
}

function renderHomeResultTable(items = []) {
  if (!items.length) {
    return '<p class="home-stat-modal-empty">该统计项下暂无项目明细。</p>';
  }

  return `
    <div class="home-stat-modal-table-wrap">
      <table class="home-stat-modal-table">
        <thead>
          <tr>
            <th class="col-code">项目编号</th>
            <th class="col-name">项目名称</th>
            <th class="col-asset">资产合计</th>
            <th class="col-liability">负债及权益合计</th>
            <th class="col-diff">差额</th>
            <th class="col-status">状态</th>
          </tr>
        </thead>
        <tbody>
          ${items.map((item) => {
            const codeText = homeResultProjectCode(item);
            const nameText = homeResultProjectName(item);
            const assetText = formatMoney(item.asset_total ?? item.valuation_asset_total ?? "");
            const liabilityText = formatMoney(item.liability_equity_total ?? "");
            const diffText = formatMoney(item.difference ?? "");
            const statusText = item.match_status || "-";
            return `
            <tr>
              <td class="col-code" title="${escapeHtml(codeText)}">${escapeHtml(codeText)}</td>
              <td class="col-name" title="${escapeHtml(nameText)}">${escapeHtml(nameText)}</td>
              <td class="col-asset num" title="${escapeHtml(assetText)}">${escapeHtml(assetText)}</td>
              <td class="col-liability num" title="${escapeHtml(liabilityText)}">${escapeHtml(liabilityText)}</td>
              <td class="col-diff num" title="${escapeHtml(diffText)}">${escapeHtml(diffText)}</td>
              <td class="col-status" title="${escapeHtml(statusText)}"><span class="home-stat-modal-status">${escapeHtml(statusText)}</span></td>
            </tr>
          `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function summarizeHomeRunForReport(run = {}) {
  const runResults = Array.isArray(run.results) ? run.results : [];
  const statusCounts = runResults.length ? homeStatusCountsFromResults(runResults) : (run.status_counts || {});
  const groups = runResults.length ? buildHomeResultGroups(runResults) : {};
  const reasonSummary = buildHomeReasonSummary(run);
  return {
    runAt: run.run_at || "",
    total: runResults.length ? runResults.length : (Number(run.total_count || 0) || 0),
    explained: runResults.length ? (groups.explained || []).length : Number(statusCounts["已解释"] || 0),
    unresolved: runResults.length
      ? (groups.unresolved || []).length
      : Number(statusCounts["未解释"] || 0) + Number(statusCounts["候选不唯一"] || 0),
    paidIn: Number(reasonSummary.paidIn || 0),
    targetCode: Number(reasonSummary.targetCode || 0),
  };
}

function compareHomeRunsAsc(left = {}, right = {}) {
  const dateCompare = String(left.run_date || "").localeCompare(String(right.run_date || ""));
  if (dateCompare) return dateCompare;
  const timeCompare = String(left.run_at || "").localeCompare(String(right.run_at || ""));
  if (timeCompare) return timeCompare;
  return String(left.id || "").localeCompare(String(right.id || ""));
}

function isSameHomeRun(left = {}, right = {}) {
  if (left.id && right.id) return String(left.id) === String(right.id);
  return String(left.run_date || "") === String(right.run_date || "")
    && String(left.run_at || "") === String(right.run_at || "");
}

function findHomeStatsBaselineRun(runs = [], currentRun = {}) {
  if (!currentRun?.run_date) return { run: null, label: "较上期" };
  const currentDate = String(currentRun.run_date || "");
  const samePeriodRuns = runs
    .filter((run) => String(run.run_date || "") === currentDate)
    .sort(compareHomeRunsAsc);
  const currentIndex = samePeriodRuns.findIndex((run) => isSameHomeRun(run, currentRun));
  if (currentIndex > 0) {
    return { run: samePeriodRuns[currentIndex - 1], label: "较上次" };
  }
  const previousPeriodRun = [...runs]
    .filter((run) => run.run_date && String(run.run_date || "") < currentDate)
    .sort((a, b) => {
      const dateCompare = String(b.run_date || "").localeCompare(String(a.run_date || ""));
      if (dateCompare) return dateCompare;
      const timeCompare = String(b.run_at || "").localeCompare(String(a.run_at || ""));
      if (timeCompare) return timeCompare;
      return String(b.id || "").localeCompare(String(a.id || ""));
    })[0] || null;
  return previousPeriodRun ? { run: previousPeriodRun, label: "较上期" } : { run: null, label: "较上期" };
}

function setHomeStatDeltaText(id, label, currentValue, baselineValue) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove("home-stat-delta--up", "home-stat-delta--down", "home-stat-delta--flat");
  if (baselineValue == null) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  const delta = Number(currentValue || 0) - Number(baselineValue || 0);
  const deltaText = delta >= 0 ? `+${delta}` : String(delta);
  el.hidden = false;
  el.innerHTML = `${escapeHtml(label)} <span class="home-stat-delta-value">${escapeHtml(deltaText)}</span>`;
  el.classList.add(delta > 0 ? "home-stat-delta--up" : delta < 0 ? "home-stat-delta--down" : "home-stat-delta--flat");
}

function renderHomeStatDeltas(currentSummary = {}, baselineSummary = null, label = "较上期") {
  const deltas = {
    homeStatTotalDiffDelta: "total",
    homeStatUnresolvedDelta: "unresolved",
    homeStatExplainedDelta: "explained",
    homeStatPaidInDelta: "paidIn",
    homeStatTargetCodeDelta: "targetCode",
  };
  Object.entries(deltas).forEach(([id, key]) => {
    setHomeStatDeltaText(id, label, currentSummary[key], baselineSummary ? baselineSummary[key] : null);
  });
}

function renderHomeReportPeriodTable(periodRuns = []) {
  const sortedRuns = [...periodRuns].sort((left, right) => {
    const timeCompare = String(right.run_at || "").localeCompare(String(left.run_at || ""));
    if (timeCompare) return timeCompare;
    return String(right.id || "").localeCompare(String(left.id || ""));
  });
  if (!sortedRuns.length) {
    return '<p class="home-stat-modal-empty">该报送期暂无执行记录。</p>';
  }

  return `
    <div class="home-stat-modal-table-wrap">
      <table class="home-stat-modal-table home-report-period-table">
        <thead>
          <tr>
            <th class="col-run-at">执行时间</th>
            <th class="col-total">差异数</th>
            <th class="col-explained">已解释</th>
            <th class="col-unresolved">未解释</th>
            <th class="col-paid-in">实收本金不一致</th>
            <th class="col-target-code">标的代码不一致</th>
          </tr>
        </thead>
        <tbody>
          ${sortedRuns.map((periodRun) => {
            const summary = summarizeHomeRunForReport(periodRun);
            const runAtText = summary.runAt ? formatDisplayTime(summary.runAt).slice(0, 16) : "--";
            return `
            <tr>
              <td class="col-run-at" title="${escapeHtml(runAtText)}">${escapeHtml(runAtText)}</td>
              <td class="col-total num">${escapeHtml(summary.total)}</td>
              <td class="col-explained num">${escapeHtml(summary.explained)}</td>
              <td class="col-unresolved num">${escapeHtml(summary.unresolved)}</td>
              <td class="col-paid-in num">${escapeHtml(summary.paidIn)}</td>
              <td class="col-target-code num">${escapeHtml(summary.targetCode)}</td>
            </tr>
          `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

const HOME_TOP_STAT_KEYS = new Set(["total", "unresolved", "explained", "paidIn", "targetCode", "reportPeriod"]);

function ensureSelectOption(select, value, label) {
  if (!select || !value) return;
  if ([...select.options].some((option) => option.value === value)) return;
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  select.appendChild(option);
}

function hasActiveResultListFilter() {
  return Boolean(
    keywordFilter.value.trim() ||
    reasonFilter.value ||
    statusFilter.value
  );
}

function applyHomeResultListFilter(key, options = {}) {
  const hadExistingFilter = Boolean(options.hadExistingFilter);
  keywordFilter.value = "";
  reasonFilter.value = "";
  statusFilter.value = "";
  const run = homeStatsState.run;
  if (key === "reportPeriod" && run?.run_date) {
    homeResultListFilterLabel = `报送期 ${run.run_date}`;
  } else if (key === "total") {
    homeResultListFilterLabel = hadExistingFilter ? (HOME_STAT_LABELS[key] || "") : "";
  } else {
    homeResultListFilterLabel = HOME_STAT_LABELS[key] || "";
  }

  if (key === "unresolved") {
    const reasonValue = "home-status:unresolved";
    ensureSelectOption(reasonFilter, reasonValue, "未解释/候选不唯一");
    reasonFilter.value = reasonValue;
  } else if (key === "explained") {
    statusFilter.value = "已解释";
  } else if (["paidIn", "targetCode"].includes(key)) {
    const reasonValue = `home-category:${key}`;
    ensureSelectOption(reasonFilter, reasonValue, HOME_STAT_LABELS[key] || "统计分类");
    reasonFilter.value = reasonValue;
  }

  syncCustomSelect(reasonFilter);
  syncCustomSelect(statusFilter);
}

async function openHomeStatResultList(key) {
  if (!HOME_TOP_STAT_KEYS.has(key)) return;
  clearResultHistoryRestoreState();
  const run = homeStatsState.run;
  const latestResults = homeStatsState.groups?.total || [];
  const hadExistingFilter = hasActiveResultListFilter();
  results = latestResults;
  hasReconciled = Boolean(results.length);
  resultEmptyState = "";
  if (run?.run_date && runDate) runDate.value = run.run_date;
  if (run?.run_at) setLastRunTime(run.run_at, historyExecutorName(run));
  applyHomeResultListFilter(key, { hadExistingFilter });
  currentPage = 1;
  renderResults();
  await switchPage("auto-check");
  if (homeResultListFilterLabel) setStatus(`已筛选：${homeResultListFilterLabel}，共 ${filteredResults().length} 条`);
}

function showHomeStatResults(key) {
  const label = HOME_STAT_LABELS[key] || "统计项目";
  const run = homeStatsState.run;
  const results = homeStatsState.results || [];
  const groups = homeStatsState.groups || {};
  const items = groups[key] || [];
  const displayCount = homeStatsState.counts?.[key] ?? items.length;
  const scopeText = homeStatsState.scopes?.[key] || (run?.run_at ? formatDisplayTime(run.run_at).slice(0, 16) : (run?.run_date || "最近一次"));

  if (!run) {
    showInfo(label, '<p class="home-stat-modal-empty">暂无核对历史，无法查看项目明细。</p>');
    return;
  }

  const isReportPeriod = key === "reportPeriod";
  const modalTitle = isReportPeriod ? "报送期差异数详情" : `${label}项目明细`;
  if (isReportPeriod) {
    const reportRuns = (homeStatsState.reportRuns || []).length ? homeStatsState.reportRuns : [run];
    const summaryText = `报送期 ${run?.run_date || "--"}，共 ${reportRuns.length} 次执行，按执行时间倒序。`;
    const content = `
      <p class="home-stat-modal-summary">${escapeHtml(summaryText)}</p>
      ${renderHomeReportPeriodTable(reportRuns)}
    `;
    showInfo(modalTitle, content, {
      detailActionLabel: "查看明细",
      onDetailAction: () => openHomeStatResultList(key),
    });
    document.querySelector("#infoModal .modal-info")?.classList.add("modal-info--home-stat");
    return;
  }

  const missingDetail = !items.length && Number(displayCount || 0) > 0;
  const summaryText = isReportPeriod
    ? `报送期 ${run?.run_date || "--"}，执行时间 ${formatDisplayTime(run?.run_at || "").slice(0, 16) || "--"}，差异数 ${displayCount} 条。`
    : `${scopeText}：${label} ${displayCount} 条。`;
  const content = `
    <p class="home-stat-modal-summary">${escapeHtml(summaryText)}</p>
    ${missingDetail ? '<p class="home-stat-modal-empty">当前历史记录只有摘要，无法展开项目明细；请重新打开该历史详情后再查看。</p>' : renderHomeResultTable(items)}
  `;
  showInfo(modalTitle, content, HOME_TOP_STAT_KEYS.has(key) ? {
    detailActionLabel: "查看明细",
    onDetailAction: () => openHomeStatResultList(key),
  } : {});
  document.querySelector("#infoModal .modal-info")?.classList.add("modal-info--home-stat");
}

function activateHomeStatTarget(target) {
  if (!target?.closest) return false;
  const trigger = target.closest("[data-home-stat]");
  if (!trigger || !trigger.closest(".home-stats-row") || !document.getElementById("page-home")?.contains(trigger)) return false;
  showHomeStatResults(trigger.dataset.homeStat || "");
  return true;
}

document.addEventListener("click", (event) => {
  if (activateHomeStatTarget(event.target)) {
    event.preventDefault();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  if (activateHomeStatTarget(event.target)) {
    event.preventDefault();
  }
});

function homeFrequencyProjectKey(item = {}) {
  return homeResultProjectCode(item) || homeResultProjectName(item);
}

function buildHomeFrequencyItems(periodRuns = [], periodDates = []) {
  const dates = periodDates.length ? periodDates : [...new Set(periodRuns.map((run) => run.run_date).filter(Boolean))];
  const dateIndex = new Map(dates.map((date, index) => [date, index]));
  const byProject = new Map();

  periodRuns.forEach((run) => {
    const runResults = Array.isArray(run.results) ? run.results : [];
    runResults.forEach((item) => {
      const projectKey = homeFrequencyProjectKey(item);
      if (!projectKey || projectKey === "-") return;
      if (!byProject.has(projectKey)) {
        byProject.set(projectKey, {
          projectKey,
          projectCode: homeResultProjectCode(item),
          projectName: homeResultProjectName(item),
          dates: new Set(),
          occurrences: [],
          latestItem: null,
          latestIndex: Number.POSITIVE_INFINITY,
        });
      }
      const record = byProject.get(projectKey);
      const cloned = {
        ...item,
        __homeRunDate: run.run_date || "",
        __homeRunAt: run.run_at || "",
        __homeRunId: run.id || "",
      };
      const periodKey = run.run_date || "";
      if (!periodKey) return;
      record.dates.add(periodKey);
      record.occurrences.push(cloned);
      const idx = dateIndex.get(run.run_date) ?? Number.POSITIVE_INFINITY;
      if (idx < record.latestIndex) {
        record.latestIndex = idx;
        record.latestItem = cloned;
        record.projectCode = homeResultProjectCode(item);
        record.projectName = homeResultProjectName(item);
      }
    });
  });

  return [...byProject.values()]
    .map((record) => {
      let consecutive = 0;
      for (const date of dates) {
        if (!record.dates.has(date)) break;
        consecutive += 1;
      }
      const periodCount = record.dates.size;
      const category = homeResultCategory(record.latestItem || {});
      return {
        ...record,
        category,
        periodCount,
        consecutive,
      };
    })
    .filter((item) => item.periodCount >= 2)
    .sort((left, right) => {
      const consecutiveDelta = right.consecutive - left.consecutive;
      if (consecutiveDelta) return consecutiveDelta;
      const periodDelta = right.periodCount - left.periodCount;
      if (periodDelta) return periodDelta;
      return right.occurrences.length - left.occurrences.length;
    })
    .slice(0, 5);
}

function renderHomeFrequencyList(frequencyItems = [], periodCount = 0) {
  const list = document.getElementById("homeFocusList");
  if (!list) return;
  if (!frequencyItems.length) {
    const emptyText = periodCount < 2 ? "至少 2 期后分析高频项目" : `近${periodCount}期暂无高频差异项目`;
    list.innerHTML = `<p class="home-analysis-empty">${escapeHtml(emptyText)}</p>`;
    return;
  }

  list.innerHTML = frequencyItems.map((item, index) => {
    const latest = item.latestItem || {};
    const title = item.projectCode && item.projectCode !== "-" ? item.projectCode : "未命名项目";
    const name = item.projectName && item.projectName !== "-" ? item.projectName : "";
    const reason = latest.difference_reason || item.category.label || "-";
    const periodText = item.consecutive >= 2 ? `连续 ${item.consecutive} 期` : `出现 ${item.periodCount} 期`;
    const fullName = `${title}${name ? ` ${name}` : ""}`;
    const totalText = `近${periodCount}期 ${item.periodCount}次`;
    const detailText = `${periodText} · 最近类型：${reason}`;
    const itemTitle = `${fullName}\n${periodText}，按报告期去重累计 ${item.periodCount} 次\n${detailText}`;
    return `
      <div class="home-focus-item" title="${escapeHtml(itemTitle)}">
        <span class="home-focus-rank ${index < 3 ? `home-focus-rank--${index + 1}` : ""}">${index + 1}</span>
        <div class="home-focus-main">
          <div class="home-focus-title-row">
            <div class="home-focus-name" title="${escapeHtml(fullName)}">${escapeHtml(fullName)}</div>
            <span class="home-focus-total" title="${escapeHtml(totalText)}">${escapeHtml(totalText)}</span>
          </div>
          <div class="home-focus-detail" title="${escapeHtml(detailText)}">${escapeHtml(detailText)}</div>
        </div>
      </div>
    `;
  }).join("");
}

async function renderHomeStats() {
  const hasHomeStats = document.getElementById("homeStatTotalDiff") || document.getElementById("homeReasonList");
  if (!hasHomeStats) return;

  try {
    const historyData = await api("/api/history");
    const runs = historyData.history || [];
    if (!runs.length) {
      setHomeEmptyState();
      return;
    }

    const recentPeriodDates = recentHomePeriodDates(runs, 12);
    const recentPeriodSummaries = homeRunsForPeriodDates(runs, recentPeriodDates);
    const recentPeriodRuns = await Promise.all(recentPeriodSummaries.map((run) => loadHomeRunDetail(run)));
    const latestSummary = latestHomeRun(runs);
    const latestRun = recentPeriodRuns.find((run) => String(run.id || "") === String(latestSummary?.id || "")) || await loadHomeRunDetail(latestSummary);
    const currentReportFirstRun = firstHomeRunsForPeriodDates(recentPeriodRuns, [latestRun.run_date])[0] || latestRun;
    const reportPeriodSummaries = runs
      .filter((run) => run.run_date === latestRun.run_date)
      .sort((left, right) => {
        const timeCompare = String(right.run_at || "").localeCompare(String(left.run_at || ""));
        if (timeCompare) return timeCompare;
        return String(right.id || "").localeCompare(String(left.id || ""));
      });
    const reportPeriodRuns = await Promise.all(reportPeriodSummaries.map((run) => loadHomeRunDetail(run)));
    const baselineInfo = findHomeStatsBaselineRun(runs, latestRun);
    const baselineRun = baselineInfo.run ? await loadHomeRunDetail(baselineInfo.run) : null;

    const results = Array.isArray(latestRun.results) ? latestRun.results : [];
    const statusCounts = results.length ? homeStatusCountsFromResults(results) : (latestRun.status_counts || latestSummary.status_counts || {});
    const total = results.length ? results.length : (Number(latestRun.total_count ?? latestSummary.total_count ?? 0) || 0);
    const explained = Number(statusCounts["已解释"] || 0);
    const groups = buildHomeResultGroups(results);
    const unresolved = results.length
      ? groups.unresolved.length
      : Number(statusCounts["未解释"] || 0) + Number(statusCounts["候选不唯一"] || 0);
    const reasonSummary = buildHomeReasonSummary(latestRun);

    const currentReportStatusCounts = homeStatusCountsForRun(currentReportFirstRun);
    const currentReportTotal = homeSummaryTotal(currentReportStatusCounts);
    const currentReportTypeSummary = homeDifferenceTypeSummaryForRun(currentReportFirstRun);
    const currentReportTypeTotal = homeSummaryTotal(currentReportTypeSummary);
    const frequencyItems = buildHomeFrequencyItems(recentPeriodRuns, recentPeriodDates);

    setHomeStatText("homeStatTotalDiff", total);
    setHomeStatText("homeStatUnresolved", unresolved);
    setHomeStatText("homeStatExplained", explained);
    setHomeStatText("homeStatPaidIn", reasonSummary.paidIn || 0);
    setHomeStatText("homeStatTargetCode", reasonSummary.targetCode || 0);
    setHomeStatText("homeStatReportPeriod", latestRun.run_date || "--");
    setHomeStatText("homeStatReportRunAt", latestRun.run_at ? formatDisplayTime(latestRun.run_at).slice(0, 16) : "--");
    renderHomeStatDeltas(
      summarizeHomeRunForReport(latestRun),
      baselineRun ? summarizeHomeRunForReport(baselineRun) : null,
      baselineInfo.label,
    );

    const combinedGroups = {
      ...groups,
      reportPeriod: groups.total || [],
    };
    const combinedCounts = {
      total,
      unresolved,
      explained,
      paidIn: reasonSummary.paidIn || 0,
      targetCode: reasonSummary.targetCode || 0,
      reportPeriod: total,
    };
    const scopes = {
      total: `核对日期 ${latestRun.run_date || "最近一期"}`,
      unresolved: `核对日期 ${latestRun.run_date || "最近一期"}`,
      explained: `核对日期 ${latestRun.run_date || "最近一期"}`,
      paidIn: `核对日期 ${latestRun.run_date || "最近一期"}`,
      targetCode: `核对日期 ${latestRun.run_date || "最近一期"}`,
      reportPeriod: `执行时间 ${formatDisplayTime(latestRun.run_at || "").slice(0, 16) || "--"}`,
    };

    homeStatsState = {
      run: latestRun,
      reportRuns: reportPeriodRuns,
      results,
      groups: combinedGroups,
      counts: combinedCounts,
      scopes,
    };

    renderHomeQualityRows(
      currentReportStatusCounts,
      currentReportTotal,
      "当前报告期第一次执行未发现需统计的匹配状态"
    );

    renderHomeReasonList(
      currentReportTypeSummary,
      currentReportTypeTotal,
      "当前报告期第一次执行暂无差异类型"
    );
    const focusScopeText = `近${recentPeriodDates.length}期`;
    const focusScope = document.getElementById("homeFocusScope");
    if (focusScope) focusScope.textContent = focusScopeText;
    renderHomeFrequencyList(frequencyItems, recentPeriodDates.length);

  } catch {
    setHomeEmptyState();
  }
}

async function renderChart() {
  const container = document.getElementById("chartContainer");
  const infoEl = document.getElementById("chartInfo");
  const emptyEl = document.getElementById("chartEmpty");
  const canvas = document.getElementById("chartCanvas");
  if (!container) return;
  setChartLoadingState(container, true);

  try {
    const historyData = await api("/api/history");
    const runs = historyData.history || [];
    if (!runs.length) {
      setChartEmptyState(container, canvas, emptyEl, true, "暂无核对数据");
      infoEl.textContent = "";
      return;
    }

    // Group by date, populate dropdown
    const runsByDate = {};
    runs.forEach((r) => {
      const d = r.run_date;
      if (!runsByDate[d]) runsByDate[d] = [];
      runsByDate[d].push(r);
    });
    const dates = Object.keys(runsByDate).sort().reverse();
    const latestDate = dates[0];

    // Populate date dropdown
    if (chartDateSelect) {
      const currentVal = chartDateSelect.value || selectedChartDate || latestDate;
      chartDateSelect.innerHTML = dates.map((d) =>
        `<option value="${d}" ${d === currentVal ? "selected" : ""}>${d}</option>`
      ).join("");
    }

    const targetDate = selectedChartDate || latestDate;
    const dateRuns = (runsByDate[targetDate] || [])
      .sort((a, b) => (a.run_at || "").localeCompare(b.run_at || ""));

    if (!dateRuns.length) {
      setChartEmptyState(container, canvas, emptyEl, true, "该日期暂无数据");
      infoEl.textContent = `日期: ${targetDate}`;
      return;
    }

    setChartEmptyState(container, canvas, emptyEl, false);
    infoEl.textContent = `日期: ${targetDate} | 共 ${dateRuns.length} 次执行`;

    if (!canvas) return;
    const values = dateRuns.map((r) => r.total_count);
    const labels = dateRuns.map((r) => formatChartRunAtLabel(r.run_at, targetDate));
    const tooltipItems = dateRuns.map((r) => {
      const runAtText = formatDisplayTime(r.run_at || "").slice(0, 16) || `${targetDate} ${(r.run_at || "").slice(11, 16)}`;
      return {
        title: runAtText,
        lines: [`差异数: ${formatMoney(r.total_count || 0)}`],
      };
    });
    if (renderChartAnimId) renderChartAnimId.cancel = true;
    renderChartAnimId = {};
    drawGlassChart(canvas, values, labels, renderChartAnimId, true, tooltipItems);

  } catch (e) {
    setChartEmptyState(container, canvas, emptyEl, true, "加载失败");
    infoEl.textContent = "";
  } finally {
    setChartLoadingState(container, false);
  }
}

/* ===== Home Trend Chart (multi metrics per date) ===== */

async function renderTrendChart() {
  const container = document.getElementById("trendContainer");
  const infoEl = document.getElementById("trendInfo");
  const emptyEl = document.getElementById("trendEmpty");
  const canvas = document.getElementById("trendCanvas");
  if (!container) return;
  setChartLoadingState(container, true);

  try {
    const historyData = await api("/api/history");
    const runs = historyData.history || [];
    if (!runs.length) {
      setChartEmptyState(container, canvas, emptyEl, true, "暂无核对数据");
      infoEl.textContent = "全部数据源";
      return;
    }

    // Group by run_date, use the first execution's difference count and execution count.
    const byDate = {};
    runs.forEach((r) => {
      const d = r.run_date;
      if (!d) return;
      if (!byDate[d]) byDate[d] = [];
      byDate[d].push(r);
    });
    const sorted = Object.entries(byDate)
      .map(([date, dateRuns]) => {
        const executionCount = dateRuns.length;
        const firstRun = [...dateRuns].sort(compareHomeRunTimeAsc)[0];
        return {
          date,
          firstRunDiff: Number(firstRun?.total_count || 0),
          executionCount,
        };
      })
      .sort((a, b) => a.date.localeCompare(b.date));

    // Apply date range filter
    let filtered = sorted;
    if (trendDateStart || trendDateEnd) {
      filtered = sorted.filter((item) => {
        if (trendDateStart && item.date < trendDateStart) return false;
        if (trendDateEnd && item.date > trendDateEnd) return false;
        return true;
      });
    }
    if (!filtered.length) {
      setChartEmptyState(container, canvas, emptyEl, true, "暂无核对数据");
      infoEl.textContent = "";
      return;
    }
    setChartEmptyState(container, canvas, emptyEl, false);
    infoEl.textContent = "";

    if (!canvas) return;
    const labels = filtered.map((item) => formatChartMonthDay(item.date));
    const showLabels = filtered.length <= 30;
    const firstRunValues = filtered.map((item) => Math.round(item.firstRunDiff));
    const executionValues = filtered.map((item) => item.executionCount);
    const firstRunStyle = trendFirstRunMetricStyle();
    if (renderTrendAnimId) renderTrendAnimId.cancel = true;
    renderTrendAnimId = {};
    drawGlassMultiMetricChart(canvas, [
      {
        name: "每期差异个数",
        values: firstRunValues,
        color: firstRunStyle.color,
        endColor: firstRunStyle.endColor,
        shadow: firstRunStyle.shadow,
        integerValues: true,
      },
      {
        name: "每期执行次数",
        values: executionValues,
        color: "#f59e0b",
        endColor: "#ef4444",
        shadow: "rgba(245,158,11,0.22)",
        integerValues: true,
      },
    ], labels, renderTrendAnimId, showLabels);

  } catch (e) {
    setChartEmptyState(container, canvas, emptyEl, true, "加载失败");
    infoEl.textContent = "";
  } finally {
    setChartLoadingState(container, false);
  }
}

/* ===== System Settings ===== */

const BUSINESS_SETTINGS_MAINTENANCE_NOTE = "以下为当前对数逻辑涉及的表、字段、业务含义和用途。每次表名或字段调整时，需要同步更新此业务设置。";

const BUSINESS_FIELD_GROUPS = [
  {
    table: "zf_detail_2024",
    source: "报表数据源",
    rows: [
      ["caldate", "核对日期", "主表按日期筛选"],
      ["projinnercode", "项目编号", "与其他表项目编号关联"],
      ["projname", "项目名称", "页面展示"],
      ["a0001", "资产合计", "计算主差异、校验资产侧"],
      ["d0000", "负债及权益合计", "计算主差异"],
      ["c1000", "实收本金余额", "与 FA 4001 判断实收信托是否有误"],
    ],
  },
  {
    table: "fa_valuationreport_dws",
    source: "DWS 数据源",
    rows: [
      ["d_valuationdate", "估值日期", "与主表核对日期一致"],
      ["c_projcode", "项目编号", "对应 zf_detail_2024.projinnercode"],
      ["c_accountcode", "科目代码", "判断 0004、1 开头、3001.XX共同类、非 1 开头、四级科目等"],
      ["c_accountname", "科目名称", "展示差异资产；与 AM 资产名称匹配"],
      ["f_marketvalue", "估值表金额/市值", "与差异金额做单行、汇总、组合匹配"],
    ],
  },
  {
    table: "fa_accountbalance_dws",
    source: "DWS 数据源",
    rows: [
      ["d_balancedate", "科目余额日期", "与主表核对日期一致"],
      ["c_projcode", "项目编号", "对应 zf_detail_2024.projinnercode"],
      ["c_accountcode", "科目代码", "当前只取 4001"],
      ["f_balance", "科目余额", "汇总后与 c1000 比较"],
    ],
  },
  {
    table: "dm.ta_pact_survamt_day_zgxg_dm",
    source: "DWS 数据源",
    rows: [
      ["tpm_date", "TA 日期", "与主表核对日期一致"],
      ["tpm_tcmpcode", "项目编号", "对应 zf_detail_2024.projinnercode"],
      ["tpm_htincome", "待结转收益", "与 tpm_shareamt 汇总核对 TA 差异"],
      ["tpm_shareamt", "份额余额", "与 tpm_htincome 汇总核对 TA 差异"],
      ["tpm_clientkind_tusp", "客户类型", "判断客户类型是否缺失"],
      ["tpm_clientkindex", "客户类型明细", "tpm_clientkind_tusp=4 时不能为空"],
      ["tpm_spvtype", "SPV 类型", "tpm_clientkind_tusp=5 时不能为空"],
      ["tpm_pactid", "合同编号", "展示客户类型为空明细"],
      ["tpm_clientname", "客户名称", "展示客户类型为空明细"],
    ],
  },
  {
    table: "ta_pact_detail_dws",
    source: "DWS 数据源",
    rows: [
      ["d_cldate", "TA 明细日期", "与主表核对日期一致"],
      ["c_projcode", "项目编号", "对应 zf_detail_2024.projinnercode"],
      ["f_shareamt", "份额余额", "与 f_alltincom 汇总后和 DM TA 表对比"],
      ["f_alltincom", "待结转收益", "与 f_shareamt 汇总后和 DM TA 表对比"],
    ],
  },
  {
    table: "am_pactasset_dws",
    source: "DWS 数据源",
    rows: [
      ["d_cldate", "AM 资产日期", "与主表核对日期一致"],
      ["c_projcode", "项目编号", "对应 zf_detail_2024.projinnercode"],
      ["c_udlyasset", "AM 资产名称", "与 FA 科目名称做相等/高匹配度匹配"],
      ["c_stockcode", "AM 标的代码", "与 FA 科目代码最后一段比较"],
      ["c_pactid", "合同代码", "关联 am_projinvest_dws"],
      ["c_spv_type", "SPV类型", "资产重复私募产品细分字段"],
      ["c_assettype", "资产类型", "资产重复私募产品细分字段"],
    ],
  },
  {
    table: "am_projinvest_dws",
    source: "DWS 数据源",
    rows: [
      ["d_cldate", "合同投融资余额日期", "与主表核对日期一致"],
      ["c_projcode", "项目编号", "对应 zf_detail_2024.projinnercode"],
      ["c_pactid", "合同代码", "对应 AM 资产表合同代码"],
      ["f_acbalance", "合同投融资余额", "判断是否为 0"],
    ],
  },
  {
    table: "dm.fa_security_balance_zgxg_dm",
    source: "DWS 数据源",
    rows: [
      ["sbm_projcode", "项目编号", "资产缺失细分关联项目"],
      ["sbm_cacldate", "核对日期", "资产缺失细分按日期筛选"],
      ["sbm_stockcode", "证券代码", "对应 FA 科目尾段"],
      ["sbm_sename", "证券名称", "对应 FA 科目名称"],
      ["sbm_balamoney_cost/sbm_balamoney_fair/sbm_balamoney_inte", "余额金额", "判断证券持仓金额是否非 0"],
      ["sbm_seclas_h2024", "债券类别_人行", "债券缺失细分字段"],
      ["sbm_gpgqtype_h", "股票股权类别_人行", "股票缺失细分字段"],
      ["sbm_fundtype", "公募私募_人行", "基金缺失细分字段"],
    ],
  },
  {
    table: "dm.am_projinvest_zgxg_dm",
    source: "DWS 数据源",
    rows: [
      ["pin_projcode", "项目编号", "贷款/股权投资缺失细分关联项目"],
      ["pin_cldate", "核对日期", "贷款/股权投资缺失细分按日期筛选"],
      ["pin_mpactid", "合同编号", "对应 FA 科目尾段"],
      ["pin_acbalance", "投融资余额", "判断合同余额是否非 0"],
      ["pin_gqtype_h", "股权投资类别", "股权投资缺失细分字段"],
    ],
  },
  {
    table: "dm.am_projinvest_spv_zgxg_dm",
    source: "DWS 数据源",
    rows: [
      ["svd_projcode", "项目编号", "特定目的载体/信托计划收益权关联项目"],
      ["svd_cldate", "核对日期", "特定目的载体/信托计划收益权按日期筛选"],
      ["svd_mpactid", "合同编号", "对应 AM 合同或 FA 科目尾段"],
      ["svd_balamoney_cost/svd_balamoney_inte/svd_balamoney_fair", "余额金额", "判断 SPV 余额是否非 0"],
      ["svd_assettype", "资产类型", "特定目的载体资产类型校验"],
    ],
  },
  {
    table: "zgxg_zhbs.ccqxx",
    source: "DWS 数据源",
    rows: [
      ["pjdw_projcode", "项目编号", "资产收益权缺失细分关联项目"],
      ["pin_mpactid", "合同编号", "对应 FA 科目尾段"],
      ["pin_acbalance", "投融资余额", "判断财产权余额是否非 0"],
    ],
  },
  {
    table: "ass_man_reg.ex_pledge_back",
    source: "报表数据源",
    rows: [
      ["project_code", "项目编号", "逆回购缺失细分关联项目"],
      ["subcode", "子编码", "只检查 7 开头数据"],
      ["buyback_money", "回购金额", "检查是否为空"],
      ["expenses", "佣金", "检查是否为空"],
    ],
  },
  {
    table: "currency_report_24.currency_detail_project_2_1_*",
    source: "报表数据源",
    rows: [
      ["caldate", "核对日期", "资产缺失细分按日期检查报表明细是否生成"],
    ],
  },
  {
    table: "currency_report_duration",
    source: "报表数据源",
    rows: [
      ["caldate", "TA 日期", "当前核心逻辑未使用，保留给后续 TA 规则扩展"],
      ["c_projectcode", "项目编号", "当前核心逻辑未使用，后续可对应 zf_detail_2024.projinnercode"],
      ["f_assetshare", "TA 实收/资产份额金额", "当前核心逻辑未使用，后续可恢复或扩展 TA 规则"],
    ],
  },
];

const BUSINESS_GROUP_LOGICAL_KEYS = {
  zf_detail_2024: ["zf_detail"],
  fa_valuationreport_dws: ["fa_valuation"],
  fa_accountbalance_dws: ["fa_account_balance"],
  "dm.ta_pact_survamt_day_zgxg_dm": ["ta_survamt_dm"],
  ta_pact_detail_dws: ["ta_pact_detail"],
  am_pactasset_dws: ["am_pact_asset"],
  am_projinvest_dws: ["am_project_invest"],
  "dm.fa_security_balance_zgxg_dm": ["fa_security_balance_dm"],
  "dm.am_projinvest_zgxg_dm": ["dm_project_invest"],
  "dm.am_projinvest_spv_zgxg_dm": ["dm_spv_project_invest"],
  "zgxg_zhbs.ccqxx": ["property_right_contract"],
  "ass_man_reg.ex_pledge_back": ["pledge_back"],
  "currency_report_24.currency_detail_project_2_1_*": [
    "report_detail_2_1_2",
    "report_detail_2_1_4",
    "report_detail_2_1_5",
    "report_detail_2_1_5_2",
    "report_detail_2_1_6",
    "report_detail_2_1_8",
    "report_detail_2_1_9",
  ],
  currency_report_duration: ["ta_asset_share_duration"],
};

function reconcileMetaByKey(logicalKey) {
  return RECONCILE_SCHEMA_TABLES.find((item) => item.key === logicalKey) || null;
}

function currentReconcileTableConfig(logicalKey) {
  const meta = reconcileMetaByKey(logicalKey);
  const existing = reconcileSchemaState.tables?.[logicalKey] || {};
  const tableEl = reconcileSchemaTableElement(logicalKey);
  if (!meta || !tableEl) {
    return {
      table: existing.table || RECONCILE_SCHEMA_DEFAULT_TABLES[logicalKey] || "",
      displayName: existing.display_name || meta?.name || logicalKey,
      sourceName: existing.source_ref?.name || existing.source_ref?.id || "",
      fields: existing.fields || {},
      optionalFields: existing.optional_fields || {},
    };
  }
  const sourceSelect = tableEl.querySelector("select.reconcile-schema-source");
  const fields = {};
  const optionalFields = {};
  (meta.fields || []).forEach(([fieldKey]) => {
    fields[fieldKey] = readTrimmedControlValue(reconcileSchemaFieldInput(tableEl, fieldKey));
  });
  (meta.optionalFields || []).forEach(([fieldKey]) => {
    optionalFields[fieldKey] = readTrimmedControlValue(reconcileSchemaFieldInput(tableEl, fieldKey));
  });
  return {
    table: readTrimmedControlValue(tableEl.querySelector("input.reconcile-schema-table-name")) || existing.table || RECONCILE_SCHEMA_DEFAULT_TABLES[logicalKey] || "",
    displayName: readTrimmedControlValue(tableEl.querySelector("input.reconcile-schema-display-name")) || existing.display_name || meta.name,
    sourceName: sourceSelect?.selectedOptions?.[0]?.textContent?.trim() || existing.source_ref?.name || existing.source_ref?.id || "",
    fields,
    optionalFields,
  };
}

function currentReconcileTableDisplayName(logicalKey, fallback = "") {
  return currentReconcileTableConfig(logicalKey).displayName || fallback || logicalKey;
}

function fieldKeyForDefaultColumn(logicalKey, defaultColumn) {
  const meta = reconcileMetaByKey(logicalKey);
  if (!meta) return "";
  const rows = [...(meta.fields || []), ...(meta.optionalFields || [])];
  const match = rows.find(([, , defaultValue]) => defaultValue === defaultColumn);
  return match?.[0] || "";
}

function currentBusinessFieldValue(logicalKey, originalFieldText) {
  const parts = String(originalFieldText || "").split("/").map((item) => item.trim()).filter(Boolean);
  if (!parts.length) return originalFieldText;
  const config = currentReconcileTableConfig(logicalKey);
  const values = parts.map((part) => {
    const fieldKey = fieldKeyForDefaultColumn(logicalKey, part);
    if (!fieldKey) return part;
    return config.fields[fieldKey] || config.optionalFields[fieldKey] || part;
  });
  return values.join("/");
}

function compactBusinessTableNames(logicalKeys = [], fallback = "") {
  const names = [...new Set(logicalKeys.map((key) => currentReconcileTableConfig(key).table).filter(Boolean))];
  if (!names.length) return fallback;
  if (names.length <= 2) return names.join("、");
  return `${names[0]} 等 ${names.length} 张表`;
}

function compactBusinessSourceNames(logicalKeys = [], fallback = "") {
  const names = [...new Set(logicalKeys.map((key) => currentReconcileTableConfig(key).sourceName).filter(Boolean))];
  if (!names.length) return fallback;
  if (names.length <= 2) return names.join("、");
  return `${names[0]} 等 ${names.length} 个数据源`;
}

function currentBusinessFieldGroups() {
  return BUSINESS_FIELD_GROUPS.map((group) => {
    const logicalKeys = BUSINESS_GROUP_LOGICAL_KEYS[group.table] || [];
    if (!logicalKeys.length) return group;
    const primaryKey = logicalKeys[0];
    return {
      ...group,
      displayName: currentReconcileTableDisplayName(primaryKey, group.table),
      table: compactBusinessTableNames(logicalKeys, group.table),
      source: compactBusinessSourceNames(logicalKeys, group.source),
      rows: group.rows.map((row) => [
        currentBusinessFieldValue(primaryKey, row[0]),
        row[1],
        row[2],
      ]),
    };
  });
}

function renderBusinessSettings() {
  const container = document.getElementById("businessSettingsContent");
  if (!container) return;

  const note = document.getElementById("businessSettingsNote");
  if (note) note.textContent = BUSINESS_SETTINGS_MAINTENANCE_NOTE;

  container.innerHTML = currentBusinessFieldGroups().map((group) => `
    <div class="business-field-group">
      <div class="business-field-header">
        <strong>${escapeHtml(group.displayName || group.table)}</strong>
        <span>${escapeHtml(group.source)}</span>
      </div>
      <table class="detail-table business-field-table">
        <thead>
          <tr>
            <th>字段</th>
            <th>业务含义</th>
            <th>当前用途</th>
          </tr>
        </thead>
        <tbody>
          ${group.rows.map((row) => `
            <tr>
              <td><code>${escapeHtml(row[0])}</code></td>
              <td>${escapeHtml(row[1])}</td>
              <td>${escapeHtml(row[2])}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `).join("");
}

// Collapsible sections - accordion style
const collapsibleSections = [];

function setupCollapsible(toggleId, bodyId, arrowId) {
  const toggle = document.getElementById(toggleId);
  const body = document.getElementById(bodyId);
  const arrow = document.getElementById(arrowId);
  if (!toggle || !body) return;
  if (!toggle.classList.contains("collapsible")) return;

  // Remove hidden attribute initially, use CSS for animation
  body.removeAttribute("hidden");
  body.classList.add("collapsed");

  collapsibleSections.push({ body, arrow });

  toggle.addEventListener("click", () => {
    const isExpanding = body.classList.contains("collapsed");

    // Close all other sections
    collapsibleSections.forEach(section => {
      if (section.body !== body) {
        section.body.classList.add("collapsed");
        if (section.arrow) {
          section.arrow.style.transform = "rotate(0deg)";
        }
      }
    });

    // Toggle current section
    if (isExpanding) {
      body.classList.remove("collapsed");
    } else {
      body.classList.add("collapsed");
    }
    if (arrow) {
      arrow.style.transform = isExpanding ? "rotate(180deg)" : "rotate(0deg)";
    }
  });
}

// Setup all collapsible sections
setupCollapsible("sysInfoToggle", "sysInfoBody", "sysInfoArrow");
setupCollapsible("defaultSettingsToggle", "defaultSettingsBody", "defaultSettingsArrow");
setupCollapsible("dataManageToggle", "dataManageBody", "dataManageArrow");
setupCollapsible("aboutToggle", "aboutBody", "aboutArrow");
renderBusinessSettings();

// Confirm modal
function showConfirm(title, message) {
  return new Promise((resolve) => {
    const modal = document.getElementById("confirmModal");
    const titleEl = document.getElementById("confirmTitle");
    const messageEl = document.getElementById("confirmMessage");
    const okBtn = document.getElementById("confirmOk");
    const cancelBtn = document.getElementById("confirmCancel");

    titleEl.textContent = title;
    messageEl.textContent = message;
    modal.hidden = false;

    const cleanup = () => {
      modal.classList.add("closing");
      setTimeout(() => {
        modal.hidden = true;
        modal.classList.remove("closing");
      }, 200);
    };

    okBtn.onclick = () => {
      cleanup();
      resolve(true);
    };

    cancelBtn.onclick = () => {
      cleanup();
      resolve(false);
    };
  });
}

function showPrompt(title, message, options = {}) {
  return new Promise((resolve) => {
    const modal = document.getElementById("promptModal");
    const titleEl = document.getElementById("promptTitle");
    const messageEl = document.getElementById("promptMessage");
    const inputEl = document.getElementById("promptInput");
    const dateInputEl = document.getElementById("promptDateInput");
    const dateControlEl = document.getElementById("promptDateControl");
    const okBtn = document.getElementById("promptOk");
    const cancelBtn = document.getElementById("promptCancel");
    const isDate = options.type === "date";
    const inputControlEl = inputEl.closest(".custom-input-shell") || inputEl;
    const activeInputEl = isDate ? dateInputEl : inputEl;
    const dialogEl = modal.querySelector(".modal-prompt");
    const focusTargetEl = isDate ? dialogEl : activeInputEl;

    titleEl.textContent = title;
    messageEl.textContent = message;
    inputControlEl.hidden = isDate;
    dateControlEl.hidden = !isDate;
    if (isDate) {
      dateInputEl.value = options.defaultValue || "";
      dateInputEl.placeholder = options.placeholder || "";
    } else {
      inputEl.type = options.type || "text";
      inputEl.value = options.defaultValue || "";
      inputEl.placeholder = options.placeholder || "";
      inputEl.autocomplete = options.autocomplete || "off";
    }
    modal.hidden = false;
    setTimeout(() => focusTargetEl?.focus(), 0);

    const cleanup = (value) => {
      okBtn.onclick = null;
      cancelBtn.onclick = null;
      activeInputEl.onkeydown = null;
      closeCustomDatePicker(dateInputEl);
      modal.classList.add("closing");
      setTimeout(() => {
        modal.hidden = true;
        modal.classList.remove("closing");
        inputEl.value = "";
        inputEl.type = "text";
        dateInputEl.value = "";
        inputControlEl.hidden = false;
        dateControlEl.hidden = true;
      }, 200);
      resolve(value);
    };

    okBtn.onclick = () => cleanup(activeInputEl.value);
    cancelBtn.onclick = () => cleanup(null);
    activeInputEl.onkeydown = (event) => {
      if (event.key === "Enter" && !isDate) {
        event.preventDefault();
        cleanup(activeInputEl.value);
      }
      if (event.key === "Escape") {
        event.preventDefault();
        cleanup(null);
      }
    };
  });
}

// Info modal
function showInfo(title, content, options = {}) {
  const modal = document.getElementById("infoModal");
  const titleEl = document.getElementById("infoTitle");
  const bodyEl = document.getElementById("infoBody");
  const closeBtn = document.getElementById("infoClose");
  const detailAction = document.getElementById("infoDetailAction");
  const infoBox = modal.querySelector(".modal-info");
  infoBox?.classList.remove("modal-info--home-stat", "modal-info--history-detail");
  if (options.modalClass) infoBox?.classList.add(options.modalClass);

  titleEl.textContent = title;
  bodyEl.innerHTML = content;
  if (detailAction) {
    detailAction.hidden = true;
    detailAction.onclick = null;
    detailAction.textContent = options.detailActionLabel || "查看明细";
  }
  modal.hidden = false;

  const cleanup = () => {
    modal.classList.add("closing");
    setTimeout(() => {
      modal.hidden = true;
      modal.classList.remove("closing");
    }, 200);
  };

  if (detailAction && typeof options.onDetailAction === "function") {
    detailAction.hidden = false;
    detailAction.onclick = () => {
      options.onDetailAction();
      cleanup();
    };
  }

  closeBtn.onclick = cleanup;
  modal.onclick = (e) => {
    if (options.closeOnBackdrop === false) return;
    if (e.target === modal) cleanup();
  };
}

// System Info
async function loadSystemInfo() {
  try {
    const payload = await api("/api/system-info");
    const settings = serverSettingsToClient(payload.settings || {});
    document.getElementById("historyRunCount").textContent = String(payload.history_run_count || 0);
    document.getElementById("loginUserInfo").textContent = userDisplayName(authState.user || {});
    document.getElementById("autoRefreshInfo").textContent = settings.autoRefreshHome === "true" ? "开启" : "关闭";
    document.getElementById("configCount").textContent = String(payload.config_count || 0);
    return true;
  } catch (_) {
    return false;
  }
}

function setSystemInfoFeedback(type, message) {
  if (!sysInfoFeedback) return;
  sysInfoFeedback.className = `sys-info-feedback sys-info-feedback--${type}`;
  sysInfoFeedback.textContent = message;
  sysInfoFeedback.hidden = !message;
}

async function runSystemInfoAction(button, pendingText, successText) {
  if (!button) return;
  if (authState.user?.role !== "admin") {
    setSystemInfoFeedback("error", "普通用户不可执行该操作");
    return;
  }
  const originalText = button.dataset.originalText || button.textContent;
  button.dataset.originalText = originalText;
  button.textContent = pendingText;
  button.disabled = true;
  if (refreshInfoBtn && refreshInfoBtn !== button) refreshInfoBtn.disabled = true;
  setSystemInfoFeedback("running", `${pendingText} ${formatClockTime()}`);
  setStatus(pendingText);
  try {
    await loadSystemInfo();
    setSystemInfoFeedback("success", `${successText} ${formatClockTime()}`);
    setStatus(successText);
  } catch (_) {
    setSystemInfoFeedback("error", `${successText}失败 ${formatClockTime()}`);
    setStatus(`${successText}失败`);
  }
  button.textContent = originalText;
  if (refreshInfoBtn) refreshInfoBtn.disabled = false;
}

refreshInfoBtn?.addEventListener("click", () => runSystemInfoAction(refreshInfoBtn, "刷新中...", "信息已刷新"));

// Default Settings
function syncDefaultSettingsControls() {
  ["visualEffects", "autoRefreshHome"].forEach((id) => {
    const select = document.getElementById(id);
    if (select) syncCustomSelect(select);
  });
}

function loadSettings() {
  const settings = normalizeClientSettings(defaultSettings);
  document.getElementById("sessionExpireHours").value = settings.sessionExpireHours || "8";
  document.getElementById("combinationLimit").value = settings.combinationLimit || "50";
  document.getElementById("autoRefreshHome").value = settings.autoRefreshHome || "false";
  document.getElementById("visualEffects").value = settings.visualEffects || "true";
  PAGE_SIZE = parseInt(settings.pageSize) || 10;
  applyVisualEffectsSetting();
  syncDefaultSettingsControls();
}

async function saveSettings() {
  const settings = {
    sessionExpireHours: document.getElementById("sessionExpireHours").value,
    pageSize: defaultSettings.pageSize || DEFAULT_SETTINGS.pageSize,
    combinationLimit: document.getElementById("combinationLimit").value,
    autoRefreshHome: document.getElementById("autoRefreshHome").value,
    visualEffects: document.getElementById("visualEffects").value,
    theme: serverDefaultSettings.theme,
    darkMode: serverDefaultSettings.darkMode,
  };
  try {
    const saved = await api("/api/settings/defaults", {
      method: "POST",
      body: JSON.stringify(clientSettingsToServer(settings)),
    });
    serverDefaultSettings = serverSettingsToClient(saved.settings || {});
    defaultSettings = withSavedUserTheme(serverDefaultSettings);
    localStorage.removeItem("autoCheckSettings");
    syncThemeBootCache();
    loadSettings();
    loadTheme();
    PAGE_SIZE = parseInt(defaultSettings.pageSize) || 10;
    currentPage = 1;
    hasReconciled = false;
    resultEmptyState = "";
    renderResults();
  showToast("设置已保存", "success");
  } catch (e) {
    showToast("设置保存失败: " + e.message, "error");
  }
}

async function resetSettings() {
  localStorage.removeItem("autoCheckSettings");
  try {
    const saved = await api("/api/settings/defaults", {
      method: "POST",
      body: JSON.stringify(clientSettingsToServer(DEFAULT_SETTINGS)),
    });
    serverDefaultSettings = serverSettingsToClient(saved.settings || {});
    defaultSettings = withSavedUserTheme(serverDefaultSettings);
    syncThemeBootCache();
    loadSettings();
    loadTheme();
    PAGE_SIZE = 10;
    currentPage = 1;
    hasReconciled = false;
    resultEmptyState = "";
    renderResults();
  showToast("已恢复默认设置", "success");
  } catch (e) {
    showToast("恢复默认失败: " + e.message, "error");
  }
}

document.getElementById("saveSettingsBtn")?.addEventListener("click", saveSettings);
document.getElementById("resetSettingsBtn")?.addEventListener("click", resetSettings);

// Data Management
document.getElementById("clearHistoryBtn")?.addEventListener("click", async () => {
  const confirmed = await showConfirm(
    "清理历史记录",
    "确定要清理所有历史记录吗？此操作不可恢复。"
  );
  if (!confirmed) return;

  try {
    const historyData = await api("/api/history");
    const history = historyData.history || [];
    for (const run of history) {
      await api("/api/history", {
        method: "DELETE",
        body: JSON.stringify({ id: run.id })
      });
    }
    clearLatestResultsSnapshot();
    results = [];
    currentPage = 1;
    hasReconciled = false;
    resultEmptyState = "";
    renderResults();
    showToast("历史记录已清理", "success");
    loadSystemInfo();
  } catch (e) {
    showToast("清理失败: " + e.message, "error");
  }
});

document.getElementById("exportConfigBtn")?.addEventListener("click", async () => {
  try {
    const data = await api("/api/configs/export");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `auto-check-configs-${formatBeijingDate()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    showToast("导出失败: " + e.message, "error");
  }
});

document.getElementById("importConfigBtn")?.addEventListener("click", () => {
  document.getElementById("importConfigFile").click();
});

document.getElementById("importConfigFile")?.addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  try {
    const text = await file.text();
    const data = JSON.parse(text);
    if (!data.configs || !Array.isArray(data.configs)) {
      throw new Error("无效的配置文件格式");
    }

    for (const config of data.configs) {
      await api("/api/configs", {
        method: "POST",
        body: JSON.stringify(config)
      });
    }
    showToast("配置导入成功", "success");
    loadConfigList();
    loadSystemInfo();
  } catch (e) {
    showToast("导入失败: " + e.message, "error");
  }
  e.target.value = "";
});

/* ===== Tools: PBC full product import (modal-based 4-step flow) ===== */
let pbcCurrentStep = 1;
let pbcUploadedFiles = []; // {name, columns, upload_id}
let pbcImportConflictState = false;
let pbcImportFailed = false;

function appendPbcLog(message, type = "") {
  if (!pbcImportLog) return;
  const line = document.createElement("div");
  line.className = "pbc-log-entry" + (type ? ` pbc-log-entry--${type}` : "");
  line.textContent = `[${formatClockTime()}] ${message}`;
  pbcImportLog.appendChild(line);
  pbcImportLog.scrollTop = pbcImportLog.scrollHeight;
}

function handlePbcImportStartError(error) {
  const message = error?.message || "导入失败";
  if (message.includes("正在导入") || message.includes("上一个任务完成")) {
    pbcImportConflictState = true;
    setPbcImportProgressState("稍后再试", "待插入表正在导入，完成后可点击重试", false);
    if (pbcRetryBtn) pbcRetryBtn.hidden = false;
    appendPbcLog("待插入表正在导入，请等待上一个任务完成后再导入。", "error");
    showToast(message, "warning");
    return;
  }
  appendPbcLog("启动失败: " + message, "error");
  showToast("导入失败: " + message, "error");
  pbcImportFailed = true;
  setPbcImportProgressState("导入失败", message, false);
}

function setPbcImportProgressState(title, subtitle, spinning = true) {
  if (pbcProgressTitle) pbcProgressTitle.textContent = title;
  if (pbcProgressSubtitle) pbcProgressSubtitle.textContent = subtitle;
  pbcProgressIcon?.classList.toggle("pbc-progress-icon--spinning", Boolean(spinning));
}

function selectedPbcDataSource() {
  const value = pbcDataSource?.value || "";
  const [configName, source] = value.split("::");
  return { configName: configName || "", source: source || "dws" };
}

function getPbcTargetTable() {
  if (!pbcTargetTable) return "";
  return (pbcTargetTable.value || "").trim();
}

function renderPbcSettings(settings = {}, dataSources = []) {
  pbcDataSources = dataSources;
  if (pbcDataSource) {
    pbcDataSource.innerHTML = dataSources.map((item) => {
      const value = `${escapeHtml(item.config_name)}::${escapeHtml(item.source)}`;
      return `<option value="${value}">${escapeHtml(item.label || value)}</option>`;
    }).join("");
    const preferred = `${settings.last_config_name || ""}::${settings.last_source || "dws"}`;
    const preferredOption = [...pbcDataSource.options].find((option) => option.value === preferred);
    if (preferredOption) pbcDataSource.value = preferred;
    else {
      const defaultOption = [...pbcDataSource.options].find((option) => {
        const source = dataSources.find((item) => `${item.config_name}::${item.source}` === option.value);
        return source?.is_default && source?.source === "dws";
      });
      if (defaultOption) pbcDataSource.value = defaultOption.value;
    }
  }
  if (pbcRecentTables) {
    pbcRecentTables.innerHTML = (settings.recent_tables || []).map((table) => `<option value="${escapeHtml(table)}"></option>`).join("");
  }
  if (pbcTargetTable && settings.recent_tables?.length) {
    pbcTargetTable.value = settings.recent_tables[0];
  }
}

async function loadPbcImportSettings() {
  if (!pbcDataSource) return;
  try {
    const payload = await api("/api/tools/pbc-import/settings");
    renderPbcSettings(payload.settings || {}, payload.data_sources || []);
  } catch (e) {
    console.error("PBC配置加载失败", e);
  }
}

/* ===== Tools: database validation ===== */
const DB_VALIDATION_TITLE = "人行逐笔校验引擎";
const DB_VALIDATION_DOWNLOAD_PREFIX = "/api/tools/db-validation/download/";
const DB_VALIDATION_HISTORY_DOWNLOAD_PREFIX = "/api/tools/db-validation/history/download/";

function dbValidationSourceValue(item = {}) {
  return item.id || "";
}

function fillDbValidationSourceSelect(select, dataSources, preferredSourceId = "") {
  if (!select) return;
  select.innerHTML = (dataSources || []).map((item) => {
    const value = dbValidationSourceValue(item);
    return `<option value="${escapeHtml(value)}">${escapeHtml(item.name || item.label || value)}</option>`;
  }).join("");
  const preferredOption = [...select.options].find((option) => option.value === preferredSourceId);
  if (preferredOption) {
    select.value = preferredSourceId;
    return;
  }
  const defaultOption = [...select.options].find((option) => {
    const source = dataSources.find((item) => dbValidationSourceValue(item) === option.value);
    return source?.is_default;
  });
  if (defaultOption) select.value = defaultOption.value;
}

function renderDbValidationTables(tables = []) {
  if (!dbValidationTableList) return;
  if (!tables.length) {
    dbValidationTableList.innerHTML = '<p class="placeholder-text">暂无可校验表单</p>';
    return;
  }
  dbValidationTableList.innerHTML = tables.map((item) => `
    <label class="db-validation-table-item">
      <input type="checkbox" value="${escapeHtml(item.code)}" checked />
      <span>${escapeHtml(item.code)}</span>
      <small>${escapeHtml(item.table_name || "")}</small>
    </label>
  `).join("");
  if (dbValidationSelectAllTablesBtn) dbValidationSelectAllTablesBtn.checked = true;
}

function renderDbValidationDatasetSettings(dataset = {}, select, sysInput, classInput) {
  fillDbValidationSourceSelect(select, dbValidationDataSources, dataset.source_id || "");
  if (sysInput) sysInput.value = dataset.sys_manage_id || "";
  if (classInput) classInput.value = dataset.classification_id || "";
}

function readDbValidationDatasetSettings(select, sysInput, classInput) {
  return {
    source_id: select?.value || "",
    sys_manage_id: (sysInput?.value || "").trim(),
    classification_id: (classInput?.value || "").trim(),
  };
}

function dbValidationFieldMappingStatusText(status = {}) {
  if (status.last_error) {
    return `字段映射刷新失败：${status.last_error}`;
  }
  if (!status.initialized) {
    return "字段映射未初始化";
  }
  const sourceText = status.refresh_source === "auto" ? "自动刷新" : "手动刷新";
  const refreshedAt = status.refreshed_at ? `，${status.refreshed_at}` : "";
  const tableCount = Number(status.table_count || 0);
  const expectedTableCount = Array.isArray(dbValidationTables) ? dbValidationTables.length : 0;
  const coverageHint = expectedTableCount && tableCount < expectedTableCount
    ? `；少于系统内置表单 ${tableCount}/${expectedTableCount} 张，请检查字段映射数据源、baseinfo/field_info 或筛选条件`
    : "";
  return `字段映射已加载：${tableCount} 张表，${status.field_count || 0} 个字段，未映射 ${status.unmapped_field_count || 0} 个字段，${sourceText}${refreshedAt}${coverageHint}`;
}

function renderDbValidationFieldMappingStatus(status = {}, prefix = "") {
  if (!dbValidationSettingsStatus) return;
  const text = dbValidationFieldMappingStatusText(status);
  dbValidationSettingsStatus.textContent = prefix ? `${prefix}${text}` : text;
}

function renderDbValidationSettings(settings = {}, dataSources = [], tables = [], defaultReportDate = "", fieldMappingStatus = null) {
  dbValidationDataSources = dataSources;
  dbValidationTables = tables;
  renderDbValidationDatasetSettings(settings.detail || {}, dbValidationDetailSource, dbValidationDetailSysManageId, dbValidationDetailClassificationId);
  renderDbValidationDatasetSettings(settings.public_info || {}, dbValidationPublicInfoSource, dbValidationPublicInfoSysManageId, dbValidationPublicInfoClassificationId);
  renderDbValidationDatasetSettings(settings.template || {}, dbValidationTemplateSource, dbValidationTemplateSysManageId, dbValidationTemplateClassificationId);
  fillDbValidationSourceSelect(dbValidationMetadataSource, dataSources, settings.field_mapping_source_id || "");
  if (dbValidationReportDate && !dbValidationReportDate.value) {
    dbValidationReportDate.value = defaultReportDate || "";
  }
  if (dbValidationBaseinfoTable) dbValidationBaseinfoTable.value = settings.baseinfo_table || "xt_reg_table_baseinfo";
  if (dbValidationFieldInfoTable) dbValidationFieldInfoTable.value = settings.field_info_table || "xt_reg_table_field_info";
  if (dbValidationPublicInfoTable) dbValidationPublicInfoTable.value = settings.public_info_table || "public_information_rh";
  renderDbValidationTables(tables);
  if (fieldMappingStatus) renderDbValidationFieldMappingStatus(fieldMappingStatus);
}

function renderDbValidationSettingsLoading() {
  if (dbValidationTableList) dbValidationTableList.innerHTML = '<p class="placeholder-text">正在加载逐笔校验配置...</p>';
  if (dbValidationSettingsStatus) dbValidationSettingsStatus.textContent = "正在加载逐笔校验配置...";
  if (dbValidationSelectAllTablesBtn) {
    dbValidationSelectAllTablesBtn.checked = false;
    dbValidationSelectAllTablesBtn.indeterminate = false;
  }
}

function renderDbValidationSettingsError(message = "逐笔校验配置加载失败") {
  const text = message ? `逐笔校验配置加载失败：${message}` : "逐笔校验配置加载失败";
  dbValidationDataSources = [];
  dbValidationTables = [];
  [dbValidationDetailSource, dbValidationPublicInfoSource, dbValidationTemplateSource, dbValidationMetadataSource].forEach((select) => {
    if (select) select.innerHTML = "";
  });
  if (dbValidationTableList) dbValidationTableList.innerHTML = `<p class="placeholder-text">${escapeHtml(text)}</p>`;
  if (dbValidationSettingsStatus) dbValidationSettingsStatus.textContent = text;
  if (dbValidationSelectAllTablesBtn) {
    dbValidationSelectAllTablesBtn.checked = false;
    dbValidationSelectAllTablesBtn.indeterminate = false;
  }
}

async function loadDbValidationSettings() {
  if (!toolCardDbValidation && !dbValidationMetadataSource) return;
  renderDbValidationSettingsLoading();
  try {
    const payload = await api("/api/tools/db-validation/settings");
    renderDbValidationSettings(
      payload.settings || {},
      payload.data_sources || [],
      payload.tables || [],
      payload.default_report_date || "",
      payload.field_mapping || {}
    );
    return payload;
  } catch (e) {
    console.error("数据库校验配置加载失败", e);
    renderDbValidationSettingsError(e.message || "请检查本地服务状态");
    return null;
  }
}

async function saveDbValidationSettings(options = {}) {
  if (!dbValidationMetadataSource) return;
  const quiet = Boolean(options.quiet);
  const refreshMapping = options.refreshMapping !== false;
  if (dbValidationSettingsStatus) dbValidationSettingsStatus.textContent = quiet ? "保存当前配置..." : "保存中...";
  if (saveDbValidationSettingsBtn) saveDbValidationSettingsBtn.disabled = true;
  if (refreshMapping && dbValidationRefreshFieldMappingBtn) dbValidationRefreshFieldMappingBtn.disabled = true;
  try {
    const payload = await api("/api/tools/db-validation/settings", {
      method: "POST",
      body: JSON.stringify({
        detail: readDbValidationDatasetSettings(
          dbValidationDetailSource,
          dbValidationDetailSysManageId,
          dbValidationDetailClassificationId
        ),
        public_info: readDbValidationDatasetSettings(
          dbValidationPublicInfoSource,
          dbValidationPublicInfoSysManageId,
          dbValidationPublicInfoClassificationId
        ),
        template: readDbValidationDatasetSettings(
          dbValidationTemplateSource,
          dbValidationTemplateSysManageId,
          dbValidationTemplateClassificationId
        ),
        field_mapping_source_id: dbValidationMetadataSource?.value || "",
        baseinfo_table: (dbValidationBaseinfoTable?.value || "").trim() || "xt_reg_table_baseinfo",
        field_info_table: (dbValidationFieldInfoTable?.value || "").trim() || "xt_reg_table_field_info",
        public_info_table: (dbValidationPublicInfoTable?.value || "").trim() || "public_information_rh",
      }),
    });
    renderDbValidationSettings(
      payload.settings || {},
      dbValidationDataSources,
      dbValidationTables,
      dbValidationReportDate?.value || "",
      payload.field_mapping || {}
    );
    if (refreshMapping) {
      if (dbValidationSettingsStatus) dbValidationSettingsStatus.textContent = quiet ? "配置已保存，正在刷新字段映射..." : "已保存，正在刷新字段映射...";
      const refreshPayload = await api("/api/tools/db-validation/field-mapping/refresh", { method: "POST" });
      const status = refreshPayload.field_mapping || {};
      renderDbValidationFieldMappingStatus(status, status.last_error ? "" : "已保存并刷新。");
      if (status.last_error) {
        if (!quiet) showToast("逐笔字段映射刷新失败", "error");
      } else if (!quiet) {
        showToast("数据库校验配置已保存，字段映射已刷新", "success");
      }
      return { ...payload, field_mapping: status };
    }
    renderDbValidationFieldMappingStatus(payload.field_mapping || {}, quiet ? "配置已保存。" : "已保存。");
    if (!quiet) showToast("数据库校验配置已保存", "success");
    return payload;
  } catch (e) {
    if (dbValidationSettingsStatus) dbValidationSettingsStatus.textContent = e.message;
    if (!quiet) showToast("保存失败: " + e.message, "error");
    throw e;
  } finally {
    if (saveDbValidationSettingsBtn) saveDbValidationSettingsBtn.disabled = false;
    if (refreshMapping && dbValidationRefreshFieldMappingBtn) dbValidationRefreshFieldMappingBtn.disabled = false;
  }
}

async function refreshDbValidationFieldMapping() {
  if (!dbValidationMetadataSource) return;
  if (dbValidationSettingsStatus) dbValidationSettingsStatus.textContent = "保存配置并刷新字段映射...";
  if (dbValidationRefreshFieldMappingBtn) dbValidationRefreshFieldMappingBtn.disabled = true;
  try {
    await saveDbValidationSettings({ quiet: true, refreshMapping: false });
    const payload = await api("/api/tools/db-validation/field-mapping/refresh", { method: "POST" });
    const status = payload.field_mapping || {};
    renderDbValidationFieldMappingStatus(status, status.last_error ? "" : "已刷新。");
    if (status.last_error) {
      showToast("逐笔字段映射刷新失败", "error");
    } else {
      showToast("逐笔字段映射已刷新", "success");
    }
  } catch (e) {
    if (dbValidationSettingsStatus) dbValidationSettingsStatus.textContent = e.message;
    showToast("刷新失败: " + e.message, "error");
  } finally {
    if (dbValidationRefreshFieldMappingBtn) dbValidationRefreshFieldMappingBtn.disabled = false;
  }
}

function appendDbValidationLog(message, type = "") {
  if (!dbValidationLog) return;
  const line = document.createElement("div");
  line.className = "pbc-log-entry" + (type ? ` pbc-log-entry--${type}` : "");
  line.textContent = `[${formatClockTime()}] ${message}`;
  dbValidationLog.appendChild(line);
  dbValidationLog.scrollTop = dbValidationLog.scrollHeight;
}

function setDbValidationProgress(title, subtitle, progress = 0, spinning = true) {
  const safeProgress = Math.max(0, Math.min(100, Number(progress) || 0));
  if (dbValidationProgressTitle) dbValidationProgressTitle.textContent = title;
  if (dbValidationProgressSubtitle) dbValidationProgressSubtitle.textContent = subtitle;
  if (dbValidationProgressFill) dbValidationProgressFill.style.width = `${safeProgress}%`;
  if (dbValidationProgressPercent) dbValidationProgressPercent.textContent = `${safeProgress}%`;
  dbValidationProgressIcon?.classList.toggle("pbc-progress-icon--spinning", Boolean(spinning));
}

function resetDbValidationModal() {
  dbValidationDownloadUrl = "";
  if (dbValidationStatus) dbValidationStatus.textContent = "";
  if (dbValidationDownloadBtn) dbValidationDownloadBtn.disabled = true;
  if (dbValidationStartBtn) dbValidationStartBtn.disabled = false;
  if (dbValidationStats) dbValidationStats.innerHTML = "";
  if (dbValidationLog) dbValidationLog.innerHTML = '<div class="pbc-log-entry pbc-log-entry--info">准备开始校验...</div>';
  setDbValidationProgress("等待开始", "确认参数后开始数据库校验", 0, false);
}

function openDbValidationModal() {
  resetDbValidationModal();
  dbValidationModalOverlay?.classList.add("active");
  loadDbValidationSettings();
}

function closeDbValidationModal() {
  dbValidationModalOverlay?.classList.remove("active");
  if (dbValidationPollTimer) {
    clearInterval(dbValidationPollTimer);
    dbValidationPollTimer = null;
  }
}

function selectedDbValidationTables() {
  if (!dbValidationTableList) return [];
  return [...dbValidationTableList.querySelectorAll('input[type="checkbox"]:checked')].map((item) => item.value);
}

function renderDbValidationResult(job = {}) {
  const result = job.result || {};
  const warnings = result.warnings || [];
  dbValidationDownloadUrl = job.download_url || `${DB_VALIDATION_DOWNLOAD_PREFIX}${encodeURIComponent(job.id || "")}`;
  if (dbValidationStats) {
    dbValidationStats.innerHTML = `
      <div class="pbc-complete-stat"><div class="pbc-complete-stat-value">${result.error_count || 0}</div><div class="pbc-complete-stat-label">校验结果</div></div>
      <div class="pbc-complete-stat"><div class="pbc-complete-stat-value">${warnings.length}</div><div class="pbc-complete-stat-label">提示信息</div></div>
      <div class="pbc-complete-stat"><div class="pbc-complete-stat-value">${(job.selected_tables || []).length}</div><div class="pbc-complete-stat-label">校验表单</div></div>
    `;
  }
  if (warnings.length) appendDbValidationLog(`提示：${warnings.slice(0, 3).join("；")}${warnings.length > 3 ? "..." : ""}`, "info");
  if (dbValidationStatus) dbValidationStatus.textContent = `完成：输出 ${result.error_count || 0} 条结果`;
  if (dbValidationDownloadBtn) dbValidationDownloadBtn.disabled = !dbValidationDownloadUrl;
}

async function openDbValidationHistory() {
  dbValidationHistoryOverlay?.classList.add("active");
  await loadDbValidationHistory();
}

function closeDbValidationHistory() {
  dbValidationHistoryOverlay?.classList.remove("active");
}

async function loadDbValidationHistory() {
  if (!dbValidationHistoryBody) return;
  dbValidationHistoryBody.innerHTML = '<tr><td colspan="7" class="empty">正在加载...</td></tr>';
  try {
    const payload = await api("/api/tools/db-validation/history");
    const sortedHistory = [...(payload.history || [])].sort(compareDbValidationHistoryRunsDesc);
    renderDbValidationHistory(sortedHistory);
  } catch (e) {
    dbValidationHistoryBody.innerHTML = `<tr><td colspan="7" class="empty">${escapeHtml(e.message)}</td></tr>`;
  }
}

function dbValidationHistoryExecutionTime(run = {}) {
  return String(run.run_at || run.started_at || run.finished_at || "").trim();
}

function dbValidationHistoryExecutionTimeValue(run = {}) {
  const raw = dbValidationHistoryExecutionTime(run);
  const match = raw.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?/);
  if (match) {
    const [, year, month, day, hour, minute, second = "0"] = match;
    return Date.UTC(
      Number(year),
      Number(month) - 1,
      Number(day),
      Number(hour),
      Number(minute),
      Number(second),
    );
  }
  const parsed = Date.parse(raw.replace(" ", "T"));
  return Number.isFinite(parsed) ? parsed : 0;
}

function compareDbValidationHistoryRunsDesc(left, right) {
  const timeDiff = dbValidationHistoryExecutionTimeValue(right) - dbValidationHistoryExecutionTimeValue(left);
  if (timeDiff !== 0) return timeDiff;
  return String(right.id || "").localeCompare(String(left.id || ""));
}

function dbValidationHistoryExecutorName(run = {}) {
  return String(run.executor_name || run.executor_username || run.executor || "-").trim() || "-";
}

function renderDbValidationHistory(history = []) {
  if (!dbValidationHistoryBody) return;
  if (!history.length) {
    dbValidationHistoryBody.innerHTML = '<tr><td colspan="7" class="empty">暂无历史记录</td></tr>';
    return;
  }
  dbValidationHistoryBody.innerHTML = history.map((run) => {
    const downloadUrl = run.download_url || `${DB_VALIDATION_HISTORY_DOWNLOAD_PREFIX}${encodeURIComponent(run.id || "")}`;
    return `
    <tr>
      <td>${escapeHtml(formatDbValidationHistoryTime(run.run_at || run.started_at || ""))}</td>
      <td>${escapeHtml(dbValidationHistoryExecutorName(run))}</td>
      <td>${escapeHtml(run.report_date || run.run_date || "-")}</td>
      <td class="money-cell">
        <button type="button" class="db-validation-history-count-link db-validation-history-download" data-url="${escapeHtml(downloadUrl)}">${formatMoney(run.result_count || 0)}</button>
      </td>
      <td>${run.enable_public_info_check ? "是" : "否"}</td>
      <td>${run.enable_template_check ? "是" : "否"}</td>
      <td class="money-cell">${formatMoney(run.table_count || (run.selected_tables || []).length || 0)}</td>
    </tr>
  `;
  }).join("");
}

function formatDbValidationHistoryTime(value = "") {
  const text = String(value || "").trim();
  if (!text) return "-";
  return text.replace("T", " ");
}

async function startDbValidation() {
  const reportDate = dbValidationReportDate?.value || "";
  const tables = selectedDbValidationTables();
  if (!reportDate) {
    showToast("请选择报告期", "warning");
    return;
  }
  if (!tables.length) {
    showToast("请至少选择一张校验表", "warning");
    return;
  }
  if (dbValidationStartBtn) dbValidationStartBtn.disabled = true;
  if (dbValidationDownloadBtn) dbValidationDownloadBtn.disabled = true;
  dbValidationDownloadUrl = "";
  if (dbValidationStats) dbValidationStats.innerHTML = "";
  if (dbValidationLog) dbValidationLog.innerHTML = "";
  setDbValidationProgress("正在校验", "数据库校验任务已启动", 5, true);
  appendDbValidationLog("正在启动数据库校验任务...", "info");
  try {
    const payload = await api("/api/tools/db-validation/start", {
      method: "POST",
      body: JSON.stringify({
        report_date: reportDate,
        selected_tables: tables,
        enable_public_info_check: !!dbValidationPublicInfoCheck?.checked,
        enable_template_check: !!dbValidationTemplateCheck?.checked,
      }),
    });
    appendDbValidationLog(`校验任务已启动：${payload.job_id}`, "info");
    await pollDbValidationJob(payload.job_id);
  } catch (e) {
    setDbValidationProgress("启动失败", e.message, 100, false);
    appendDbValidationLog("启动失败: " + e.message, "error");
    showToast("数据库校验失败: " + e.message, "error");
    if (dbValidationStartBtn) dbValidationStartBtn.disabled = false;
  }
}

async function pollDbValidationJob(jobId) {
  if (dbValidationPollTimer) clearInterval(dbValidationPollTimer);
  let lastLogCount = 0;
  const poll = async () => {
    try {
      const payload = await api(`/api/tools/db-validation/status/${encodeURIComponent(jobId)}`);
      const job = payload.job || {};
      const progress = job.progress || 0;
      setDbValidationProgress(job.step || "正在校验", `报告期 ${job.report_date || "-"}`, progress, job.status === "running");
      const logs = job.logs || [];
      logs.slice(lastLogCount).forEach((log) => {
        const msg = log.message || "";
        const type = msg.includes("失败") || msg.includes("错误") ? "error" : msg.includes("完成") ? "success" : "info";
        appendDbValidationLog(msg, type);
      });
      lastLogCount = logs.length;
      if (["completed", "failed"].includes(job.status)) {
        clearInterval(dbValidationPollTimer);
        dbValidationPollTimer = null;
        if (dbValidationStartBtn) dbValidationStartBtn.disabled = false;
        if (job.status === "completed") {
          setDbValidationProgress("校验完成", "可下载 Excel 结果文件", 100, false);
          renderDbValidationResult(job);
          showToast("数据库校验完成", "success");
        } else {
          setDbValidationProgress("校验失败", job.error || "请查看执行日志", 100, false);
          appendDbValidationLog(`校验失败: ${job.error || ""}`, "error");
          showToast("数据库校验失败: " + (job.error || "未知错误"), "error");
        }
      }
    } catch (e) {
      clearInterval(dbValidationPollTimer);
      dbValidationPollTimer = null;
      if (dbValidationStartBtn) dbValidationStartBtn.disabled = false;
      setDbValidationProgress("校验失败", e.message, 100, false);
      appendDbValidationLog("状态查询失败: " + e.message, "error");
    }
  };
  dbValidationPollTimer = setInterval(poll, 1000);
  await poll();
}

toolCardDbValidation?.addEventListener("click", openDbValidationModal);
dbValidationModalClose?.addEventListener("click", closeDbValidationModal);
dbValidationCloseBtn?.addEventListener("click", closeDbValidationModal);
dbValidationHistoryBtn?.addEventListener("click", openDbValidationHistory);
dbValidationHistoryClose?.addEventListener("click", closeDbValidationHistory);
dbValidationHistoryOverlay?.addEventListener("click", (e) => {
  if (e.target === dbValidationHistoryOverlay) closeDbValidationHistory();
});
dbValidationHistoryBody?.addEventListener("click", (e) => {
  const button = e.target.closest(".db-validation-history-download");
  if (!button) return;
  const url = button.dataset.url || "";
  if (url) window.location.href = url;
});
dbValidationStartBtn?.addEventListener("click", startDbValidation);
dbValidationDownloadBtn?.addEventListener("click", () => {
  if (dbValidationDownloadUrl) window.location.href = dbValidationDownloadUrl;
});
dbValidationRulesDocBtn?.addEventListener("click", () => {
  window.location.href = "/api/tools/db-validation/rules-document";
});
dbValidationSelectAllTablesBtn?.addEventListener("change", () => {
  const btn = dbValidationSelectAllTablesBtn;
  // When indeterminate, browser sets checked=false on click; force to the intended state
  if (btn.indeterminate) {
    btn.checked = true;
    btn.indeterminate = false;
  }
  const boxes = [...(dbValidationTableList?.querySelectorAll('input[type="checkbox"]') || [])];
  boxes.forEach((box) => { box.checked = btn.checked; });
});

// Update select-all checkbox state when individual table checkboxes change
dbValidationTableList?.addEventListener("change", (e) => {
  if (e.target.type === "checkbox" && dbValidationSelectAllTablesBtn) {
    const boxes = [...dbValidationTableList.querySelectorAll('input[type="checkbox"]')];
    const checkedCount = boxes.filter((b) => b.checked).length;
    const total = boxes.length;
    dbValidationSelectAllTablesBtn.checked = checkedCount === total;
    dbValidationSelectAllTablesBtn.indeterminate = checkedCount > 0 && checkedCount < total;
  }
});
saveDbValidationSettingsBtn?.addEventListener("click", saveDbValidationSettings);
dbValidationRefreshFieldMappingBtn?.addEventListener("click", refreshDbValidationFieldMapping);

/* ===== Tools: flow chain execution ===== */
function fillFlowSourceSelect(select, dataSources, selected = "") {
  if (!select) return;
  select.innerHTML = dataSources.map((item) => {
    const value = item.id || "";
    const label = item.name || value;
    return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
  }).join("");
  if (selected && [...select.options].some((option) => option.value === selected)) {
    select.value = selected;
  } else if (select.options.length) {
    select.value = select.options[0].value;
  }
}

function renderFlowSettingsLoadError(message = "流程链配置加载失败") {
  const text = message ? `流程链配置加载失败：${message}` : "流程链配置加载失败";
  flowSettings = { ...(flowSettings || {}), chains: [] };
  flowDataSources = [];
  selectedFlowChainIds = [];
  if (flowSource) flowSource.innerHTML = "";
  if (flowChainSettingsList) flowChainSettingsList.innerHTML = `<p class="placeholder-text">${escapeHtml(text)}</p>`;
  if (flowChainList) flowChainList.innerHTML = `<p class="placeholder-text">${escapeHtml(text)}</p>`;
  if (flowStartBtn) flowStartBtn.disabled = true;
  updateFlowChainSelectionSummary();
}

async function loadFlowSettings() {
  if (!flowSource && !toolCardFlow) return null;
  try {
    const payload = await api("/api/tools/flow/settings");
    flowSettings = payload.settings || {};
    flowDataSources = payload.data_sources || [];
    fillFlowSourceSelect(flowSource, flowDataSources, flowSettings.source_id || "");
    if (flowExecuteUrl) flowExecuteUrl.value = flowSettings.execute_url || "";
    if (flowFlowTable) flowFlowTable.value = flowSettings.flow_table || "sp_flow";
    if (flowTaskTable) flowTaskTable.value = flowSettings.task_table || "sp_task";
    if (flowPollInterval) flowPollInterval.value = flowSettings.poll_interval_seconds || 5;
    if (flowStepTimeout) flowStepTimeout.value = flowSettings.step_timeout_minutes || 60;
    flowDefinitions = [];
    flowDefinitionsLoaded = false;
    flowDefinitionSearchItems = [];
    renderFlowDefinitionLimitHint();
    renderFlowChainSettings(flowSettings.chains || []);
    renderFlowChainPicker();
    await loadFlowToastStatus();
    return flowSettings;
  } catch (e) {
    console.error("流程链配置加载失败", e);
    renderFlowSettingsLoadError(e.message || "请检查本地服务状态");
    return null;
  }
}

function flowStepsToText(steps = []) {
  return steps.map((step) => `${step.flow_id || ""}${step.name ? `|${step.name}` : ""}`).join("\n");
}

function flowStepsFromText(text = "") {
  return String(text || "").split(/\r?\n/).map((line) => {
    const trimmed = line.trim();
    if (!trimmed) return null;
    const [flowId, ...nameParts] = trimmed.split("|");
    const flow_id = (flowId || "").trim();
    if (!flow_id) return null;
    return { flow_id, name: nameParts.join("|").trim() };
  }).filter(Boolean);
}

function normalizeFlowStep(step = {}) {
  const flowId = String(step.flow_id || step.id || "").trim();
  if (!flowId) return null;
  return {
    flow_id: flowId,
    name: String(step.name || step.flow_name || "").trim(),
  };
}

function setFlowChainEditorSelectedSteps(steps = []) {
  flowChainEditorSelectedSteps = steps.map(normalizeFlowStep).filter(Boolean);
  renderFlowSelectedSteps();
  renderFlowDefinitionTable();
}

function renderFlowSelectedSteps() {
  if (!flowSelectedStepList) return;
  if (!flowChainEditorSelectedSteps.length) {
    flowSelectedStepList.innerHTML = '<p class="placeholder-text">尚未选择流程</p>';
    return;
  }
  flowSelectedStepList.innerHTML = flowChainEditorSelectedSteps.map((step, index) => `
    <div class="flow-selected-step" data-index="${index}">
      <span class="flow-step-index">${index + 1}</span>
      <span class="flow-selected-step-name" title="${escapeHtml(step.name || step.flow_id)}${step.flow_id && step.name ? ' (ID: ' + escapeHtml(step.flow_id) + ')' : ''}">${escapeHtml(step.name || step.flow_id)}</span>
      <div class="flow-selected-step-actions">
        <button type="button" class="btn-icon" data-action="move-step-up" title="上移" ${index === 0 ? "disabled" : ""}>↑</button>
        <button type="button" class="btn-icon" data-action="move-step-down" title="下移" ${index === flowChainEditorSelectedSteps.length - 1 ? "disabled" : ""}>↓</button>
        <button type="button" class="btn-icon" data-action="remove-selected-step" title="移除">×</button>
      </div>
    </div>
  `).join("");
}

async function loadFlowDefinitionsForEditor({ force = false } = {}) {
  if (!flowDefinitionTable) return;
  if (flowDefinitionsLoaded && !force) {
    renderFlowDefinitionTable();
    return;
  }
  flowDefinitionTable.innerHTML = '<p class="placeholder-text">正在加载流程表...</p>';
  try {
    const payload = await api("/api/tools/flow/definitions");
    flowDefinitions = (payload.flows || []).map(normalizeFlowStep).filter(Boolean);
    flowDefinitionsLoaded = true;
    renderFlowDefinitionLimitHint(payload);
    renderFlowDefinitionTable();
  } catch (e) {
    flowDefinitionsLoaded = false;
    flowDefinitions = [];
    renderFlowDefinitionLimitHint();
    flowDefinitionTable.innerHTML = `<p class="placeholder-text">${escapeHtml(e.message || "流程表加载失败")}</p>`;
  }
}

function renderFlowDefinitionLimitHint(payload = {}) {
  if (!flowDefinitionLimitHint) return;
  if (payload.truncated) {
    const limit = Number(payload.limit || 500);
    flowDefinitionLimitHint.hidden = false;
    flowDefinitionLimitHint.textContent = limit === 500
      ? "仅展示前 500 条，请搜索流程名称或 flow_id 添加更多流程。"
      : `仅展示前 ${limit} 条，请搜索流程名称或 flow_id 添加更多流程。`;
  } else {
    flowDefinitionLimitHint.hidden = true;
    flowDefinitionLimitHint.textContent = "";
  }
}

function _renderFlowDefinitionTable(flows) {
  if (!flowDefinitionTable) return;
  const selectedIds = new Set(flowChainEditorSelectedSteps.map((step) => step.flow_id));
  if (!flows.length) {
    flowDefinitionTable.innerHTML = '<p class="placeholder-text">未找到匹配流程</p>';
    return;
  }
  flowDefinitionTable.innerHTML = `
    <div class="flow-def-header">
      <th>流程名称</th>
      <th>操作</th>
    </div>
    <div class="flow-def-list">
      ${flows.map((flow) => {
        const selected = selectedIds.has(flow.flow_id);
        return `
          <div class="flow-def-row">
            <span class="flow-def-name">${escapeHtml(flow.name || "-")}</span>
            <div class="flow-def-action">
              <button type="button" class="btn-outline btn-sm" data-action="add-flow-definition" data-flow-id="${escapeHtml(flow.flow_id)}" data-flow-name="${escapeHtml(flow.name || "")}" ${selected ? "disabled" : ""}>${selected ? "已加入" : "加入"}</button>
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderFlowDefinitionTable() {
  if (!flowDefinitionTable) return;
  const keyword = (flowDefinitionSearch?.value || "").trim();

  if (!flowDefinitionsLoaded) {
    flowDefinitionTable.innerHTML = '<p class="placeholder-text">打开弹框后加载流程表</p>';
    return;
  }

  // 输入框为空：直接用缓存渲染
  if (!keyword) {
    _renderFlowDefinitionTable(flowDefinitions);
    return;
  }

  // 有搜索词：后端查询（防抖 300ms）
  clearTimeout(flowSearchTimer);
  flowDefinitionTable.innerHTML = '<p class="placeholder-text">搜索中...</p>';
  flowSearchTimer = setTimeout(async () => {
    try {
      const payload = await api(`/api/tools/flow/definitions?keyword=${encodeURIComponent(keyword)}`);
      const items = (payload.flows || []).map(normalizeFlowStep).filter(Boolean);
      renderFlowDefinitionLimitHint(payload);
      // 搜索结果并入 flowDefinitions，避免后续“加入”时找不到
      for (const item of items) {
        if (!flowDefinitions.some((f) => f.flow_id === item.flow_id)) {
          flowDefinitions.push(item);
        }
      }
      _renderFlowDefinitionTable(items);
    } catch (e) {
      renderFlowDefinitionLimitHint();
      flowDefinitionTable.innerHTML = `<p class="placeholder-text">${escapeHtml(e.message || "搜索失败")}</p>`;
    }
  }, 300);
}

function addFlowDefinitionToSelected(flowInput = {}) {
  const requestedFlow = normalizeFlowStep(flowInput);
  const flow = flowDefinitions.find((item) => item.flow_id === requestedFlow?.flow_id) || requestedFlow;
  if (!flow) {
    if (flowChainEditorStatus) flowChainEditorStatus.textContent = "未找到该流程，请刷新流程列表后重试";
    return;
  }
  if (flowChainEditorSelectedSteps.some((step) => step.flow_id === flow.flow_id)) return;
  setFlowChainEditorSelectedSteps([...flowChainEditorSelectedSteps, flow]);
}

function moveFlowChainEditorStep(index, direction) {
  const nextIndex = index + direction;
  if (index < 0 || nextIndex < 0 || index >= flowChainEditorSelectedSteps.length || nextIndex >= flowChainEditorSelectedSteps.length) return;
  const steps = [...flowChainEditorSelectedSteps];
  [steps[index], steps[nextIndex]] = [steps[nextIndex], steps[index]];
  setFlowChainEditorSelectedSteps(steps);
}

function removeFlowChainEditorStep(index) {
  if (index < 0 || index >= flowChainEditorSelectedSteps.length) return;
  const steps = [...flowChainEditorSelectedSteps];
  steps.splice(index, 1);
  setFlowChainEditorSelectedSteps(steps);
}

async function saveFlowSettings() {
  if (saveFlowSettingsBtn) saveFlowSettingsBtn.disabled = true;
  if (flowSettingsStatus) flowSettingsStatus.textContent = "保存中...";
  try {
    const settings = readFlowSettingsFromForm();
    const executeUrlError = validateFlowExecuteUrl(settings.execute_url);
    if (executeUrlError) throw new Error(executeUrlError);
    const payload = await api("/api/tools/flow/settings", {
      method: "POST",
      body: JSON.stringify(settings),
    });
    flowSettings = payload.settings || settings;
    flowDefinitions = [];
    flowDefinitionsLoaded = false;
    flowDefinitionSearchItems = [];
    renderFlowChainSettings(flowSettings.chains || []);
    renderFlowChainPicker();
    if (flowSettingsStatus) flowSettingsStatus.textContent = "已保存";
    showToast("流程链配置已保存", "success");
  } catch (e) {
    if (flowSettingsStatus) flowSettingsStatus.textContent = e.message;
    showToast("保存失败: " + e.message, "error");
  } finally {
    if (saveFlowSettingsBtn) saveFlowSettingsBtn.disabled = false;
  }
}

function validateFlowExecuteUrl(value = "") {
  const url = String(value || "").trim();
  if (!url) return "";
  let parsed;
  try {
    parsed = new URL(url);
  } catch (_) {
    return "流程执行接口必须是以 http:// 或 https:// 开头的完整地址";
  }
  if (!["http:", "https:"].includes(parsed.protocol) || !parsed.host) {
    return "流程执行接口必须是以 http:// 或 https:// 开头的完整地址";
  }
  if (parsed.searchParams.has("id")) {
    return "流程执行接口不要包含 id 参数，系统会在执行时自动追加当前流程 flow_id";
  }
  return "";
}

function renderFlowChainPicker() {
  if (!flowChainList) return;
  const chains = (flowSettings?.chains || []).filter((chain) => chain.enabled !== false);
  
  if (!chains.length) {
    flowChainList.innerHTML = '<p class="placeholder-text">暂无可执行流程链</p>';
    updateFlowChainSelectionSummary();
    return;
  }
  
  flowChainList.innerHTML = chains.map((chain) => `
    <div class="flow-chain-item" data-id="${escapeHtml(chain.id)}" onclick="toggleFlowChainSelection('${escapeHtml(chain.id)}')">
      <input type="checkbox" ${selectedFlowChainIds.includes(chain.id) ? "checked" : ""} onclick="event.stopPropagation(); toggleFlowChainSelection('${escapeHtml(chain.id)}')">
      <div class="flow-chain-item-info">
        <span class="flow-chain-item-name">${escapeHtml(chain.name || chain.id)}</span>
        <span class="flow-chain-item-meta">共 ${(chain.steps || []).length} 个流程</span>
      </div>
    </div>
  `).join("");
  
  updateFlowChainSelectionSummary();
}

function toggleFlowChainSelection(chainId) {
  const index = selectedFlowChainIds.indexOf(chainId);
  if (index > -1) {
    selectedFlowChainIds.splice(index, 1);
  } else {
    selectedFlowChainIds.push(chainId);
  }
  renderFlowChainPicker();
}

function updateFlowChainSelectionSummary() {
  if (!flowChainSelectionSummary) return;
  
  const summaryEl = flowChainSelectionSummary;
  const countEl = flowChainSelectedCount;
  
  if (!selectedFlowChainIds.length) {
    summaryEl.innerHTML = "<p>请选择要执行的流程链</p>";
    summaryEl.classList.remove("has-selection");
    if (countEl) countEl.textContent = "已选 0 个";
    return;
  }
  
  const chains = (flowSettings?.chains || []).filter((c) => selectedFlowChainIds.includes(c.id));
  // 按选择顺序排序
  const sortedChains = selectedFlowChainIds.map(id => chains.find(c => c.id === id)).filter(Boolean);
  const totalSteps = sortedChains.reduce((sum, c) => sum + (c.steps || []).length, 0);
  
  summaryEl.classList.add("has-selection");
  summaryEl.innerHTML = `
    <p><strong>已选 ${sortedChains.length} 个流程链，共 ${totalSteps} 个流程</strong></p>
    <div class="flow-chain-execution-order">
      ${sortedChains.map((chain, i) => `
        <div class="flow-chain-order-item">
          <span class="flow-chain-order-name">${escapeHtml(chain.name || chain.id)}</span>
        </div>
        ${i < sortedChains.length - 1 ? '<span class="flow-chain-order-arrow">→</span>' : ''}
      `).join("")}
    </div>
    <p style="margin-top: 8px; font-size: 11px; color: var(--on-surface-variant);">按以上顺序串行执行</p>
  `;
  if (countEl) countEl.textContent = `已选 ${sortedChains.length} 个`;
}

function flowStepStatusText(status = "") {
  return {
    pending: "待执行",
    submitted: "已提交",
    running: "执行中",
    completed: "已结束",
    failed: "失败",
    cancelled: "已取消",
  }[status] || status || "-";
}

function setFlowProgress(title, subtitle, progress = 0, spinning = true) {
  const safeProgress = Math.max(0, Math.min(100, Number(progress) || 0));
  if (flowProgressTitle) flowProgressTitle.textContent = title;
  if (flowProgressSubtitle) flowProgressSubtitle.textContent = subtitle;
  if (flowProgressFill) flowProgressFill.style.width = `${safeProgress}%`;
  if (flowProgressPercent) flowProgressPercent.textContent = formatFlowPercent(safeProgress);
  flowProgressIcon?.classList.toggle("pbc-progress-icon--spinning", Boolean(spinning));
}

function appendFlowLog(message, type = "") {
  if (!flowLog) return;
  const line = document.createElement("div");
  line.className = "pbc-log-entry" + (type ? ` pbc-log-entry--${type}` : "");
  line.textContent = `[${formatClockTime()}] ${message}`;
  flowLog.appendChild(line);
  flowLog.scrollTop = flowLog.scrollHeight;
}

async function openFlowModal() {
  flowModalOverlay?.classList.add("active");
  try {
    const statusPayload = await api("/api/flow-chain/status");
    const activeJob = statusPayload.job || null;
    if (activeJob && ["running", "pending", "cancelling"].includes(activeJob.status)) {
      showFlowModalProgressMode(activeJob);
      return;
    }
  } catch (_) {
    // Network or auth errors are handled elsewhere; continue to new execution mode.
  }
  if (flowLog) flowLog.innerHTML = '<div class="pbc-log-entry pbc-log-entry--info">准备开始执行...</div>';
  setFlowProgress("等待开始", "选择流程链后开始执行", 0, false);
  if (flowStatus) flowStatus.textContent = "";
  if (flowStartBtn) flowStartBtn.disabled = false;
  if (flowCancelBtn) flowCancelBtn.disabled = true;
  if (flowBgRunBtn) flowBgRunBtn.hidden = true;
  selectedFlowChainIds = [];
  isFlowExecuting = false;
  currentExecutingChainIndex = 0;
  await loadFlowSettings();
}

function showFlowModalProgressMode(job) {
  const chainName = job.chain_name || "";
  const executorName = job.executor_name || "";
  const isMyJob = !executorName || executorName === (authState.user?.display_name || authState.user?.username || "");
  const statusLabel = { running: "流程链执行中", pending: "等待执行", cancelling: "正在取消" }[job.status] || job.status;
  setFlowProgress(statusLabel, chainName, job.progress || 0, job.status === "running");
  if (flowStartBtn) flowStartBtn.disabled = true;
  if (flowCancelBtn) flowCancelBtn.disabled = job.status !== "running" || !isMyJob;
  if (flowBgRunBtn) flowBgRunBtn.hidden = !isMyJob || !["running", "pending"].includes(job.status);
  if (flowStatus) {
    if (isMyJob) {
      flowStatus.textContent = "流程在后台运行中，可点击「后台运行」关闭弹窗";
      flowStatus.dataset.type = "";
    } else {
      flowStatus.innerHTML = `<strong>${escapeHtml(executorName)}</strong> 正在执行，当前只读`;
      flowStatus.dataset.type = "other-executor";
    }
  }
  if (flowLog) {
    flowLog.innerHTML = "";
    (job.logs || []).forEach((log) => {
      const msg = log.message || "";
      const type = msg.includes("失败") ? "error" : msg.includes("完成") || msg.includes("结束") ? "success" : "info";
      appendFlowLog(msg, type);
    });
  }
  flowCurrentJobId = job.id || "";
  isFlowExecuting = true;
  startFlowModalBackgroundPoll(job.id);
}

function startFlowModalBackgroundPoll(jobId) {
  if (flowPollTimer) clearInterval(flowPollTimer);
  let lastLogCount = 0;
  const poll = async () => {
    try {
      const payload = await api(`/api/tools/flow/status/${encodeURIComponent(jobId)}`);
      const job = payload.job || {};
      const chainName = job.chain_name || "";
      const statusLabel = { running: "流程链执行中", pending: "等待执行", cancelling: "正在取消" }[job.status] || job.status;
      setFlowProgress(statusLabel, chainName, job.progress || 0, job.status === "running");
      const logs = job.logs || [];
      logs.slice(lastLogCount).forEach((log) => {
        const msg = log.message || "";
        appendFlowLog(msg, msg.includes("失败") ? "error" : msg.includes("完成") || msg.includes("结束") ? "success" : "info");
      });
      lastLogCount = logs.length;
      if (["completed", "failed", "cancelled"].includes(job.status)) {
        clearInterval(flowPollTimer);
        flowPollTimer = null;
        isFlowExecuting = false;
        if (flowStartBtn) flowStartBtn.disabled = false;
        if (flowCancelBtn) flowCancelBtn.disabled = true;
        if (flowBgRunBtn) flowBgRunBtn.hidden = true;
        const doneLabel = { completed: "执行完成", failed: "执行失败", cancelled: "已取消" }[job.status] || "执行结束";
        setFlowProgress(doneLabel, job.error || chainName, 100, false);
        if (flowStatus) flowStatus.textContent = job.status === "completed" ? "执行完成，可关闭弹窗" : job.error || "执行结束";
        handleFlowJobEnd(job);
      }
    } catch (e) {
      clearInterval(flowPollTimer);
      flowPollTimer = null;
      isFlowExecuting = false;
      if (flowStartBtn) flowStartBtn.disabled = false;
      if (flowCancelBtn) flowCancelBtn.disabled = true;
      if (flowBgRunBtn) flowBgRunBtn.hidden = true;
      setFlowProgress("状态查询失败", e.message, 100, false);
    }
  };
  flowPollTimer = setInterval(poll, 1500);
  poll();
}

function closeFlowModal() {
  flowModalOverlay?.classList.remove("active");
  if (!flowToastStarted && flowPollTimer) {
    clearInterval(flowPollTimer);
    flowPollTimer = null;
  }
  if (!isFlowExecuting) {
    currentExecutingChainIndex = 0;
  }
}

async function startFlowChain() {
  if (!selectedFlowChainIds.length) {
    showToast("请先选择要执行的流程链", "warning");
    return;
  }
  
  const chains = (flowSettings?.chains || []).filter((c) => selectedFlowChainIds.includes(c.id));
  if (!chains.length) {
    showToast("请先配置流程链", "warning");
    return;
  }
  
  isFlowExecuting = true;
  currentExecutingChainIndex = 0;
  flowChainExecutionResults = []; // 初始化执行结果收集数组
  if (flowStartBtn) flowStartBtn.disabled = true;
  if (flowCancelBtn) flowCancelBtn.disabled = false;
  if (flowBgRunBtn) flowBgRunBtn.hidden = true;
  if (flowLog) flowLog.innerHTML = "";
  if (flowStatus) flowStatus.textContent = "流程任务正在提交...";
  
  await executeNextFlowChain(chains);
}

async function executeNextFlowChain(allChains) {
  if (currentExecutingChainIndex >= allChains.length) {
    // 所有流程链执行完成
    isFlowExecuting = false;
    setFlowProgress("全部执行完成", `共完成 ${allChains.length} 个流程链`, 100, false);
    appendFlowLog("✅ 所有流程链执行完成", "success");
    showToast("所有流程链执行完成", "success");
    if (flowStartBtn) flowStartBtn.disabled = false;
    if (flowCancelBtn) flowCancelBtn.disabled = true;
    return;
  }
  
  const chain = allChains[currentExecutingChainIndex];
  flowCurrentChainInfo = chain;
  flowToastRunContext = {
    totalChains: allChains.length,
    currentChainIndex: currentExecutingChainIndex,
    currentChainName: chain.name || chain.id || "",
  };
  const totalSteps = allChains.reduce((sum, c) => sum + (c.steps || []).length, 0);
  const progressBase = (currentExecutingChainIndex / allChains.length) * 100;
  
  setFlowProgress(
    `执行中 (${currentExecutingChainIndex + 1}/${allChains.length})`, 
    chain.name || "", 
    progressBase, 
    true
  );
  appendFlowLog(`开始执行流程链 ${currentExecutingChainIndex + 1}/${allChains.length}：${chain.name || chain.id}`, "info");
  
  try {
    const payload = await api("/api/tools/flow/start", {
      method: "POST",
      body: JSON.stringify({ 
        chain_id: chain.id,
        is_multi_chain: allChains && allChains.length > 1,
      }),
    });
    flowCurrentJobId = payload.job_id || "";
    if (flowBgRunBtn) flowBgRunBtn.hidden = !flowCurrentJobId;
    if (flowStatus) flowStatus.textContent = "已提交，流程在后台运行中，可点击「后台运行」关闭弹窗";
    appendFlowLog(`流程任务已启动：${flowCurrentJobId}`, "info");
    await pollFlowChainJob(flowCurrentJobId, allChains);
  } catch (e) {
    setFlowProgress("启动失败", e.message, 100, false);
    appendFlowLog("启动失败: " + e.message, "error");
    showToast("流程执行失败: " + e.message, "error");
    isFlowExecuting = false;
    if (flowStartBtn) flowStartBtn.disabled = false;
    if (flowCancelBtn) flowCancelBtn.disabled = true;
    if (flowBgRunBtn) flowBgRunBtn.hidden = true;
  }
}

async function pollFlowChainJob(jobId, allChains = null) {
  if (flowPollTimer) clearInterval(flowPollTimer);
  let lastLogCount = 0;
  const poll = async () => {
    try {
      const payload = await api(`/api/tools/flow/status/${encodeURIComponent(jobId)}`);
      const job = payload.job || {};
      
      // 计算整体进度
      let overallProgress = job.progress || 0;
      if (allChains && allChains.length > 1) {
        const singleChainWeight = 100 / allChains.length;
        overallProgress = currentExecutingChainIndex * singleChainWeight + (job.progress || 0) * singleChainWeight / 100;
      }
      
      // 同步更新浮动提示条
      if (flowToastStarted && flowToastJob) {
        flowToastJob = { ...flowToastJob, ...job, progress: overallProgress };
        renderFlowToast();
      }

      const title = allChains && allChains.length > 1
        ? `执行中 (${currentExecutingChainIndex + 1}/${allChains.length}): ${job.step || "正在执行"}`
        : (job.step || "正在执行");
      
      setFlowProgress(title, job.chain_name || "", overallProgress, job.status === "running");
      
      const logs = job.logs || [];
      logs.slice(lastLogCount).forEach((log) => {
        const msg = log.message || "";
        appendFlowLog(msg, msg.includes("失败") ? "error" : msg.includes("完成") || msg.includes("结束") ? "success" : "info");
      });
      lastLogCount = logs.length;
      
      if (["completed", "failed", "cancelled"].includes(job.status)) {
        clearInterval(flowPollTimer);
        flowPollTimer = null;
        
        // 收集当前流程链执行结果
        flowChainExecutionResults.push({
          chain_name: job.chain_name || "",
          status: job.status,
          step_count: (job.steps || []).length,
          duration_seconds: calculateDurationSeconds(job.started_at, job.finished_at),
          error: job.error || "",
        });
        
        if (job.status === "completed") {
          appendFlowLog(`✅ 流程链执行完成：${job.chain_name || ""}`, "success");
          
          // 继续执行下一个流程链
          if (allChains && allChains.length > 1) {
            currentExecutingChainIndex++;
            
            // 如果所有流程链都执行完成，保存合并记录
            if (currentExecutingChainIndex >= allChains.length) {
              await saveMergedFlowChainHistory(allChains, job);
            } else {
              setTimeout(() => executeNextFlowChain(allChains), 3000);
              return;
            }
          }
        } else if (job.status === "failed") {
          appendFlowLog(`❌ 流程链执行失败：${job.error || ""}`, "error");
          isFlowExecuting = false;
        } else {
          appendFlowLog(`⏹️ 流程链已取消`, "info");
          isFlowExecuting = false;
        }
        
        if (flowStartBtn) flowStartBtn.disabled = false;
        if (flowCancelBtn) flowCancelBtn.disabled = true;
        if (flowBgRunBtn) flowBgRunBtn.hidden = true;
        setFlowProgress(job.status === "completed" ? "执行完成" : "执行结束", job.error || job.chain_name || "", overallProgress, false);
        handleFlowJobEnd({ ...job, progress: overallProgress });
        
        if (job.status === "completed" && (!allChains || allChains.length <= 1)) {
          showToast("流程执行完成", "success");
        }
      }
    } catch (e) {
      clearInterval(flowPollTimer);
      flowPollTimer = null;
      isFlowExecuting = false;
      if (flowStartBtn) flowStartBtn.disabled = false;
      if (flowCancelBtn) flowCancelBtn.disabled = true;
      if (flowBgRunBtn) flowBgRunBtn.hidden = true;
      setFlowProgress("状态查询失败", e.message, 100, false);
      appendFlowLog("状态查询失败: " + e.message, "error");
    }
  };
  flowPollTimer = setInterval(poll, 1000);
  await poll();
}

function calculateDurationSeconds(startStr, endStr) {
  if (!startStr || !endStr) return 0;
  try {
    const start = new Date(startStr.replace(" ", "T"));
    const end = new Date(endStr.replace(" ", "T"));
    const diff = Math.floor((end - start) / 1000);
    return Math.max(0, diff);
  } catch (e) {
    return 0;
  }
}

async function saveMergedFlowChainHistory(allChains, lastJob) {
  try {
    const startedAt = flowChainExecutionResults[0]?.started_at || lastJob.started_at || "";
    const finishedAt = lastJob.finished_at || "";
    
    await api("/api/tools/flow/save-merged-history", {
      method: "POST",
      body: JSON.stringify({
        id: lastJob.id,
        started_at: startedAt,
        finished_at: finishedAt,
        chain_details: flowChainExecutionResults,
      }),
    });
    
    appendFlowLog("✅ 多流程链合并记录已保存", "success");
  } catch (e) {
    appendFlowLog("保存合并记录失败: " + e.message, "error");
  } finally {
    flowChainExecutionResults = [];
  }
}

async function cancelFlowChain() {
  if (!flowCurrentJobId) return;
  if (flowCancelBtn?.disabled) return;
  if (flowCancelBtn) flowCancelBtn.disabled = true;
  const currentProgress = parseFloat(flowProgressFill?.style.width || "0") || 0;
  setFlowProgress("停止中", flowCurrentChainInfo?.name || "", currentProgress, true);
  try {
    await api("/api/tools/flow/cancel", {
      method: "POST",
      body: JSON.stringify({ job_id: flowCurrentJobId }),
    });
    appendFlowLog("已发送停止请求", "info");
  } catch (e) {
    if (isFlowExecuting && flowCancelBtn) flowCancelBtn.disabled = false;
    showToast("停止失败: " + e.message, "error");
  }
}

async function openFlowHistory() {
  flowHistoryOverlay?.classList.add("active");
  await loadFlowHistory();
}

function closeFlowHistory() {
  flowHistoryOverlay?.classList.remove("active");
}

async function loadFlowHistory() {
  if (!flowHistoryBody) return;
  flowHistoryBody.innerHTML = '<tr><td colspan="7" class="empty">正在加载...</td></tr>';
  try {
    const payload = await api("/api/tools/flow/history");
    renderFlowHistory(payload.history || []);
  } catch (e) {
    flowHistoryBody.innerHTML = `<tr><td colspan="7" class="empty">${escapeHtml(e.message)}</td></tr>`;
  }
}

function formatFlowDuration(seconds) {
  if (!seconds || seconds <= 0) return "-";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins === 0) return `${secs}秒`;
  return `${mins}分${secs}秒`;
}

function formatFlowChainName(run) {
  if (run.is_multi_chain) {
    const count = run.chain_names?.length || 0;
    return `多流程链(${count}条)`;
  }
  return run.chain_name || "-";
}

function renderFlowHistory(history = []) {
  if (!flowHistoryBody) return;
  if (!history.length) {
    flowHistoryBody.innerHTML = '<tr><td colspan="7" class="empty">暂无执行记录</td></tr>';
    return;
  }
  flowHistoryBody.innerHTML = history.map((run) => `
    <tr>
      <td>${escapeHtml((run.run_at || "").replace("T", " ") || "-")}</td>
      <td title="${escapeHtml(run.is_multi_chain ? (run.chain_names || []).join(" → ") : run.chain_name || "")}">${escapeHtml(formatFlowChainName(run))}</td>
      <td>${escapeHtml(run.executor_name || flowTriggerText(run.trigger_type || ""))}</td>
      <td>${escapeHtml(flowJobStatusText(run.status || ""))}</td>
      <td class="money-cell">${formatMoney(run.step_count || (run.steps || []).length || 0)}</td>
      <td>${escapeHtml(formatFlowDuration(run.duration_seconds))}</td>
      <td>${escapeHtml((run.finished_at || "").replace("T", " ") || "-")}</td>
    </tr>
  `).join("");
}

function flowTriggerText(trigger = "") {
  return "手工执行";
}

function flowJobStatusText(status = "") {
  return {
    pending: "待执行",
    running: "执行中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
  }[status] || status || "-";
}

function renderFlowChainSettings(chains = []) {
  if (!flowChainSettingsList) return;
  const safeChains = chains || [];
  if (flowSettings) flowSettings.chains = safeChains;
  if (!safeChains.length) {
    flowChainSettingsList.innerHTML = '<p class="placeholder-text">暂无流程链配置</p>';
    return;
  }
  flowChainSettingsList.innerHTML = safeChains.map((chain, index) => {
    return `
      <div class="flow-chain-config" data-index="${index}">
        <div class="flow-chain-summary-main">
          <strong>${escapeHtml(chain.name || `流程链${index + 1}`)}</strong>
        </div>
        <div class="flow-chain-config-actions">
          <button type="button" class="btn-outline btn-sm" data-action="edit-chain">编辑</button>
          <button type="button" class="btn-outline btn-sm flow-chain-remove" data-action="remove-chain">删除</button>
        </div>
      </div>
    `;
  }).join("");
}

function readFlowSettingsFromForm() {
  return {
    source_id: flowSource?.value || "",
    execute_url: (flowExecuteUrl?.value || "").trim(),
    flow_table: (flowFlowTable?.value || "").trim() || "sp_flow",
    task_table: (flowTaskTable?.value || "").trim() || "sp_task",
    poll_interval_seconds: Number(flowPollInterval?.value || 5),
    step_timeout_minutes: Number(flowStepTimeout?.value || 60),
    chains: flowSettings?.chains || [],
  };
}

function addFlowChainConfig() {
  openFlowChainEditor(-1);
}

function openFlowChainEditor(index = -1) {
  const chains = flowSettings?.chains || [];
  const chain = index >= 0 ? chains[index] : {
    id: `chain-${Date.now()}`,
    name: `流程链${chains.length + 1}`,
    enabled: true,
    steps: [],
  };
  if (!chain) return;
  flowEditingChainIndex = index;
  if (flowChainEditorTitle) flowChainEditorTitle.textContent = index >= 0 ? "编辑流程链" : "新增流程链";
  if (flowChainEditorName) flowChainEditorName.value = chain.name || "";
  if (flowChainEditorEnabled) flowChainEditorEnabled.checked = chain.enabled !== false;
  if (flowDefinitionSearch) flowDefinitionSearch.value = "";
  setFlowChainEditorSelectedSteps(chain.steps || []);
  if (flowChainEditorStatus) flowChainEditorStatus.textContent = "";
  flowChainEditorOverlay?.classList.add("active");
  document.body.style.overflow = "hidden";
  loadFlowDefinitionsForEditor();
}

function closeFlowChainEditor() {
  flowChainEditorOverlay?.classList.remove("active");
  document.body.style.overflow = "";
  flowEditingChainIndex = -1;
}

function setFlowChainEditorStatus(message, type = "info") {
  if (flowChainEditorStatus) {
    flowChainEditorStatus.textContent = message || "";
    flowChainEditorStatus.dataset.type = type;
  }
}

function saveFlowChainFromEditor() {
  const chains = [...(flowSettings?.chains || [])];
  const existing = flowEditingChainIndex >= 0 ? chains[flowEditingChainIndex] : {};
  const name = (flowChainEditorName?.value || "").trim();
  const steps = flowChainEditorSelectedSteps.map(normalizeFlowStep).filter(Boolean);
  if (!name) {
    setFlowChainEditorStatus("请填写链路名称", "error");
    showToast("请填写链路名称", "warning");
    return;
  }
  if (!steps.length) {
    setFlowChainEditorStatus("请至少配置一个流程", "error");
    showToast("请至少配置一个流程", "warning");
    return;
  }
  const nextChain = {
    id: existing.id || `chain-${Date.now()}`,
    name,
    enabled: !!flowChainEditorEnabled?.checked,
    steps,
  };
  if (flowEditingChainIndex >= 0) {
    chains[flowEditingChainIndex] = nextChain;
  } else {
    chains.push(nextChain);
  }
  flowSettings = { ...(flowSettings || {}), chains };
  renderFlowChainSettings(chains);
  renderFlowChainPicker();
  if (flowSettingsStatus) flowSettingsStatus.textContent = "链路已更新，点击保存配置后生效";
  showToast("流程链已加入列表，请点击保存配置生效", "success");
  closeFlowChainEditor();
}

toolCardFlow?.addEventListener("click", openFlowModal);
flowModalClose?.addEventListener("click", closeFlowModal);
flowStartBtn?.addEventListener("click", startFlowChain);
flowCancelBtn?.addEventListener("click", cancelFlowChain);
flowBgRunBtn?.addEventListener("click", () => {
  if (!flowCurrentJobId || !flowCurrentChainInfo) {
    showToast("流程任务正在提交，请稍后再切到后台运行", "info");
    return;
  }
  if (flowCurrentJobId && flowCurrentChainInfo) {
    flowToastStarted = true;
    flowToastRunContext = {
      totalChains: Math.max(1, selectedFlowChainIds.length || 1),
      currentChainIndex: currentExecutingChainIndex,
      currentChainName: flowCurrentChainInfo.name || flowCurrentChainInfo.id || "",
    };
    flowToastJob = {
      id: flowCurrentJobId,
      chain_id: flowCurrentChainInfo.id,
      chain_name: flowCurrentChainInfo.name,
      status: "running",
      progress: 0,
      step: "正在执行",
      steps: (flowCurrentChainInfo.steps || []).map((s) => ({ flow_id: s.flow_id, flow_name: s.name || s.flow_id, status: "pending" })),
      logs: [],
      error: "",
    };
    flowToastSeenJobId = flowCurrentJobId;
    flowToastDismissed = false;
    if (flowToastAutoCloseTimer) { clearTimeout(flowToastAutoCloseTimer); flowToastAutoCloseTimer = null; }
    renderFlowToast();
    startFlowToastPollIfNeeded();
  }
  closeFlowModal();
});
flowHistoryBtn?.addEventListener("click", openFlowHistory);
flowHistoryClose?.addEventListener("click", closeFlowHistory);
flowHistoryOverlay?.addEventListener("click", (e) => {
  if (e.target === flowHistoryOverlay) closeFlowHistory();
});
addFlowChainBtn?.addEventListener("click", addFlowChainConfig);
saveFlowSettingsBtn?.addEventListener("click", saveFlowSettings);
flowChainSettingsList?.addEventListener("click", (e) => {
  const editButton = e.target.closest("[data-action='edit-chain']");
  if (editButton) {
    const card = editButton.closest(".flow-chain-config");
    openFlowChainEditor(Number(card?.dataset.index || "-1"));
    return;
  }
  const button = e.target.closest("[data-action='remove-chain']");
  if (!button) return;
  const card = button.closest(".flow-chain-config");
  const index = Number(card?.dataset.index || "-1");
  const chains = [...(flowSettings?.chains || [])];
  chains.splice(index, 1);
  flowSettings = { ...(flowSettings || {}), chains };
  renderFlowChainSettings(chains);
  renderFlowChainPicker();
});
flowChainEditorClose?.addEventListener("click", closeFlowChainEditor);
flowChainEditorCancel?.addEventListener("click", closeFlowChainEditor);
flowChainEditorSave?.addEventListener("click", saveFlowChainFromEditor);
flowDefinitionRefreshBtn?.addEventListener("click", () => loadFlowDefinitionsForEditor({ force: true }));
flowDefinitionSearch?.addEventListener("input", renderFlowDefinitionTable);
addManualFlowBtn?.addEventListener("click", () => {
  const flowId = String(flowManualFlowId?.value || "").trim();
  if (!flowId) {
    if (flowChainEditorStatus) flowChainEditorStatus.textContent = "请输入 flow_id";
    return;
  }
  addFlowDefinitionToSelected({ flow_id: flowId });
  if (flowManualFlowId) flowManualFlowId.value = "";
});
flowManualFlowId?.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  addManualFlowBtn?.click();
});
flowDefinitionTable?.addEventListener("click", (e) => {
  const button = e.target.closest("[data-action='add-flow-definition']");
  if (!button) return;
  addFlowDefinitionToSelected({
    flow_id: button.dataset.flowId || "",
    name: button.dataset.flowName || "",
  });
});
flowSelectedStepList?.addEventListener("click", (e) => {
  const button = e.target.closest("[data-action]");
  if (!button) return;
  const row = button.closest(".flow-selected-step");
  const index = Number(row?.dataset.index || "-1");
  if (button.dataset.action === "move-step-up") {
    moveFlowChainEditorStep(index, -1);
  } else if (button.dataset.action === "move-step-down") {
    moveFlowChainEditorStep(index, 1);
  } else if (button.dataset.action === "remove-selected-step") {
    removeFlowChainEditorStep(index);
  }
});

/* ===== 流程后台执行浮动提示条 ===== */
const flowToastContainer = document.getElementById("flowToastContainer");
let flowToastJob = null;
let flowToastSeenJobId = "";
let flowToastDismissed = false;
let flowToastPollTimer = null;
let flowToastAutoCloseTimer = null;
let flowToastStarted = false;
let flowToastRunContext = { totalChains: 1, currentChainIndex: 0, currentChainName: "" };

function flowToastThemeClass() {
  return document.documentElement.getAttribute("data-theme") === "space-tech" ? "flow-toast--vitality" : "flow-toast--calm";
}

function flowToastStatusText(status = "") {
  return {
    pending: "等待执行",
    running: "执行中",
    completed: "执行完成",
    failed: "执行失败",
    cancelled: "已取消",
  }[status] || status || "";
}

function flowToastIcon(status = "") {
  return {completed: "✓", failed: "✗", cancelled: "⏹"}[status] || "⚙";
}

function formatFlowPercent(value) {
  const percent = Math.max(0, Math.min(100, Number(value) || 0));
  return `${percent.toFixed(2)}%`;
}

function flowToastIsMultiChain() {
  return Number(flowToastRunContext.totalChains || 1) > 1;
}

function flowToastChainPosition() {
  const total = Math.max(1, Number(flowToastRunContext.totalChains || 1));
  const current = Math.min(Math.max(1, Number(flowToastRunContext.currentChainIndex || 0) + 1), total);
  return `${current}/${total}`;
}

function flowToastTitle(job = {}) {
  const statusText = flowToastStatusText(job.status);
  if (flowToastIsMultiChain()) return `多流程链${statusText}：${flowToastChainPosition()}`;
  return `${job.chain_name || flowToastRunContext.currentChainName || "流程链"} - ${statusText}`;
}

function flowToastSub(job = {}) {
  if (!job || !job.status) return "";
  const currentStep = job.step || "正在执行";
  if (flowToastIsMultiChain()) {
    const chainName = job.chain_name || flowToastRunContext.currentChainName || "-";
    if (job.status === "failed") return `失败链：${chainName} ｜ 原因：${job.error || currentStep} · 1分钟后自动关闭`;
    if (job.status === "completed") return `当前链：${chainName} ｜ 全部完成 · 1分钟后自动关闭`;
    return `当前链：${chainName} ｜ 当前流程：${currentStep}`;
  }
  if (job.status === "running") return `当前流程：${currentStep}`;
  if (job.status === "completed") return "执行完成 · 1分钟后自动关闭";
  if (job.status === "failed") return (job.error || "执行失败") + " · 1分钟后自动关闭";
  return job.error || job.step || "";
}

function flowToastProgressPercent(job = {}) {
  return formatFlowPercent(job.progress);
}

function flowToastCurrentStep(job = {}) {
  const steps = job.steps || [];
  if (!steps.length) return "";
  const completed = steps.filter((step) => ["completed", "failed", "cancelled"].includes(step.status)).length;
  const current = job.status === "completed" ? steps.length : Math.min(completed + 1, steps.length);
  return `${current}/${steps.length}`;
}

async function loadFlowToastStatus() {
  try {
    const payload = await api("/api/flow-chain/status");
    const job = payload.job || null;
    if (flowToastStarted && job) {
      if (flowToastSeenJobId !== job.id) {
        flowToastSeenJobId = job.id;
        flowToastDismissed = false;
      }
      flowToastJob = job;
      renderFlowToast();
      startFlowToastPollIfNeeded();
    } else if (!job) {
      stopFlowToastPoll();
    }
  } catch (_) {
    // Network error: keep existing toast state, don't clear
    stopFlowToastPoll();
  }
}

function startFlowToastPollIfNeeded() {
  if (!flowToastJob || flowToastJob.status !== "running") {
    stopFlowToastPoll();
    return;
  }
  if (flowToastAutoCloseTimer) { clearTimeout(flowToastAutoCloseTimer); flowToastAutoCloseTimer = null; }
  if (flowToastPollTimer) return;
  flowToastPollTimer = setInterval(loadFlowToastStatus, 1000);
}

function stopFlowToastPoll() {
  if (!flowToastPollTimer) return;
  clearInterval(flowToastPollTimer);
  flowToastPollTimer = null;
}

function handleFlowJobEnd(job = {}) {
  stopFlowToastPoll();
  if (!flowToastStarted && !flowToastJob) return;
  flowToastJob = job || null;
  flowToastSeenJobId = job?.id || flowToastSeenJobId;
  flowToastStarted = false;
  renderFlowToast();
  if (flowToastAutoCloseTimer) clearTimeout(flowToastAutoCloseTimer);
  flowToastAutoCloseTimer = setTimeout(() => {
    flowToastDismissed = true;
    flowToastContainer.innerHTML = "";
    flowToastAutoCloseTimer = null;
  }, 60000);
}

function renderFlowToast() {
  if (!flowToastContainer) return;
  const job = flowToastJob;
  if (!job || flowToastDismissed) {
    flowToastContainer.innerHTML = "";
    return;
  }
  const theme = flowToastThemeClass();
  const logs = (job.logs || []).slice(-50);
  const expanded = flowToastContainer.dataset.expanded === "true";
  flowToastContainer.innerHTML = `
    <div class="flow-toast ${theme} ${job.status}${expanded ? " expanded" : ""}">
      <div class="flow-toast-header">
        <div class="flow-toast-icon">${flowToastIcon(job.status)}</div>
        <div class="flow-toast-info">
          <div class="flow-toast-title">${escapeHtml(flowToastTitle(job))}</div>
          <div class="flow-toast-sub">${escapeHtml(flowToastSub(job))}</div>
        </div>
        <div class="flow-toast-step">${escapeHtml(flowToastCurrentStep(job))}</div>
        <div class="flow-toast-actions">
          <button type="button" class="flow-toast-action" data-action="toggle-flow-toast">${expanded ? "收起" : "展开"}</button>
          ${job.status !== "running" ? '<button type="button" class="flow-toast-close" data-action="close-flow-toast" title="关闭">&times;</button>' : ""}
        </div>
      </div>
      <div class="flow-toast-progress-track">
        <div class="flow-toast-progress-fill" style="width:${flowToastProgressPercent(job)}"></div>
      </div>
      <div class="flow-toast-logs">
        <ul class="flow-toast-log-list">
          ${logs.map((item) => `<li class="flow-toast-log-item"><span class="flow-toast-log-time">${escapeHtml(item.time || "")}</span><span class="flow-toast-log-msg">${escapeHtml(item.message || "")}</span></li>`).join("")}
        </ul>
      </div>
    </div>
  `;
  const logList = flowToastContainer.querySelector(".flow-toast-log-list");
  if (logList) logList.scrollTop = logList.scrollHeight;
}

flowToastContainer?.addEventListener("click", (event) => {
  const toggleButton = event.target.closest("[data-action='toggle-flow-toast']");
  if (toggleButton) {
    const toast = toggleButton.closest(".flow-toast");
    if (!toast) return;
    toast.classList.toggle("expanded");
    const isExpanded = toast.classList.contains("expanded");
    toggleButton.textContent = isExpanded ? "收起" : "展开";
    flowToastContainer.dataset.expanded = isExpanded ? "true" : "false";
    return;
  }
  const closeButton = event.target.closest("[data-action='close-flow-toast']");
  if (closeButton) {
    flowToastDismissed = true;
    flowToastContainer.dataset.expanded = "false";
    flowToastContainer.innerHTML = "";
  }
});

/* ===== Modal open / close ===== */
function openPbcModal() {
  resetPbcModal();
  pbcModalOverlay.classList.add("active");
  loadPbcImportSettings();
}

function closePbcModal() {
  pbcModalOverlay.classList.remove("active");
  if (pbcPollTimer) { clearInterval(pbcPollTimer); pbcPollTimer = null; }
}

function resetPbcModal() {
  pbcCurrentStep = 1;
  pbcUploadedFiles = [];
  pbcColumns = [];
  pbcFiles = [];
  pbcUploadId = "";
  pbcMappings = [];
  pbcTableColumns = [];
  updatePbcStepUI();
  if (pbcZipFile) pbcZipFile.value = "";
  if (pbcFileList) pbcFileList.hidden = true;
  if (pbcFileListBody) pbcFileListBody.innerHTML = "";
  if (pbcMappingList) pbcMappingList.innerHTML = '<p class="placeholder-text">读取目标列后显示映射关系</p>';
  if (pbcMappingCount) pbcMappingCount.textContent = "";
  renderPbcColumnNotice();
  if (pbcProgressFill) pbcProgressFill.style.width = "0%";
  if (pbcProgressPercent) pbcProgressPercent.textContent = "0%";
  if (pbcImportLog) pbcImportLog.innerHTML = '<div class="pbc-log-entry pbc-log-entry--info">准备开始导入...</div>';
  setPbcImportProgressState("正在导入中", "请勿关闭页面，数据正在写入数据库", true);
  pbcImportConflictState = false;
  pbcImportFailed = false;
  if (pbcRetryBtn) pbcRetryBtn.hidden = true;
  if (pbcCompleteStats) pbcCompleteStats.innerHTML = "";
  if (pbcCompleteDesc) pbcCompleteDesc.textContent = "数据已成功导入到目标数据库";
  if (pbcImportMode) pbcImportMode.value = "replace";
  setPbcUploadState(false);
  updatePbcUploadSummary();
}

toolCardPbc?.addEventListener("click", openPbcModal);
pbcModalClose?.addEventListener("click", closePbcModal);

/* ===== Step navigation ===== */
function updatePbcStepUI() {
  // Update step indicators
  pbcStepsContainer.querySelectorAll(".pbc-step").forEach((el) => {
    const s = Number(el.dataset.step);
    const isDone = s < pbcCurrentStep || (pbcCurrentStep === 4 && s === 4);
    el.classList.toggle("pbc-step--active", s === pbcCurrentStep);
    el.classList.toggle("pbc-step--done", isDone);
  });
  // Update connectors
  pbcStepsContainer.querySelectorAll(".pbc-step-connector").forEach((el, idx) => {
    el.classList.toggle("active", idx < pbcCurrentStep - 1);
  });
  // Show/hide step content
  for (let i = 1; i <= 4; i++) {
    const el = document.getElementById("pbcStep" + i);
    if (el) el.classList.toggle("pbc-step-content--active", i === pbcCurrentStep);
  }
  // Footer buttons
  pbcPrevBtn.hidden = pbcCurrentStep <= 1 || (pbcCurrentStep === 3 && !pbcImportFailed) || pbcCurrentStep === 4;
  pbcNextBtn.hidden = pbcCurrentStep === 3 || pbcCurrentStep === 4;
  if (pbcRetryBtn) pbcRetryBtn.hidden = !(pbcCurrentStep === 3 && pbcImportConflictState);
  pbcNextBtn.disabled =
    (pbcCurrentStep === 1 && pbcUploadedFiles.length === 0) ||
    (pbcCurrentStep === 2 && !hasPbcActiveMappings());
  pbcFinishBtn.hidden = pbcCurrentStep !== 4;

  if (pbcCurrentStep === 2) {
    pbcNextBtn.textContent = "下一步";
    pbcNextBtn.hidden = false;
  } else if (pbcCurrentStep === 3) {
    pbcNextBtn.hidden = true;
  }
  updatePbcUploadSummary();
}

function goToStep(step) {
  if (step === 2 && pbcUploadedFiles.length === 0) return;
  if (step === 3 && !hasPbcActiveMappings()) return;
  pbcCurrentStep = step;
  updatePbcStepUI();
  if (step === 3) startImportFlow();
}

pbcPrevBtn?.addEventListener("click", () => {
  if (pbcCurrentStep > 1) goToStep(pbcCurrentStep - 1);
});

pbcNextBtn?.addEventListener("click", async () => {
  if (pbcNextBtn.disabled) return;
  if (pbcCurrentStep === 1) goToStep(2);
  else if (pbcCurrentStep === 2) {
    const confirmed = await showConfirm("确认导入", "即将开始数据导入，是否确认？");
    if (!confirmed) return;
    goToStep(3);
  }
});

pbcFinishBtn?.addEventListener("click", closePbcModal);
pbcRetryBtn?.addEventListener("click", () => {
  if (pbcRetryBtn.disabled) return;
  pbcRetryBtn.hidden = true;
  pbcImportConflictState = false;
  startImportFlow();
});

/* ===== Step 1: File upload ===== */
pbcUploadArea?.addEventListener("click", () => pbcZipFile?.click());

pbcUploadArea?.addEventListener("dragover", (e) => { e.preventDefault(); pbcUploadArea.classList.add("drag-over"); });
pbcUploadArea?.addEventListener("dragleave", () => pbcUploadArea.classList.remove("drag-over"));
pbcUploadArea?.addEventListener("drop", async (e) => {
  e.preventDefault();
  pbcUploadArea.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) await handlePbcFileUpload(file);
});

pbcZipFile?.addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (file) await handlePbcFileUpload(file);
});

function setPbcUploadState(uploading, percent = 0, filename = "") {
  if (pbcUploadArea) pbcUploadArea.classList.toggle("uploading", Boolean(uploading));
  if (pbcZipFile) pbcZipFile.disabled = Boolean(uploading);
  if (pbcUploadProgress) pbcUploadProgress.hidden = !uploading;
  const safePercent = Math.max(0, Math.min(100, Math.round(percent || 0)));
  if (pbcUploadProgressFill) pbcUploadProgressFill.style.width = `${safePercent}%`;
  if (pbcUploadProgressPercent) pbcUploadProgressPercent.textContent = `${safePercent}%`;
  if (pbcUploadProgressText) pbcUploadProgressText.textContent = uploading ? `正在上传 ${filename || "文件"}...` : "正在上传...";
}

function uploadPbcFileWithProgress(file, form) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/tools/pbc-import/upload");
    if (authState.csrfToken) xhr.setRequestHeader("X-CSRF-Token", authState.csrfToken);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        setPbcUploadState(true, (event.loaded / event.total) * 100, file.name);
      } else {
        setPbcUploadState(true, 12, file.name);
      }
    };
    xhr.onload = () => {
      let payload = {};
      try {
        payload = JSON.parse(xhr.responseText || "{}");
      } catch (_) {
        reject(new Error("upload response is invalid"));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(payload.error || `upload failed: ${xhr.status}`));
        return;
      }
      resolve(payload);
    };
    xhr.onerror = () => reject(new Error("upload network error"));
    xhr.onabort = () => reject(new Error("upload aborted"));
    setPbcUploadState(true, 0, file.name);
    xhr.send(form);
  });
}

async function handlePbcFileUpload(file) {
  const form = new FormData();
  form.append("file", file);
  try {
    const payload = await uploadPbcFileWithProgress(file, form);
    const uploadId = payload.upload_id || "";
    const columns = payload.columns || [];
    const files = payload.files || [];
    pbcUploadedFiles.push({ name: file.name, columns, upload_id: uploadId, files });
    syncPbcUploadAggregate();
    pbcMappings = [];
    pbcTableColumns = [];
    renderPbcFileList();
    renderPbcColumnNotice();
    updatePbcStepUI();
  } catch (e) {
    showToast("文件上传失败: " + e.message, "error");
  } finally {
    setPbcUploadState(false);
    if (pbcZipFile) pbcZipFile.value = "";
  }
}

function renderPbcFileList() {
  if (!pbcFileList || !pbcFileListBody) return;
  if (pbcUploadedFiles.length === 0) {
    pbcFileList.hidden = true;
    pbcFileListBody.innerHTML = "";
    return;
  }
  pbcFileList.hidden = false;
  const rows = [];
  pbcUploadedFiles.forEach((upload, idx) => {
    const files = upload.files?.length ? upload.files : [{ name: upload.name, columns: upload.columns || [] }];
    files.forEach((file) => {
      rows.push(`
        <div class="pbc-file-list-row">
          <span class="pbc-file-name">${escapeHtml(file.name || upload.name)}</span>
          <span class="pbc-file-cols">${(file.columns || []).length} 列</span>
          <span><button class="pbc-file-remove-btn" data-idx="${idx}">&times;</button></span>
        </div>
      `);
    });
  });
  pbcFileListBody.innerHTML = rows.join("");
}

function syncPbcUploadAggregate() {
  // Multiple uploads share one mapping surface, so import columns use the union while rows keep their source file metadata.
  const seenColumns = new Set();
  const columns = [];
  const files = [];
  pbcUploadedFiles.forEach((upload) => {
    (upload.columns || []).forEach((column) => {
      if (!seenColumns.has(column)) {
        seenColumns.add(column);
        columns.push(column);
      }
    });
    const uploadFiles = upload.files?.length ? upload.files : [{ name: upload.name, columns: upload.columns || [] }];
    uploadFiles.forEach((file) => files.push(file));
  });
  const latest = pbcUploadedFiles[pbcUploadedFiles.length - 1];
  pbcUploadId = latest?.upload_id || "";
  pbcColumns = columns;
  pbcFiles = files;
  updatePbcUploadSummary();
}

function getPbcUploadIds() {
  return pbcUploadedFiles.map((upload) => upload.upload_id).filter(Boolean);
}

function updatePbcUploadSummary() {
  if (!pbcUploadSummary) return;
  const fileCount = pbcFiles.length || pbcUploadedFiles.length;
  pbcUploadSummary.textContent = `共 ${fileCount} 个文件`;
  pbcUploadSummary.hidden = !(pbcCurrentStep === 1 && fileCount > 0);
  if (pbcClearFilesBtn) {
    pbcClearFilesBtn.hidden = pbcCurrentStep !== 1;
    pbcClearFilesBtn.disabled = fileCount === 0;
  }
}

function clearPbcUploadedFiles() {
  pbcUploadedFiles = [];
  syncPbcUploadAggregate();
  pbcMappings = [];
  pbcTableColumns = [];
  renderPbcMappings();
  renderPbcFileList();
  renderPbcColumnNotice();
  updatePbcStepUI();
  if (pbcZipFile) pbcZipFile.value = "";
}

pbcClearFilesBtn?.addEventListener("click", () => {
  if (pbcClearFilesBtn.disabled) return;
  clearPbcUploadedFiles();
});

pbcFileListBody?.addEventListener("click", (e) => {
  const btn = e.target.closest(".pbc-file-remove-btn");
  if (!btn) return;
  const idx = Number(btn.dataset.idx);
  pbcUploadedFiles.splice(idx, 1);
  syncPbcUploadAggregate();
  pbcMappings = [];
  pbcTableColumns = [];
  renderPbcMappings();
  renderPbcFileList();
  renderPbcColumnNotice();
  updatePbcStepUI();
});

/* ===== Step 2: Mapping ===== */
function hasPbcActiveMappings() {
  return pbcMappings.some((mapping) => mapping.source_column && mapping.target_column);
}

function hidePbcColumnNotice() {
  if (!pbcColumnNotice) return;
  pbcColumnNotice.hidden = true;
  pbcColumnNotice.innerHTML = "";
  pbcColumnNotice.title = "";
}

function renderPbcColumnNotice() {
  if (!pbcColumnNotice) return;
  const files = pbcFiles || [];
  if (files.length <= 1 || !pbcColumns.length) {
    hidePbcColumnNotice();
    return;
  }
  const missingByFile = files.map((file) => {
    const fileColumns = new Set(file.columns || []);
    return {
      name: file.name || "",
      missing: pbcColumns.filter((column) => !fileColumns.has(column)),
    };
  }).filter((item) => item.missing.length > 0);
  if (!missingByFile.length) {
    hidePbcColumnNotice();
    return;
  }
  // Keep the inline notice compact; the full per-file detail is available through the title tooltip.
  const fullDetails = missingByFile
    .map((item) => `${item.name} 缺少 ${item.missing.length} 列：${item.missing.join("、")}`)
    .join("\n");
  const rows = missingByFile.slice(0, 4).map((item) => `
    <div class="pbc-column-notice-row">
      <span>${escapeHtml(item.name)}</span>
      <small>缺少 ${item.missing.length} 列：${escapeHtml(item.missing.slice(0, 4).join("、"))}${item.missing.length > 4 ? "..." : ""}</small>
    </div>
  `).join("");
  pbcColumnNotice.hidden = false;
  pbcColumnNotice.title = fullDetails;
  pbcColumnNotice.innerHTML = `
    <div class="pbc-column-notice-title">上传文件列不一致，系统将按列并集导入；单个文件缺失的列会写入空值。</div>
    ${rows}
  `;
}

function renderPbcMappings() {
  if (!pbcMappingList) return;
  if (!pbcMappings.length) {
    pbcMappingList.innerHTML = '<p class="placeholder-text">读取目标列后显示映射关系</p>';
    if (pbcMappingCount) pbcMappingCount.textContent = "";
    updatePbcStepUI();
    return;
  }
  const targetOptions = pbcTableColumns.map((target) => {
    const label = `${target.name}${target.comment ? ` - ${target.comment}` : ""}`;
    return `<option value="${escapeHtml(target.name)}">${escapeHtml(label)}</option>`;
  }).join("");
  pbcMappingList.innerHTML = pbcMappings.map((mapping, index) => {
    const canRestore = !mapping.target_column && mapping.auto_target_column && mapping.manual_unmapped_from_auto;
    return `
    <div class="pbc-mapping-item ${!mapping.target_column ? "pbc-mapping-item--unmapped" : ""}">
      <span class="pbc-mapping-source" title="${escapeHtml(mapping.source_column)}">${escapeHtml(mapping.source_column)}</span>
      <span class="pbc-mapping-arrow">→</span>
      <select data-index="${index}">
        <option value="">不导入</option>
        ${targetOptions}
      </select>
      <button class="pbc-mapping-action ${canRestore ? "pbc-mapping-restore" : "pbc-mapping-remove"}" data-index="${index}" data-action="${canRestore ? "restore" : "remove"}" title="${canRestore ? "还原自动映射" : "移除列"}">
        ${canRestore
          ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v6h6"/></svg>'
          : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'}
      </button>
    </div>
  `;
  }).join("");
  pbcMappings.forEach((mapping, index) => {
    const select = pbcMappingList.querySelector(`select[data-index="${index}"]`);
    if (select) select.value = mapping.target_column || "";
  });
  if (pbcMappingCount) {
    const active = pbcMappings.filter((m) => m.target_column).length;
    pbcMappingCount.textContent = `${active}/${pbcMappings.length} 已映射`;
  }
  updatePbcStepUI();
}

function normalizePbcAutoMappings(mappings) {
  return (mappings || []).map((mapping) => ({
    ...mapping,
    auto_target_column: mapping.target_column || "",
    auto_target_comment: mapping.target_comment || "",
    manual_unmapped_from_auto: false,
  }));
}

function removePbcMapping(index) {
  const mapping = pbcMappings[index];
  if (!mapping) return;
  mapping.target_column = "";
  mapping.target_comment = "";
  mapping.manual_unmapped_from_auto = Boolean(mapping.auto_target_column);
}

function restorePbcAutoMapping(index) {
  const mapping = pbcMappings[index];
  if (!mapping?.auto_target_column) return;
  mapping.target_column = mapping.auto_target_column;
  mapping.target_comment = mapping.auto_target_comment || "";
  mapping.manual_unmapped_from_auto = false;
}

pbcMappingList?.addEventListener("change", (e) => {
  const select = e.target.closest("select[data-index]");
  if (!select) return;
  const index = Number(select.dataset.index);
  if (!pbcMappings[index]) return;
  const target = select.value;
  const source = pbcMappings[index].source_column;
  const existing = pbcTableColumns.find((column) => column.name === target);
  pbcMappings[index] = {
    source_column: source,
    target_column: target,
    target_comment: existing?.comment || "",
    auto_target_column: pbcMappings[index].auto_target_column || "",
    auto_target_comment: pbcMappings[index].auto_target_comment || "",
    manual_unmapped_from_auto: false,
  };
  renderPbcMappings();
});

pbcMappingList?.addEventListener("click", (e) => {
  const btn = e.target.closest(".pbc-mapping-action");
  if (!btn) return;
  const index = Number(btn.dataset.index);
  if (btn.dataset.action === "restore") restorePbcAutoMapping(index);
  else removePbcMapping(index);
  renderPbcMappings();
});

pbcLoadMappingsBtn?.addEventListener("click", async () => {
  if (getPbcUploadIds().length === 0 || pbcUploadedFiles.length === 0) return;
  const { configName, source } = selectedPbcDataSource();
  pbcLoadMappingsBtn.disabled = true;
  try {
    const payload = await api("/api/tools/pbc-import/columns", {
      method: "POST",
      body: JSON.stringify({
        config_name: configName,
        source,
        target_table: getPbcTargetTable(),
        source_columns: pbcColumns,
        upload_ids: getPbcUploadIds(),
      }),
    });
    if (payload.upload_inspections?.length) {
      const byUploadId = new Map(payload.upload_inspections.map((item) => [item.upload_id, item]));
      pbcUploadedFiles = pbcUploadedFiles.map((upload) => {
        const inspection = byUploadId.get(upload.upload_id);
        return inspection ? { ...upload, columns: inspection.columns || [], files: inspection.files || [] } : upload;
      });
      syncPbcUploadAggregate();
      renderPbcFileList();
    }
    pbcColumns = payload.source_columns || pbcColumns;
    pbcTableColumns = payload.table_columns || [];
    pbcMappings = normalizePbcAutoMappings(payload.mappings || []);
    hidePbcColumnNotice();
    renderPbcMappings();
  } catch (e) {
    showToast("映射失败: " + e.message, "error");
  } finally {
    pbcLoadMappingsBtn.disabled = false;
  }
});

/* ===== Step 3: Import ===== */
function finishPbcImportSuccess(job, targetTable) {
  if (pbcCompleteDesc) pbcCompleteDesc.textContent = `数据已成功导入到 ${targetTable}`;
  if (pbcCompleteStats) {
    pbcCompleteStats.innerHTML = `
      <div class="pbc-complete-stat"><div class="pbc-complete-stat-value">${job.rows_imported || 0}</div><div class="pbc-complete-stat-label">导入行数</div></div>
      <div class="pbc-complete-stat"><div class="pbc-complete-stat-value">${pbcMappings.filter(m => m.target_column).length}</div><div class="pbc-complete-stat-label">映射字段</div></div>
      <div class="pbc-complete-stat"><div class="pbc-complete-stat-value">${pbcUploadedFiles.length}</div><div class="pbc-complete-stat-label">处理文件</div></div>
    `;
  }
  pbcCurrentStep = 4;
  updatePbcStepUI();
  pbcStepsContainer.querySelector('.pbc-step[data-step="3"]')?.classList.add("pbc-step--done");
  loadPbcImportSettings();
}

function finishPbcImportFailure(job) {
  const message = job?.error || job?.message || "导入失败，请检查导入日志。";
  appendPbcLog(`导入失败: ${message}`, "error");
  showToast(`导入失败: ${message}`, "error");
  pbcImportFailed = true;
  setPbcImportProgressState("导入失败", "导入过程中发生错误，请查看日志", false);
  pbcCurrentStep = 3;
  updatePbcStepUI();
}

async function startImportFlow() {
  if (getPbcUploadIds().length === 0 || pbcUploadedFiles.length === 0) {
    showToast("请先上传文件", "warning");
    goToStep(1);
    return;
  }
  const targetTable = getPbcTargetTable();
  pbcImportConflictState = false;
  pbcImportFailed = false;
  if (pbcRetryBtn) pbcRetryBtn.hidden = true;
  setPbcImportProgressState("正在导入中", "请勿关闭页面，数据正在写入数据库", true);
  if (pbcImportLog) pbcImportLog.innerHTML = '<div class="pbc-log-entry pbc-log-entry--info">准备开始导入...</div>';
  if (pbcProgressFill) pbcProgressFill.style.width = "0%";
  if (pbcProgressPercent) pbcProgressPercent.textContent = "0%";

  const { configName, source } = selectedPbcDataSource();
  try {
    const mappings = pbcMappings.filter((mapping) => mapping.source_column && mapping.target_column);
    appendPbcLog("正在启动导入任务...", "info");
    const payload = await api("/api/tools/pbc-import/start", {
      method: "POST",
      body: JSON.stringify({
        upload_id: pbcUploadId,
        upload_ids: getPbcUploadIds(),
        config_name: configName,
        source,
        target_table: targetTable,
        columns: pbcColumns,
        drop_columns: [],
        column_order: pbcColumns,
        column_mappings: mappings,
        mode: pbcImportMode?.value || "replace",
      }),
    });
    appendPbcLog(`导入任务已启动：${payload.job_id}`, "info");
    await pollPbcImportJob(payload.job_id, targetTable);
  } catch (e) {
    handlePbcImportStartError(e);
    pbcCurrentStep = 3;
    updatePbcStepUI();
  }
}

async function pollPbcImportJob(jobId, targetTable) {
  if (pbcPollTimer) clearInterval(pbcPollTimer);
  let lastLogCount = 0;
  const poll = async () => {
    try {
      const payload = await api(`/api/tools/pbc-import/status/${encodeURIComponent(jobId)}`);
      const job = payload.job || {};
      const progress = job.progress || 0;
      if (pbcProgressFill) pbcProgressFill.style.width = `${progress}%`;
      if (pbcProgressPercent) pbcProgressPercent.textContent = `${progress}%`;
      const logs = job.logs || [];
      logs.slice(lastLogCount).forEach((log) => {
        const msg = log.message || "";
        const type = msg.includes("失败") || msg.includes("错误") ? "error" : msg.includes("完成") ? "success" : "info";
        appendPbcLog(msg, type);
      });
      lastLogCount = logs.length;
      if (["completed", "failed"].includes(job.status)) {
        clearInterval(pbcPollTimer);
        pbcPollTimer = null;
        if (job.status === "failed") {
          finishPbcImportFailure(job);
        } else {
          finishPbcImportSuccess(job, targetTable);
        }
      }
    } catch (e) {
      clearInterval(pbcPollTimer);
      pbcPollTimer = null;
      finishPbcImportFailure({ error: e.message });
    }
  };
  pbcPollTimer = setInterval(poll, 1000);
  await poll();
}

/* ===== Toast notifications ===== */
const toastContainer = document.getElementById("toastContainer");

function cssEscape(value) {
  return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function showToast(message, type = "info") {
  if (!toastContainer) return;
  const existingToast = toastContainer.querySelector(`[data-message="${cssEscape(message)}"][data-type="${cssEscape(type)}"]`);
  if (existingToast && !existingToast.classList.contains("toast--removing")) return;
  const icons = {
    error: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
    warning: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    info: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
    success: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,
  };
  const toast = document.createElement("div");
  toast.className = `toast toast--${type}`;
  toast.dataset.message = message;
  toast.dataset.type = type;
  const iconEl = document.createElement("span");
  iconEl.className = "toast-icon";
  iconEl.innerHTML = icons[type] || icons.info;
  const messageEl = document.createElement("span");
  messageEl.textContent = message;
  toast.appendChild(iconEl);
  toast.appendChild(messageEl);
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("toast--removing");
    toast.addEventListener("animationend", () => toast.remove());
  }, 3500);
}

// Theme Settings
function loadTheme() {
  const theme = normalizeTheme(getSavedTheme() || defaultSettings.theme || "space-tech");
  defaultSettings.theme = theme;
  applyTheme(theme);
  const darkMode = normalizeDarkMode(getSavedDarkMode() || defaultSettings.darkMode || "false");
  defaultSettings.darkMode = darkMode;
  applyDarkMode(darkMode);
}

const THEME_SHELL_TRANSITION_MS = 560;
let themeShellTransitionTimer = null;

function clearThemeShellTransition() {
  if (themeShellTransitionTimer) {
    window.clearTimeout(themeShellTransitionTimer);
    themeShellTransitionTimer = null;
  }
  document.documentElement.classList.remove(
    "theme-shell-transitioning",
    "theme-shell-to-space-tech",
    "theme-shell-to-light",
    "theme-shell-view-transitioning",
  );
  document.documentElement.style.removeProperty("--theme-shell-transition-duration");
}

function runThemeShellTransition(targetTheme) {
  const root = document.documentElement;
  const normalizedTarget = normalizeTheme(targetTheme);
  const currentTheme = normalizeTheme(root.getAttribute("data-theme") || defaultSettings.theme);
  if (currentTheme === normalizedTarget) return;
  if (!visualEffectsEnabled()) return;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) return;

  clearThemeShellTransition();
  const directionClass = normalizedTarget === "space-tech" ? "theme-shell-to-space-tech" : "theme-shell-to-light";
  root.style.setProperty("--theme-shell-transition-duration", `${THEME_SHELL_TRANSITION_MS}ms`);
  root.classList.add("theme-shell-transitioning", directionClass);
  themeShellTransitionTimer = window.setTimeout(clearThemeShellTransition, THEME_SHELL_TRANSITION_MS);
}

function commitTheme(theme) {
  if (theme === "space-tech") {
    document.documentElement.setAttribute("data-theme", "space-tech");
  } else {
    document.documentElement.setAttribute("data-theme", "light");
  }
  updateSpaceTopNavFrost();
  refreshHomeChartsForTheme();
}

function applyThemeWithTransition(theme) {
  const root = document.documentElement;
  const normalizedTarget = normalizeTheme(theme);
  const currentTheme = normalizeTheme(root.getAttribute("data-theme") || defaultSettings.theme);
  if (currentTheme === normalizedTarget) {
    commitTheme(normalizedTarget);
    return;
  }
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) {
    commitTheme(normalizedTarget);
    return;
  }

  const directionClass = normalizedTarget === "space-tech" ? "theme-shell-to-space-tech" : "theme-shell-to-light";
  clearThemeShellTransition();
  root.style.setProperty("--theme-shell-transition-duration", `${THEME_SHELL_TRANSITION_MS}ms`);
  root.classList.add("theme-shell-transitioning", directionClass);

  if (document.startViewTransition) {
    root.classList.add("theme-shell-view-transitioning");
    const transition = document.startViewTransition(() => {
      commitTheme(normalizedTarget);
    });
    transition.finished.finally(clearThemeShellTransition);
    return;
  }

  commitTheme(normalizedTarget);
  themeShellTransitionTimer = window.setTimeout(clearThemeShellTransition, THEME_SHELL_TRANSITION_MS);
}

function applyTheme(theme, options = {}) {
  theme = normalizeTheme(theme);
  if (options.animate) {
    applyThemeWithTransition(theme);
  } else {
    commitTheme(theme);
  }
}

function syncDarkModeButtons(enabled) {
  [topDarkModeToggle, sidebarDarkModeToggle].forEach((button) => {
    if (!button) return;
    button.classList.toggle("active", enabled);
    button.setAttribute("aria-pressed", enabled ? "true" : "false");
    const icon = button.querySelector(".dark-mode-icon");
    if (icon) icon.textContent = enabled ? "☀" : "☽";
  });
}

function applyDarkMode(darkMode) {
  const enabled = String(darkMode) === "true";
  if (enabled) {
    document.documentElement.setAttribute("data-color-mode", "dark");
  } else {
    document.documentElement.setAttribute("data-color-mode", "light");
  }
  syncDarkModeButtons(enabled);
}

async function saveAndApplyTheme(theme, options = {}) {
  theme = normalizeTheme(theme);
  saveUserThemePreference(THEME_KEY_BASE, theme);
  defaultSettings.theme = theme;
  applyTheme(theme, options);
  try {
    syncThemeBootCache();
    setStatus("主题已保存");
  } catch (e) {
    setStatus("主题保存失败: " + e.message);
  }
}

async function saveAndApplyDarkMode(darkMode) {
  darkMode = String(darkMode) === "true" ? "true" : "false";
  saveUserThemePreference(DARK_MODE_KEY_BASE, darkMode);
  defaultSettings.darkMode = darkMode;
  applyDarkMode(darkMode);
  try {
    syncThemeBootCache();
    applyDarkMode(darkMode);
    setStatus(darkMode === "true" ? "暗色模式已开启" : "暗色模式已关闭");
  } catch (e) {
    setStatus("暗色模式保存失败: " + e.message);
  }
}

function getNextTheme(theme = defaultSettings.theme) {
  return normalizeTheme(theme) === "space-tech" ? "light" : "space-tech";
}

function toggleThemeFromLogo() {
  saveAndApplyTheme(getNextTheme(defaultSettings.theme), { animate: true });
}

document.querySelectorAll("[data-theme-toggle-logo]").forEach((button) => {
  button.addEventListener("click", toggleThemeFromLogo);
});

[topDarkModeToggle, sidebarDarkModeToggle].forEach((button) => {
  button?.addEventListener("click", () => {
    const next = defaultSettings.darkMode === "true" ? "false" : "true";
    saveAndApplyDarkMode(next);
  });
});

// About section
document.getElementById("aboutHelp")?.addEventListener("click", (e) => {
  e.preventDefault();
  showInfo("使用帮助", `
    <h4>快速开始</h4>
    <ul>
      <li>在系统设置中配置数据源（DWS 和报表库）</li>
      <li>在对数执行页面选择日期并运行</li>
      <li>查看核对结果和差异分析</li>
      <li>对数历史页面可查看过往核对记录</li>
    </ul>

    <h4>功能说明</h4>
    <ul>
      <li><strong>报送导航</strong>：查看监管报送统计、流程进度和注意事项</li>
      <li><strong>智能核数 / 对数总览</strong>：查看核对趋势和统计图表</li>
      <li><strong>智能核数 / 对数执行</strong>：执行余额核对，查看差异详情</li>
      <li><strong>智能核数 / 对数历史</strong>：查看历史核对记录，并可在详情中恢复到结果页</li>
      <li><strong>系统设置</strong>：配置数据源、默认选项、业务字段清单、主题等</li>
    </ul>

    <h4>主要功能</h4>
    <ul>
      <li>自动对数：根据预设规则自动核对项目余额</li>
      <li>差异分析：智能识别差异原因并提供详细说明</li>
      <li>历史记录：保存每次核对结果，支持对比分析</li>
      <li>数据导出：支持导出核对结果为 Excel 文件</li>
      <li>多数据源：支持 PostgreSQL 和 MySQL 数据库</li>
    </ul>

    <h4>技术栈</h4>
    <ul>
      <li>后端：Python 3.12 + psycopg + PyMySQL</li>
      <li>前端：原生 HTML/CSS/JavaScript</li>
      <li>打包：PyInstaller</li>
    </ul>

    <h4>常见问题</h4>
    <p><strong>Q: 连接测试失败怎么办？</strong></p>
    <p>A: 检查数据库地址、端口、用户名和密码是否正确。</p>

    <p><strong>Q: 如何导出核对结果？</strong></p>
    <p>A: 在对数执行页面点击"导出"按钮，可导出 Excel 文件。</p>
  `);
});

document.getElementById("aboutChangelog")?.addEventListener("click", (e) => {
  e.preventDefault();
  showInfo("更新日志", `
    <div class="changelog-item">
      <div>
        <span class="changelog-version">v2.1</span>
        <span class="changelog-date">2026-07-02</span>
      </div>
              <ul>
        <li>新增报送导航状态定时统计、鱼骨进度、报送日期到期完成兜底和治理统计四周期维护。</li>
        <li>报送导航支持手工刷新统计、普通用户 5 分钟可见倒计时、管理员免冷却和步骤异常详情。</li>
        <li>新增智能核数多级菜单，整合对数总览、对数执行和对数历史。</li>
        <li>新增界面圆角个性化设置。</li>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v2.0.8</span>
        <span class="changelog-date">2026-06-12</span>
      </div>
       <ul>
        <li>新增监管智核品牌名称和系统 Logo。</li>
        <li>新增点击 Logo 切换主题能力。</li>
        <li>新增登录进入主界面动效。</li>
        <li>首页组合图表指标改为每期差异个数。</li>
        <li>自动对数 AM 标的复核新增尾码和江苏信托名称兜底。</li>
        <li>流程链配置补充执行接口规则说明。</li>
        <li>流程链配置支持按 flow_id 搜索和手工添加流程。</li>
        <li>自动对数处理脚本按 AM 合同来源生成，衡泰来源提示联系衡泰系统处理。</li>
        <li>修复流程链点击停止时任务编号未正确传递的问题。</li>
        <li>新增系统设置动画效果开关，支持统一关闭复杂渐变、毛玻璃、悬浮阴影和动态渲染。</li>
        <li>新增流程后台执行悬浮提示，支持单流程链与多流程链进度区分显示。</li>
        <li>执行历史新增执行时长列，支持单流程链和多流程链时长记录。</li>
        <li>多流程链执行历史合并为一条记录，流程链列显示"多流程链(X条)"，悬浮显示全部流程链名称。</li>
        <li>新增自动对账表字段可视化配置、字段自动读取、字段下拉选择与取消、表字段保存校验和配置文件初始化能力。</li>
        <li>新增自动对账表标准中文名维护能力。</li>
        <li>系统优化及BUG修复。</li>
       </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v2.0.7</span>
        <span class="changelog-date">2026-06-11</span>
      </div>
      <ul>
        <li>新增流程链配置、手工执行及执行记录查看。</li>
        <li>流程链配置支持从流程表选择流程。</li>
        <li>自动对数新增3001共同类科目与实收本金多次重复识别。</li>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v2.0.6</span>
        <span class="changelog-date">2026-06-06</span>
      </div>
      <ul>
        <li>新增人行逐笔校验引擎公开信息校验、模板校验和规则说明能力。</li>
        <li>自动对数差异原因调整为固定基础分类，细分原因在详情展示。</li>
        <li>自动对数资产缺失细分新增多资产格式化具体原因和详情表格。</li>
        <li>自动对数资产重复新增私募产品细分原因和详情表格。</li>
        <li>自动对数资产差异新增贷款及财产权合同细分原因和详情表格。</li>
        <li>自动对数资产端组合候选过多时支持科目分组组合，并新增债券DM证券余额差异细分。</li>
        <li>自动对数资产差异和负债权益科目差异新增逆/正回购金额比对。</li>
        <li>自动对数资产差异解释后支持继续核对剩余差额并展示组合差异类型。</li>
        <li>自动对数差异类型筛选支持组合差异类型匹配。</li>
        <li>自动对数资产端和负债权益主差异多组候选时展示候选不唯一。</li>
        <li>自动对数资产缺失候选不唯一时支持AM复核确认候选组，实收本金缺失/重复新增c1000防误判判断。</li>
        <li>自动对数导出Excel新增组合差异备注列。</li>
        <li>自动对数处理脚本支持多个FA/AM标的不一致生成。</li>
        <li>自动对数负债权益正回购差异新增具体原因。</li>
        <li>自动对数结果列表和导出字段改为差异类型，并新增具体原因列。</li>
        <li>自动对数历史详情同步展示具体原因。</li>
        <li>自动对数结果详情改为单行展开查看。</li>
        <li>自动对数实收本金差异与负债权益混合场景支持剩余差额核对。</li>
        <li>自动对数实收本金差异新增TA差异细分原因。</li>
        <li>自动对数负债权益和实收本金新增格式化具体原因和详情表格。</li>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v2.0.5</span>
        <span class="changelog-date">2026-06-06</span>
      </div>
      <ul>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v2.0.4</span>
        <span class="changelog-date">2026-06-06</span>
      </div>
      <ul>
        <li>新增浏览器页签品牌精简显示。</li>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v2.0.3</span>
        <span class="changelog-date">2026-06-06</span>
      </div>
      <ul>
        <li>新增准星·监管报送助手品牌名称和系统 Logo。</li>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v2.0.2</span>
        <span class="changelog-date">2026-06-04</span>
      </div>
      <ul>
        <li>导出 Excel 新增处理脚本列。</li>
        <li>新增用户姓名，导航用户按钮、用户列表和执行历史优先显示姓名。</li>
        <li>新增对数任务全局互斥和一键导入同表冲突提示。</li>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v2.0.1</span>
        <span class="changelog-date">2026-06-03</span>
      </div>
      <ul>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v2.0</span>
        <span class="changelog-date">2026-06-03</span>
      </div>
      <ul>
        <li>新增工具页面与人行全量产品一键导入能力。</li>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v1.4.0</span>
        <span class="changelog-date">2026-06-02</span>
      </div>
      <ul>
        <li>新增首页趋势图日期筛选和零差异完成效果。</li>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v1.3.0</span>
        <span class="changelog-date">2026-06-01</span>
      </div>
      <ul>
        <li>新增后台执行、停止执行和执行日志。</li>
        <li>新增默认设置持久化、历史分页和系统信息操作反馈。</li>
        <li>新增估值表资产合计列、导出详情和 1541 财产权核对。</li>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v1.2.1</span>
        <span class="changelog-date">2026-06-01</span>
      </div>
      <ul>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v1.2.0</span>
        <span class="changelog-date">2026-05-30</span>
      </div>
      <ul>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v1.1.0</span>
        <span class="changelog-date">2026-05-29</span>
      </div>
      <ul>
        <li>新增系统设置、业务设置、主题和图表能力。</li>
        <li>系统优化及BUG修复。</li>
      </ul>
    </div>

    <div class="changelog-item">
      <div>
        <span class="changelog-version">v1.0.0</span>
        <span class="changelog-date">2026-05-20</span>
      </div>
      <ul>
        <li>初始版本：自动对数、历史记录、多数据源和 Excel 导出。</li>
      </ul>
    </div>
  `);
});

// Initialize settings
initializeCustomSelects();
window.addEventListener("scroll", updateSpaceTopNavFrost, { passive: true });
mainContent?.addEventListener("scroll", updateSpaceTopNavFrost, { passive: true });
window.addEventListener("resize", updateSpaceTopNavFrost);
window.addEventListener("resize", fitHomeReportPeriodValue);
window.addEventListener("resize", scheduleHomeChartsResize);

// Initial load
(async () => {
  await ensureAuthenticated();
  let settingsPayload = null;
  try {
    settingsPayload = await loadDefaultSettings();
    loadSettings();
  } catch (_) {
    serverDefaultSettings = normalizeClientSettings({
      ...getSavedSettings(),
      theme: DEFAULT_SETTINGS.theme,
      darkMode: DEFAULT_SETTINGS.darkMode,
    });
    defaultSettings = withSavedUserTheme(serverDefaultSettings);
    syncThemeBootCache();
    loadSettings();
  }
  loadTheme();
  const savedPage = location.hash.slice(1);
  if (savedPage && document.getElementById("page-" + savedPage)) {
    await switchPage(savedPage, { forceHomeRefresh: savedPage === "home" });
  } else {
    // 默认显示报送导航
    await switchPage("report-navigation");
  }
  try { const d = await api("/api/config"); if (!runDate.value) runDate.value = d.default_run_date || settingsPayload?.api_default_run_date || ""; } catch (_) { if (!runDate.value) runDate.value = settingsPayload?.api_default_run_date || ""; }
  restoreLatestResultsSnapshot();
  await loadLatestHistoryResults();
  loadSystemInfo();
  await loadFlowToastStatus();
})();
