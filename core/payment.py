"""Pembayaran via QR (pengirim sudah login).

Alur:  GET /pay?merchant=ID  ->  get_merchant_for_qr()
       POST /pay/review      ->  create_pay_session()   (nominal + ringkasan)
       POST /pay/confirm     ->  confirm_payment()      (PIN + transfer)

Sesi berlaku `PAY_SESSION_TTL` detik dan sekali pakai. Penandaan 'terpakai' dan
transfer berada dalam satu transaksi database, jadi klik ganda atau refresh
tidak dapat menggandakan pembayaran.
"""
import sqlite3

import config
from core import auth, clock, security, wallet
from core.db import immediate_tx
from core.errors import (
    AkunTidakAktif,
    PenerimaTidakDitemukan,
    SaldoTidakCukup,
    SesiTidakValid,
    TransferKeDiriSendiri,
)
from core.models import PaySession, Receipt, User


def get_merchant_for_qr(conn: sqlite3.Connection, merchant_id: str) -> User:
    merchant = auth.get_user(conn, (merchant_id or "").strip()[:64])
    if merchant is None or not merchant.is_active:
        raise PenerimaTidakDitemukan("QR Code tidak dikenali: penerima tidak ditemukan atau tidak aktif.")
    return merchant


def create_pay_session(
    conn: sqlite3.Connection, sender_id: str, merchant_id: str, amount: int | str
) -> PaySession:
    amount = security.validate_amount(amount, config.MAX_TRANSFER_PER_TX)
    sender = auth.require_user(conn, sender_id)
    if not sender.is_active:
        raise AkunTidakAktif()
    merchant = get_merchant_for_qr(conn, merchant_id)
    if merchant.id == sender.id:
        raise TransferKeDiriSendiri("Anda tidak dapat membayar ke akun Anda sendiri.")
    if sender.balance < amount:
        raise SaldoTidakCukup()

    token = security.new_token()
    expires_at = clock.now() + config.PAY_SESSION_TTL
    with immediate_tx(conn):
        conn.execute("DELETE FROM pay_sessions WHERE expires_at < ?", (clock.now(),))
        conn.execute(
            "INSERT INTO pay_sessions (token, sender_id, merchant_id, amount, expires_at, used) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            (token, sender.id, merchant.id, amount, expires_at),
        )
    return PaySession(token, sender.id, merchant.id, merchant.name, amount, expires_at)


def get_pay_session(conn: sqlite3.Connection, sender_id: str, token: str) -> PaySession:
    """Sesi yang masih berlaku dan milik `sender_id`; selain itu SesiTidakValid."""
    row = conn.execute(
        "SELECT s.token, s.sender_id, s.merchant_id, s.amount, s.expires_at, m.name AS merchant_name "
        "FROM pay_sessions s JOIN users m ON m.id = s.merchant_id "
        "WHERE s.token = ? AND s.used = 0 AND s.expires_at >= ?",
        ((token or "")[:100], clock.now()),
    ).fetchone()
    if row is None or row["sender_id"].lower() != (sender_id or "").lower() or row["amount"] is None:
        raise SesiTidakValid()
    return PaySession(
        row["token"], row["sender_id"], row["merchant_id"], row["merchant_name"], row["amount"], row["expires_at"]
    )


def confirm_payment(conn: sqlite3.Connection, sender_id: str, token: str, pin: str) -> Receipt:
    session = get_pay_session(conn, sender_id, token)
    auth.verify_pin(conn, session.sender_id, pin)

    def mark_used() -> None:
        cur = conn.execute(
            "UPDATE pay_sessions SET used = 1 WHERE token = ? AND used = 0 AND expires_at >= ?",
            (session.token, clock.now()),
        )
        if cur.rowcount != 1:
            raise SesiTidakValid()

    return wallet.execute_transfer(
        conn, session.sender_id, session.merchant_id, session.amount, "Pembayaran QR", "QR_PAYMENT", mark_used
    )
