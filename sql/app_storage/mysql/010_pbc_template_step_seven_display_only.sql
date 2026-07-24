INSERT INTO `report_nav_step_fields`
  (`step_source_id`, `field_role`, `column_name`)
SELECT `id`, 'create_date_field', 'create_date'
FROM `report_nav_step_sources`
WHERE `step_code` = 'pbc_template_6'
  AND `source_role` = 'primary'
ON DUPLICATE KEY UPDATE `column_name`=VALUES(`column_name`);

DELETE FROM `report_nav_step_overrides`
WHERE `step_code` = 'pbc_template_7';

DELETE FROM `report_nav_step_snapshots`
WHERE `step_code` = 'pbc_template_7';

DELETE FROM `report_nav_step_values`
WHERE `step_code` = 'pbc_template_7';

DELETE FROM `report_nav_step_dependencies`
WHERE `step_code` = 'pbc_template_7'
   OR `depends_on_step_code` = 'pbc_template_7';

DELETE FROM `report_nav_step_fields`
WHERE `step_source_id` IN (
  SELECT `id`
  FROM `report_nav_step_sources`
  WHERE `step_code` = 'pbc_template_7'
);

DELETE FROM `report_nav_step_sources`
WHERE `step_code` = 'pbc_template_7';

INSERT INTO `report_nav_steps`
  (`step_code`, `process_code`, `step_name`, `display_order`, `evaluator_key`,
   `enabled`, `default_completed`, `manual_completion_allowed`)
VALUES
  ('pbc_template_7', 'pbc_template', '归档后制表人填写数据调整情况说明（如有）',
   7, 'display_only', 1, 0, 0)
ON DUPLICATE KEY UPDATE
  `process_code`=VALUES(`process_code`),
  `step_name`=VALUES(`step_name`),
  `display_order`=VALUES(`display_order`),
  `evaluator_key`=VALUES(`evaluator_key`),
  `enabled`=VALUES(`enabled`),
  `default_completed`=VALUES(`default_completed`),
  `manual_completion_allowed`=VALUES(`manual_completion_allowed`);

DELETE FROM `report_nav_process_snapshots`
WHERE `process_code` = 'pbc_template';
