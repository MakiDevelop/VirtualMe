CREATE TABLE IF NOT EXISTS crisis_events (
    id INTEGER PRIMARY KEY,
    interviewee_id TEXT NOT NULL,
    category TEXT NOT NULL,
    ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);
