CREATE TABLE IF NOT EXISTS `currency_report_duration` (
  `id1` varchar(666) NOT NULL COMMENT 'id',
  `c_productcode` varchar(100) DEFAULT NULL COMMENT 'SPV',
  `c_productname` varchar(100) DEFAULT NULL COMMENT '产品名称',
  `c_projectcode` varchar(100) DEFAULT NULL COMMENT '项目编号',
  `c_projectname` varchar(100) DEFAULT NULL COMMENT '项目名称',
  `caldate` date DEFAULT NULL COMMENT '报告日期',
  `f_assetshare` decimal(23,2) DEFAULT NULL COMMENT '期末产品份额',
  `amt_endp` decimal(30,2) DEFAULT NULL COMMENT '4001',
  PRIMARY KEY (`id1`),
  KEY `currency_report_duration_c_projectcode_IDX` (`c_projectcode`) USING BTREE,
  KEY `currency_report_duration_caldate_IDX` (`caldate`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='资金申报期间募集信息';
