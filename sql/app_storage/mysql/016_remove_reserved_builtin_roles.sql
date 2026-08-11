-- Auto Check: remove reserved builtin roles (governance / regulatory_report / data_middle / fund_custody)
-- Run against existing auto_check DB after backup. Does not change app_schema_version.
-- Effect:
--   1) Remap users on those roles to ordinary user
--   2) Delete leftover rows for those role codes from role_definitions (if table exists)
--   3) Matrix/remarks JSON keys for those roles are ignored by app runtime merge

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `auto_check`;

UPDATE `users`
SET `role` = 'user',
    `updated_at` = CURRENT_TIMESTAMP(6)
WHERE `role` IN ('governance', 'regulatory_report', 'data_middle', 'fund_custody');

DELETE FROM `role_definitions`
WHERE `role_code` IN ('governance', 'regulatory_report', 'data_middle', 'fund_custody');
