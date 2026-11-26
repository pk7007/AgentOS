CREATE TABLE factory_proposals (
    id                 TEXT PRIMARY KEY,
    project_id         TEXT NOT NULL REFERENCES projects(id),
    task_id            TEXT REFERENCES tasks(id),
    template_id        TEXT NOT NULL,
    body               TEXT NOT NULL,
    base_template      TEXT,
    temporary          INTEGER NOT NULL DEFAULT 1,
    expires_at         TEXT,
    status             TEXT NOT NULL DEFAULT 'proposed',
    problems           TEXT NOT NULL DEFAULT '[]',
    owner_reasons      TEXT NOT NULL DEFAULT '[]',
    approval_id        TEXT,
    registered_version INTEGER,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX factory_proposals_status ON factory_proposals(status);

CREATE TABLE rehabilitations (
    id            TEXT PRIMARY KEY,
    template_id   TEXT NOT NULL,
    from_version  INTEGER NOT NULL,
    to_version    INTEGER NOT NULL,
    baseline_mean REAL,
    status        TEXT NOT NULL DEFAULT 'probation',
    started_at    TEXT NOT NULL,
    closed_at     TEXT
);
CREATE INDEX rehabilitations_template ON rehabilitations(template_id, status);

CREATE TABLE transfers (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id),
    task_id       TEXT NOT NULL REFERENCES tasks(id),
    from_instance TEXT NOT NULL REFERENCES agent_instances(id),
    to_instance   TEXT REFERENCES agent_instances(id),
    to_template   TEXT NOT NULL,
    memory_id     TEXT,
    created_at    TEXT NOT NULL,
    actor         TEXT NOT NULL
);
