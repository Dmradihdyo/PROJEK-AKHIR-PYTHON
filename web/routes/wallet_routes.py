"""Dashboard, top up, transfer, riwayat, profil, dan QR milik pengguna."""
from datetime import date, timedelta

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from markupsafe import Markup

import config
from core import auth, clock, complaints, export, netinfo, qr, reports, security, wallet
from core.formatting import tx_label
from web import charts
from core.errors import (
    DataTidakValid,
    EWalletError,
    PenerimaTidakDitemukan,
    PinSalah,
    SaldoTidakCukup,
    TransferKeDiriSendiri,
)
from web.helpers import current_user, get_conn, login_required, status_for

bp = Blueprint("wallet", __name__)

TOPUP_METHODS = {
    "va": "Virtual Account (simulasi)",
    "bank": "Transfer Bank (simulasi)",
    "kartu": "Kartu (simulasi)",
}
PAGE_SIZE = 20


def _redirect_receipt(receipt):
    return redirect(url_for("wallet.transaction_detail", ref_no=receipt.ref_no))


# ---------------------------------------------------------------- dashboard
@bp.get("/dashboard")
@login_required
def dashboard():
    user = current_user()
    conn = get_conn()
    today = clock.today()
    month = reports.user_summary(conn, user.id, today[:8] + "01", today)
    return render_template(
        "dashboard.html",
        recent=wallet.get_history(conn, user.id, limit=5),
        income=sum(r.total for r in month if r.direction == "IN"),
        expense=sum(r.total for r in month if r.direction == "OUT"),
        tx_count=sum(r.count for r in month),
    )


# --------------------------------------------------------------- statistik
def _presets(today: str) -> list[dict]:
    day = date.fromisoformat(today)
    return [
        {"label": "7 Hari", "start": (day - timedelta(days=6)).isoformat(), "end": today},
        {"label": "30 Hari", "start": (day - timedelta(days=29)).isoformat(), "end": today},
        {"label": "Bulan Ini", "start": today[:8] + "01", "end": today},
    ]


@bp.get("/statistics")
@login_required
def statistics():
    user = current_user()
    conn = get_conn()
    tab = "out" if request.args.get("tab") == "out" else "in"
    today = clock.today()
    date_from = request.args.get("from") or today[:8] + "01"
    date_to = request.args.get("to") or today
    try:
        rows = reports.user_summary(conn, user.id, date_from, date_to)
    except EWalletError as exc:
        flash(str(exc), "danger")
        date_from, date_to = today[:8] + "01", today
        rows = reports.user_summary(conn, user.id, date_from, date_to)

    wanted = "IN" if tab == "in" else "OUT"
    cats = [r for r in rows if r.direction == wanted]
    total = sum(r.total for r in cats)
    legend = [
        {"index": i % charts.PALETTE_SIZE, "label": tx_label(r.type, r.direction), "share": round(r.total / total * 100)}
        for i, r in enumerate(cats)
    ]
    return render_template(
        "statistics.html",
        tab=tab,
        date_from=date_from,
        date_to=date_to,
        dates={"from": date_from, "to": date_to},
        presets=_presets(today),
        total=total,
        tx_count=sum(r.count for r in cats),
        segments=charts.donut_segments([r.total for r in cats]),
        legend=legend,
        recent=wallet.get_history(conn, user.id, date_from=date_from, date_to=date_to, limit=5),
    )


# ------------------------------------------------------------------- top up
@bp.route("/topup", methods=["GET", "POST"])
@login_required
def topup():
    user = current_user()
    status = 200
    if request.method == "POST":
        method = TOPUP_METHODS.get(request.form.get("method", ""))
        try:
            if method is None:
                raise DataTidakValid("Pilih metode top up.")
            receipt = wallet.top_up(
                get_conn(), user.id, request.form.get("amount", "").strip(), request.form.get("pin", ""), method
            )
        except EWalletError as exc:
            flash(str(exc), "danger")
            status = status_for(exc)
        else:
            flash("Top up berhasil.", "success")
            return _redirect_receipt(receipt)
    return render_template(
        "topup.html", methods=TOPUP_METHODS, form=request.form, min_amount=config.MIN_AMOUNT, max_amount=config.MAX_TOPUP_PER_TX
    ), status


# ----------------------------------------------------------------- transfer
def _transfer_form(status=200):
    return render_template(
        "transfer.html", form=request.form, min_amount=config.MIN_AMOUNT, max_amount=config.MAX_TRANSFER_PER_TX
    ), status


def _transfer_confirm(recipient, amount, note, status=200):
    return render_template("transfer_confirm.html", recipient=recipient, amount=amount, note=note), status


@bp.route("/transfer", methods=["GET", "POST"])
@login_required
def transfer():
    """Langkah 1: data penerima dan nominal. Langkah 2 (PIN) ada di /transfer/confirm."""
    user = current_user()
    if request.method == "GET":
        return _transfer_form()
    try:
        amount = security.validate_amount(request.form.get("amount", "").strip(), config.MAX_TRANSFER_PER_TX)
        note = security.validate_note(request.form.get("note", ""))
        recipient = auth.get_user(get_conn(), request.form.get("recipient", "").strip())
        if recipient is None or not recipient.is_active:
            raise PenerimaTidakDitemukan()
        if recipient.id == user.id:
            raise TransferKeDiriSendiri()
        if user.balance < amount:
            raise SaldoTidakCukup()
    except EWalletError as exc:
        flash(str(exc), "danger")
        return _transfer_form(status_for(exc))
    return _transfer_confirm(recipient, amount, note)


@bp.post("/transfer/confirm")
@login_required
def transfer_confirm():
    user = current_user()
    recipient_id = request.form.get("recipient", "").strip()
    note = request.form.get("note", "")
    try:
        amount = security.validate_amount(request.form.get("amount", "").strip(), config.MAX_TRANSFER_PER_TX)
        receipt = wallet.transfer(get_conn(), user.id, recipient_id, amount, request.form.get("pin", ""), note)
    except PinSalah as exc:
        # PIN salah: tetap di langkah konfirmasi agar pengguna bisa mencoba lagi (dibatasi core).
        flash(str(exc), "danger")
        recipient = auth.get_user(get_conn(), recipient_id)
        if recipient is None:
            abort(400)
        return _transfer_confirm(recipient, amount, note, status_for(exc))
    except EWalletError as exc:
        flash(str(exc), "danger")
        return _transfer_form(status_for(exc))
    flash("Transfer berhasil.", "success")
    return _redirect_receipt(receipt)


# ------------------------------------------------------------------ riwayat
def _history_filters():
    return {
        "type_": request.args.get("type") or None,
        "status": request.args.get("status") or None,
        "date_from": request.args.get("from") or None,
        "date_to": request.args.get("to") or None,
    }


@bp.get("/history")
@login_required
def history():
    user = current_user()
    filters = _history_filters()
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    rows, has_next = [], False
    try:
        fetched = wallet.get_history(
            get_conn(), user.id, **filters, limit=PAGE_SIZE + 1, offset=(page - 1) * PAGE_SIZE
        )
        rows, has_next = fetched[:PAGE_SIZE], len(fetched) > PAGE_SIZE
    except EWalletError as exc:
        flash(str(exc), "danger")
    query = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template(
        "history.html", rows=rows, page=page, has_next=has_next, query=query, types=wallet.TYPES
    )


@bp.get("/history.csv")
@login_required
def history_csv():
    user = current_user()
    try:
        filters = _history_filters()
        rows = []
        for page in range(25):  # maksimal 5.000 baris per ekspor
            chunk = wallet.get_history(get_conn(), user.id, **filters, limit=200, offset=page * 200)
            rows += chunk
            if len(chunk) < 200:
                break
    except EWalletError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("wallet.history"))
    return Response(
        export.transactions_to_csv(rows),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="riwayat_{user.id}.csv"'},
    )


@bp.get("/transactions/<ref_no>")
@login_required
def transaction_detail(ref_no):
    user = current_user()
    tx = wallet.get_transaction(get_conn(), user.id, ref_no[:20])
    if tx is None:
        abort(404)  # juga untuk transaksi milik orang lain: tidak membocorkan keberadaannya
    other = auth.get_user(get_conn(), tx.counterparty_id) if tx.counterparty_id and tx.counterparty_id != "-" else None
    return render_template("receipt.html", tx=tx, other=other)


# ------------------------------------------------------------------- profil
@bp.route("/complaints", methods=["GET", "POST"])
@login_required
def complaints_page():
    user = current_user()
    conn = get_conn()
    status = 200
    if request.method == "POST":
        try:
            item = complaints.create(
                conn,
                user.id,
                request.form.get("category", ""),
                request.form.get("message", ""),
                request.form.get("transaction_ref", ""),
            )
        except EWalletError as exc:
            flash(str(exc), "danger")
            status = status_for(exc)
        else:
            flash(f"Aduan #{item['id']} berhasil dikirim.", "success")
            return redirect(url_for("wallet.complaints_page"))
    return render_template(
        "complaints.html", complaints=complaints.list_for_user(conn, user.id), categories=complaints.CATEGORIES,
        form=request.form,
    ), status


@bp.get("/profile")
@login_required
def profile():
    return render_template("profile.html")


@bp.route("/profile/pin", methods=["GET", "POST"])
@login_required
def change_pin():
    user = current_user()
    status = 200
    if request.method == "POST":
        try:
            if request.form.get("pin", "") != request.form.get("pin2", ""):
                raise DataTidakValid("Konfirmasi PIN tidak cocok.")
            auth.change_pin(get_conn(), user.id, request.form.get("password", ""), request.form.get("pin", ""))
        except EWalletError as exc:
            flash(str(exc), "danger")
            status = status_for(exc)
        else:
            flash("PIN berhasil diubah.", "success")
            return redirect(url_for("wallet.profile"))
    return render_template("change_pin.html"), status


# ----------------------------------------------------------------- QR saya
@bp.get("/scan")
@login_required
def scan():
    """Halaman scanner QR kamera. Pembayaran tetap dimulai oleh route /pay setelah
    merchant divalidasi server dan pengguna mengisi nominal + PIN."""
    return render_template("scan.html")


@bp.get("/qr")
@login_required
def my_qr():
    user = current_user()
    chosen = netinfo.normalize_ip(request.args.get("ip"))
    host = netinfo.host_for_qr(chosen)
    options = netinfo.candidates()
    amount_input = request.args.get("amount", "").strip()
    fixed_amount = None
    error_message = ""
    if amount_input:
        try:
            fixed_amount = security.validate_amount(amount_input, config.MAX_TRANSFER_PER_TX)
        except EWalletError as exc:
            error_message = str(exc)
    if not host:
        return render_template("my_qr.html", host="", svg=None, pay_url="", options=options,
                               amount_input=amount_input, fixed_amount=fixed_amount, error_message=error_message,
                               min_amount=config.MIN_AMOUNT, max_amount=config.MAX_TRANSFER_PER_TX)
    port = int(request.environ.get("SERVER_PORT") or config.PORT)
    expires_at = clock.now() + config.PAY_SESSION_TTL if fixed_amount is not None else None
    pay_url = qr.build_pay_url(host, port, user.id, fixed_amount, expires_at) if not error_message else ""
    svg = Markup(qr.to_svg(pay_url)) if pay_url else None
    return render_template("my_qr.html", host=host, svg=svg, pay_url=pay_url, options=options,
                           amount_input=amount_input, fixed_amount=fixed_amount, error_message=error_message,
                           min_amount=config.MIN_AMOUNT, max_amount=config.MAX_TRANSFER_PER_TX)
