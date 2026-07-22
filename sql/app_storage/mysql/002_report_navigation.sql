CREATE TABLE IF NOT EXISTS `report_nav_processes` (
  `process_code` VARCHAR(64) NOT NULL COMMENT '流程节点编码',
  `process_name` VARCHAR(128) NOT NULL COMMENT '流程节点名称',
  `display_order` INT NOT NULL COMMENT '展示顺序',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `allow_manual_step_completion` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否允许手工完成步骤',
  PRIMARY KEY (`process_code`),
  KEY `idx_report_nav_processes_order` (`enabled`, `display_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航流程节点配置';

CREATE TABLE IF NOT EXISTS `report_nav_process_months` (
  `process_code` VARCHAR(64) NOT NULL COMMENT '流程节点编码',
  `month_no` TINYINT UNSIGNED NOT NULL COMMENT '适用月份（1至12）',
  PRIMARY KEY (`process_code`, `month_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航流程适用月份';

CREATE TABLE IF NOT EXISTS `report_nav_steps` (
  `step_code` VARCHAR(64) NOT NULL COMMENT '步骤编码',
  `process_code` VARCHAR(64) NOT NULL COMMENT '所属流程节点编码',
  `step_name` VARCHAR(255) NOT NULL COMMENT '步骤名称',
  `display_order` INT NOT NULL COMMENT '展示顺序',
  `evaluator_key` VARCHAR(64) NOT NULL COMMENT '固定判断器编码',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `default_completed` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否默认完成',
  `manual_completion_allowed` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否允许手工完成',
  PRIMARY KEY (`step_code`),
  KEY `idx_report_nav_steps_process_order` (`process_code`, `enabled`, `display_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航流程步骤配置';

CREATE TABLE IF NOT EXISTS `report_nav_step_dependencies` (
  `step_code` VARCHAR(64) NOT NULL COMMENT '当前步骤编码',
  `depends_on_step_code` VARCHAR(64) NOT NULL COMMENT '依赖步骤编码',
  PRIMARY KEY (`step_code`, `depends_on_step_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航步骤依赖关系';

CREATE TABLE IF NOT EXISTS `report_nav_step_sources` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `step_code` VARCHAR(64) NOT NULL COMMENT '步骤编码',
  `source_role` VARCHAR(64) NOT NULL COMMENT '数据源角色',
  `data_source_name` VARCHAR(128) NOT NULL COMMENT '系统数据源名称',
  `table_name` VARCHAR(255) NOT NULL COMMENT '物理表名',
  `display_order` INT NOT NULL COMMENT '数据源展示顺序',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_report_nav_step_sources_role` (`step_code`, `source_role`, `display_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航步骤数据源配置';

CREATE TABLE IF NOT EXISTS `report_nav_step_fields` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `step_source_id` BIGINT NOT NULL COMMENT '步骤数据源配置ID',
  `field_role` VARCHAR(64) NOT NULL COMMENT '字段业务角色',
  `column_name` VARCHAR(128) NOT NULL COMMENT '物理字段名',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_report_nav_step_fields_role` (`step_source_id`, `field_role`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航步骤字段映射';

CREATE TABLE IF NOT EXISTS `report_nav_step_values` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `step_code` VARCHAR(64) NOT NULL COMMENT '步骤编码',
  `value_role` VARCHAR(64) NOT NULL COMMENT '参数角色',
  `value_text` VARCHAR(255) NOT NULL COMMENT '参数值',
  `value_type` VARCHAR(32) NOT NULL DEFAULT 'text' COMMENT '参数类型',
  `display_order` INT NOT NULL DEFAULT 0 COMMENT '参数值顺序',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_report_nav_step_values_role` (`step_code`, `value_role`, `display_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航步骤固定参数';

CREATE TABLE IF NOT EXISTS `report_nav_step_overrides` (
  `report_month` CHAR(7) NOT NULL COMMENT '报送月份（YYYY-MM）',
  `step_code` VARCHAR(64) NOT NULL COMMENT '步骤编码',
  `completed` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否人工完成',
  `operator_id` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '操作人用户ID',
  `operator_username` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '操作人账号',
  `operator_name` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '操作人姓名',
  `created_at` DATETIME(6) NOT NULL COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`report_month`, `step_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航步骤人工完成记录';

CREATE TABLE IF NOT EXISTS `report_nav_step_snapshots` (
  `report_month` CHAR(7) NOT NULL COMMENT '报送月份（YYYY-MM）',
  `step_code` VARCHAR(64) NOT NULL COMMENT '步骤编码',
  `auto_status` VARCHAR(32) NOT NULL COMMENT '自动判断状态',
  `effective_status` VARCHAR(32) NOT NULL COMMENT '最终生效状态',
  `completion_source` VARCHAR(32) NOT NULL COMMENT '完成来源（自动或手工）',
  `status_message` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '状态说明',
  `error_message` TEXT NULL COMMENT '判断错误信息',
  `auto_completed_at` DATETIME(6) NULL COMMENT '自动完成时间',
  `evaluated_at` DATETIME(6) NOT NULL COMMENT '统计时间',
  `run_id` BIGINT NULL COMMENT '统计任务ID',
  PRIMARY KEY (`report_month`, `step_code`),
  KEY `idx_report_nav_step_snapshots_run` (`run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航步骤统计快照';

CREATE TABLE IF NOT EXISTS `report_nav_process_snapshots` (
  `report_month` CHAR(7) NOT NULL COMMENT '报送月份（YYYY-MM）',
  `process_code` VARCHAR(64) NOT NULL COMMENT '流程节点编码',
  `total_steps` INT NOT NULL COMMENT '步骤总数',
  `completed_steps` INT NOT NULL COMMENT '已完成步骤数',
  `status` VARCHAR(32) NOT NULL COMMENT '流程节点状态',
  `completed_at` DATETIME(6) NULL COMMENT '流程节点全部完成时间',
  `evaluated_at` DATETIME(6) NOT NULL COMMENT '统计时间',
  `run_id` BIGINT NULL COMMENT '统计任务ID',
  PRIMARY KEY (`report_month`, `process_code`),
  KEY `idx_report_nav_process_snapshots_run` (`run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航流程节点统计快照';

CREATE TABLE IF NOT EXISTS `report_nav_card_snapshots` (
  `stat_period` VARCHAR(16) NOT NULL COMMENT '统计周期',
  `card_code` VARCHAR(64) NOT NULL COMMENT '统计卡编码',
  `total_count` INT NOT NULL COMMENT '总数',
  `completed_count` INT NOT NULL COMMENT '已完成数',
  `incomplete_count` INT NOT NULL COMMENT '未完成数',
  `comparison_delta` INT NULL COMMENT '与上一完整统计周期相比的已完成数变化',
  `completion_rate` DECIMAL(7,4) NOT NULL DEFAULT 0 COMMENT '完成率（百分比）',
  `evaluated_at` DATETIME(6) NOT NULL COMMENT '统计时间',
  `run_id` BIGINT NULL COMMENT '统计任务ID',
  PRIMARY KEY (`stat_period`, `card_code`),
  KEY `idx_report_nav_card_snapshots_run` (`run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航顶部统计卡快照';

CREATE TABLE IF NOT EXISTS `report_nav_card_manual_values` (
  `stat_period` VARCHAR(16) NOT NULL COMMENT '统计周期（week、month、quarter、year）',
  `card_code` VARCHAR(64) NOT NULL COMMENT '统计卡编码',
  `completed_count` INT NOT NULL DEFAULT 0 COMMENT '已完成数量',
  `incomplete_count` INT NOT NULL DEFAULT 0 COMMENT '未完成数量',
  `operator_id` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '操作人用户ID',
  `operator_username` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '操作人账号',
  `operator_name` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '操作人姓名',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`stat_period`, `card_code`),
  KEY `idx_report_nav_card_manual_values_card` (`card_code`, `stat_period`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航治理统计卡人工维护值';

CREATE TABLE IF NOT EXISTS `report_nav_card_manual_history` (
  `stat_period` VARCHAR(16) NOT NULL COMMENT '统计周期类型',
  `period_key` VARCHAR(16) NOT NULL COMMENT '真实自然周期标识',
  `card_code` VARCHAR(64) NOT NULL COMMENT '统计卡编码',
  `completed_count` INT NOT NULL DEFAULT 0 COMMENT '已完成数量',
  `incomplete_count` INT NOT NULL DEFAULT 0 COMMENT '未完成数量',
  `operator_id` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '操作人用户ID',
  `operator_username` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '操作人账号',
  `operator_name` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '操作人姓名',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`stat_period`, `period_key`, `card_code`),
  KEY `idx_report_nav_card_manual_history_card` (`card_code`, `stat_period`, `period_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航治理统计卡自然周期历史值';

CREATE TABLE IF NOT EXISTS `report_nav_monthly_schedules` (
  `report_month` CHAR(7) NOT NULL COMMENT '报送月份（YYYY-MM）',
  `process_code` VARCHAR(64) NOT NULL COMMENT '流程节点编码',
  `report_date` DATE NOT NULL COMMENT '报送日期',
  `source_type` VARCHAR(32) NOT NULL COMMENT '日期来源',
  `source_year` SMALLINT NULL COMMENT '来源年份',
  `owner_name` VARCHAR(128) NULL COMMENT '月度负责人',
  `updated_by` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '更新人',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`report_month`, `process_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航月度报送日期';

CREATE TABLE IF NOT EXISTS `report_nav_work_calendar` (
  `calendar_date` DATE NOT NULL COMMENT '日历日期',
  `calendar_year` SMALLINT NOT NULL COMMENT '日历年份',
  `day_type` VARCHAR(32) NOT NULL COMMENT '日期类型（holiday或adjusted_workday）',
  `day_name` VARCHAR(64) NOT NULL COMMENT '节假日或调休名称',
  `source_document` VARCHAR(255) NOT NULL COMMENT '国务院节假日安排文件',
  `updated_by` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '更新人',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`calendar_date`),
  KEY `idx_report_nav_work_calendar_year_type` (`calendar_year`, `day_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航中国法定工作日例外日历';

CREATE TABLE IF NOT EXISTS `report_nav_stat_runs` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `trigger_type` VARCHAR(32) NOT NULL COMMENT '触发类型',
  `report_month` CHAR(7) NOT NULL COMMENT '报送月份（YYYY-MM）',
  `business_report_date` DATE NULL COMMENT '业务报告期',
  `started_at` DATETIME(6) NOT NULL COMMENT '开始时间',
  `finished_at` DATETIME(6) NULL COMMENT '结束时间',
  `status` VARCHAR(32) NOT NULL COMMENT '执行状态',
  `completed_processes` INT NOT NULL DEFAULT 0 COMMENT '已完成流程节点数',
  `failed_steps` INT NOT NULL DEFAULT 0 COMMENT '判断异常步骤数',
  `error_message` TEXT NULL COMMENT '全局错误信息',
  PRIMARY KEY (`id`),
  KEY `idx_report_nav_stat_runs_month_started` (`report_month`, `started_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航统计任务执行记录';

CREATE TABLE IF NOT EXISTS `report_nav_scheduler_state` (
  `id` TINYINT NOT NULL COMMENT '固定主键',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `interval_minutes` INT NOT NULL DEFAULT 10 COMMENT '执行间隔（分钟）',
  `next_run_at` DATETIME(6) NULL COMMENT '下次计划时间',
  `lock_owner` VARCHAR(64) NULL COMMENT '租约锁持有者',
  `lock_until` DATETIME(6) NULL COMMENT '租约锁到期时间',
  `last_started_at` DATETIME(6) NULL COMMENT '最近开始时间',
  `last_finished_at` DATETIME(6) NULL COMMENT '最近完成时间',
  `last_status` VARCHAR(32) NULL COMMENT '最近执行状态',
  `last_error` TEXT NULL COMMENT '最近错误信息',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航定时任务状态';
