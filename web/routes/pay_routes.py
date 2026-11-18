"""Pembayaran via QR dari browser (HP): /pay -> /pay/review -> /pay/confirm."""
from urllib.parse import parse_qs, urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for

from core import payment, qr
from core.errors import DataTidakValid, EWalletError, PinSalah, SesiTidakValid
from web.helpers import current_user, get_conn, login_required, status_for

bp = Blueprint("pay", __name__)


def _fixed_amount(merchant_id: str, amount: str, expires: str, signature: str) -> int | None:
    has_payload = any((amount, expires, signature))
    if not has_payload:
        return None
    fixed = qr.verify_fixed_payload(merchant_id, amount, expires, signature)
    if fixed is None:
        raise DataTidakValid("QR nominal tetap tidak valid atau sudah kedaluwarsa.")
    return fixed


def _error_page(message: str, merchant_id: str = "", status: int = 400):
    return render_template("pay_error.html", message=message, merchant_id=merchant_id), status


@bp.get("/pay")
@login_required
def start():
    """Dibuka dari QR. Jika belum login, `login_required` mengarahkan ke login lalu kembali ke sini."""
    raw_merchant = request.args.get("merchant") or request.args.get("recipient") or ""
    merchant_id = raw_merchant
    if raw_merchant.startswith(("http://", "https://", "/pay")):
        parsed = urlparse(raw_merchant)
        if parsed.path != "/pay":
            merchant_id = ""
        else:
            query = parse_qs(parsed.query)
            merchant_id = (query.get("merchant") or query.get("recipient") or [""])[0]
    user = current_user()
    try:
        merchant = payment.get_merchant_for_qr(get_conn(), merchant_id)
        fixed_amount = _fixed_amount(
            merchant.id,
            request.args.get("amount", ""),
            request.args.get("expires", ""),
            request.args.get("sig", ""),
        )
    except EWalletError as exc:
        return _error_page(str(exc), status=status_for(exc))
    if merchant.id == user.id:
        return _error_page("Ini QR milik Anda sendiri. Anda tidak dapat membayar ke akun sendiri.")
    return render_template("pay_start.html", merchant=merchant, fixed_amount=fixed_amount,
                           fixed_expires=request.args.get("expires", ""), fixed_sig=request.args.get("sig", ""))


@bp.post("/pay/review")
@login_required
def review():
    user = current_user()
    merchant_id = request.form.get("merchant", "")
    try:
        fixed_amount = _fixed_amount(
            merchant_id,
            request.form.get("amount", "") if request.form.get("fixed") == "1" else "",
            request.form.get("expires", ""),
            request.form.get("sig", ""),
        )
        amount = fixed_amount if fixed_amount is not None else request.form.get("amount", "").strip()
        session = payment.create_pay_session(get_conn(), user.id, merchant_id, amount)
    except EWalletError as exc:
        flash(str(exc), "danger")
        try:
            merchant = payment.get_merchant_for_qr(get_conn(), merchant_id)
        except EWalletError as inner:
            return _error_page(str(inner), status=status_for(inner))
        return render_template("pay_start.html", merchant=merchant, fixed_amount=fixed_amount,
                               fixed_expires=request.form.get("expires", ""), fixed_sig=request.form.get("sig", "")), status_for(exc)
    return render_template("pay_review.html", ps=session)


@bp.post("/pay/confirm")
@login_required
def confirm():
    user = current_user()
    token = request.form.get("token", "")
    try:
        receipt = payment.confirm_payment(get_conn(), user.id, token, request.form.get("pin", ""))
    except PinSalah as exc:
        # Sesi belum terpakai: tampilkan ringkasan lagi agar PIN bisa diulang.
        flash(str(exc), "danger")
        try:
            session = payment.get_pay_session(get_conn(), user.id, token)
        except SesiTidakValid as inner:
            return _error_page(str(inner), status=400)
        return render_template("pay_review.html", ps=session), status_for(exc)
    except EWalletError as exc:
        return _error_page(str(exc), status=status_for(exc))
    flash("Pembayaran berhasil.", "success")
    return redirect(url_for("wallet.transaction_detail", ref_no=receipt.ref_no))
