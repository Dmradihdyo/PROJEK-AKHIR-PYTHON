"""Konfigurasi Elektro Wallet.

Nilai dapat diubah lewat variabel lingkungan (atau file .env). Semua nominal
dalam Rupiah bulat (int).
"""
import functools
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("EWALLET_DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.environ.get("EWALLET_DB", DATA_DIR / "ewallet.db"))


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        return default
    return value if low <= value <= high else default


# --- Web ---
PORT = _int_env("EWALLET_PORT", 8080, 1024, 65535)
# IP yang ditanam di QR. Kosong = deteksi otomatis (lihat core/netinfo.py).
HOST_IP = os.environ.get("EWALLET_HOST_IP", "").strip()

# --- Aturan nominal (satu aturan untuk web dan console) ---
MIN_AMOUNT = 1_000
MAX_TOPUP_PER_TX = 5_000_000
MAX_TRANSFER_PER_TX = 10_000_000
DAILY_TOPUP_LIMIT = 10_000_000
DAILY_OUT_LIMIT = 20_000_000  # total transfer + pembayaran QR keluar per hari

# --- Sesi pembayaran QR ---
PAY_SESSION_TTL = 300  # detik

# --- Pembatasan percobaan (anti brute-force) ---
LOGIN_MAX_FAILS = 5  # per pasangan (User ID, IP)
IP_MAX_FAILS = 20  # per IP, lintas User ID
PIN_MAX_FAILS = 3  # per User ID
LOCK_BASE_SECONDS = 60  # kunci pertama; berlipat dua tiap kunci berulang
LOCK_MAX_SECONDS = 900
ATTEMPT_WINDOW = 900  # hitungan gagal dilupakan bila tak ada kegagalan baru

# --- OTP lupa password (simulasi) ---
OTP_TTL = 300
OTP_MAX_FAILS = 5


@functools.lru_cache(maxsize=1)
def _file_secret() -> str:
    path = DATA_DIR / "secret.key"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    path.write_text(key, encoding="utf-8")
    return key


def get_secret_key() -> str:
    """Kunci rahasia aplikasi (cookie Flask dan 'pepper' hash).

    Urutan: variabel EWALLET_SECRET_KEY, lalu file data/secret.key (dibuat
    otomatis). Jika kunci hilang atau berubah, semua password/PIN lama tidak
    bisa diverifikasi lagi.
    """
    return os.environ.get("EWALLET_SECRET_KEY") or _file_secret()
