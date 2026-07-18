# Interface Radius Surface Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户截图指定的鱼骨详情、日期分组、注意事项、历史详情、流程执行、上传、系统设置等矩形表面全部读取现有全局圆角值，同时不改变任何业务功能或特殊形状。

**Architecture:** 继续使用 `styles.css` 末尾现有的集中式 `--ui-radius` 覆盖层，只增加逐项核对过的精确选择器，并保持覆盖层唯一声明为 `border-radius`。静态测试把新选择器加入契约、把暗色切换外壳从禁止项移入必需项；README 记录详细覆盖，应用内更新日志沿用已有“系统优化及BUG修复”精简口径。

**Tech Stack:** 原生 HTML/CSS/JavaScript、Python 3.12、pytest、PowerShell、PyInstaller、Windows WebView/浏览器验收。

## Global Constraints

- 仅修改界面显示，不修改 HTML 结构、JavaScript 事件、API、数据库、权限、表单值、焦点顺序或点击区域。
- 全部目标使用同一个 `--ui-radius`；范围仍为 1–15px、默认 4px、步长 1px。
- 默认太空主题、沉稳主题和暗色模式均需兼容。
- 圆形图标、头像、状态点、图表节点、胶囊、标签、进度条、复选框、单选框、滑块和 SVG 内部形状保持原样。
- 覆盖层禁止使用全局 `button`、`table`、`[class*=item]`、`[class*=card]` 或通配后代选择器。
- `src/auto_check/web/app.js` 的 v2.1 日志保持“新增界面圆角个性化设置。”和“系统优化及BUG修复。”的精简口径，不展开本次界面细节。
- 所有编辑在 `D:\trae\autocheck\.worktrees\user-interface-radius-preferences` 独立 worktree 内完成。

---

### Task 1: 用静态测试锁定截图指定覆盖范围

**Files:**
- Modify: `tests/test_web_static.py:2874-2990`

**Interfaces:**
- Consumes: `styles.css` 中 `/* User interface radius preference: start/end */` 标记区，以及 `README_MD` 测试常量。
- Produces: 20 个新增必需选择器、特殊形状排除契约和 README 详细覆盖契约。

- [ ] **Step 1: 扩展圆角选择器契约测试**

在 `test_user_radius_override_is_semantic_and_border_radius_only()` 的必需选择器元组中加入：

```python
        "#page-report-navigation .report-nav-branch-panel",
        "#page-report-navigation .report-nav-batch",
        "#page-report-navigation .report-nav-todo",
        ".dark-mode-toggle",
        ".history-summary-item",
        ".history-count-item",
        ".history-section",
        ".flow-chain-list",
        ".flow-chain-selection-summary",
        ".flow-run-panel:last-child #flowLog",
        ".flow-history-table-wrap",
        ".db-validation-history-table-wrap",
        ".pbc-upload-area",
        "#page-settings .metric-item",
        "#page-settings .db-validation-source-row",
        ".flow-chain-config",
        ".config-item",
        "#page-settings .about-description",
        "#page-settings .about-features",
        "#page-settings .about-tech",
```

从同一测试的 `forbidden_selector` 元组中仅删除：

```python
        ".dark-mode-toggle",
```

保留 `.checkbox`、`.radio`、`.range-track`、`.range-thumb`、`svg`、`overlay` 和 `[class*=card]` 等现有禁止项。

- [ ] **Step 2: 增加 README 详细覆盖测试**

在圆角静态测试附近新增：

```python
def test_readme_documents_expanded_interface_radius_surface_coverage():
    readme = _read(README_MD)

    for text in (
        "鱼骨详情卡",
        "报送日期分组卡",
        "注意事项卡",
        "暗色切换按钮外壳",
        "历史详情与执行历史表格外框",
        "一键导入上传区",
        "系统信息指标卡",
        "数据源与流程链配置行",
        "关于系统内容卡",
    ):
        assert text in readme
```

- [ ] **Step 3: 运行测试并确认先失败**

Run:

```powershell
python -m pytest -q tests/test_web_static.py::test_user_radius_override_is_semantic_and_border_radius_only tests/test_web_static.py::test_readme_documents_expanded_interface_radius_surface_coverage
```

Expected: FAIL；第一个测试报告新增选择器尚不在覆盖层，第二个测试报告 README 尚缺详细覆盖用语。

---

### Task 2: 实现精确 CSS 覆盖并同步 README

**Files:**
- Modify: `src/auto_check/web/styles.css:12073-12142`
- Modify: `README.md:26`
- Modify: `README.md:318`
- Test: `tests/test_web_static.py`

**Interfaces:**
- Consumes: 现有根变量 `--ui-radius` 和 Task 1 的必需选择器契约。
- Produces: 所有截图指定矩形表面统一读取 `var(--ui-radius)`，且 README 当前功能与 v2.1 说明同步。

- [ ] **Step 1: 把精确选择器加入集中式覆盖层**

在 `/* User interface radius preference: start */` 与 `end` 之间的现有选择器列表中加入以下内容，继续共用原规则体：

```css
#page-report-navigation .report-nav-branch-panel,
#page-report-navigation .report-nav-batch,
#page-report-navigation .report-nav-todo,
.dark-mode-toggle,
.history-summary-item,
.history-count-item,
.history-section,
.flow-chain-list,
.flow-chain-selection-summary,
.flow-run-panel:last-child #flowLog,
.flow-history-table-wrap,
.db-validation-history-table-wrap,
.pbc-upload-area,
#page-settings .metric-item,
#page-settings .db-validation-source-row,
.flow-chain-config,
.config-item,
#page-settings .about-description,
#page-settings .about-features,
#page-settings .about-tech,
```

规则体保持完全不变：

```css
{
  border-radius: var(--ui-radius) !important;
}
```

- [ ] **Step 2: 更新 README 当前功能说明**

在 `README.md` 的“系统设置”条目中，把覆盖说明扩展为包含以下完整句子：

```markdown
截图指定的矩形子表面也统一跟随该值，包括鱼骨详情卡、报送日期分组卡、注意事项卡、暗色切换按钮外壳、历史详情与执行历史表格外框、一键导入上传区、系统信息指标卡、数据源与流程链配置行、关于系统内容卡。
```

保持紧随其后的特殊形状排除说明不变。

- [ ] **Step 3: 更新 README v2.1 详细变更**

在 v2.1 的“新增用户级界面圆角个性化设置”条目末尾加入：

```markdown
；截图指定的矩形子表面进一步覆盖鱼骨详情、报送日期、注意事项、历史详情、执行历史、上传区、系统信息、数据源与流程链配置以及关于系统内容卡
```

不要修改应用界面版本号，也不要展开 `src/auto_check/web/app.js` 的精简更新日志。

- [ ] **Step 4: 运行聚焦测试并确认通过**

Run:

```powershell
python -m pytest -q tests/test_web_static.py::test_user_radius_override_is_semantic_and_border_radius_only tests/test_web_static.py::test_readme_documents_expanded_interface_radius_surface_coverage tests/test_web_static.py::test_v21_changelog_documents_interface_radius_concisely
```

Expected: 3 passed；更新日志仍保持精简，CSS 覆盖层只包含 `border-radius`。

- [ ] **Step 5: 运行前端静态测试**

Run:

```powershell
python -m pytest -q tests/test_web_static.py
```

Expected: PASS，无失败或错误。

- [ ] **Step 6: 检查本任务差异**

Run:

```powershell
git diff -- src/auto_check/web/styles.css tests/test_web_static.py README.md
git diff --check
```

Expected: CSS 只在集中式覆盖层增加精确选择器；测试只扩展圆角契约；README 只补充覆盖说明；无 whitespace error。

- [ ] **Step 7: 提交实现**

```powershell
git add src/auto_check/web/styles.css tests/test_web_static.py README.md
git commit -m "fix: extend unified radius to highlighted surfaces"
```

---

### Task 3: 全量验证、重新打包与浏览器验收

**Files:**
- Verify: `src/auto_check/web/styles.css`
- Verify: `tests/test_web_static.py`
- Verify: `README.md`
- Modify: `dist/auto-check.exe`

**Interfaces:**
- Consumes: Task 2 已提交的 CSS/测试/README。
- Produces: 通过全量回归的新 Windows 可执行文件，以及 1px、4px、15px 下的可视验收结果。

- [ ] **Step 1: 运行全量测试**

Run:

```powershell
python -m pytest -q
```

Expected: 全部测试通过，无 error、failure 或异常 skip 增长。

- [ ] **Step 2: 运行显示-only 审计**

Run:

```powershell
git show --stat --oneline HEAD
git diff HEAD^ --check
rg -n "User interface radius preference|report-nav-branch-panel|dark-mode-toggle|history-summary-item|flow-chain-list|pbc-upload-area|db-validation-source-row|about-tech" src/auto_check/web/styles.css tests/test_web_static.py README.md
```

Expected: 当前实现提交只涉及 `styles.css`、`test_web_static.py`、`README.md`；集中式覆盖层仍只有 `border-radius`，无业务代码变化。

- [ ] **Step 3: 只停止当前 worktree 的旧可执行文件**

Run:

```powershell
$exePath = (Resolve-Path "dist\auto-check.exe").Path
Get-CimInstance Win32_Process -Filter "Name = 'auto-check.exe'" |
  Where-Object { $_.ExecutablePath -eq $exePath } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Expected: 仅停止可执行路径等于当前 worktree `dist\auto-check.exe` 的进程；不处理其他目录的同名进程。

- [ ] **Step 4: 刷新 Windows 可执行文件**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1 -SkipTests
```

Expected: PyInstaller 退出码 0，`dist\auto-check.exe` 更新时间刷新且文件非空。

- [ ] **Step 5: 打包后复跑关键测试与完整性检查**

Run:

```powershell
python -m pytest -q tests/test_web_static.py tests/test_server.py tests/test_security.py
git diff --check
Get-FileHash dist\auto-check.exe -Algorithm SHA256
Get-Item dist\auto-check.exe | Select-Object FullName, Length, LastWriteTime
```

Expected: 测试全部通过；无 whitespace error；exe 有 SHA256、非零长度和新的修改时间。

- [ ] **Step 6: 提交打包产物**

```powershell
git add dist/auto-check.exe
git commit -m "build: refresh Windows executable"
```

- [ ] **Step 7: 隐藏启动新可执行文件并检查 HTTP**

Run:

```powershell
$exePath = (Resolve-Path "dist\auto-check.exe").Path
$process = Start-Process -FilePath $exePath -WorkingDirectory (Get-Location) -WindowStyle Hidden -PassThru
$process.Id
$response = $null
for ($attempt = 0; $attempt -lt 20; $attempt++) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing http://localhost:8765/ -TimeoutSec 2
    break
  } catch {
    Start-Sleep -Milliseconds 500
  }
}
if (-not $response) { throw "auto-check did not become ready on port 8765" }
$response | Select-Object StatusCode
```

Expected: 返回新进程 ID，首页 HTTP 状态为 200。

- [ ] **Step 8: 使用浏览器验证 1px、4px、15px 预览**

在已登录页面进入“系统设置→界面设置”；如果会话失效，使用现有管理员账号重新登录。分别把滑块拖到 1px、4px、15px，但不点击保存，逐类抽查：

- 报送导航：鱼骨详情卡、报送日期分组卡、注意事项卡。
- 暗色模式：切换按钮外壳跟随数值，内部月亮图形不变。
- 历史/流程/逐笔：历史详情卡、流程链列表与摘要、执行日志、两类执行历史表格外框。
- 工具/设置：上传区、系统信息指标卡、逐笔数据源配置行、流程链与数据源配置行、关于系统三类内容卡。

Expected: 所有矩形目标的计算样式 `border-radius` 与滑块值一致；复选框、圆形图标、状态点、进度条和表格行保持原样；弹窗开关、暗色切换、流程选择、历史查看和文件选择入口仍可操作。

- [ ] **Step 9: 恢复已保存值并记录最终状态**

离开系统设置页触发未保存预览撤销，再返回界面设置确认显示已保存的 4px；不要把 1px 或 15px 写入数据库。

Run:

```powershell
git status --short
git log -3 --oneline
```

Expected: 工作区干净；最近提交依次包含设计补充、CSS/测试/README 实现和 exe 刷新。
