import pytest


def test_migrate_idempotent(home):
    from agentos import db

    c = db.connect()
    assert db.migrate(c) == 1
    assert db.migrate(c) == 1
    c.close()


def test_write_tx_rolls_back(conn):
    from agentos import db

    with pytest.raises(RuntimeError):
        with db.write_tx(conn):
            conn.execute("INSERT INTO settings VALUES ('k','1')")
            raise RuntimeError
    assert conn.execute("SELECT count(*) FROM settings WHERE key='k'").fetchone()[0] == 0


def test_write_tx_commits(conn):
    from agentos import db

    with db.write_tx(conn):
        conn.execute("INSERT INTO settings VALUES ('k','1')")
    assert conn.execute("SELECT value FROM settings WHERE key='k'").fetchone()[0] == "1"


def test_require_initialized_raises_before_init(home):
    from agentos import db
    from agentos.errors import NotInitialized

    with pytest.raises(NotInitialized):
        db.require_initialized()
