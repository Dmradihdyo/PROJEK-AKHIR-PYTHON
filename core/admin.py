"""Fungsi khusus admin. Setiap fungsi memeriksa role ADMIN pelaku (`actor_id`) di dalam
core, jadi antarmuka mana pun tidak bisa melewatinya. Aksi yang mengubah data juga
mewajibkan PIN admin dan dicatat di audit_log."""
import sqlite3
from pathlib import Path

import config
from core import auth, clock, outbox, reports, security, wallet
from core.audit import log as audit
from core.db import immediate_tx
from core.errors import AkunTidakDitemukan, BatasTransaksiTerlampaui, DataTidakValid, SaldoTidakCukup, TidakBerhak
from core.models import Transaction, User


def require_admin(conn: sqlite3.Connection, actor_id: str) -> User:
    actor = auth.get_user(conn, actor_id or "")
    if actor is None or not actor.is_active or not actor.is_admin:
        raise TidakBerhak("Fitur ini hanya untuk admin.")
    return actor


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_users(
    conn: sqlite3.Connection, actor_id: str, query: str | None = None, limit: int = 20, offset: int = 0
) -> list[User]:
    """Daftar akun (terbaru di atas). `query` mencari di ID, nama, dan email."""
    require_admin(conn, actor_id)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    query = (query or "").strip()
    if query:
        pattern = f"%{_escape_like(query)}%"
        rows = conn.execute(
            "SELECT * FROM users WHERE id LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\' OR email LIKE ? ESCAPE '\\' "
            "ORDER BY rowid DESC LIMIT ? OFFSET ?",
            (pattern, pattern, pattern, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM users ORDER BY rowid DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return [auth._to_user(r) for r in rows]


def list_transactions(
    conn: sqlite3.Connection,
    actor_id: str,
    *,
    user_id: str | None = None,
    type_: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Transaction]:
    """Transaksi seluruh pengguna (atau satu pengguna bila `user_id` diisi)."""
    require_admin(conn, actor_id)
    return wallet.query_transactions(
        conn,
        (user_id or "").strip() or None,
        type_=type_,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


def summary(conn: sqlite3.Connection, actor_id: str) -> dict:
    require_admin(conn, actor_id)
    return reports.system_summary(conn, clock.today())


def check_consistency(conn: sqlite3.Connection, actor_id: str) -> list[dict]:
    require_admin(conn, actor_id)
    return reports.check_consistency(conn)


def set_status(conn: sqlite3.Connection, actor_id: str, target_id: str, status: str, pin: str) -> User:
    """Blokir ('BLOKIR') atau aktifkan ('AKTIF') akun. Admin tidak bisa memblokir dirinya
    sendiri atau admin lain."""
    actor = require_admin(conn, actor_id)
    if status not in ("AKTIF", "BLOKIR"):
        raise DataTidakValid("Status harus AKTIF atau BLOKIR.")
    target = auth.get_user(conn, (target_id or "").strip())
    if target is None:
        raise AkunTidakDitemukan()
    if status == "BLOKIR" and target.is_admin:
        raise TidakBerhak("Akun admin tidak dapat diblokir.")
    auth.verify_pin(conn, actor.id, pin)
    with immediate_tx(conn):
        conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, target.id))
        audit(conn, actor.id, "ADMIN_SET_STATUS", f"{target.id} -> {status}")
    return auth.require_user(conn, target.id)


def reset_password(conn: sqlite3.Connection, actor_id: str, target_id: str, new_password: str, pin: str) -> None:
    """Atur password baru untuk pengguna (admin tidak pernah bisa melihat password lama).
    Kunci login/PIN milik pengguna ikut dibuka."""
    actor = require_admin(conn, actor_id)
    security.validate_password(new_password)
    target = auth.get_user(conn, (target_id or "").strip())
    if target is None:
        raise AkunTidakDitemukan()
    if target.is_admin and target.id.lower() != actor.id.lower():
        raise TidakBerhak("Password admin lain tidak dapat direset dari sini.")
    auth.verify_pin(conn, actor.id, pin)
    key = target.id.lower()
    prefix = f"{key}|"
    with immediate_tx(conn):
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?", (security.hash_secret("password", new_password), target.id)
        )
        conn.execute("DELETE FROM attempts WHERE kind IN ('PIN', 'PWD') AND subject = ?", (key,))
        conn.execute(
            "DELETE FROM attempts WHERE kind IN ('LOGIN', 'RESET') AND substr(subject, 1, ?) = ?", (len(prefix), prefix)
        )
        conn.execute("UPDATE otp_codes SET used = 1 WHERE user_id = ?", (target.id,))
        audit(conn, actor.id, "ADMIN_RESET_PASSWORD", target.id)


def backup_database(conn: sqlite3.Connection, actor_id: str, dest_dir: str | Path | None = None) -> Path:
    """Salin database ke file cadangan bertanda waktu (aman dijalankan saat server aktif)."""
    actor = require_admin(conn, actor_id)
    folder = Path(dest_dir) if dest_dir is not None else config.DATA_DIR / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = clock.iso().replace(" ", "_").replace(":", "")
    target = folder / f"ewallet_backup_{stamp}.db"
    counter = 1
    while target.exists():
        target = folder / f"ewallet_backup_{stamp}_{counter}.db"
        counter += 1
    dest = sqlite3.connect(str(target))
    try:
        conn.backup(dest)
    finally:
        dest.close()
    audit(conn, actor.id, "ADMIN_BACKUP", target.name)
    return target


def read_outbox(conn: sqlite3.Connection, actor_id: str, lines: int = 10) -> list[str]:
    """Kotak surat OTP simulasi (lihat core/outbox.py) untuk membantu pengguna yang lupa password."""
    require_admin(conn, actor_id)
    db_file = conn.execute("PRAGMA database_list").fetchone()["file"]
    return outbox.tail(db_file, lines) if db_file else []


def clear_lockout(conn: sqlite3.Connection, actor_id: str, target_id: str, pin: str) -> User:
    """Hapus lockout milik satu akun tanpa menghapus lockout global per IP."""
    actor = require_admin(conn, actor_id)
    target = auth.get_user(conn, (target_id or "").strip())
    if target is None:
        raise AkunTidakDitemukan()
    auth.verify_pin(conn, actor.id, pin)
    subject = target.id.lower()
    prefix = subject + "|"
    with immediate_tx(conn):
        conn.execute("DELETE FROM attempts WHERE kind IN ('PIN', 'PWD') AND subject = ?", (subject,))
        conn.execute(
            "DELETE FROM attempts WHERE kind IN ('LOGIN', 'RESET') AND substr(subject, 1, ?) = ?",
            (len(prefix), prefix),
        )
        audit(conn, actor.id, "ADMIN_CLEAR_LOCKOUT", target.id)
    return auth.require_user(conn, target.id)


def refund_transaction(
    conn: sqlite3.Connection, actor_id: str, original_ref_no: str, reason: str, pin: str
) -> str:
    """Refund penuh untuk satu transaksi OUT berhasil, atomik dan idempotent."""
    actor = require_admin(conn, actor_id)
    original_ref_no = (original_ref_no or "").strip()[:32]
    reason = security.validate_note(reason)
    if len(reason) < 10:
        raise DataTidakValid("Alasan refund minimal 10 karakter.")
    original = conn.execute(
        "SELECT * FROM transactions WHERE ref_no = ? AND direction = 'OUT' AND status = 'BERHASIL' "
        "AND type IN ('TRANSFER', 'QR_PAYMENT')",
        (original_ref_no,),
    ).fetchone()
    if original is None:
        raise DataTidakValid("Transaksi OUT berhasil tidak ditemukan atau tidak dapat direfund.")
    if not original["counterparty_id"] or original["counterparty_id"] == "-":
        raise DataTidakValid("Transaksi tidak memiliki penerima yang dapat dikembalikan.")
    auth.verify_pin(conn, actor.id, pin)
    with immediate_tx(conn):
        if conn.execute("SELECT 1 FROM refunds WHERE original_ref_no = ?", (original_ref_no,)).fetchone():
            raise DataTidakValid("Transaksi ini sudah pernah direfund.")
        fresh = conn.execute("SELECT * FROM transactions WHERE ref_no = ?", (original_ref_no,)).fetchone()
        sender_id = fresh["user_id"]
        recipient_id = fresh["counterparty_id"]
        recipient = conn.execute("SELECT balance FROM users WHERE id = ?", (recipient_id,)).fetchone()
        sender = conn.execute("SELECT id FROM users WHERE id = ?", (sender_id,)).fetchone()
        if recipient is None or sender is None:
            raise AkunTidakDitemukan()
        if recipient["balance"] < fresh["amount"]:
            raise SaldoTidakCukup("Saldo penerima tidak cukup untuk refund penuh.")
        conn.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (fresh["amount"], recipient_id))
        conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (fresh["amount"], sender_id))
        stamp = clock.iso()
        note = f"REFUND {original_ref_no}: {reason}"
        refund_out = wallet._insert_tx(
            conn, user_id=recipient_id, type_=fresh["type"], direction="OUT", amount=fresh["amount"],
            counterparty=sender_id, note=note, status="BERHASIL", stamp=stamp,
        )
        wallet._insert_tx(
            conn, user_id=sender_id, type_=fresh["type"], direction="IN", amount=fresh["amount"],
            counterparty=recipient_id, note=note, status="BERHASIL", stamp=stamp, group_ref=refund_out,
        )
        conn.execute(
            "INSERT INTO refunds (original_ref_no, refund_ref_no, actor_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (original_ref_no, refund_out, actor.id, reason, stamp),
        )
        audit(conn, actor.id, "ADMIN_REFUND", f"original={original_ref_no};refund={refund_out}")
        return refund_out


def list_refunds(conn: sqlite3.Connection, actor_id: str, limit: int = 50) -> list[dict]:
    require_admin(conn, actor_id)
    rows = conn.execute("SELECT * FROM refunds ORDER BY created_at DESC LIMIT ?", (max(1, min(int(limit), 200)),)).fetchall()
    return [dict(row) for row in rows]


def recent_audit(conn: sqlite3.Connection, actor_id: str, limit: int = 30) -> list[dict]:
    require_admin(conn, actor_id)
    rows = conn.execute(
        "SELECT created_at, actor, action, detail FROM audit_log ORDER BY id DESC LIMIT ?",
        (max(1, min(int(limit), 200)),),
    ).fetchall()
    return [dict(r) for r in rows]
