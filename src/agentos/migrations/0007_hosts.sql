CREATE TABLE host_installs (
    id           TEXT PRIMARY KEY,
    host         TEXT NOT NULL,
    dest         TEXT NOT NULL,
    files        TEXT NOT NULL,
    defs_hash    TEXT NOT NULL,
    host_version TEXT,
    backup_dir   TEXT,
    previous_id  TEXT REFERENCES host_installs(id),
    status       TEXT NOT NULL DEFAULT 'active',
    installed_at TEXT NOT NULL,
    actor        TEXT NOT NULL
);
CREATE INDEX host_installs_host ON host_installs(host, status);
