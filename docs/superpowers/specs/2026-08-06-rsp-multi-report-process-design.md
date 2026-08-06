# 报表特殊处理关联报送多选

日期：2026-08-06

## 目标

一条特殊处理记录可关联多个报送流程；「全部」页签仍显示一行；列表「关联报送」列用顿号拼接名称；多选控件适当加宽。

## 方案

- 新增子表 `report_special_processing_processes` 存多选；主表 `report_process_code` 保留为首项，`report_process_name_snapshot` 加宽为拼接名称。
- API 使用 `report_process_codes: string[]`（兼容单值 `report_process_code`）。
- 页签筛选与按报送统计走子表；同一记录在多个页签各计一次，全部按记录计一次。
- 前端本模块多选勾选控件，选择框加宽；不改全站下拉。

## 迁移

`002_multi_report_processes.sql`：建子表、回填、加宽名称快照列；`manifest.schema_version` → 2。
