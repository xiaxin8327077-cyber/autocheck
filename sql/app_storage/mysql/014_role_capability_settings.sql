-- Auto Check role capability settings storage schema
-- Run this against an existing, manually created auto_check database after backing up production data.
-- Safety: the script creates only an idempotent platform table and never changes app_schema_version or application data.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `auto_check`;

CREATE TABLE IF NOT EXISTS `role_capability_settings` (
  `id` TINYINT UNSIGNED NOT NULL COMMENT '固定主键，仅允许 1',
  `matrix_json` JSON NOT NULL COMMENT '角色×能力矩阵快照（JSON）',
  `remarks_json` JSON NULL COMMENT '角色备注（role→remark，JSON）',
  `version` INT NOT NULL DEFAULT 1 COMMENT '矩阵版本号，一期固定为 1',
  `updated_by` VARCHAR(64) NULL COMMENT '更新人用户 ID',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  CONSTRAINT `chk_role_capability_settings_singleton` CHECK (`id` = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='角色能力矩阵配置（单行 JSON 快照）';
