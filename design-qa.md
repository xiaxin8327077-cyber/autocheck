# 报送导航统计周期与报送时间 Design QA

- source visual truth path: `D:\xiaxin\wx\xwechat_files\ccqlove_5f6d\msg\file\2026-07\11\ac124736-b3bc-404d-ac31-00fb0223ad5a.png`
- implementation screenshot path: `D:\xiaxin\auto_check\.worktrees\mysql-app-storage\build\report-navigation-qa-light.png`
- dark implementation screenshot path: `D:\xiaxin\auto_check\.worktrees\mysql-app-storage\build\report-navigation-qa-dark.png`
- narrow implementation screenshot path: `D:\xiaxin\auto_check\.worktrees\mysql-app-storage\build\report-navigation-qa-narrow.png`
- calm-title implementation screenshot path: `D:\xiaxin\auto_check\.worktrees\mysql-app-storage\build\report-navigation-qa-calm-title.png`
- calm dark-title implementation screenshot path: `D:\xiaxin\auto_check\.worktrees\mysql-app-storage\build\report-navigation-qa-calm-dark-title.png`
- vitality-title implementation screenshot path: `D:\xiaxin\auto_check\.worktrees\mysql-app-storage\build\report-navigation-qa-vitality-title.png`
- title comparison evidence: `D:\xiaxin\auto_check\.worktrees\mysql-app-storage\build\report-navigation-qa-title-comparison.png`
- full-view comparison evidence: `D:\xiaxin\auto_check\.worktrees\mysql-app-storage\build\report-navigation-qa-comparison.png`
- focused flow-header comparison evidence: `D:\xiaxin\auto_check\.worktrees\mysql-app-storage\build\report-navigation-qa-flow-comparison.png`
- focused period comparison evidence: `D:\xiaxin\auto_check\.worktrees\mysql-app-storage\build\report-navigation-qa-period-comparison.png`
- viewport: desktop `1869 × 810`; responsive check `1000 × 810`（浏览器内容宽度 985px）
- state: 报送导航、浅色活力主题；另核验沉稳主题标题、沉稳暗色标题和 1100px 以下响应式回退

## Full-view comparison

设计稿与实现截图在同一比较图中核验。统计周期已去除整行卡片容器并恢复蓝色短横线、标签和浅蓝选择框；报送时间已恢复暖黄色卡片、黄色机构标签和蓝色日期。根据用户确认的定制要求，实现中的两块报送时间卡片相对整张流程卡片水平居中，而设计稿原图位于右侧，此处属于明确的预期差异。

新增主题差异也已通过浏览器渲染核验：沉稳主题在统计周期同行左侧显示 20px、700 字重的“报送导航”，活力主题的计算样式为 `display: none`，因此与设计稿顶部区域一样不出现页面内标题。沉稳暗色模式下标题保持可读的浅色前景。

## Focused comparison

- 统计周期：容器背景透明、边框为 0、阴影为 none；标签与选择框的颜色、间距、圆角和箭头位置与设计稿一致。
- 报送时间：卡片内边距、暖黄色渐变、橙色边框、机构标签、正文层级和蓝色日期与设计稿一致；卡片内部文字保持左对齐。
- 居中：浏览器测得流程卡片中心与报送时间卡片组中心偏差为 `0px`。
- 主题标题：沉稳主题标题显示且字号为 `20px`；活力主题标题隐藏；沉稳暗色标题颜色为 `rgb(225, 227, 229)`。

## Required fidelity surfaces

- Fonts and typography: 沿用应用现有字体栈；沉稳主题页面标题为 20px/700，与其他页面标题一致；标签为 13px/800，正文为 12.5px、1.65 行高，日期为 12px 等宽字体；未发现影响阅读的换行或截断。
- Spacing and layout rhythm: 统计周期采用 `12px` 间距及 `4px 2px 0` 内边距；时间卡片采用 `10px 14px` 内边距及 `12px` 间距。桌面端整体精确居中，窄屏回退后标题在上、时间卡片在下且无横向溢出。
- Colors and visual tokens: 浅色模式匹配设计稿的蓝色周期控件和暖黄色时间卡片；暗色模式保留蓝色日期、暖色边框及足够对比度。
- Image quality and asset fidelity: 目标区域不包含位图资产；统计周期箭头复用设计稿提供的原始 SVG 路径，没有新增近似图形。
- Copy and content: 统计周期选项、人行/金监标签、项目名称和日期与设计稿及正式页面一致。

## Primary interactions and runtime checks

- 原生统计周期下拉框保留可选择结构，并具备 hover/focus 样式。
- 活力浅色、沉稳浅色、沉稳暗色和窄屏状态均由浏览器实际渲染。
- 浏览器控制台未发现 error 或 warning。

## Findings

没有可执行的 P0、P1 或 P2 差异。报送时间从设计稿右对齐改为整体居中，以及沉稳主题专属页面标题，均是用户确认的有意变化。

## Comparison history

- Pass 1: 全景和两个重点区域比较均未发现 P0/P1/P2 问题；无需视觉修复迭代。
- Pass 2: 新增沉稳主题专属标题后，浏览器核验标题在沉稳浅色/暗色主题显示、活力主题隐藏；流程时间卡片组中心偏差仍为 0px，未引入新的 P0/P1/P2 问题。

## Follow-up polish

无阻塞性交付项。

final result: passed
