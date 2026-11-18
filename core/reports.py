"""Laporan dan pemeriksaan konsistensi (dipakai web, console, dan pengujian)."""
import re
import sqlite3
from dataclasses import dataclass

from core.errors import DataTidakValid

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class SummaryRow:
    type: str
    direction: str
    total: int
    count: int


def user_summary(conn: sqlite3.Connection, user_id: str, date_from: str, date_to: str) -> list[SummaryRow]:
    """Total dan jumlah transaksi BERHASIL milik satu pengguna per (tipe, arah) pada rentang
    tanggal (inklusif, format YYYY-MM-DD). Dipakai halaman Statistik dan ringkasan beranda."""
    if not (_DATE_RE.fullmatch(date_from or "") and _DATE_RE.fullmatch(date_to or "")):
        raise DataTidakValid("Format tanggal harus YYYY-MM-DD.")
    if date_from > date_to:
        raise DataTidakValid("Tanggal awal tidak boleh setelah tanggal akhir.")
    rows = conn.execute(
        "SELECT type, direction, SUM(amount) AS total, COUNT(*) AS n FROM transactions "
        "WHERE user_id = ? AND status = 'BERHASIL' AND substr(created_at, 1, 10) BETWEEN ? AND ? "
        "GROUP BY type, direction ORDER BY total DESC",
        (user_id, date_from, date_to),
    ).fetchall()
    return [SummaryRow(r["type"], r["direction"], int(r["total"]), int(r["n"])) for r in rows]


def system_summary(conn: sqlite3.Connection, today: str) -> dict:
    """Ringkasan seluruh sistem (untuk admin). `today` = 'YYYY-MM-DD'."""
    users = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(balance), 0) AS total, "
        "COALESCE(SUM(status = 'BLOKIR'), 0) AS blocked FROM users"
    ).fetchone()
    trx = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(status = 'GAGAL'), 0) AS failed FROM transactions"
    ).fetchone()
    topup_today = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions "
        "WHERE type = 'TOPUP' AND status = 'BERHASIL' AND substr(created_at, 1, 10) = ?",
        (today,),
    ).fetchone()[0]
    count_today = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE direction = 'OUT' AND status = 'BERHASIL' "
        "AND type != 'TOPUP' AND substr(created_at, 1, 10) = ?",
        (today,),
    ).fetchone()[0]
    return {
        "users": int(users["n"]),
        "blocked": int(users["blocked"]),
        "total_balance": int(users["total"]),
        "transactions": int(trx["n"]),
        "failed": int(trx["failed"]),
        "topup_today": int(topup_today),
        "payments_today": int(count_today),
    }


def check_consistency(conn: sqlite3.Connection) -> list[dict]:
    """Bandingkan saldo setiap akun dengan total mutasi BERHASIL (IN - OUT).

    Mengembalikan daftar akun yang tidak cocok; daftar kosong = konsisten."""
    rows = conn.execute(
        "SELECT u.id, u.balance, "
        "COALESCE(SUM(CASE WHEN t.direction = 'IN' THEN t.amount "
        "                  WHEN t.direction = 'OUT' THEN -(t.amount + t.fee) END), 0) AS expected "
        "FROM users u LEFT JOIN transactions t ON t.user_id = u.id AND t.status = 'BERHASIL' "
        "GROUP BY u.id HAVING u.balance != expected"
    ).fetchall()
    return [{"user_id": r["id"], "balance": r["balance"], "expected": r["expected"]} for r in rows]
