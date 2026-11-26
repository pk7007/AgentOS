CREATE TABLE evidence (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id),
    command       TEXT NOT NULL,
    cwd           TEXT NOT NULL,
    exit_code     INTEGER NOT NULL,
    timed_out     INTEGER NOT NULL DEFAULT 0,
    stdout_sha256 TEXT NOT NULL,
    stderr_sha256 TEXT NOT NULL,
    output_tail   TEXT NOT NULL,
    git_head      TEXT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT NOT NULL,
    duration_ms   INTEGER NOT NULL,
    actor         TEXT NOT NULL
);
CREATE INDEX evidence_project ON evidence(project_id);
CREATE INDEX evaluations_instance ON evaluations(instance_id, evaluator_id, category);
