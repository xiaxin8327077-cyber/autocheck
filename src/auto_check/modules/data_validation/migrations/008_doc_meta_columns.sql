ALTER TABLE data_validation_doc_tables MODIFY dimension LONGTEXT NULL COMMENT '维度/范围说明'
-- module-statement-break
ALTER TABLE data_validation_doc_tables MODIFY period VARCHAR(500) NULL COMMENT '采集周期'
