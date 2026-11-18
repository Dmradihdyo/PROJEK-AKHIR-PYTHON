"""Format tampilan."""


TX_LABELS = {
    ("TOPUP", "IN"): "Top Up",
    ("TRANSFER", "OUT"): "Transfer Keluar",
    ("TRANSFER", "IN"): "Transfer Masuk",
    ("QR_PAYMENT", "OUT"): "Bayar via QR",
    ("QR_PAYMENT", "IN"): "Terima via QR",
}

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")


def tx_label(type_: str, direction: str) -> str:
    """Nama transaksi yang ramah pengguna, mis. ('TRANSFER', 'OUT') -> 'Transfer Keluar'."""
    return TX_LABELS.get((type_, direction), type_.replace("_", " ").title())


def short_datetime(stamp: str) -> str:
    """'2026-09-21 15:02:11' -> '21 Sep 2026, 15:02'. Teks yang tidak dikenal dikembalikan apa adanya."""
    try:
        date_part, time_part = stamp.split(" ")
        year, month, day = (int(x) for x in date_part.split("-"))
        return f"{day} {_MONTHS[month - 1]} {year}, {time_part[:5]}"
    except (ValueError, IndexError):
        return stamp


def format_rupiah(amount: int) -> str:
    """1500000 -> 'Rp 1.500.000'."""
    sign = "-" if amount < 0 else ""
    return f"{sign}Rp {abs(int(amount)):,}".replace(",", ".")
