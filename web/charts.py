"""Data grafik donat. Dirender sebagai SVG dengan atribut saja (aman untuk CSP, tanpa style inline)."""

PALETTE_SIZE = 5  # jumlah warna di app.css (.seg-0 .. .seg-4)


def donut_segments(values: list[int]) -> list[dict]:
    """Ubah nilai menjadi segmen donat pada lingkaran berkeliling 100 (r = 15.9155).

    Tiap segmen: index warna, pct (panjang garis), gap, offset (stroke-dashoffset).
    Segmen pertama dimulai dari jam 12 (offset 25)."""
    total = sum(v for v in values if v > 0)
    if total <= 0:
        return []
    segments, used = [], 0.0
    for i, value in enumerate(values):
        if value <= 0:
            continue
        pct = value / total * 100
        segments.append(
            {
                "index": i % PALETTE_SIZE,
                "pct": round(pct, 3),
                "gap": round(100 - pct, 3),
                "offset": round(25 - used, 3),
                "share": round(pct),
            }
        )
        used += pct
    return segments
