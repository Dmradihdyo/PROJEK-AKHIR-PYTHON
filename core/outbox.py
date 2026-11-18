"""Kotak surat simulasi: pengganti pengiriman email/SMS untuk kode OTP.

Tidak ada email sungguhan yang dikirim. Kode ditulis ke berkas teks `outbox.txt` di folder
database, sehingga web dan console memakai cara pengiriman yang sama dan pengguna tidak
melihat kode di layar tempat ia memintanya. Berkas ini hanya untuk demo.
"""
from pathlib import Path

from core import clock


def outbox_path(db_path: str | Path) -> Path:
    return Path(db_path).parent / "outbox.txt"


def deliver_otp(db_path: str | Path, user_id: str, email: str, code: str) -> Path:
    path = outbox_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean_email = "".join(ch for ch in email if ch.isprintable())[:120]
    clean_id = "".join(ch for ch in user_id if ch.isprintable())[:64]
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{clock.iso()}] Ke: {clean_email} (akun {clean_id}) | Kode OTP reset password: {code} | berlaku 5 menit\n")
    return path


def tail(db_path: str | Path, lines: int = 10) -> list[str]:
    path = outbox_path(db_path)
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()[-max(1, lines):]
