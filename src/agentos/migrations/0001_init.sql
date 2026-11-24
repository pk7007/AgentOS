CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE projects (
    id           TEXT PRIMARY KEY,
    path         TEXT NOT NULL,
    name         TEXT NOT NULL,
    active       INTEGER NOT NULL DEFAULT 1,
    activated_at TEXT NOT NULL
);

CREATE TABLE tasks (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(id),
    parent_id    TEXT REFERENCES tasks(id),
    title        TEXT NOT NULL,
    objective    TEXT NOT NULL DEFAULT '',
    capabilities TEXT NOT NULL DEFAULT '[]',
    acceptance   TEXT NOT NULL DEFAULT '[]',
    priority     INTEGER NOT NULL DEFAULT 50,
    risk         TEXT NOT NULL DEFAULT 'low',
    state        TEXT NOT NULL DEFAULT 'pending',
    retries      INTEGER NOT NULL DEFAULT 0,
    max_retries  INTEGER NOT NULL DEFAULT 2,
    depth        INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX tasks_project ON tasks(project_id, state);

CREATE TABLE task_deps (
    task_id    TEXT NOT NULL REFERENCES tasks(id),
    depends_on TEXT NOT NULL REFERENCES tasks(id),
    PRIMARY KEY (task_id, depends_on)
);

CREATE TABLE agent_templates (
    id         TEXT NOT NULL,
    version    INTEGER NOT NULL,
    status     TEXT NOT NULL DEFAULT 'active',
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (id, version)
);

CREATE TABLE agent_instances (
    id                    TEXT PRIMARY KEY,
    template_id           TEXT NOT NULL,
    template_version      INTEGER NOT NULL,
    project_id            TEXT NOT NULL REFERENCES projects(id),
    task_id               TEXT NOT NULL REFERENCES tasks(id),
    parent_id             TEXT REFERENCES agent_instances(id),
    depth                 INTEGER NOT NULL DEFAULT 0,
    host                  TEXT NOT NULL,
    state                 TEXT NOT NULL,
    termination_confirmed INTEGER,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    last_reason           TEXT
);
CREATE INDEX agent_instances_state ON agent_instances(state);
CREATE INDEX agent_instances_task ON agent_instances(task_id);

CREATE TABLE evaluations (
    id             TEXT PRIMARY KEY,
    instance_id    TEXT NOT NULL REFERENCES agent_instances(id),
    template_id    TEXT NOT NULL,
    evaluator_id   TEXT NOT NULL,
    category       TEXT NOT NULL,
    scores         TEXT NOT NULL,
    weighted       REAL NOT NULL,
    evidence       TEXT NOT NULL,
    flags          TEXT NOT NULL DEFAULT '[]',
    external_cause INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);
CREATE INDEX evaluations_template ON evaluations(template_id, category);

CREATE TABLE budgets (
    scope       TEXT NOT NULL,
    scope_id    TEXT NOT NULL,
    kind        TEXT NOT NULL,
    limit_value REAL NOT NULL,
    PRIMARY KEY (scope, scope_id, kind)
);

CREATE TABLE reservations (
    id         TEXT PRIMARY KEY,
    scope      TEXT NOT NULL,
    scope_id   TEXT NOT NULL,
    kind       TEXT NOT NULL,
    amount     REAL NOT NULL,
    actual     REAL,
    holder     TEXT NOT NULL,
    state      TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);
CREATE INDEX reservations_scope ON reservations(scope, scope_id, kind, state);

CREATE TABLE approvals (
    id           TEXT PRIMARY KEY,
    action       TEXT NOT NULL,
    params_hash  TEXT NOT NULL,
    params       TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    granted_at   TEXT,
    consumed_at  TEXT
);

CREATE TABLE memory (
    id           TEXT PRIMARY KEY,
    project_id   TEXT,
    scope        TEXT NOT NULL,
    layer        TEXT NOT NULL,
    content      TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source       TEXT NOT NULL,
    author       TEXT NOT NULL,
    confidence   REAL NOT NULL,
    validated    INTEGER NOT NULL DEFAULT 0,
    version      INTEGER NOT NULL DEFAULT 1,
    supersedes   TEXT,
    superseded   INTEGER NOT NULL DEFAULT 0,
    deleted      INTEGER NOT NULL DEFAULT 0,
    tags         TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL
);
CREATE INDEX memory_scope ON memory(project_id, scope, layer);

CREATE VIRTUAL TABLE memory_fts USING fts5(content, content='memory', content_rowid='rowid');
CREATE TRIGGER memory_ai AFTER INSERT ON memory BEGIN
    INSERT INTO memory_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER memory_ad AFTER DELETE ON memory BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
END;
CREATE TRIGGER memory_au AFTER UPDATE OF content ON memory BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
    INSERT INTO memory_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TABLE events (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    id         TEXT NOT NULL,
    ts         TEXT NOT NULL,
    kind       TEXT NOT NULL,
    actor      TEXT NOT NULL,
    project_id TEXT,
    payload    TEXT NOT NULL,
    prev_hash  TEXT NOT NULL,
    hash       TEXT NOT NULL
);
CREATE INDEX events_kind ON events(kind);

CREATE TABLE handovers (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    host       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    path       TEXT NOT NULL,
    resumed_by TEXT,
    resumed_at TEXT
);
