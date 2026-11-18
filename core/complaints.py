"""Aduan pengguna dan penanganannya oleh admin."""
import sqlite3

from core import auth, clock, security
from core.audit import log as audit
from core.db import immediate_tx
from core.errors import AkunTidakDitemukan, DataTidakValid, TidakBerhak

CATEGORIES = ("TRANSACTION", "ACCOUNT", "QR", "OTHER")
STATUSES = ("OPEN", "IN_PROGRESS", "RESOLVED", "REJECTED")


def _validate_category(value: str) -> str:
    value = (value or "").strip().upper()
    if value not in CATEGORIES:
        raise DataTidakValid("Kategori aduan tidak valid.")
    return value


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


def create(
    conn: sqlite3.Connection,
    reporter_id: str,
    category: str,
    message: str,
    transaction_ref: str | None = None,
) -> dict:
    user = auth.require_user(conn, reporter_id)
    if not user.is_active:
        raise TidakBerhak("Akun tidak aktif.")
    category = _validate_category(category)
    message = security.validate_note(message)
    if len(message) < 10:
        raise DataTidakValid("Aduan minimal 10 karakter.")
    if len(message) > 1000:
        raise DataTidakValid("Aduan maksimal 1000 karakter.")
    transaction_ref = (transaction_ref or "").strip()[:32] or None
    if transaction_ref:
        row = conn.execute(
            "SELECT 1 FROM transactions WHERE ref_no = ? AND user_id = ?", (transaction_ref, reporter_id)
        ).fetchone()
        if row is None:
            raise DataTidakValid("Transaksi tidak ditemukan pada riwayat akun Anda.")
    stamp = clock.iso()
    with immediate_tx(conn):
        cur = conn.execute(
            "INSERT INTO complaints (reporter_id, transaction_ref, category, message, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'OPEN', ?, ?)",
            (reporter_id, transaction_ref, category, message, stamp, stamp),
        )
        complaint_id = cur.lastrowid
        audit(conn, reporter_id, "COMPLAINT_CREATE", f"id={complaint_id};category={category}")
    row = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    return _row(row)


def list_for_user(conn: sqlite3.Connection, reporter_id: str, limit: int = 50) -> list[dict]:
    auth.require_user(conn, reporter_id)
    rows = conn.execute(
        "SELECT * FROM complaints WHERE reporter_id = ? ORDER BY id DESC LIMIT ?",
        (reporter_id, max(1, min(int(limit), 200))),
    ).fetchall()
    return [_row(row) for row in rows]


def list_for_admin(
    conn: sqlite3.Connection, actor_id: str, status: str | None = None, limit: int = 50
) -> list[dict]:
    from core.admin import require_admin

    require_admin(conn, actor_id)
    if status:
        status = status.strip().upper()
        if status not in STATUSES:
            raise DataTidakValid("Status aduan tidak valid.")
        rows = conn.execute(
            "SELECT c.*, u.name AS reporter_name FROM complaints c JOIN users u ON u.id = c.reporter_id "
            "WHERE c.status = ? ORDER BY c.id DESC LIMIT ?",
            (status, max(1, min(int(limit), 200))),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT c.*, u.name AS reporter_name FROM complaints c JOIN users u ON u.id = c.reporter_id "
            "ORDER BY c.id DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        ).fetchall()
    return [_row(row) for row in rows]


def update_status(
    conn: sqlite3.Connection, actor_id: str, complaint_id: int, status: str, admin_note: str, pin: str
) -> dict:
    from core.admin import require_admin

    actor = require_admin(conn, actor_id)
    status = status.strip().upper()
    if status not in STATUSES:
        raise DataTidakValid("Status aduan tidak valid.")
    admin_note = security.validate_note(admin_note)
    auth.verify_pin(conn, actor.id, pin)
    stamp = clock.iso()
    with immediate_tx(conn):
        row = conn.execute("SELECT * FROM complaints WHERE id = ?", (int(complaint_id),)).fetchone()
        if row is None:
            raise DataTidakValid("Aduan tidak ditemukan.")
        conn.execute(
            "UPDATE complaints SET status = ?, admin_id = ?, admin_note = ?, updated_at = ? WHERE id = ?",
            (status, actor.id, admin_note, stamp, int(complaint_id)),
        )
        audit(conn, actor.id, "COMPLAINT_UPDATE", f"id={complaint_id};status={status}")
    return _row(conn.execute("SELECT * FROM complaints WHERE id = ?", (int(complaint_id),)).fetchone())
