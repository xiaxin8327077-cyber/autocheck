"""执行对数结果刷新和执行冲突的场景。逻辑直接取自页面脚本。"""

from __future__ import annotations

import json
import subprocess
import tempfile
import textwrap
from pathlib import Path

from auto_check.app.history import reconcile_watch_from_runs


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "src" / "auto_check" / "web" / "app.js"


def _extract_function(source: str, name: str) -> str:
    marker = f"function {name}("
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"missing function {name}")
    if source[max(0, start - 6):start] == "async ":
        start -= 6
    return source[start:_matching_brace_end(source, source.find("{", start))]


def _extract_const_array(source: str, name: str) -> str:
    marker = f"const {name} ="
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"missing const {name}")
    return source[start:_matching_brace_end(source, source.find("[", start))].rstrip(";")


def _matching_brace_end(source: str, open_index: int) -> int:
    opener = source[open_index]
    closer = {"{": "}", "[": "]"}[opener]
    depth = 0
    quote = ""
    escape = False
    template_expr = 0
    i = open_index
    while i < len(source):
        ch = source[i]
        if quote == "`" and not escape and ch == "$" and i + 1 < len(source) and source[i + 1] == "{":
            template_expr += 1
            i += 2
            continue
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = ""
            elif quote == "`" and template_expr and ch == "}":
                template_expr -= 1
            i += 1
            continue
        if ch in {"'", '"', "`"}:
            quote = ch
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise AssertionError(f"unclosed block at {open_index}")


def _page_functions() -> str:
    source = APP_JS.read_text(encoding="utf-8")
    names = [
        "formatDisplayTime",
        "normalizeExecutorDisplayName",
        "userDisplayName",
        "historyExecutorName",
        "reconcileAmountKey",
        "stableJson",
        "reconcileResultSignature",
        "reconcileResultsChanged",
        "rememberDisplayedReconcileRun",
        "isNewerReconcileRunAt",
        "reconcileWatchActor",
        "buildReconcileWatchMessage",
        "pickReconcileWatchRun",
        "currentReconcileWatchDate",
        "isConfirmDialogOpen",
        "loadReconcileHistoryRun",
        "applyReconcileHistoryRun",
        "findChangedSameDateRun",
        "refreshLatestReconcileResults",
        "noteReconcileCompletion",
        "flushPendingReconcileCompletion",
        "checkReconcileResultUpdates",
        "isRunConflictMessage",
        "handleRunStartError",
    ]
    parts = [_extract_const_array(source, "RECONCILE_RESULT_AMOUNT_FIELDS")]
    parts.extend(_extract_function(source, name) for name in names)
    return "\n".join(parts)


def _run_page_scenarios() -> list[dict]:
    page = _page_functions()
    script = textwrap.dedent(
        """
        const assert = require('node:assert/strict');
        const scenarios = [];
        function scenario(name, fn) { scenarios.push({ name, fn }); }

        let results = [];
        let displayedReconcileRun = { id: '', runDate: '', runAt: '', signature: '' };
        let reconcileWatchDismissedKey = '';
        let reconcileWatchUnchangedRunId = '';
        let reconcileWatchPromptOpen = false;
        let reconcileWatchReady = true;
        let reconcileCompletionPending = false;
        let reconcileWatchChecking = false;
        let reconcileRefreshInFlight = false;
        let runJobId = null;
        let latestRunAt = '';
        let latestRunExecutor = '';
        let currentPage = 1;
        let homeResultListFilterLabel = '';
        let hideLastRunTimeForNoSourceData = false;
        let pageName = 'auto-check';
        let documentHidden = false;
        let confirmOpen = false;
        const authState = { user: { id: 'me' } };
        const runDate = { value: '2026-09-30' };
        const keywordFilter = { value: '' };
        const reasonFilter = { value: '' };
        const statusFilter = { value: '' };
        const refreshResultsBtn = { disabled: false };
        const document = {
          get hidden() { return documentHidden; },
          documentElement: { getAttribute: () => pageName },
          getElementById: () => ({ hidden: !confirmOpen }),
        };

        const calls = {
          api: [],
          confirms: [],
          applied: [],
          toasts: [],
          statuses: [],
          polls: [],
          logs: [],
          wave: [],
        };
        let apiImpl = async () => ({});
        let confirmImpl = async () => false;
        async function api(path) {
          calls.api.push(path);
          return apiImpl(path);
        }
        async function showConfirm(title, message, options) {
          calls.confirms.push({ title, message, options });
          confirmOpen = true;
          try { return await confirmImpl(title, message, options); }
          finally { confirmOpen = false; }
        }
        function syncCustomSelect() {}
        function renderResults() {}
        function clearResultHistoryRestoreState() {}
        function setLastRunTime(value, executorName) { calls.statuses.push(['last-run', value, executorName]); }
        function saveLatestResultsSnapshot() {}
        function setStatus(text) { calls.statuses.push(text); }
        function showToast(message, type) { calls.toasts.push({ message, type }); }
        function showWaveProgress() { calls.wave.push('show'); }
        function hideWaveProgress() { calls.wave.push('hide'); }
        function setWaveProgress(progress, step) { calls.wave.push(['progress', progress, step]); }
        function appendRunLog(message) { calls.logs.push(message); }
        function pollActiveRunConflict(jobId, executorName) { calls.polls.push({ jobId, executorName }); }

        __PAGE_FUNCTIONS__

        function reset() {
          results = [];
          displayedReconcileRun = { id: '', runDate: '', runAt: '', signature: '' };
          reconcileWatchDismissedKey = '';
          reconcileWatchUnchangedRunId = '';
          reconcileWatchPromptOpen = false;
          reconcileWatchReady = true;
          reconcileCompletionPending = false;
          reconcileWatchChecking = false;
          reconcileRefreshInFlight = false;
          runJobId = null;
          pageName = 'auto-check';
          documentHidden = false;
          confirmOpen = false;
          runDate.value = '2026-09-30';
          authState.user.id = 'me';
          for (const key of Object.keys(calls)) calls[key].length = 0;
          apiImpl = async () => ({});
          confirmImpl = async () => false;
        }

        function showRun(run, items) {
          results = items || run.results || [];
          rememberDisplayedReconcileRun(run, results);
          runDate.value = run.run_date;
        }

        const old930 = {
          id: 'old-930',
          run_date: '2026-09-30',
          run_at: '2026-09-30 09:00:00',
          executor_name: '王五',
          results: [{ project_code: 'P1', project_name: '项目1', difference: '10.00', difference_reason: '资产差异', match_status: '未解释', details: [] }],
        };
        const changed930 = {
          id: 'new-930',
          run_date: '2026-09-30',
          run_at: '2026-11-01 11:05:02',
          executor_name: '李四',
          results: [{ project_code: 'P1', project_name: '项目1', difference: '12.50', difference_reason: '资产差异', match_status: '未解释', details: [] }],
        };
        const same930 = {
          id: 'same-930',
          run_date: '2026-09-30',
          run_at: '2026-11-01 12:00:00',
          executor_name: '李四',
          results: [{ project_code: 'P1', project_name: '项目1', difference: '10.00', difference_reason: '资产差异', match_status: '未解释', details: [] }],
        };
        const run1001 = {
          id: 'latest-1001',
          run_date: '2026-10-01',
          run_at: '2026-11-01 10:20:15',
          executor_name: '张三',
          results: [{ project_code: 'P9', project_name: '项目9', difference: '1', difference_reason: '实收本金差异', match_status: '已解释', details: [] }],
        };

        scenario('金额格式不同但数值相同不算结果变化', () => {
          const left = [{ project_code: 'P1', difference: '1,000.50', asset_total: '10', details: [{ kind: 'a', data: { gap: '1.0' } }] }];
          const right = [{ project_code: 'P1', difference: '1000.5', asset_total: '10.00', details: [{ data: { gap: '1.0' }, kind: 'a' }] }];
          assert.equal(reconcileResultsChanged(left, right), false);
        });

        scenario('差异金额或明细变化算结果变化', () => {
          const base = [{ project_code: 'P1', difference: '10.00', details: [{ kind: 'gap', data: { value: '1' } }] }];
          assert.equal(reconcileResultsChanged(base, [{ ...base[0], difference: '10.01' }]), true);
          assert.equal(reconcileResultsChanged(base, [{ ...base[0], details: [{ kind: 'gap', data: { value: '2' } }] }]), true);
        });

        scenario('三种提示文案与确认后的加载选择', () => {
          const newer = { id: 'latest-1001', run_date: '2026-10-01', run_at: '2026-11-01 10:20:15', executor_name: '张三' };
          const same = { id: 'new-930', run_date: '2026-09-30', run_at: '2026-11-01 11:05:02', executor_name: '李四', results: [] };
          assert.equal(
            buildReconcileWatchMessage('2026-09-30', newer, null),
            '校验日期 2026-10-01 已有对数结果（张三，2026-11-01 10:20:15）。是否加载这批结果？',
          );
          assert.equal(
            buildReconcileWatchMessage('2026-09-30', null, same),
            '校验日期 2026-09-30 已重新执行，结果有变化（李四，2026-11-01 11:05:02）。是否加载最新结果？',
          );
          assert.equal(
            buildReconcileWatchMessage('2026-09-30', newer, same),
            '校验日期 2026-10-01 已有对数结果（张三，2026-11-01 10:20:15）。校验日期 2026-09-30 已重新执行，结果有变化（李四，2026-11-01 11:05:02）。是否加载最新一次执行的结果？',
          );
          assert.equal(pickReconcileWatchRun(newer, same).id, 'new-930');
          assert.equal(pickReconcileWatchRun({ ...newer, run_at: '2026-11-01 12:00:00' }, same).id, 'latest-1001');
        });

        scenario('停在930且出现1001时取消不加载，同一批不再询问', async () => {
          reset();
          showRun(old930);
          apiImpl = async (path) => {
            if (path.startsWith('/api/history/watch')) {
              return { newer_date: run1001, same_date: old930 };
            }
            throw new Error('不应加载明细 ' + path);
          };
          await checkReconcileResultUpdates();
          assert.equal(calls.confirms.length, 1);
          assert.match(calls.confirms[0].message, /是否加载这批结果/);
          assert.equal(results[0].project_code, 'P1');
          await checkReconcileResultUpdates();
          assert.equal(calls.confirms.length, 1);
        });

        scenario('停在930且当期重跑结果有变化时确认后才加载', async () => {
          reset();
          showRun(old930);
          apiImpl = async (path) => {
            if (path.startsWith('/api/history/watch')) return { newer_date: null, same_date: changed930 };
            if (path.includes('/api/history/new-930')) return { history: changed930 };
            throw new Error(path);
          };
          confirmImpl = async () => true;
          await checkReconcileResultUpdates();
          assert.match(calls.confirms[0].message, /已重新执行，结果有变化/);
          assert.equal(results[0].difference, '12.50');
          assert.equal(displayedReconcileRun.id, 'new-930');
          assert.equal(runDate.value, '2026-09-30');
        });

        scenario('当期重跑但结果没变时不提示', async () => {
          reset();
          showRun(old930);
          apiImpl = async (path) => {
            if (path.startsWith('/api/history/watch')) return { newer_date: null, same_date: same930 };
            if (path.includes('/api/history/same-930')) return { history: same930 };
            throw new Error(path);
          };
          await checkReconcileResultUpdates();
          assert.equal(calls.confirms.length, 0);
          assert.equal(results[0].difference, '10.00');
          const detailCalls = calls.api.filter((path) => path.includes('/api/history/same-930')).length;
          await checkReconcileResultUpdates();
          assert.equal(calls.api.filter((path) => path.includes('/api/history/same-930')).length, detailCalls);
        });

        scenario('停在1001时更早日期的重跑不提示', async () => {
          reset();
          showRun(run1001);
          apiImpl = async () => ({ newer_date: null, same_date: run1001 });
          await checkReconcileResultUpdates();
          assert.equal(calls.confirms.length, 0);
        });

        scenario('两件事同时发生时加载执行时间更新的一次，并继续询问剩下的', async () => {
          reset();
          showRun(old930);
          let accepted = false;
          apiImpl = async (path) => {
            if (path.startsWith('/api/history/watch')) {
              const date = new URL(path, 'http://local').searchParams.get('run_date');
              if (date === '2026-10-01') return { newer_date: null, same_date: run1001 };
              return { newer_date: run1001, same_date: changed930 };
            }
            if (path.includes('/api/history/new-930')) return { history: changed930 };
            if (path.includes('/api/history/latest-1001')) return { history: run1001 };
            throw new Error(path);
          };
          confirmImpl = async () => true;
          await checkReconcileResultUpdates();
          assert.match(calls.confirms[0].message, /是否加载最新一次执行的结果/);
          assert.equal(displayedReconcileRun.id, 'new-930');
          accepted = true;
          for (let i = 0; i < 20 && calls.confirms.length < 2; i += 1) {
            await new Promise((resolve) => setTimeout(resolve, 10));
          }
          assert.equal(calls.confirms.length, 2);
          assert.match(calls.confirms[1].message, /是否加载这批结果/);
        });

        scenario('手动刷新加载最新校验日期的最新结果', async () => {
          reset();
          showRun(old930);
          apiImpl = async (path) => {
            if (path === '/api/history/watch') return { latest_date: run1001 };
            if (path.includes('/api/history/latest-1001')) return { history: run1001 };
            throw new Error(path);
          };
          await refreshLatestReconcileResults();
          assert.equal(calls.confirms.length, 0);
          assert.equal(displayedReconcileRun.id, 'latest-1001');
          assert.equal(runDate.value, '2026-10-01');
          calls.api.length = 0;
          calls.toasts.length = 0;
          await refreshLatestReconcileResults();
          assert.equal(calls.api.some((path) => path.includes('/api/history/latest-1001')), false);
          assert.equal(calls.toasts.at(-1).message, '已是最新结果');
        });

        scenario('没有历史时刷新只提示暂无结果', async () => {
          reset();
          apiImpl = async () => ({ latest_date: null });
          await refreshLatestReconcileResults();
          assert.equal(calls.toasts[0].message, '暂无对数结果');
          assert.equal(displayedReconcileRun.id, '');
        });

        scenario('自己执行完成不触发询问，别人完成且不在对数页时先记住', async () => {
          reset();
          apiImpl = async () => { throw new Error('自己的完成不应查询'); };
          noteReconcileCompletion({ executor_id: 'me', id: 'latest-1001' });
          assert.equal(calls.api.length, 0);
          assert.equal(reconcileCompletionPending, false);
          pageName = 'report-navigation';
          noteReconcileCompletion({ executor_id: 'other', id: 'latest-1001' });
          assert.equal(calls.api.length, 0);
          assert.equal(reconcileCompletionPending, true);
          pageName = 'auto-check';
          apiImpl = async () => ({ newer_date: null, same_date: null });
          flushPendingReconcileCompletion();
          await new Promise((resolve) => setTimeout(resolve, 0));
          assert.equal(calls.api.length, 1);
          assert.equal(calls.confirms.length, 0);
        });

        scenario('确认框打开或页面隐藏时不马上询问，回到页面后再问', async () => {
          reset();
          confirmOpen = true;
          noteReconcileCompletion({ executor_id: 'other', id: 'latest-1001' });
          assert.equal(reconcileCompletionPending, true);
          assert.equal(calls.api.length, 0);
          confirmOpen = false;
          documentHidden = true;
          flushPendingReconcileCompletion();
          assert.equal(reconcileCompletionPending, true);
          documentHidden = false;
          apiImpl = async () => ({ newer_date: null, same_date: null });
          flushPendingReconcileCompletion();
          await new Promise((resolve) => setTimeout(resolve, 0));
          assert.equal(calls.api.length, 1);
          assert.equal(reconcileCompletionPending, false);
        });

        scenario('执行冲突后选择否不看进度，选择查看进度才跟随这一次', async () => {
          reset();
          const plain = await handleRunStartError(new Error('数据库连接失败'));
          assert.equal(plain.conflict, false);
          assert.equal(calls.confirms.length, 0);

          confirmImpl = async () => false;
          const declined = await handleRunStartError({
            message: '对数任务正在执行，请等待当前任务完成后再开始。',
            payload: { active_job: { id: 'job-1', executor: { display_name: '张三' } } },
          });
          assert.equal(declined.conflict, true);
          assert.equal(declined.watching, false);
          assert.equal(calls.polls.length, 0);
          assert.equal(calls.confirms.at(-1).title, '对数任务正在执行');
          assert.equal(calls.confirms.at(-1).message, '张三正在执行。是否查看当前进度？');
          assert.deepEqual(calls.confirms.at(-1).options, { cancelText: '否', okText: '查看进度' });

          confirmImpl = async () => true;
          const accepted = await handleRunStartError({
            message: '对数任务正在执行，请等待当前任务完成后再开始。',
            payload: { active_job: { id: 'job-2', executor: { display_name: '张三' } } },
          });
          assert.equal(accepted.watching, true);
          assert.deepEqual(calls.polls.at(-1), { jobId: 'job-2', executorName: '张三' });
        });

        (async () => {
          const failures = [];
          for (const item of scenarios) {
            try { await item.fn(); }
            catch (error) { failures.push(item.name + ': ' + error.stack); }
          }
          if (failures.length) {
            console.error(failures.join('\\n\\n'));
            process.exit(1);
          }
          console.log(JSON.stringify({ passed: scenarios.length }));
        })();
        """
    ).replace("__PAGE_FUNCTIONS__", page)
    with tempfile.TemporaryDirectory() as directory:
        script_path = Path(directory) / "reconcile-refresh-scenarios.js"
        script_path.write_text(script, encoding="utf-8")
        completed = subprocess.run(
            ["node", str(script_path)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return json.loads(completed.stdout)


def test_reconcile_page_scenarios_cover_dates_results_refresh_and_conflict():
    outcome = _run_page_scenarios()
    assert outcome["passed"] >= 12


def test_watch_ignores_older_dates_even_when_their_execution_is_later():
    runs = [
        {"id": "blank", "run_date": "", "run_at": "2026-12-01 00:00:00"},
        {"id": "aug", "run_date": "2026-08-31", "run_at": "2026-11-02 08:00:00", "total_count": 1},
        {"id": "sep-early", "run_date": "2026-09-30", "run_at": "2026-09-30 09:00:00", "total_count": 2},
        {"id": "sep-late", "run_date": "2026-09-30", "run_at": "2026-09-30 18:00:00", "total_count": 3},
        {"id": "oct-early", "run_date": "2026-10-01", "run_at": "2026-10-01 08:00:00", "total_count": 4},
        {"id": "oct-late", "run_date": "2026-10-01", "run_at": "2026-10-01 10:20:15", "total_count": 5},
    ]

    stayed = reconcile_watch_from_runs(runs, "2026-09-30")
    assert stayed["same_date"]["id"] == "sep-late"
    assert stayed["newer_date"]["id"] == "oct-late"
    assert stayed["latest_date"]["id"] == "oct-late"

    newer_day = reconcile_watch_from_runs(runs, "2026-10-01")
    assert newer_day["newer_date"] is None
    assert newer_day["same_date"]["id"] == "oct-late"

    assert reconcile_watch_from_runs([], "2026-09-30") == {
        "run_date": "2026-09-30",
        "same_date": None,
        "newer_date": None,
        "latest_date": None,
    }
