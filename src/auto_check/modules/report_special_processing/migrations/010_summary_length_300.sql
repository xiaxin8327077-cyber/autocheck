-- 处理摘要上限由 200 调整为 300，与录入校验一致。已有内容短于新上限，只放宽列宽，不改写数据。
ALTER TABLE report_special_processing_records
    MODIFY COLUMN summary VARCHAR(300) NULL COMMENT '特殊处理事项摘要';
