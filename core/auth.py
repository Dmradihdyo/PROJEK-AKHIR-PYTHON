"""Registrasi, login, PIN, dan lupa password (OTP simulasi).

Pembatasan percobaan (lockout) disimpan di tabel `attempts`:
- LOGIN     per pasangan (User ID, IP). Penyerang di IP lain tidak bisa mengunci
            akun korban, dan korban tetap bisa login dari perangkatnya sendiri.
- LOGIN_IP  per IP, lintas User ID (menahan penebakan banyak akun dari satu IP).
- PIN       per User ID (PIN hanya dipakai setelah login, jadi penyerangnya
            sudah memegang sesi korban).
- PWD       verifikasi password saat ganti PIN.
- RESET     permintaan OTP lupa password.
Kunci berlipat dua pada kunci berulang, dan baris lama dibersihkan satu per satu
(tidak pernah dikosongkan sekaligus).
"""
import sqlite3

import config
from core import clock, security
from core.audit import log as audit
from core.db import immediate_tx
from core.errors import (
    AkunTerkunci,
    AkunTidakAktif,
    AkunTidakDitemukan,
    EmailSudahAda,
    IdSudahAda,
    KredensialSalah,
    OtpTidakValid,
    PinSalah,
)
from core.models import User

LOCAL_IP = "local"  # dipakai console (tidak ada alamat IP klien)


# ------------------------------------------------------------------ pengguna
def _to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        phone=row["phone"],
        balance=row["balance"],
        role=row["role"],
        status=row["status"],
        created_at=row["created_at"],
    )


def get_user(conn: sqlite3.Connection, user_id: str) -> User | None:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _to_user(row) if row else None


def count_users(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def require_user(conn: sqlite3.Connection, user_id: str) -> User:
    user = get_user(conn, user_id)
    if user is None:
        raise AkunTidakDitemukan()
    return user


# ---------------------------------------------------------------- lockout
def _lock_remaining(conn: sqlite3.Connection, kind: str, subject: str) -> int:
    row = conn.execute(
        "SELECT locked_until FROM attempts WHERE kind = ? AND subject = ?", (kind, subject)
    ).fetchone()
    if row and row["locked_until"] > clock.now():
        return row["locked_until"] - clock.now()
    return 0


def _fail(conn: sqlite3.Connection, kind: str, subject: str, max_fails: int) -> tuple[int, int]:
    """Catat satu kegagalan. Mengembalikan (sisa_percobaan, detik_kunci).

    detik_kunci > 0 berarti kunci baru saja dipasang."""
    now = clock.now()
    with immediate_tx(conn):
        conn.execute(
            "DELETE FROM attempts WHERE locked_until < ? AND last_failed < ?", (now, now - 3600)
        )
        row = conn.execute(
            "SELECT failed, lock_count, locked_until, last_failed FROM attempts WHERE kind = ? AND subject = ?",
            (kind, subject),
        ).fetchone()
        failed, lock_count = 0, 0
        if row:
            failed, lock_count = row["failed"], row["lock_count"]
            idle = now - row["last_failed"]
            if idle > config.ATTEMPT_WINDOW:
                failed = 0
            if idle > 3600:
                lock_count = 0
        failed += 1
        remaining, lock_seconds, locked_until = max_fails - failed, 0, 0
        if failed >= max_fails:
            lock_seconds = min(config.LOCK_BASE_SECONDS * (2**lock_count), config.LOCK_MAX_SECONDS)
            locked_until = now + lock_seconds
            lock_count += 1
            failed, remaining = 0, 0
            audit(conn, subject, "LOCKOUT", f"{kind} dikunci {lock_seconds} detik")
        conn.execute(
            "INSERT INTO attempts (kind, subject, failed, lock_count, locked_until, last_failed) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(kind, subject) DO UPDATE SET failed = excluded.failed, "
            "lock_count = excluded.lock_count, locked_until = excluded.locked_until, "
            "last_failed = excluded.last_failed",
            (kind, subject, failed, lock_count, locked_until, now),
        )
    return remaining, lock_seconds


def _clear(conn: sqlite3.Connection, kind: str, subject: str) -> None:
    exists = conn.execute(
        "SELECT 1 FROM attempts WHERE kind = ? AND subject = ?", (kind, subject)
    ).fetchone()
    if exists:  # hindari mengambil kunci tulis jika tidak perlu
        conn.execute("DELETE FROM attempts WHERE kind = ? AND subject = ?", (kind, subject))


def _clean_ip(ip: str | None) -> str:
    return (ip or LOCAL_IP).strip()[:64] or LOCAL_IP


# --------------------------------------------------------------- registrasi
def _create_user(
    conn: sqlite3.Connection,
    user_id: str,
    name: str,
    email: str,
    password: str,
    pin: str,
    phone: str | None,
    role: str,
) -> User:
    user_id = security.validate_user_id(user_id)
    name = security.validate_name(name)
    email = security.validate_email(email)
    phone = security.validate_phone(phone)
    security.validate_password(password)
    security.validate_pin(pin)

    if conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone():
        raise IdSudahAda()
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise EmailSudahAda()

    password_hash = security.hash_secret("password", password)
    pin_hash = security.hash_secret("pin", pin)
    try:
        with immediate_tx(conn):
            conn.execute(
                "INSERT INTO users (id, name, email, phone, password_hash, pin_hash, balance, role, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, ?, 'AKTIF', ?)",
                (user_id, name, email, phone, password_hash, pin_hash, role, clock.iso()),
            )
            audit(conn, user_id, "REGISTER", f"role={role}")
    except sqlite3.IntegrityError as exc:  # balapan dua pendaftaran bersamaan
        message = str(exc).lower()
        if "email" in message:
            raise EmailSudahAda() from exc
        raise IdSudahAda() from exc
    return require_user(conn, user_id)


def register(
    conn: sqlite3.Connection,
    user_id: str,
    name: str,
    email: str,
    password: str,
    pin: str,
    phone: str | None = None,
) -> User:
    """Pendaftaran publik: role selalu USER."""
    return _create_user(conn, user_id, name, email, password, pin, phone, "USER")


def create_admin(
    conn: sqlite3.Connection, user_id: str, name: str, email: str, password: str, pin: str
) -> User:
    """Hanya untuk scripts/init_db.py. Tidak dipanggil dari web."""
    return _create_user(conn, user_id, name, email, password, pin, None, "ADMIN")


# -------------------------------------------------------------------- login
def login(conn: sqlite3.Connection, user_id: str, password: str, ip: str | None = None) -> User:
    user_id = (user_id or "").strip()[:64]
    password = password if isinstance(password, str) else ""
    ip = _clean_ip(ip)
    subject = f"{user_id.lower()}|{ip}"

    remaining = max(_lock_remaining(conn, "LOGIN", subject), _lock_remaining(conn, "LOGIN_IP", ip))
    if remaining:
        raise AkunTerkunci(remaining)

    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row:
        ok = security.verify_secret("password", password, row["password_hash"])
    else:
        security.burn_verify_time("password", password)
        ok = False

    if not ok:
        _, lock_user = _fail(conn, "LOGIN", subject, config.LOGIN_MAX_FAILS)
        _, lock_ip = _fail(conn, "LOGIN_IP", ip, config.IP_MAX_FAILS)
        if max(lock_user, lock_ip):
            raise AkunTerkunci(max(lock_user, lock_ip))
        raise KredensialSalah()

    if row["status"] != "AKTIF":
        raise AkunTidakAktif()

    _clear(conn, "LOGIN", subject)  # counter IP sengaja tidak di-reset
    if security.needs_rehash(row["password_hash"]):
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (security.hash_secret("password", password), row["id"]),
        )
    return _to_user(row)


# ---------------------------------------------------------------------- PIN
def verify_pin(conn: sqlite3.Connection, user_id: str, pin: str) -> None:
    """Dipanggil oleh setiap operasi yang memindahkan saldo. Melempar PinSalah /
    AkunTerkunci; kembali tanpa nilai jika PIN benar."""
    subject = user_id.lower()
    remaining = _lock_remaining(conn, "PIN", subject)
    if remaining:
        raise AkunTerkunci(remaining)

    row = conn.execute("SELECT pin_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise AkunTidakDitemukan()
    pin = pin if isinstance(pin, str) else ""
    if security.verify_secret("pin", pin, row["pin_hash"]):
        _clear(conn, "PIN", subject)
        return

    left, lock = _fail(conn, "PIN", subject, config.PIN_MAX_FAILS)
    if lock:
        raise AkunTerkunci(lock)
    raise PinSalah(left)


def change_pin(conn: sqlite3.Connection, user_id: str, password: str, new_pin: str) -> None:
    """Ganti PIN setelah verifikasi password (juga berfungsi sebagai 'lupa PIN')."""
    security.validate_pin(new_pin)
    subject = user_id.lower()
    remaining = _lock_remaining(conn, "PWD", subject)
    if remaining:
        raise AkunTerkunci(remaining)

    row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise AkunTidakDitemukan()
    password = password if isinstance(password, str) else ""
    if not security.verify_secret("password", password, row["password_hash"]):
        _, lock = _fail(conn, "PWD", subject, config.LOGIN_MAX_FAILS)
        if lock:
            raise AkunTerkunci(lock)
        raise KredensialSalah("Password salah.")
    _clear(conn, "PWD", subject)

    with immediate_tx(conn):
        conn.execute(
            "UPDATE users SET pin_hash = ? WHERE id = ?", (security.hash_secret("pin", new_pin), user_id)
        )
        audit(conn, user_id, "PIN_CHANGE")
    _clear(conn, "PIN", subject)


# ---------------------------------------------------------- lupa password
def request_password_reset(
    conn: sqlite3.Connection, user_id: str, email: str, ip: str | None = None
) -> str | None:
    """Buat OTP 6 digit (simulasi: tidak ada email sungguhan).

    Mengembalikan kode jika User ID + email cocok, selain itu None. Pemanggil
    wajib menyampaikan hasil ke pengguna dengan pesan yang sama di kedua kasus
    (agar tidak membocorkan akun mana yang ada). Pada mode demo, kode
    ditampilkan di log server atau console admin, bukan di layar pengguna."""
    user_id = (user_id or "").strip()[:64]
    email = (email or "").strip().lower()
    ip = _clean_ip(ip)
    subject = f"{user_id.lower()}|{ip}"

    remaining = _lock_remaining(conn, "RESET", subject)
    if remaining:
        raise AkunTerkunci(remaining)
    # Setiap permintaan dihitung, berhasil atau tidak.
    _fail(conn, "RESET", subject, config.LOGIN_MAX_FAILS)

    row = conn.execute("SELECT id, email, status FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None or row["email"].lower() != email or row["status"] != "AKTIF":
        return None

    code = security.new_otp()
    with immediate_tx(conn):
        conn.execute("UPDATE otp_codes SET used = 1 WHERE user_id = ? AND used = 0", (row["id"],))
        conn.execute(
            "INSERT INTO otp_codes (user_id, code_hash, expires_at) VALUES (?, ?, ?)",
            (row["id"], security.hash_otp(row["id"], code), clock.now() + config.OTP_TTL),
        )
        audit(conn, row["id"], "PASSWORD_RESET_REQUEST", f"ip={ip}")
    return code


def reset_password(conn: sqlite3.Connection, user_id: str, otp: str, new_password: str) -> None:
    security.validate_password(new_password)
    user_id = (user_id or "").strip()[:64]
    otp = otp if isinstance(otp, str) else ""

    row = conn.execute(
        "SELECT o.id, o.code_hash, o.failed, u.id AS uid FROM otp_codes o "
        "JOIN users u ON u.id = o.user_id "
        "WHERE o.user_id = ? AND o.used = 0 AND o.expires_at >= ? "
        "ORDER BY o.id DESC LIMIT 1",
        (user_id, clock.now()),
    ).fetchone()
    if row is None or row["failed"] >= config.OTP_MAX_FAILS:
        raise OtpTidakValid()

    if not security.safe_equal(row["code_hash"], security.hash_otp(row["uid"], otp)):
        conn.execute("UPDATE otp_codes SET failed = failed + 1 WHERE id = ?", (row["id"],))
        raise OtpTidakValid()

    with immediate_tx(conn):
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (security.hash_secret("password", new_password), row["uid"]),
        )
        conn.execute("UPDATE otp_codes SET used = 1 WHERE user_id = ?", (row["uid"],))
        audit(conn, row["uid"], "PASSWORD_RESET")
