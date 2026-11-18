"""Aplikasi Flask Elektro Wallet (antarmuka web)."""
import os
from datetime import timedelta

from flask import Flask, render_template
from flask_wtf.csrf import CSRFError, CSRFProtect

import config
from core import db
from core.formatting import format_rupiah, short_datetime, tx_label
from web.helpers import close_conn, current_user

csrf = CSRFProtect()

_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
)


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=config.get_secret_key(),
        DB_PATH=str(config.DB_PATH),
        SESSION_COOKIE_NAME="ewallet_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Demo lokal memakai HTTP. Set EWALLET_COOKIE_SECURE=1 bila disajikan lewat HTTPS.
        SESSION_COOKIE_SECURE=os.environ.get("EWALLET_COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=15),  # kedaluwarsa bila tidak aktif
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    csrf.init_app(app)

    conn = db.connect(app.config["DB_PATH"])
    try:
        db.init_db(conn)
    finally:
        conn.close()

    app.teardown_appcontext(close_conn)

    from web.routes import auth_routes, pay_routes, wallet_routes

    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(wallet_routes.bp)
    app.register_blueprint(pay_routes.bp)

    @app.template_filter("rupiah")
    def rupiah_filter(value: int) -> str:
        return format_rupiah(value)

    @app.template_filter("tx_label")
    def tx_label_filter(tx) -> str:
        return tx_label(tx.type, tx.direction)

    @app.template_filter("dt")
    def dt_filter(stamp: str) -> str:
        return short_datetime(stamp)

    @app.template_filter("initial")
    def initial_filter(name: str) -> str:
        return (name or "?")[:1].upper()

    @app.template_filter("first_name")
    def first_name_filter(name: str) -> str:
        return (name or "").split(" ")[0]

    @app.context_processor
    def inject_user():
        return {"user": current_user()}

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self)"
        if not response.direct_passthrough and response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        return "OK", 200, {"Content-Type": "text/plain; charset=utf-8"}

    @app.errorhandler(CSRFError)
    def csrf_error(_exc):
        return (
            render_template(
                "error.html", title="Formulir Kedaluwarsa",
                message="Formulir sudah kedaluwarsa atau tidak valid. Muat ulang halaman lalu coba lagi.",
            ),
            400,
        )

    @app.errorhandler(404)
    def not_found(_exc):
        return render_template("error.html", title="Halaman Tidak Ditemukan", message="Halaman yang dicari tidak ada."), 404

    @app.errorhandler(413)
    def too_large(_exc):
        return render_template("error.html", title="Permintaan Terlalu Besar", message="Data yang dikirim terlalu besar."), 413

    @app.errorhandler(500)
    def server_error(_exc):
        return render_template("error.html", title="Terjadi Kesalahan", message="Terjadi kesalahan di server. Saldo Anda aman; cek riwayat sebelum mengulang."), 500

    return app
