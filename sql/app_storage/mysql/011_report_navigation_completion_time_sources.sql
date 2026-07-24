DELETE FROM `report_nav_step_fields`
WHERE `field_role` = 'update_date_field'
  AND `step_source_id` IN (
    SELECT `source`.`id`
    FROM `report_nav_step_sources` AS `source`
    INNER JOIN `report_nav_steps` AS `step`
      ON `step`.`step_code` = `source`.`step_code`
    WHERE `step`.`evaluator_key` IN ('all_versions_present', 'version_present')
  );

INSERT INTO `report_nav_step_sources`
  (`step_code`, `source_role`, `data_source_name`, `table_name`, `display_order`, `enabled`)
VALUES
  ('pbc_central_4', 'completion_time', 'currency_report_24',
   'currency_report_duration', 3, 1)
ON DUPLICATE KEY UPDATE
  `data_source_name`=VALUES(`data_source_name`),
  `table_name`=VALUES(`table_name`),
  `enabled`=VALUES(`enabled`);

INSERT INTO `report_nav_step_fields`
  (`step_source_id`, `field_role`, `column_name`)
SELECT `id`, 'period_field', 'caldate'
FROM `report_nav_step_sources`
WHERE `step_code` = 'pbc_central_4'
  AND `source_role` = 'completion_time'
ON DUPLICATE KEY UPDATE `column_name`=VALUES(`column_name`);

INSERT INTO `report_nav_step_fields`
  (`step_source_id`, `field_role`, `column_name`)
SELECT `id`, 'create_date_field', 'create_date'
FROM `report_nav_step_sources`
WHERE `step_code` = 'pbc_central_4'
  AND `source_role` = 'completion_time'
ON DUPLICATE KEY UPDATE `column_name`=VALUES(`column_name`);

DELETE FROM `report_nav_process_snapshots`
WHERE `process_code` IN (
  'pbc_central',
  'pbc_template',
  'jr_1104',
  'full_elements',
  'citic_registration',
  'east5',
  'five_articles'
);
