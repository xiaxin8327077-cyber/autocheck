-- 报表特殊处理录入：特殊处理内容升级为“数据源 → 处理表 → 处理字段 → 修改前/修改后”。
-- 1) datasource_id / datasource_name_snapshot / datasource_type 保存系统已配置数据源的引用与名称快照；
-- 2) structured_content_json 保存完整结构化内容（编辑回显的唯一事实来源），历史旧记录保持 NULL；
-- 3) table_name / field_name 继续存派生规范串（字段分组间用全角双分号分隔），value_before / value_after
--    放宽为 TEXT 并改存“每个关联字段一行、按字段顺序逐行对应”的派生聚合，供台账、导出、审计无缝展示。
ALTER TABLE report_special_processing_records
    ADD COLUMN datasource_id VARCHAR(64) NULL COMMENT '系统已配置数据源ID，历史手工录入记录为NULL' AFTER business_system_name_snapshot,
    ADD COLUMN datasource_name_snapshot VARCHAR(200) NULL COMMENT '数据源名称快照' AFTER datasource_id,
    ADD COLUMN datasource_type VARCHAR(32) NULL COMMENT '数据源类型（postgresql或mysql），历史手工录入记录为NULL' AFTER datasource_name_snapshot,
    ADD COLUMN structured_content_json LONGTEXT NULL COMMENT '数据源到表到字段到修改前修改后的完整结构化JSON，历史手工录入记录为NULL' AFTER datasource_type,
    MODIFY COLUMN value_before TEXT NULL COMMENT '修改前聚合，每个关联字段一行，与修改字段名逐行对应',
    MODIFY COLUMN value_after TEXT NULL COMMENT '修改后聚合，每个关联字段一行，与修改字段名逐行对应';
