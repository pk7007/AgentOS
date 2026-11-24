"""Where AgentOS keeps runtime state. Never inside a repository."""

import os
from pathlib import Path


def agentos_home() -> Path:
    env = os.environ.get("AGENTOS_HOME")
    return Path(env) if env else Path.home() / ".agentos"


def state_dir() -> Path:
    return agentos_home() / "state"


def db_path() -> Path:
    return state_dir() / "agentos.db"


def backups_dir() -> Path:
    return agentos_home() / "backups"


def handovers_dir() -> Path:
    return agentos_home() / "handovers"


def logs_dir() -> Path:
    return agentos_home() / "logs"


def all_dirs() -> list[Path]:
    return [state_dir(), backups_dir(), handovers_dir(), logs_dir()]
