# Vitality Top Navigation Centering Implementation Plan

**Goal:** Keep the vitality-theme page buttons visually centered across the full top bar while preserving the user control on the right and placing the dark-mode toggle immediately to its left.

**Architecture:** Split the top bar into brand, page navigation, and action regions. Use equal flexible outer CSS Grid columns around the intrinsic-width center navigation so unequal brand and action widths cannot shift the menu away from the viewport center. Collapse to a two-row grid below 900px and retain horizontal menu scrolling on narrow screens.

**Tech Stack:** Static HTML, CSS Grid/Flexbox, pytest static-structure tests, existing PowerShell packaging script.

### Task 1: Lock the layout contract with a static test

- [x] Assert that page links remain inside `.top-nav-tabs` and that dark/user controls move into `.top-nav-actions` in the requested order.
- [x] Assert equal outer grid tracks, centered tabs, and right-aligned actions.
- [x] Run the focused test and confirm it fails before implementation.

### Task 2: Implement desktop and narrow-screen layouts

- [x] Move the dark-mode and user controls into a dedicated action container.
- [x] Use `minmax(0, 1fr) auto minmax(0, 1fr)` for exact desktop centering.
- [x] Use brand/actions on row one and a centered, horizontally scrollable menu on row two below 900px.
- [x] Keep the menu scrollable from the leading edge below 640px.

### Task 3: Document and verify

- [x] Update README with the visible behavior change; keep the in-app changelog at the required generic “系统优化及BUG修复” wording.
- [x] Run focused/static/full tests and `git diff --check`.
- [x] Stop any packaged executable using the target path, rebuild `dist/auto-check.exe`, and record its checksum.
