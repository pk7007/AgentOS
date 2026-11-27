CREATE TABLE messages (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    sender     TEXT NOT NULL,
    recipient  TEXT NOT NULL,
    kind       TEXT NOT NULL,
    task_id    TEXT REFERENCES tasks(id),
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at    TEXT
);
CREATE INDEX messages_recipient ON messages(project_id, recipient, read_at);

CREATE TABLE claims (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id),
    path        TEXT NOT NULL,
    instance_id TEXT NOT NULL REFERENCES agent_instances(id),
    claimed_at  TEXT NOT NULL,
    released_at TEXT
);
CREATE UNIQUE INDEX claims_open ON claims(project_id, path) WHERE released_at IS NULL;

CREATE TABLE workflows (
    name         TEXT NOT NULL,
    version      INTEGER NOT NULL,
    body         TEXT NOT NULL,
    body_hash    TEXT NOT NULL,
    source       TEXT,
    created_at   TEXT NOT NULL,
    actor        TEXT NOT NULL,
    PRIMARY KEY (name, version)
);

CREATE TABLE bench_runs (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    n          INTEGER NOT NULL,
    p50_ms     REAL NOT NULL,
    p95_ms     REAL NOT NULL,
    per_sec    REAL NOT NULL,
    version    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX bench_runs_name ON bench_runs(name, created_at);

ALTER TABLE agent_instances ADD COLUMN last_heartbeat TEXT;
ALTER TABLE memory ADD COLUMN uses INTEGER NOT NULL DEFAULT 0;
ALTER TABLE memory ADD COLUMN last_used_at TEXT;
