CREATE TABLE benchmark_cases (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id),
    suite         TEXT NOT NULL,
    title         TEXT NOT NULL,
    capabilities  TEXT NOT NULL DEFAULT '[]',
    acceptance    TEXT NOT NULL DEFAULT '[]',
    check_command TEXT NOT NULL,
    split         TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    actor         TEXT NOT NULL
);
CREATE INDEX benchmark_cases_suite ON benchmark_cases(project_id, suite, split);

CREATE TABLE experiments (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL REFERENCES projects(id),
    kind                TEXT NOT NULL,
    target              TEXT NOT NULL,
    suite               TEXT NOT NULL,
    hypothesis          TEXT NOT NULL,
    champion            TEXT NOT NULL,
    challenger          TEXT NOT NULL,
    challenger_template TEXT,
    status              TEXT NOT NULL DEFAULT 'trialing',
    gate_evidence       TEXT NOT NULL DEFAULT '[]',
    result              TEXT,
    monitor             TEXT,
    created_at          TEXT NOT NULL,
    decided_at          TEXT,
    actor               TEXT NOT NULL
);
CREATE INDEX experiments_status ON experiments(status);

CREATE TABLE trials (
    id            TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(id),
    case_id       TEXT NOT NULL REFERENCES benchmark_cases(id),
    arm           TEXT NOT NULL,
    label         TEXT NOT NULL,
    task_id       TEXT NOT NULL REFERENCES tasks(id),
    template_id   TEXT NOT NULL,
    instance_id   TEXT REFERENCES agent_instances(id),
    evidence_id   TEXT REFERENCES evidence(id),
    evaluation_id TEXT REFERENCES evaluations(id),
    created_at    TEXT NOT NULL,
    UNIQUE (experiment_id, case_id, arm)
);
CREATE INDEX trials_task ON trials(task_id);

CREATE TABLE retrospectives (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    scope      TEXT NOT NULL,
    scope_id   TEXT,
    report     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    actor      TEXT NOT NULL
);
