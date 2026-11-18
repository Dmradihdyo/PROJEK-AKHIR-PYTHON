"""Koneksi SQLite, skema, dan helper transaksi.

Koneksi dibuat dengan `isolation_level=None` (mode autocommit), sehingga
transaksi hanya dimulai secara eksplisit lewat `immediate_tx()`. Dengan
`BEGIN IMMEDIATE`, kunci tulis diambil di awal: dua transfer bersamaan dari
saldo yang sama tidak bisa saling menyalip.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import config

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY COLLATE NOCASE,
  name          TEXT NOT NULL,
  email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
  phone         TEXT UNIQUE,
  password_hash TEXT NOT NULL,
  pin_hash      TEXT NOT NULL,
  balance       INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
  role          TEXT NOT NULL DEFAULT 'USER' CHECK (role IN ('USER','MERCHANT','ADMIN')),
  status        TEXT NOT NULL DEFAULT 'AKTIF' CHECK (status IN ('AKTIF','BLOKIR')),
  created_at    TEXT NOT NULL
);

-- Satu transfer = dua baris (OUT milik pengirim, IN milik penerima).
-- ref_no unik per baris; group_ref sama untuk pasangan baris tersebut.
CREATE TABLE IF NOT EXISTS transactions (
  id              INTEGER PRIMARY KEY,
  ref_no          TEXT NOT NULL UNIQUE,
  group_ref       TEXT NOT NULL,
  user_id         TEXT NOT NULL COLLATE NOCASE REFERENCES users(id),
  type            TEXT NOT NULL CHECK (type IN ('TOPUP','TRANSFER','QR_PAYMENT','BILL','PULSA')),
  direction       TEXT NOT NULL CHECK (direction IN ('IN','OUT')),
  amount          INTEGER NOT NULL CHECK (amount > 0),
  fee             INTEGER NOT NULL DEFAULT 0 CHECK (fee >= 0),
  counterparty_id TEXT COLLATE NOCASE,
  note            TEXT,
  status          TEXT NOT NULL CHECK (status IN ('BERHASIL','GAGAL','MENUNGGU')),
  created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trx_user ON transactions(user_id, id);
CREATE INDEX IF NOT EXISTS idx_trx_group ON transactions(group_ref);

CREATE TABLE IF NOT EXISTS pay_sessions (
  token       TEXT PRIMARY KEY,
  sender_id   TEXT NOT NULL COLLATE NOCASE REFERENCES users(id),
  merchant_id TEXT NOT NULL COLLATE NOCASE REFERENCES users(id),
  amount      INTEGER CHECK (amount IS NULL OR amount > 0),
  expires_at  INTEGER NOT NULL,
  used        INTEGER NOT NULL DEFAULT 0 CHECK (used IN (0,1))
);

CREATE TABLE IF NOT EXISTS payment_requests (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  requester_id TEXT NOT NULL COLLATE NOCASE REFERENCES users(id),
  payer_id     TEXT COLLATE NOCASE REFERENCES users(id),
  amount       INTEGER NOT NULL CHECK (amount > 0),
  note         TEXT,
  status       TEXT NOT NULL DEFAULT 'MENUNGGU'
               CHECK (status IN ('MENUNGGU','DIBAYAR','DITOLAK','KEDALUWARSA')),
  expires_at   INTEGER NOT NULL
);

-- Pembatasan percobaan untuk login, PIN, dan reset password. Tersimpan di
-- database sehingga tidak hilang saat server dimulai ulang.
CREATE TABLE IF NOT EXISTS attempts (
  kind         TEXT NOT NULL,      -- LOGIN | LOGIN_IP | PIN | PWD | RESET
  subject      TEXT NOT NULL,      -- 'user|ip', 'ip', atau user_id
  failed       INTEGER NOT NULL DEFAULT 0,
  lock_count   INTEGER NOT NULL DEFAULT 0,
  locked_until INTEGER NOT NULL DEFAULT 0,
  last_failed  INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (kind, subject)
);

CREATE TABLE IF NOT EXISTS otp_codes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    TEXT NOT NULL COLLATE NOCASE REFERENCES users(id),
  code_hash  TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  failed     INTEGER NOT NULL DEFAULT 0,
  used       INTEGER NOT NULL DEFAULT 0 CHECK (used IN (0,1))
);

CREATE TABLE IF NOT EXISTS audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  actor      TEXT NOT NULL,
  action     TEXT NOT NULL,
  detail     TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS refunds (
  original_ref_no TEXT PRIMARY KEY,
  refund_ref_no   TEXT NOT NULL UNIQUE,
  actor_id        TEXT NOT NULL REFERENCES users(id),
  reason          TEXT NOT NULL,
  created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS complaints (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  reporter_id     TEXT NOT NULL COLLATE NOCASE REFERENCES users(id),
  transaction_ref TEXT,
  category        TEXT NOT NULL CHECK (category IN ('TRANSACTION','ACCOUNT','QR','OTHER')),
  message         TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'OPEN'
                  CHECK (status IN ('OPEN','IN_PROGRESS','RESOLVED','REJECTED')),
  admin_id        TEXT COLLATE NOCASE REFERENCES users(id),
  admin_note      TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_complaints_reporter ON complaints(reporter_id, id);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status, id);
CREATE INDEX IF NOT EXISTS idx_refunds_refund ON refunds(refund_ref_no);
"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Buka koneksi baru. Gunakan satu koneksi per thread/request."""
    target = str(path if path is not None else config.DB_PATH)
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    if target != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Buat tabel jika belum ada (aman dijalankan berulang)."""
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


@contextmanager
def immediate_tx(conn: sqlite3.Connection):
    """Transaksi tulis atomik: COMMIT jika sukses, ROLLBACK jika ada exception.

    Tidak boleh bersarang. Catatan percobaan gagal (lockout) sengaja ditulis di
    luar transaksi uang agar tidak ikut dibatalkan oleh ROLLBACK.
    """
    if conn.in_transaction:
        raise RuntimeError("immediate_tx tidak boleh bersarang")
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
