"""Helper web: koneksi per request, pengguna saat ini, login_required, redirect aman.

Lapisan web tidak menjalankan SQL sendiri; semua lewat paket `core`.
"""
import re
from functools import wraps
from urllib.parse import urlparse

from flask import current_app, g, redirect, request, session, url_for

from core import auth, db
from core.errors import AkunTerkunci, KredensialSalah

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def get_conn():
    if "conn" not in g:
        g.conn = db.connect(current_app.config["DB_PATH"])
    return g.conn


def close_conn(_exc=None):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


def client_ip() -> str:
    # Sengaja memakai remote_addr, bukan header X-Forwarded-For yang bisa dipalsukan.
    return request.remote_addr or "unknown"


def current_user():
    """Pengguna yang sedang login (atau None). Dicek ulang ke database di setiap
    request, jadi akun yang diblokir langsung kehilangan sesinya."""
    if "user" in g:
        return g.user
    g.user = None
    uid = session.get("uid")
    if uid:
        user = auth.get_user(get_conn(), uid)
        if user is not None and user.is_active:
            g.user = user
        else:
            session.clear()
    return g.user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            if request.method == "GET":
                return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def safe_next(target: str | None) -> str | None:
    """Terima hanya path lokal ('/pay?x=1'). Menolak URL luar, '//host', dan '\\'
    agar parameter ?next= tidak bisa dipakai untuk open redirect."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return None
    if "\\" in target or _CONTROL_RE.search(target):
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


def status_for(exc: Exception) -> int:
    """Kode HTTP untuk galat core."""
    if isinstance(exc, AkunTerkunci):
        return 429
    if isinstance(exc, KredensialSalah):
        return 401
    return 400
