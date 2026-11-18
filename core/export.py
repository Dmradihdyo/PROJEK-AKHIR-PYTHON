"""Ekspor riwayat transaksi ke CSV (dipakai web dan console)."""
import csv
import io
from typing import Iterable

from core.models import Transaction

HEADER = ["no_referensi", "waktu", "tipe", "arah", "nominal", "lawan", "catatan", "status"]


def csv_safe(value) -> str:
    """Cegah CSV injection: sel yang diawali = + - @ dibaca Excel sebagai rumus."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def transactions_to_csv(rows: Iterable[Transaction]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(HEADER)
    for t in rows:
        writer.writerow(
            [t.ref_no, t.created_at, t.type, t.direction, t.amount, csv_safe(t.counterparty_id), csv_safe(t.note), t.status]
        )
    return out.getvalue()
