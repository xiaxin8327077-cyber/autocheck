-- Auto Check role definitions storage schema
-- Run this against an existing, manually created auto_check database after backing up production data.
-- Safety: the script creates only an idempotent platform table and never changes app_schema_version or application data.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `auto_check`;

CREATE TABLE IF NOT EXISTS `role_definitions` (
  `role_code` VARCHAR(32) NOT NULL COMMENT '角色码（自定义角色由系统生成 custom_<序号>）',
  `display_name` VARCHAR(64) NOT NULL COMMENT '角色显示名',
  `remark` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '角色备注',
  `is_system` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否系统内建角色（1=内建，0=自定义）',
  `created_by` VARCHAR(64) NULL COMMENT '创建人用户 ID',
  `created_at` DATETIME(6) NOT NULL COMMENT '创建时间',
  `updated_by` VARCHAR(64) NULL COMMENT '更新人用户 ID',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`role_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='角色定义表（自定义角色；系统内建角色由代码常量定义，不存本表）';