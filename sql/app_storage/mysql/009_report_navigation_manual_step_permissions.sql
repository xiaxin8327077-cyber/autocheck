UPDATE `report_nav_steps`
SET `manual_completion_allowed` = CASE
  WHEN `step_code` = 'pbc_template_7' THEN 1
  ELSE 0
END;
