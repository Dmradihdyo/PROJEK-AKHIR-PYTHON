"""Registrasi, login/logout, dan lupa password."""
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from core import auth, outbox
from core.errors import DataTidakValid, EWalletError
from web.helpers import client_ip, current_user, get_conn, safe_next, status_for

bp = Blueprint("auth", __name__)


@bp.get("/")
def index():
    if current_user():
        return redirect(url_for("wallet.dashboard"))
    return render_template("welcome.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("wallet.dashboard"))
    nxt = safe_next(request.values.get("next"))
    status = 200
    if request.method == "POST":
        try:
            user = auth.login(
                get_conn(), request.form.get("user_id", ""), request.form.get("password", ""), ip=client_ip()
            )
        except EWalletError as exc:
            flash(str(exc), "danger")
            status = status_for(exc)
        else:
            if user.is_admin:
                flash("Akun admin hanya dapat diakses melalui Console.", "warning")
                status = 403
            else:
                session.clear()  # sesi baru setiap login (mencegah session fixation)
                session["uid"] = user.id
                session.permanent = True
                return redirect(nxt or url_for("wallet.dashboard"))
    return render_template("login.html", next=nxt), status


@bp.post("/logout")
def logout():
    session.clear()
    flash("Anda telah keluar.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("wallet.dashboard"))
    status = 200
    form = request.form
    if request.method == "POST":
        try:
            if form.get("password", "") != form.get("password2", ""):
                raise DataTidakValid("Konfirmasi password tidak cocok.")
            if form.get("pin", "") != form.get("pin2", ""):
                raise DataTidakValid("Konfirmasi PIN tidak cocok.")
            auth.register(
                get_conn(),
                form.get("user_id", ""),
                form.get("name", ""),
                form.get("email", ""),
                form.get("password", ""),
                form.get("pin", ""),
                form.get("phone", ""),
            )
        except EWalletError as exc:
            flash(str(exc), "danger")
            status = status_for(exc)
        else:
            flash("Akun berhasil dibuat. Silakan login.", "success")
            return redirect(url_for("auth.login"))
    return render_template("register.html", form=form), status


@bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    status = 200
    if request.method == "POST":
        user_id = request.form.get("user_id", "")
        try:
            code = auth.request_password_reset(get_conn(), user_id, request.form.get("email", ""), ip=client_ip())
        except EWalletError as exc:
            flash(str(exc), "danger")
            status = status_for(exc)
        else:
            if code:
                # MODE DEMO: tidak ada email sungguhan. Kode ditulis ke "kotak surat" simulasi
                # (outbox.txt di folder database) dan dicatat di terminal server.
                outbox.deliver_otp(current_app.config["DB_PATH"], user_id.strip(), request.form.get("email", ""), code)
                current_app.logger.warning("[DEMO OTP] Kode reset password untuk '%s': %s", user_id.strip(), code)
            # Pesan sama untuk akun ada/tidak ada, agar tidak membocorkan akun yang terdaftar.
            flash(
                "Jika User ID dan email cocok, kode OTP telah dikirim. "
                "(Mode demo: tidak ada email sungguhan; kode ada di terminal server dan berkas outbox.txt.)",
                "info",
            )
            return redirect(url_for("auth.reset", user_id=user_id.strip()))
    return render_template("forgot.html"), status


@bp.route("/reset", methods=["GET", "POST"])
def reset():
    status = 200
    user_id = request.values.get("user_id", "").strip()
    if request.method == "POST":
        try:
            if request.form.get("password", "") != request.form.get("password2", ""):
                raise DataTidakValid("Konfirmasi password tidak cocok.")
            auth.reset_password(get_conn(), user_id, request.form.get("otp", "").strip(), request.form.get("password", ""))
        except EWalletError as exc:
            flash(str(exc), "danger")
            status = status_for(exc)
        else:
            flash("Password berhasil diubah. Silakan login.", "success")
            return redirect(url_for("auth.login"))
    return render_template("reset.html", user_id=user_id), status
