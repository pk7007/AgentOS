"""Limits, budgets and reservations. Filled in by the admission task."""

import sqlite3


def release_for_instance(conn: sqlite3.Connection, instance_id: str) -> None:
    """Release open reservations held by an instance (stub until budgets exist)."""
