CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interviewee_id TEXT NOT NULL,
    week INTEGER NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    energy_score INTEGER,
    notes TEXT,
    UNIQUE(interviewee_id, week)
);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    voice_audio_path TEXT,
    ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS anchors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interviewee_id TEXT NOT NULL,
    dimension TEXT NOT NULL,
    layer TEXT NOT NULL,
    content TEXT NOT NULL,
    triangulated INTEGER NOT NULL DEFAULT 0,
    source_question_ids TEXT NOT NULL DEFAULT '[]',
    source_turn_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    pii_tag TEXT
);

CREATE TABLE IF NOT EXISTS voice_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interviewee_id TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    embedding BLOB,
    source_turn_id INTEGER REFERENCES turns(id),
    pii_scrubbed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS question_state (
    interviewee_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    week INTEGER NOT NULL,
    asked_count INTEGER NOT NULL DEFAULT 0,
    answered_depth TEXT,
    last_asked_at TEXT,
    PRIMARY KEY (interviewee_id, question_id)
);

CREATE TABLE IF NOT EXISTS blind_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interviewee_id TEXT NOT NULL,
    week INTEGER NOT NULL,
    correctness_per_item TEXT NOT NULL DEFAULT '{}',
    overall_accuracy REAL NOT NULL,
    verdict TEXT NOT NULL,
    weakest_dimension TEXT,
    recommended_action TEXT,
    ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
