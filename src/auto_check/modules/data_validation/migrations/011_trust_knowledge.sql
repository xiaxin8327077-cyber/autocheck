CREATE TABLE IF NOT EXISTS data_validation_trust_knowledge (
    id INTEGER NOT NULL PRIMARY KEY,
    revision INTEGER NOT NULL,
    active_revision INTEGER NOT NULL,
    draft_json TEXT NOT NULL,
    active_json TEXT NOT NULL,
    updated_by VARCHAR(64) NOT NULL,
    updated_at VARCHAR(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
