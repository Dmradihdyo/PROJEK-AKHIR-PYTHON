"""Catatan audit untuk aksi penting (bukan pengganti tabel transactions)."""
import sqlite3

from core import clock


def log(conn: sqlite3.Connection, actor: str, action: str, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_log (actor, action, detail, created_at) VALUES (?, ?, ?, ?)",
        (actor, action, detail, clock.iso()),
    )
