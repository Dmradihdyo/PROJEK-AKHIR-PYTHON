"""Pembuatan QR Code dan URL pembayaran.

QR nominal tetap menandatangani merchant, nominal, dan masa berlaku. Parameter URL
boleh dibaca atau diubah oleh pembayar, tetapi server hanya menerima payload jika
signature HMAC masih valid.
"""
import hashlib
import hmac
from urllib.parse import quote

import qrcode
from qrcode.constants import ERROR_CORRECT_M

import config
from core import clock

BORDER = 4  # quiet zone standar QR: 4 modul


def _fixed_payload_signature(merchant_id: str, amount: int, expires_at: int) -> str:
    secret = config.get_secret_key().encode("utf-8")
    payload = f"qr-fixed:{merchant_id.lower()}:{amount}:{expires_at}".encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def build_pay_url(
    host: str,
    port: int,
    merchant_id: str,
    amount: int | None = None,
    expires_at: int | None = None,
) -> str:
    """URL QR pembayaran.

    Tanpa amount: pembayar mengisi nominal sendiri.
    Dengan amount + expires_at: nominal tetap dan signature ditambahkan.
    """
    url = f"http://{host}:{port}/pay?merchant={quote(merchant_id, safe='')}"
    if amount is not None:
        if expires_at is None:
            raise ValueError("expires_at wajib untuk QR nominal tetap")
        signature = _fixed_payload_signature(merchant_id, int(amount), int(expires_at))
        url += f"&amount={int(amount)}&expires={int(expires_at)}&sig={signature}"
    return url


def verify_fixed_payload(
    merchant_id: str, amount_text: str, expires_text: str, signature: str, now: int | None = None
) -> int | None:
    """Kembalikan nominal jika payload QR nominal tetap sah dan belum kedaluwarsa."""
    if not (amount_text or "").isdigit() or not (expires_text or "").isdigit():
        return None
    amount = int(amount_text)
    expires_at = int(expires_text)
    if amount <= 0 or expires_at < (clock.now() if now is None else now):
        return None
    expected = _fixed_payload_signature(merchant_id, amount, expires_at)
    if not hmac.compare_digest(expected, signature or ""):
        return None
    return amount


def matrix(text: str) -> list[list[bool]]:
    """Matriks modul termasuk quiet zone (True = hitam)."""
    code = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=BORDER)
    code.add_data(text)
    code.make(fit=True)
    return code.get_matrix()


def to_svg(text: str, label: str = "QR Code pembayaran") -> str:
    """SVG vektor (tajam di ukuran berapa pun). Isinya hanya satu <path> dari koordinat
    angka, jadi aman disisipkan langsung ke HTML (tanpa style/script inline)."""
    grid = matrix(text)
    size = len(grid)
    parts = []
    for y, row in enumerate(grid):
        x = 0
        while x < size:
            if row[x]:
                start = x
                while x < size and row[x]:
                    x += 1
                parts.append(f"M{start},{y}h{x - start}v1h-{x - start}z")
            else:
                x += 1
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'role="img" aria-label="{label}" shape-rendering="crispEdges">'
        f'<rect width="{size}" height="{size}" fill="#ffffff"/>'
        f'<path fill="#000000" d="{"".join(parts)}"/></svg>'
    )


def to_ansi(text: str) -> str:
    """Untuk terminal (console): latar putih/hitam, 2 spasi per modul agar mendekati persegi."""
    white, black, reset = "\033[107m  \033[0m", "\033[40m  \033[0m", "\033[0m"
    lines = ["".join(black if cell else white for cell in row) for row in matrix(text)]
    return "\n".join(lines) + reset
