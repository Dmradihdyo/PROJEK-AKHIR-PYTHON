"""Sumber waktu tunggal. Pengujian cukup mengganti `clock.now`."""
import time


def now() -> int:
    """Detik epoch saat ini."""
    return int(time.time())


def iso(ts: int | None = None) -> str:
    """Waktu lokal 'YYYY-MM-DD HH:MM:SS' (dipakai di kolom created_at)."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now() if ts is None else ts))


def today() -> str:
    """Tanggal lokal 'YYYY-MM-DD'."""
    return iso()[:10]
