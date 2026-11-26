CREATE TABLE objectives (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL REFERENCES projects(id),
    title            TEXT NOT NULL,
    statement        TEXT NOT NULL DEFAULT '',
    acceptance       TEXT NOT NULL DEFAULT '[]',
    complexity_score INTEGER,
    complexity_band  TEXT,
    state            TEXT NOT NULL DEFAULT 'open',
    report           TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    delivered_at     TEXT
);
CREATE INDEX objectives_project ON objectives(project_id, state);

CREATE TABLE departments (
    id           TEXT PRIMARY KEY,
    objective_id TEXT NOT NULL REFERENCES objectives(id),
    function     TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    dissolved_at TEXT,
    UNIQUE (objective_id, function)
);

ALTER TABLE tasks ADD COLUMN objective_id TEXT REFERENCES objectives(id);
ALTER TABLE tasks ADD COLUMN department TEXT;
ALTER TABLE tasks ADD COLUMN effort INTEGER NOT NULL DEFAULT 1;
CREATE INDEX tasks_objective ON tasks(objective_id);

CREATE TABLE task_acceptances (
    task_id       TEXT PRIMARY KEY REFERENCES tasks(id),
    evaluation_id TEXT NOT NULL REFERENCES evaluations(id),
    evidence_id   TEXT NOT NULL REFERENCES evidence(id),
    accepted_at   TEXT NOT NULL,
    actor         TEXT NOT NULL
);
