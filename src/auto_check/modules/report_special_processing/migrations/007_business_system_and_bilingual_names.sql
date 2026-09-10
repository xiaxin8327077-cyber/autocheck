-- 报表特殊处理录入：新增所属业务系统字段，表名/字段名升级为双语多项规范串。
-- 1) business_system_code / business_system_name_snapshot 保存字典项代码与名称快照；
-- 2) table_name / field_name 放宽为 TEXT，承载“中文名｜英文名”多项（；分隔）规范串。
ALTER TABLE report_special_processing_records
    ADD COLUMN business_system_code VARCHAR(64) NULL COMMENT '所属业务系统字典项编码' AFTER dimension,
    ADD COLUMN business_system_name_snapshot VARCHAR(100) NULL COMMENT '所属业务系统名称快照' AFTER business_system_code,
    MODIFY COLUMN table_name TEXT NULL COMMENT '处理表名，中文名｜英文名，多项用；分隔',
    MODIFY COLUMN field_name TEXT NULL COMMENT '处理字段名，中文名｜英文名，多项用；分隔';
