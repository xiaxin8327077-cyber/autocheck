CREATE TABLE IF NOT EXISTS data_validation_analysis_results (
    cache_key VARCHAR(64) NOT NULL PRIMARY KEY,
    response_json LONGTEXT NOT NULL,
    updated_at VARCHAR(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
