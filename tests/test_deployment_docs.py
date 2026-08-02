from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MYSQL_STORAGE_DOC = ROOT / "docs" / "mysql-application-storage.zh-CN.md"
DEPLOYMENT_DOC = ROOT / "docs" / "deployment.zh-CN.md"
INTRANET_DEPLOYMENT_DOC = ROOT / "docs" / "intranet-production-deployment.zh-CN.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_sql_order(section: str, scripts: list[str]) -> None:
    positions = [section.index(script) for script in scripts]
    assert positions == sorted(positions)


def _changelog_version_block(markdown: str, version: str) -> str:
    return next(
        section
        for section in re.split(r"(?m)(?=^`v\d+(?:\.\d+)+`)", markdown)
        if section.startswith(f"`{version}`")
    )


def test_changelog_version_block_stops_at_multi_segment_version() -> None:
    changelog = """`v2.1` (2026-07-02)
- 系统优化及BUG修复。

`v2.0.8` (2026-06-12)
- 新增用户级界面圆角个性化设置：旧版本内容。
"""

    v21_changes = _changelog_version_block(changelog, "v2.1")

    assert "`v2.0.8`" not in v21_changes
    assert "旧版本内容" not in v21_changes


def test_readme_documents_user_interface_radius_behavior_and_scope() -> None:
    readme = _read(README)
    current_features = readme.split("## 当前功能", 1)[1].split(
        "## MySQL 应用库上线准备", 1
    )[0]
    system_settings = next(
        line for line in current_features.splitlines() if line.startswith("- 系统设置：")
    )
    latest_changes = readme.split("## 最新变更说明", 1)[1]
    v21_changes = _changelog_version_block(latest_changes, "v2.1")
    v21_radius_change = next(
        line
        for line in v21_changes.splitlines()
        if line.startswith("- 新增用户级界面圆角个性化设置：")
    )

    for expected in [
        "每个用户独立",
        "系统设置→界面设置",
        "1–15px",
        "默认 4px",
        "拖动即可预览",
        "显式保存",
        "仅影响显示，不改变系统功能",
        "导航",
        "卡片",
        "按钮",
        "输入框",
        "选择控件",
        "弹窗及弹窗内控件",
        "特殊形状",
    ]:
        assert expected in system_settings

    for expected in [
        "系统设置→界面设置",
        "1–15px",
        "默认 4px",
        "拖动即时预览并显式保存",
        "弹窗及弹窗内控件",
        "仅影响显示、不改变系统功能",
        "特殊形状保持原样",
    ]:
        assert expected in v21_radius_change


def test_readme_documents_fixed_logo_theme_and_personal_line_style() -> None:
    readme = _read(README)
    current_features = readme.split("## 当前功能", 1)[1].split(
        "## MySQL 应用库上线准备", 1
    )[0]
    latest_changes = readme.split("## 最新变更说明", 1)[1]
    v21_changes = _changelog_version_block(latest_changes, "v2.1")

    for expected in [
        "#3466D9",
        "#6AA4FF",
        "固定采用 Logo 蓝",
        "不再提供自定义主题色入口",
        "语义颜色",
        "每期执行次数折线使用 Logo 橙色渐变",
        "直线折线",
        "平滑曲线",
        "默认直线折线",
        "登录页",
        "强制浅色",
    ]:
        assert expected in current_features

    for expected in [
        "固定 Logo 蓝渐变",
        "#3466D9",
        "#6AA4FF",
        "移除系统设置中的自定义主题色入口",
        "默认直线折线",
        "平滑曲线",
        "登录页",
        "强制浅色",
    ]:
        assert expected in v21_changes


def test_rollout_docs_distinguish_migrated_rows_from_complete_mysql_schema() -> None:
    acceptance_sections = {
        README: next(
            line for line in _read(README).splitlines() if "上线核验" in line
        ),
        DEPLOYMENT_DOC: next(
            line
            for line in _read(DEPLOYMENT_DOC).splitlines()
            if "上线验收" in line
        ),
        INTRANET_DEPLOYMENT_DOC: next(
            line
            for line in _read(INTRANET_DEPLOYMENT_DOC).splitlines()
            if "上线验收" in line
        ),
        MYSQL_STORAGE_DOC: _read(MYSQL_STORAGE_DOC)
        .split("## 五、验收口径", 1)[1]
        .split("## 六、回滚", 1)[0],
    }

    for acceptance in acceptance_sections.values():
        assert "原 20 张迁移目标表的数据行数" in acceptance
        assert "与迁移报告一致" in acceptance
        assert "当前完整 43 张应用存储表结构" in acceptance
        assert "012_module_system.sql" in acceptance
        assert "013_report_navigation_provider_states.sql" in acceptance
        assert "备份" in acceptance
        assert "人工执行" in acceptance
        assert "39 张目标表和迁移行数齐全" not in acceptance


def test_mysql_rollout_docs_require_module_schema_upgrade_sequence() -> None:
    for path in [README, MYSQL_STORAGE_DOC, DEPLOYMENT_DOC, INTRANET_DEPLOYMENT_DOC]:
        text = _read(path)
        scripts = [
            "001_init_schema.sql",
            "002_report_navigation.sql",
            "003_report_navigation_seed.sql",
            "004_user_interface_preferences.sql",
            "005_user_appearance_preferences.sql",
            "006_system_interface_preferences.sql",
            "007_report_navigation_schedule_owner.sql",
            "008_report_navigation_work_calendar.sql",
            "009_report_navigation_manual_step_permissions.sql",
            "010_pbc_template_step_seven_display_only.sql",
            "011_report_navigation_completion_time_sources.sql",
            "012_module_system.sql",
            "013_report_navigation_provider_states.sql",
        ]
        assert "43 张" in text
        if path == README:
            preparation = text.split("上线前需要按以下顺序处理：", 1)[1].split("示例：", 1)[0]
        elif path == MYSQL_STORAGE_DOC:
            preparation = text.split("## 二、上线与升级顺序", 1)[1].split("## 三、", 1)[0]
        else:
            preparation = text.split("## MySQL 应用库", 1)[1].split("`app_database`", 1)[0]
        _assert_sql_order(preparation, scripts)

    mysql_doc = _read(MYSQL_STORAGE_DOC)
    assert "user_interface_preferences" in mysql_doc
    assert "每个用户" in mysql_doc
    assert "不设置外键" in mysql_doc
    assert "孤儿偏好" in mysql_doc
    assert "system_interface_preferences" in mysql_doc
    assert "绝不使用 `app_settings`" in mysql_doc


def test_deployment_upgrade_docs_define_safe_manual_004_through_008_boundary() -> None:
    for path in [DEPLOYMENT_DOC, INTRANET_DEPLOYMENT_DOC]:
        text = _read(path)
        assert "升级应用前" in text
        assert "CREATE TABLE IF NOT EXISTS" in text
        assert "information_schema" in text
        assert "可重复执行" in text
        assert "不代表已在任何线上环境执行" in text
        assert "每个用户" in text
        assert "不设置外键" in text
        assert "孤儿偏好" in text
        assert "012_module_system.sql" in text
        assert "013_report_navigation_provider_states.sql" in text
        assert "43 张" in text
        assert "app_schema_version" in text
        assert "备份" in text
        assert "人工执行" in text


def test_operator_followable_upgrade_sequences_include_013_after_012() -> None:
    scripts_001_to_013 = [
        "001_init_schema.sql",
        "002_report_navigation.sql",
        "003_report_navigation_seed.sql",
        "004_user_interface_preferences.sql",
        "005_user_appearance_preferences.sql",
        "006_system_interface_preferences.sql",
        "007_report_navigation_schedule_owner.sql",
        "008_report_navigation_work_calendar.sql",
        "009_report_navigation_manual_step_permissions.sql",
        "010_pbc_template_step_seven_display_only.sql",
        "011_report_navigation_completion_time_sources.sql",
        "012_module_system.sql",
        "013_report_navigation_provider_states.sql",
    ]
    scripts_004_to_013 = scripts_001_to_013[3:]

    for path in [DEPLOYMENT_DOC, INTRANET_DEPLOYMENT_DOC]:
        text = _read(path)
        preparation = text.split("## MySQL 应用库", 1)[1].split("`app_database`", 1)[0]
        follow_up = next(
            line for line in text.splitlines() if line.startswith("`user_interface_preferences`")
        )
        _assert_sql_order(preparation, scripts_001_to_013)
        _assert_sql_order(follow_up, scripts_004_to_013)
        assert follow_up.index("013_report_navigation_provider_states.sql") < follow_up.index("再替换应用")
        assert "先备份" in follow_up
        assert "人工执行" in follow_up

    storage = _read(MYSQL_STORAGE_DOC)
    storage_follow_up = next(
        line for line in storage.splitlines() if line.startswith("从已完成 `001`")
    )
    offline_export = storage.split("### 离线导出", 1)[1].split("## 五、验收口径", 1)[0]
    _assert_sql_order(storage_follow_up, scripts_004_to_013)
    assert storage_follow_up.index("013_report_navigation_provider_states.sql") < storage_follow_up.index("再部署新程序")
    _assert_sql_order(offline_export, scripts_004_to_013)
    assert "备份" in offline_export
    assert "人工执行" in offline_export

    readme_incremental = next(
        line for line in _read(README).splitlines() if line.startswith("- 应用存储增量升级：")
    )
    _assert_sql_order(readme_incremental, scripts_001_to_013[6:])
    assert "备份" in readme_incremental
    assert "人工执行" in readme_incremental


def test_empty_mysql_upgrade_runs_002_through_012_with_documented_prerequisites() -> None:
    upgrade = _read(ROOT / "docs" / "production-baseline-diff-audit-2026-07-24.zh-CN.md").split(
        "## 建议升级顺序", 1
    )[1]
    scripts = [
        "002_report_navigation.sql",
        "003_report_navigation_seed.sql",
        "004_user_interface_preferences.sql",
        "005_user_appearance_preferences.sql",
        "006_system_interface_preferences.sql",
        "007_report_navigation_schedule_owner.sql",
        "008_report_navigation_work_calendar.sql",
        "009_report_navigation_manual_step_permissions.sql",
        "010_pbc_template_step_seven_display_only.sql",
        "011_report_navigation_completion_time_sources.sql",
        "012_module_system.sql",
    ]

    _assert_sql_order(upgrade, scripts)
    for prerequisite in [
        "002：依赖导出的 20 张基础表",
        "003：依赖 `002` 创建的报送导航表",
        "004：独立创建用户界面偏好表",
        "005：依赖 `004` 创建的 `user_interface_preferences`",
        "006：独立创建系统界面偏好表",
        "007：依赖 `002` 创建的 `report_nav_monthly_schedules`",
        "008：独立创建工作日日历表",
        "009：依赖 `002` 创建的 `report_nav_steps`",
        "010：依赖 `002` 创建的报送导航表",
        "011：依赖 `002` 创建的报送导航表",
        "012：仅创建模块平台表",
    ]:
        assert prerequisite in upgrade


def test_mysql_storage_doc_contains_complete_final_interface_preference_ddl() -> None:
    mysql_doc = _read(MYSQL_STORAGE_DOC)
    canonical = mysql_doc.split("## 三、界面偏好完整规范 DDL", 1)[1].split(
        "## 四、配置示例", 1
    )[0]

    for expected in [
        "CREATE TABLE `user_interface_preferences`",
        "`user_id` VARCHAR(64) NOT NULL",
        "`radius_px` TINYINT UNSIGNED NOT NULL DEFAULT 4",
        "`line_chart_style` VARCHAR(16) NOT NULL DEFAULT 'straight'",
        "`vitality_theme_color` CHAR(7) NULL",
        "`calm_theme_color` CHAR(7) NULL",
        "CONSTRAINT `chk_user_interface_radius_px` CHECK (`radius_px` BETWEEN 1 AND 15)",
        "CONSTRAINT `chk_user_interface_line_chart_style` CHECK (`line_chart_style` IN ('straight', 'smooth'))",
        "CONSTRAINT `chk_user_interface_vitality_theme_color`",
        "CONSTRAINT `chk_user_interface_calm_theme_color`",
        "CREATE TABLE `system_interface_preferences`",
        "`id` TINYINT UNSIGNED NOT NULL",
        "`vitality_theme_color` CHAR(7) NOT NULL DEFAULT '#3466D9'",
        "`calm_theme_color` CHAR(7) NOT NULL DEFAULT '#355F63'",
        "`updated_by` VARCHAR(64) NULL",
        "CONSTRAINT `chk_system_interface_preferences_singleton` CHECK (`id` = 1)",
        "CONSTRAINT `chk_system_interface_vitality_theme_color`",
        "CONSTRAINT `chk_system_interface_calm_theme_color`",
        "REGEXP_LIKE(`vitality_theme_color`, '^#[0-9A-F]{6}$', 'c')",
        "REGEXP_LIKE(`calm_theme_color`, '^#[0-9A-F]{6}$', 'c')",
    ]:
        assert expected in canonical

    assert "theme_gradient_enabled" not in canonical
    assert "app_settings" not in canonical
    assert "BINARY `vitality_theme_color` REGEXP" not in canonical
    assert "BINARY `calm_theme_color` REGEXP" not in canonical
