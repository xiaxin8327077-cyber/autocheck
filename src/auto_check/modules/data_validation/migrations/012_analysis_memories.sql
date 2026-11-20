CREATE TABLE IF NOT EXISTS data_validation_analysis_memories (
    id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
    memory_key VARCHAR(64) NOT NULL,
    context_key VARCHAR(64) NOT NULL,
    request_key VARCHAR(64) NOT NULL,
    pattern_key VARCHAR(64) NOT NULL,
    request_text TEXT NOT NULL,
    baseline_json TEXT NOT NULL,
    UNIQUE KEY dv_memory_unique (memory_key),
    KEY dv_memory_exact (context_key, request_key, id),
    KEY dv_memory_pattern (context_key, pattern_key, id),
    KEY dv_memory_recent (context_key, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
