# Task 7 Report: Hide Data Management Settings Card

## 修改范围

- 从 `src/auto_check/web/index.html` 移除了系统设置整张“数据管理”卡及其清理历史、导出配置、导入配置入口的 DOM。
- “默认设置”卡保留原有控件与 DOM 内容，并因前述卡片移除而前移至顶部三列布局的第三列。
- 更新 `tests/test_web_static.py` 静态结构断言：数据管理 DOM 不再存在、默认设置紧随界面设置、既有处理器仍保留。
- 更新 `README.md` 当前系统设置说明和 v2.1 详细变更；更新 `src/auto_check/web/app.js` 当前 v2.1 应用内日志日期，既有精简条目保持为“系统优化及BUG修复”。
- 将 Task 7 的补充范围（默认设置前移）写入批准计划。

## 保留的后台与 JS 逻辑

- 未修改后端接口。
- 未移除 `dataManageToggle` 折叠初始化，以及清理历史、导出配置、导入配置和文件导入的既有 JavaScript handler/function；由于页面入口移除，这些逻辑不再由设置页展示触发。

## 验证边界

- 按用户要求，未运行任何自动化测试。
- 按用户要求，未做页面、HTTP 或浏览器验收。
- 已执行 `git diff --check`；仅出现既有 CRLF/LF 提示，无 whitespace error。

## 打包产物

- 构建前仅停止了 `ExecutablePath` 精确匹配当前 worktree `dist\\auto-check.exe` 的进程。
- Codex Python 缺少 PyInstaller；已只读定位并验证系统 Python 3.12 与 PyInstaller 6.21.0。
- 打包命令：`powershell -ExecutionPolicy Bypass -File scripts\\package-windows.ps1 -SkipTests -Clean -PythonPath 'C:\\Users\\jh832\\AppData\\Local\\Programs\\Python\\Python312\\python.exe'`
- 产物：`dist\\auto-check.exe`
- SHA256：`3C9CDAF7FACFC20A18AA5A58B56161937946D8C4164ACC780EAEEE77FD0D24EF`
- 大小：30,377,471 bytes
- 时间：2026-07-18 15:21:23 +08:00

## Commit

- `fix: hide data management settings card`
