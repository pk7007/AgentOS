CREATE TABLE runtime_bindings (
    instance_id     TEXT PRIMARY KEY REFERENCES agent_instances(id),
    host            TEXT NOT NULL,
    session_id      TEXT,
    tool_use_id     TEXT,
    native_agent_id TEXT,
    claimed_at      TEXT NOT NULL,
    started_at      TEXT,
    stopped_at      TEXT
);
CREATE UNIQUE INDEX runtime_bindings_native ON runtime_bindings(host, native_agent_id)
    WHERE native_agent_id IS NOT NULL;
