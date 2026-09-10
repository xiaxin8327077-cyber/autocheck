SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `auto_check`;

INSERT INTO `system_dictionaries` (
  `dictionary_code`, `dictionary_name`, `description`,
  `enabled`, `system_locked`, `sort_order`,
  `created_by`, `created_at`, `updated_by`, `updated_at`
) VALUES (
  'report_period_field', '报送期字段匹配', '报表特殊处理自动识别数据日期字段时使用的匹配词',
  1, 1, 20,
  'system', CURRENT_TIMESTAMP(6), 'system', CURRENT_TIMESTAMP(6)
) ON DUPLICATE KEY UPDATE `dictionary_code` = `dictionary_code`;

INSERT INTO `system_dictionary_items` (
  `dictionary_code`, `item_code`, `item_name`, `description`,
  `enabled`, `sort_order`,
  `created_by`, `created_at`, `updated_by`, `updated_at`
) VALUES
  ('report_period_field', 'cldate', 'cldate', '数据日期字段匹配词', 1, 10, 'system', CURRENT_TIMESTAMP(6), 'system', CURRENT_TIMESTAMP(6)),
  ('report_period_field', 'caldate', 'caldate', '数据日期字段匹配词', 1, 20, 'system', CURRENT_TIMESTAMP(6), 'system', CURRENT_TIMESTAMP(6))
ON DUPLICATE KEY UPDATE `item_code` = `item_code`;
