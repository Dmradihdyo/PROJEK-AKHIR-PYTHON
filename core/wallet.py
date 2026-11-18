"""Saldo, top up, transfer, dan riwayat.

Aturan penting (ditulis sekali di sini, dipakai web dan console):
- Semua uang berupa int Rupiah.
- Setiap operasi yang menggerakkan saldo WAJIB menerima PIN dan memverifikasinya.
- Perpindahan saldo + pencatatan transaksi berada dalam satu transaksi database.
- Kegagalan bisnis (saldo kurang, batas harian, akun tidak aktif) dicatat sebagai
  baris berstatus GAGAL setelah transaksi uang di-rollback.
"""
import re
import sqlite3
from typing import Callable

import config
from core import auth, clock, security
from core.db import immediate_tx
from core.errors import (
    AkunTidakAktif,
    AkunTidakDitemukan,
    BatasTransaksiTerlampaui,
    DataTidakValid,
    PenerimaTidakDitemukan,
    SaldoTidakCukup,
    TransferKeDiriSendiri,
)
from core.formatting import format_rupiah
from core.models import Receipt, Transaction

TYPES = ("TOPUP", "TRANSFER", "QR_PAYMENT")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


# ------------------------------------------------------------------ helper
def get_balance(conn: sqlite3.Connection, user_id: str) -> int:
    return auth.require_user(conn, user_id).balance


def _sum_today(conn: sqlite3.Connection, user_id: str, direction: str, types: tuple[str, ...]) -> int:
    marks = ",".join("?" for _ in types)
    row = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM transactions "
        f"WHERE user_id = ? AND direction = ? AND status = 'BERHASIL' "
        f"AND type IN ({marks}) AND substr(created_at, 1, 10) = ?",
        (user_id, direction, *types, clock.today()),
    ).fetchone()
    return int(row[0])


def _insert_tx(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    type_: str,
    direction: str,
    amount: int,
    counterparty: str | None,
    note: str,
    status: str,
    stamp: str,
    group_ref: str | None = None,
) -> str:
    """Harus dipanggil di dalam transaksi tulis (BEGIN IMMEDIATE)."""
    next_id = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM transactions").fetchone()[0]
    ref_no = f"TRX{1000 + next_id}"
    conn.execute(
        "INSERT INTO transactions (id, ref_no, group_ref, user_id, type, direction, amount, fee, "
        "counterparty_id, note, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
        (next_id, ref_no, group_ref or ref_no, user_id, type_, direction, amount, counterparty, note, status, stamp),
    )
    return ref_no


def _record_failed(
    conn: sqlite3.Connection,
    user_id: str,
    type_: str,
    amount: int,
    counterparty: str | None,
    reason: str,
) -> None:
    try:
        with immediate_tx(conn):
            _insert_tx(
                conn,
                user_id=user_id,
                type_=type_,
                direction="OUT",
                amount=amount,
                counterparty=counterparty,
                note=reason,
                status="GAGAL",
                stamp=clock.iso(),
            )
    except sqlite3.Error:
        pass  # pencatatan gagal tidak boleh menutupi error asli


# ---------------------------------------------------------------- top up
def top_up(conn: sqlite3.Connection, user_id: str, amount: int | str, pin: str, method: str = "Simulasi") -> Receipt:
    amount = security.validate_amount(amount, config.MAX_TOPUP_PER_TX)
    note = "Metode: " + (security.validate_note(method) or "Simulasi")
    user = auth.require_user(conn, user_id)
    if not user.is_active:
        raise AkunTidakAktif()
    auth.verify_pin(conn, user.id, pin)

    with immediate_tx(conn):
        row = conn.execute("SELECT status FROM users WHERE id = ?", (user.id,)).fetchone()
        if row is None or row["status"] != "AKTIF":
            raise AkunTidakAktif()
        today = _sum_today(conn, user.id, "IN", ("TOPUP",))
        if today + amount > config.DAILY_TOPUP_LIMIT:
            sisa = max(config.DAILY_TOPUP_LIMIT - today, 0)
            raise BatasTransaksiTerlampaui(f"Batas top up harian terlampaui. Sisa batas hari ini: {format_rupiah(sisa)}.")
        conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user.id))
        stamp = clock.iso()
        ref = _insert_tx(
            conn, user_id=user.id, type_="TOPUP", direction="IN", amount=amount,
            counterparty="-", note=note, status="BERHASIL", stamp=stamp,
        )
        balance = conn.execute("SELECT balance FROM users WHERE id = ?", (user.id,)).fetchone()[0]
    return Receipt(ref, "TOPUP", amount, user.id, None, note, stamp, balance)


# -------------------------------------------------------------- transfer
def execute_transfer(
    conn: sqlite3.Connection,
    sender_id: str,
    recipient_id: str,
    amount: int,
    note: str,
    type_: str,
    in_tx_hook: Callable[[], None] | None = None,
) -> Receipt:
    """Inti perpindahan saldo. TIDAK memverifikasi PIN: hanya boleh dipanggil dari
    dalam core setelah `auth.verify_pin`. `in_tx_hook` berjalan di dalam transaksi
    yang sama (dipakai pembayaran QR untuk menandai sesi terpakai)."""
    try:
        with immediate_tx(conn):
            if in_tx_hook:
                in_tx_hook()
            sender = conn.execute("SELECT id, status, balance FROM users WHERE id = ?", (sender_id,)).fetchone()
            recipient = conn.execute("SELECT id, status FROM users WHERE id = ?", (recipient_id,)).fetchone()
            if sender is None:
                raise AkunTidakDitemukan()
            if recipient is None:
                raise PenerimaTidakDitemukan()
            if sender["id"] == recipient["id"]:
                raise TransferKeDiriSendiri()
            if sender["status"] != "AKTIF" or recipient["status"] != "AKTIF":
                raise AkunTidakAktif("Akun pengirim atau penerima tidak aktif.")
            if sender["balance"] < amount:
                raise SaldoTidakCukup()
            spent = _sum_today(conn, sender["id"], "OUT", ("TRANSFER", "QR_PAYMENT"))
            if spent + amount > config.DAILY_OUT_LIMIT:
                sisa = max(config.DAILY_OUT_LIMIT - spent, 0)
                raise BatasTransaksiTerlampaui(
                    f"Batas transaksi keluar harian terlampaui. Sisa batas hari ini: {format_rupiah(sisa)}."
                )

            debit = conn.execute(
                "UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?",
                (amount, sender["id"], amount),
            )
            if debit.rowcount != 1:
                raise SaldoTidakCukup()
            conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, recipient["id"]))

            stamp = clock.iso()
            ref_out = _insert_tx(
                conn, user_id=sender["id"], type_=type_, direction="OUT", amount=amount,
                counterparty=recipient["id"], note=note, status="BERHASIL", stamp=stamp,
            )
            _insert_tx(
                conn, user_id=recipient["id"], type_=type_, direction="IN", amount=amount,
                counterparty=sender["id"], note=note, status="BERHASIL", stamp=stamp, group_ref=ref_out,
            )
            balance = conn.execute("SELECT balance FROM users WHERE id = ?", (sender["id"],)).fetchone()[0]
            return Receipt(ref_out, type_, amount, sender["id"], recipient["id"], note, stamp, balance)
    except (SaldoTidakCukup, AkunTidakAktif, BatasTransaksiTerlampaui) as exc:
        # Transaksi uang sudah di-rollback; catat percobaan yang gagal untuk audit.
        _record_failed(conn, sender_id, type_, amount, recipient_id, str(exc))
        raise


def transfer(
    conn: sqlite3.Connection,
    sender_id: str,
    recipient_id: str,
    amount: int | str,
    pin: str,
    note: str = "",
) -> Receipt:
    amount = security.validate_amount(amount, config.MAX_TRANSFER_PER_TX)
    note = security.validate_note(note)
    sender = auth.require_user(conn, sender_id)
    recipient = auth.get_user(conn, (recipient_id or "").strip())
    if recipient is None:
        raise PenerimaTidakDitemukan()
    if recipient.id == sender.id:
        raise TransferKeDiriSendiri()
    auth.verify_pin(conn, sender.id, pin)
    return execute_transfer(conn, sender.id, recipient.id, amount, note, "TRANSFER")


# --------------------------------------------------------------- riwayat
def _to_transaction(row: sqlite3.Row) -> Transaction:
    return Transaction(**{key: row[key] for key in row.keys()})


def get_history(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    type_: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Transaction]:
    """Riwayat milik satu pengguna, terbaru di atas. Tanggal format YYYY-MM-DD."""
    return query_transactions(
        conn, user_id, type_=type_, status=status, date_from=date_from, date_to=date_to, limit=limit, offset=offset
    )


def query_transactions(
    conn: sqlite3.Connection,
    user_id: str | None,
    *,
    type_: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Transaction]:
    """Kueri transaksi dengan filter tervalidasi. `user_id=None` berarti semua pengguna:
    hanya boleh dipanggil dari fungsi yang sudah memeriksa hak admin (core/admin.py)."""
    where: list[str] = []
    params: list = []
    if user_id is not None:
        where.append("user_id = ?")
        params.append(user_id)
    if type_:
        if type_ not in TYPES:
            raise DataTidakValid("Tipe transaksi tidak dikenal.")
        where.append("type = ?")
        params.append(type_)
    if status:
        if status not in ("BERHASIL", "GAGAL", "MENUNGGU"):
            raise DataTidakValid("Status transaksi tidak dikenal.")
        where.append("status = ?")
        params.append(status)
    for column_expr, value in (("substr(created_at, 1, 10) >= ?", date_from), ("substr(created_at, 1, 10) <= ?", date_to)):
        if value:
            if not _DATE_RE.fullmatch(value):
                raise DataTidakValid("Format tanggal harus YYYY-MM-DD.")
            where.append(column_expr)
            params.append(value)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = conn.execute(
        f"SELECT * FROM transactions {clause} ORDER BY id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return [_to_transaction(r) for r in rows]


def get_transaction(conn: sqlite3.Connection, user_id: str, ref_no: str) -> Transaction | None:
    """Detail satu transaksi; hanya jika milik `user_id`."""
    row = conn.execute(
        "SELECT * FROM transactions WHERE ref_no = ? AND user_id = ?", (ref_no, user_id)
    ).fetchone()
    return _to_transaction(row) if row else None
