CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interviewee_id TEXT NOT NULL,
    week INTEGER NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    energy_score INTEGER,
    current_question_id TEXT,
    notes TEXT,
    UNIQUE(interviewee_id, week)
);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS redactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id INTEGER NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    original TEXT NOT NULL,
    replacement TEXT NOT NULL,
    span_start INTEGER,
    span_end INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_redactions_turn
    ON redactions(turn_id);

CREATE TABLE IF NOT EXISTS anchors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interviewee_id TEXT NOT NULL,
    dimension TEXT NOT NULL,
    layer TEXT NOT NULL,
    content TEXT NOT NULL,
    triangulated INTEGER NOT NULL DEFAULT 0,
    source_question_ids TEXT NOT NULL DEFAULT '[]',
    source_turn_ids TEXT NOT NULL DEFAULT '[]',
    active INTEGER NOT NULL DEFAULT 1,
    archived_at TEXT,
    archive_reason TEXT,
    model TEXT,  -- 記錄產生此 anchor 的模型 (e.g. claude-3-5-haiku-20241022, claude-3-5-sonnet-20241022)
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    pii_tag TEXT
);

CREATE TABLE IF NOT EXISTS persona_triples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interviewee_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    relation TEXT NOT NULL,
    object TEXT NOT NULL,
    source_turn_ids TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    embedding BLOB,
    active INTEGER NOT NULL DEFAULT 1,
    archived_at TEXT,
    archive_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_triples_interviewee
    ON persona_triples(interviewee_id);

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

CREATE TABLE IF NOT EXISTS subjects (
    interviewee_id TEXT PRIMARY KEY,
    display_name TEXT,
    domain TEXT NOT NULL DEFAULT 'unspecified',
    goal TEXT,
    status TEXT NOT NULL DEFAULT 'extracting',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS checklist_items (
    interviewee_id TEXT NOT NULL,
    item_key TEXT NOT NULL,
    label TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (interviewee_id, item_key)
);

CREATE TABLE IF NOT EXISTS transport_events (
    event_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    interviewee_id TEXT,
    message_id TEXT,
    status TEXT NOT NULL DEFAULT 'processing',
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS persona_download_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    interviewee_id TEXT NOT NULL,
    zip_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    download_count INTEGER NOT NULL DEFAULT 0,
    last_downloaded_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_persona_download_tokens_expires_at
    ON persona_download_tokens(expires_at);

CREATE TABLE IF NOT EXISTS persona_download_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interviewee_id TEXT,
    token_hash TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    success INTEGER NOT NULL,
    failure_reason TEXT,
    zip_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_persona_download_logs_token_hash
    ON persona_download_logs(token_hash);
