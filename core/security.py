"""Hash password/PIN, token acak, dan validasi input.

Hash: Argon2id (salt acak per pengguna ada di dalam string hash). Sebelum
di-hash, rahasia diberi 'pepper' lewat HMAC-SHA256 dengan kunci aplikasi.
Jika database bocor tetapi kunci tidak, PIN 6 digit tidak bisa ditebak offline.
"""
import hashlib
import hmac
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

import config
from core.errors import (
    DataTidakValid,
    NominalTidakValid,
    PasswordLemah,
    PinTidakValid,
)
from core.formatting import format_rupiah

_hasher = PasswordHasher()
_dummy_hash: str | None = None


# --------------------------------------------------------------------- hash
def _prehash(kind: str, secret: str) -> str:
    key = config.get_secret_key().encode("utf-8")
    return hmac.new(key, f"{kind}:{secret}".encode("utf-8"), hashlib.sha256).hexdigest()


def hash_secret(kind: str, secret: str) -> str:
    """kind = 'password' atau 'pin' (pemisah domain agar hash tidak tertukar)."""
    return _hasher.hash(_prehash(kind, secret))


def verify_secret(kind: str, secret: str, stored: str) -> bool:
    try:
        return _hasher.verify(stored, _prehash(kind, secret))
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    return _hasher.check_needs_rehash(stored)


def burn_verify_time(kind: str, secret: str) -> None:
    """Dipanggil saat User ID tidak ada, agar waktu respons sama dengan ID yang ada
    (mencegah penebakan User ID lewat selisih waktu)."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_secret(kind, "dummy-value")
    verify_secret(kind, secret, _dummy_hash)


# ------------------------------------------------------------------- token
def new_token() -> str:
    return secrets.token_urlsafe(24)


def new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(user_id: str, code: str) -> str:
    key = config.get_secret_key().encode("utf-8")
    return hmac.new(key, f"otp:{user_id.lower()}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def safe_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ----------------------------------------------------------------- validasi
_USER_ID_RE = re.compile(r"[A-Za-z0-9_]{3,20}")
_EMAIL_RE = re.compile(r"[^@\s|]+@[^@\s|]+\.[^@\s|]+")
_NAME_RE = re.compile(r"[A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F0-9 .,'\-]{0,59}")
_PHONE_RE = re.compile(r"(\+62|0)8[0-9]{7,12}")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def validate_user_id(value: str) -> str:
    value = (value or "").strip()
    if not _USER_ID_RE.fullmatch(value):
        raise DataTidakValid("User ID harus 3-20 karakter: huruf, angka, atau garis bawah (_).")
    return value


def validate_name(value: str) -> str:
    value = " ".join((value or "").split())
    if not _NAME_RE.fullmatch(value):
        raise DataTidakValid("Nama harus diawali huruf, maksimal 60 karakter (huruf, angka, spasi, . , ' -).")
    return value


def validate_email(value: str) -> str:
    value = (value or "").strip().lower()
    if len(value) > 120 or not _EMAIL_RE.fullmatch(value):
        raise DataTidakValid("Format email tidak valid.")
    return value


def validate_phone(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if not _PHONE_RE.fullmatch(value):
        raise DataTidakValid("Nomor HP tidak valid (contoh: 081234567890).")
    return value


def validate_password(value: str) -> str:
    value = value or ""
    if (
        not 8 <= len(value) <= 128
        or not any(c.isupper() for c in value)
        or not any(c.islower() for c in value)
        or not any(c.isdigit() for c in value)
    ):
        raise PasswordLemah()
    return value


def validate_pin(value: str) -> str:
    value = value or ""
    if len(value) != 6 or any(c not in "0123456789" for c in value):
        raise PinTidakValid()
    return value


def validate_note(value: str | None) -> str:
    value = " ".join((value or "").split())
    if len(value) > 100 or _CONTROL_RE.search(value):
        raise DataTidakValid("Catatan maksimal 100 karakter.")
    return value


def parse_amount(value: int | str) -> int:
    """Terima int atau teks berisi digit saja. Menolak float, negatif, '1e9', spasi."""
    if isinstance(value, bool):
        raise NominalTidakValid()
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 12:
        return int(value)
    raise NominalTidakValid("Nominal harus berupa bilangan bulat Rupiah (hanya angka).")


def validate_amount(value: int | str, maximum: int) -> int:
    amount = parse_amount(value)
    if amount < config.MIN_AMOUNT:
        raise NominalTidakValid(f"Nominal minimal {format_rupiah(config.MIN_AMOUNT)}.")
    if amount > maximum:
        raise NominalTidakValid(f"Nominal maksimal {format_rupiah(maximum)} per transaksi.")
    return amount
