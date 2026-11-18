"""Console pengguna Elektro Wallet. Hanya memanggil `core`; tidak ada SQL di sini."""
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import config
from console.admin_cli import AdminConsole
from console.ui import UI, normalize_amount_input, sound_startup, sound_logout, sound_info
from core import auth, clock, complaints, export, netinfo, outbox, payment, qr, reports, security, wallet
from core.errors import (
    AkunTerkunci,
    AkunTidakAktif,
    DataTidakValid,
    EWalletError,
    PinSalah,
    SaldoTidakCukup,
    TransferKeDiriSendiri,
)
from core.formatting import format_rupiah, short_datetime, tx_label
from core.models import Receipt

TOPUP_METHODS = {"1": "Virtual Account (simulasi)", "2": "Transfer Bank (simulasi)", "3": "Kartu (simulasi)"}
PAGE_SIZE = 8


def parse_merchant(text: str) -> str:
    """Terima User ID biasa atau URL QR (http://host:port/pay?merchant=ID) dan ambil ID-nya."""
    text = (text or "").strip()
    if "merchant=" in text or text.lower().startswith("http"):
        query = parse_qs(urlparse(text).query)
        values = query.get("merchant") or query.get("recipient")
        return values[0] if values else ""
    return text


class ConsoleApp:
    def __init__(self, conn: sqlite3.Connection, ui: UI | None = None, db_path=None, port: int | None = None,
                 export_dir: Path | None = None):
        self.conn = conn
        self.ui = ui or UI()
        self.db_path = db_path or config.DB_PATH
        self.port = port or config.PORT
        self.export_dir = Path(export_dir) if export_dir else Path.cwd()
        self.user = None

    # ------------------------------------------------------------ utilitas
    def _safe(self, action):
        """Jalankan satu aksi menu; galat core ditampilkan sebagai pesan, bukan crash."""
        try:
            return action()
        except EWalletError as exc:
            self.ui.error(str(exc))
            self.ui.pause()

    def _with_pin(self, action):
        """Minta PIN lalu jalankan action(pin). PIN salah boleh diulang; Enter kosong = batal.
        Batas percobaan dan penguncian diatur oleh core (AkunTerkunci diteruskan ke pemanggil)."""
        while True:
            pin = self.ui.secret(" Masukkan PIN (Enter = batal): ")
            if not pin:
                self.ui.info("Dibatalkan.")
                return None
            try:
                return action(pin)
            except PinSalah as exc:
                self.ui.error(str(exc))

    def _ask_amount(self, prompt: str) -> str:
        return normalize_amount_input(self.ui.ask(prompt))

    def _print_receipt(self, title: str, receipt: Receipt, other_label: str | None = None, other_value: str | None = None):
        ui = self.ui
        lines = [
            ("No. Referensi", receipt.ref_no),
            ("Akun", receipt.user_id),
        ]
        if other_label:
            lines.append((other_label, other_value or ""))
        lines += [
            ("Nominal", format_rupiah(receipt.amount)),
            ("Saldo terbaru", format_rupiah(receipt.balance_after)),
            ("Waktu", short_datetime(receipt.created_at)),
            ("Status", "✓ BERHASIL"),
        ]
        if receipt.note:
            lines.insert(3, ("Catatan", receipt.note))
        ui.say()
        ui.receipt_box(title, lines, money_keys=("Nominal", "Saldo terbaru"))

    # -------------------------------------------------------- menu utama
    def run(self) -> None:
        ui = self.ui
        sound_startup()
        try:
            while True:
                self._main_screen()
                choice = ui.ask(" Pilih menu (1-4): ").strip()
                if choice == "1":
                    self._login()
                elif choice == "2":
                    self._safe(self._register)
                elif choice == "3":
                    self._safe(self._forgot_password)
                elif choice == "4":
                    ui.say()
                    sound_logout()
                    ui.say(ui.c("  Terima kasih telah menggunakan ⚡ Elektro Wallet.", "cyan"))
                    ui.say()
                    return
                else:
                    ui.error("Pilihan menu tidak valid.")
                    ui.pause()
        except (EOFError, KeyboardInterrupt):
            ui.say("\n  Sampai jumpa.")

    def _main_screen(self) -> None:
        ui = self.ui
        ui.header_logo("MENU UTAMA", "Selamat datang di Elektro Wallet")
        running = netinfo.is_port_open(self.port)
        ui.kv("Total pengguna",  auth.count_users(self.conn), 20)
        ui.kv("IP laptop (LAN)", netinfo.host_for_qr() or "(tidak terdeteksi)", 20)
        ui.kv_status("Web server",
                     f"Berjalan di port {self.port}" if running else "Tidak berjalan (jalankan run.py)",
                     running, 20)
        ui.say()
        ui.menu_item("1", "Login Akun",          "🔑")
        ui.menu_item("2", "Registrasi Akun Baru","📝")
        ui.menu_item("3", "Lupa Password",       "🔒")
        ui.menu_item("4", "Keluar Program",      "🚪")
        ui.say()

    # ------------------------------------------------ registrasi & login
    def _register(self) -> None:
        ui = self.ui
        ui.header_logo("REGISTRASI AKUN BARU")
        name = ui.ask(" Nama lengkap          : ")
        user_id = ui.ask(" User ID (3-20 huruf/angka/_): ")
        email = ui.ask(" Email                 : ")
        phone = ui.ask(" Nomor HP (opsional)   : ")
        password = ui.secret(" Password (min 8, besar+kecil+angka): ")
        if password != ui.secret(" Ulangi password      : "):
            raise DataTidakValid("Konfirmasi password tidak cocok.")
        pin = ui.secret(" PIN (6 angka)         : ")
        if pin != ui.secret(" Ulangi PIN           : "):
            raise DataTidakValid("Konfirmasi PIN tidak cocok.")
        user = auth.register(self.conn, user_id, name, email, password, pin, phone)
        ui.ok(f"Akun '{user.id}' berhasil dibuat. Silakan login.")
        ui.pause()

    def _login(self) -> None:
        ui = self.ui
        for attempt in range(1, 4):
            ui.header_logo(f"LOGIN AKUN", f"Percobaan {attempt} dari 3")
            user_id = ui.ask(" User ID  : ")
            password = ui.secret(" Password : ")
            try:
                user = auth.login(self.conn, user_id, password, ip=auth.LOCAL_IP)
            except EWalletError as exc:
                ui.error(str(exc))
                ui.pause()
                if isinstance(exc, (AkunTerkunci, AkunTidakAktif)):
                    return  # terkunci / diblokir: mengulang tidak ada gunanya
                continue
            self.user = user
            ui.ok(f"Selamat datang, {user.name}.")
            ui.pause()
            if user.is_admin:
                AdminConsole(self, user).run()
            else:
                self._dashboard()
            self.user = None
            return
        ui.error("Terlalu banyak percobaan. Kembali ke menu utama.")
        ui.pause()

    def _forgot_password(self) -> None:
        ui = self.ui
        ui.header_logo("LUPA PASSWORD")
        user_id = ui.ask(" User ID : ")
        email = ui.ask(" Email   : ")
        code = auth.request_password_reset(self.conn, user_id, email, ip=auth.LOCAL_IP)
        if code:
            outbox.deliver_otp(self.db_path, user_id.strip(), email, code)
        ui.info("Jika User ID dan email cocok, kode OTP telah dikirim.")
        ui.info("(Mode demo: tidak ada email sungguhan. Kode ada di berkas outbox.txt di folder data.)")
        otp = ui.ask("\n Masukkan kode OTP 6 angka (Enter = batal): ").strip()
        if not otp:
            return
        new_password = ui.secret(" Password baru : ")
        if new_password != ui.secret(" Ulangi        : "):
            raise DataTidakValid("Konfirmasi password tidak cocok.")
        auth.reset_password(self.conn, user_id, otp, new_password)
        ui.ok("Password berhasil diubah. Silakan login.")
        ui.pause()

    # --------------------------------------------------------- dashboard
    def _dashboard(self) -> None:
        ui = self.ui
        actions = {
            "1": self._balance, "2": self._top_up, "3": self._transfer, "4": self._my_qr, "5": self._pay_qr,
            "6": self._history, "7": self._statistics, "8": self._complaints, "9": self._profile, "10": self._change_pin,
        }
        while True:
            user = auth.get_user(self.conn, self.user.id)
            if user is None or not user.is_active:
                ui.error("Akun Anda tidak aktif. Anda dikeluarkan.")
                ui.pause()
                return
            self.user = user
            ui.header("DASHBOARD", f"Halo, {user.name}  ·  [{user.id}]")
            ui.menu_item("1",  "Cek Saldo",                  "💰")
            ui.menu_item("2",  "Top Up Saldo",               "⬆")
            ui.menu_item("3",  "Transfer Saldo",             "↔")
            ui.menu_item("4",  "QR Code Saya",               "📷")
            ui.menu_item("5",  "Bayar via QR / ID Penerima", "💳")
            ui.menu_item("6",  "Riwayat Transaksi",          "📋")
            ui.menu_item("7",  "Statistik",                  "📊")
            ui.menu_item("8",  "Aduan",                      "📣")
            ui.menu_item("9",  "Profil",                     "👤")
            ui.menu_item("10", "Ubah / Lupa PIN",            "🔐")
            ui.menu_item("0",  "Logout",                     "🚪")
            ui.say()
            choice = ui.ask("  Pilih menu (0-10) › ").strip()
            if choice == "0":
                sound_logout()
                ui.say(f"\n  {ui.c('Sampai jumpa,', 'dim')} {ui.c(user.name + '!', 'cyan')}\n")
                return
            action = actions.get(choice)
            if action is None:
                ui.error("Pilihan menu tidak valid.")
                ui.pause()
                continue
            self._safe(action)

    def _balance(self) -> None:
        ui = self.ui
        ui.header("CEK SALDO")
        ui.panel([
            f"User ID  :  {self.user.id}",
            f"Nama     :  {self.user.name}",
        ])
        ui.say()
        ui.kv_money("Saldo Anda", format_rupiah(self.user.balance), 14)
        ui.say()
        ui.pause()

    def _top_up(self) -> None:
        ui = self.ui
        ui.header("TOP UP SALDO", "Simulasi pengisian saldo")
        ui.section("Pilih Metode")
        for key, label in TOPUP_METHODS.items():
            ui.menu_item(key, label, "🏦")
        ui.say()
        method = TOPUP_METHODS.get(ui.ask("  Pilih metode (1-3) › ").strip())
        if method is None:
            raise DataTidakValid("Pilih metode top up 1-3.")
        ui.say()
        amount = security.validate_amount(
            self._ask_amount(
                f"  Nominal (min {format_rupiah(config.MIN_AMOUNT)}, maks {format_rupiah(config.MAX_TOPUP_PER_TX)}) › Rp "
            ),
            config.MAX_TOPUP_PER_TX,
        )
        receipt = self._with_pin(lambda pin: (ui.loading("Memproses top up"), wallet.top_up(self.conn, self.user.id, amount, pin, method))[1])
        if receipt:
            self._print_receipt("BUKTI TOP UP BERHASIL", receipt, "Metode", method)
            ui.pause()

    def _transfer(self) -> None:
        ui = self.ui
        ui.header("TRANSFER SALDO")
        ui.kv_money("Saldo Anda", format_rupiah(self.user.balance), 14)
        ui.say()
        recipient_id = ui.ask("  User ID penerima › ").strip()
        recipient = auth.get_user(self.conn, recipient_id)
        if recipient is None or not recipient.is_active:
            raise DataTidakValid("Penerima tidak ditemukan.")
        if recipient.id == self.user.id:
            raise TransferKeDiriSendiri()
        ui.panel([f"Penerima  :  {recipient.name}  [{recipient.id}]"], color="green")
        ui.say()
        amount = security.validate_amount(self._ask_amount("  Nominal transfer › Rp "), config.MAX_TRANSFER_PER_TX)
        if self.user.balance < amount:
            raise SaldoTidakCukup()
        note = security.validate_note(ui.ask("  Catatan (opsional) › "))
        receipt = self._with_pin(lambda pin: (ui.loading("Memproses transfer"), wallet.transfer(self.conn, self.user.id, recipient.id, amount, pin, note))[1])
        if receipt:
            self._print_receipt("BUKTI TRANSFER BERHASIL", receipt, "Penerima", f"{recipient.name} ({recipient.id})")
            ui.pause()

    def _my_qr(self) -> None:
        ui = self.ui
        ui.header("QR CODE SAYA")
        host = netinfo.host_for_qr()
        if not host:
            ui.error("IP LAN laptop tidak terdeteksi (belum tersambung ke Wi-Fi/hotspot?).")
            ui.say(" Set variabel EWALLET_HOST_IP (mis. 192.168.1.10) lalu jalankan ulang.")
            ui.pause()
            return
        url = qr.build_pay_url(host, self.port, self.user.id)
        fixed_amount = None
        amount_text = ui.ask(" Nominal tetap (Enter = diisi pembayar, B = kembali): Rp ").strip()
        if amount_text.lower() == "b":
            return
        if amount_text:
            fixed_amount = security.validate_amount(amount_text, config.MAX_TRANSFER_PER_TX)
            expires_at = clock.now() + config.PAY_SESSION_TTL
            url = qr.build_pay_url(host, self.port, self.user.id, fixed_amount, expires_at)
        ui.say(f" Penerima: {self.user.name} ({self.user.id})\n")
        ui.say(qr.to_ansi(url))
        ui.say(f"\n URL di QR  : {url}")
        ui.say(f" Nominal QR : {format_rupiah(fixed_amount) if fixed_amount is not None else 'diisi pembayar'}")
        if netinfo.is_port_open(self.port):
            ui.say(f" Web server : BERJALAN di port {self.port}")
        else:
            ui.error(f"Web server belum berjalan. Jalankan run.py agar HP dapat membuka halaman bayar (port {self.port}).")
        ui.say(" Jika QR di terminal sulit dipindai, buka versi web: menu QR Saya.")
        ui.pause()

    def _pay_qr(self) -> None:
        ui = self.ui
        ui.header("BAYAR VIA QR / ID PENERIMA")
        ui.info("Tempel URL dari QR atau ketik User ID penerima.")
        ui.say()
        merchant = payment.get_merchant_for_qr(self.conn, parse_merchant(ui.ask("  Penerima › ").strip()))
        ui.panel([f"Penerima  :  {merchant.name}  [{merchant.id}]"], color="green")
        ui.say()
        amount = self._ask_amount("  Nominal › Rp ")
        session = payment.create_pay_session(self.conn, self.user.id, merchant.id, amount)
        ui.say()
        ui.section("Ringkasan Pembayaran")
        ui.kv("Penerima",   f"{session.merchant_name} ({session.merchant_id})", 14)
        ui.kv_money("Total", format_rupiah(session.amount), 14)
        ui.kv_money("Sisa saldo", format_rupiah(self.user.balance - session.amount), 14)
        ui.say()
        receipt = self._with_pin(lambda pin: (ui.loading("Memproses pembayaran"), payment.confirm_payment(self.conn, self.user.id, session.token, pin))[1])
        if receipt:
            self._print_receipt("BUKTI PEMBAYARAN QR", receipt, "Penerima", f"{session.merchant_name} ({session.merchant_id})")
            ui.pause()

    # ----------------------------------------------------------- riwayat
    def _ask_filters(self) -> dict | None:
        ui = self.ui
        ui.say(" Filter (Enter = lewati, B = kembali):")
        type_ = ui.ask(f"  Tipe {'/'.join(wallet.TYPES)} : ").strip()
        if type_.lower() == "b":
            return None
        status = ui.ask("  Status BERHASIL/GAGAL      : ").strip()
        if status.lower() == "b":
            return None
        date_from = ui.ask("  Dari tanggal (YYYY-MM-DD)  : ").strip()
        if date_from.lower() == "b":
            return None
        date_to = ui.ask("  Sampai tanggal             : ").strip()
        if date_to.lower() == "b":
            return None
        return {
            "type_": type_.upper() or None,
            "status": status.upper() or None,
            "date_from": date_from or None,
            "date_to": date_to or None,
        }

    def _history(self) -> None:
        ui = self.ui
        ui.header("RIWAYAT TRANSAKSI")
        filters = self._ask_filters()
        if filters is None:
            ui.info("Kembali.")
            return
        page = 0
        while True:
            rows = wallet.get_history(self.conn, self.user.id, **filters, limit=PAGE_SIZE + 1, offset=page * PAGE_SIZE)
            shown, has_next = rows[:PAGE_SIZE], len(rows) > PAGE_SIZE
            ui.header(f"RIWAYAT TRANSAKSI - halaman {page + 1}")
            if not shown:
                ui.say(" Tidak ada transaksi yang cocok.")
            else:
                ui.table(
                    ["Referensi", "Waktu", "Jenis", "Lawan", "Nominal", "Status"],
                    [
                        [t.ref_no, short_datetime(t.created_at), tx_label(t.type, t.direction),
                         t.counterparty_id or "-", ("+" if t.direction == "IN" else "-") + format_rupiah(t.amount), t.status]
                        for t in shown
                    ],
                    right=(4,),
                )
            ui.rule()
            options = " [C] Cetak TXT  [E] Ekspor CSV  [B] Kembali"
            if has_next:
                options = " [N] Berikutnya" + options
            if page > 0:
                options = " [P] Sebelumnya" + options
            choice = ui.ask(options + " : ").strip().lower()
            if choice == "n" and has_next:
                page += 1
            elif choice == "p" and page > 0:
                page -= 1
            elif choice == "e":
                self._export_csv(filters)
            elif choice == "c":
                self._print_history(rows, filters)
            elif choice in ("", "b"):
                return

    def _export_csv(self, filters: dict) -> None:
        rows = []
        for page in range(25):  # maksimal 5.000 baris
            chunk = wallet.get_history(self.conn, self.user.id, **filters, limit=200, offset=page * 200)
            rows += chunk
            if len(chunk) < 200:
                break
        path = self.export_dir / f"riwayat_{self.user.id}.csv"
        path.write_text(export.transactions_to_csv(rows), encoding="utf-8", newline="")
        self.ui.ok(f"{len(rows)} transaksi diekspor ke {path}")

    def _statistics(self) -> None:
        ui = self.ui
        ui.header("STATISTIK")
        today = clock.today()
        default_from = today[:8] + "01"
        date_from = ui.ask(f"  Dari tanggal [{default_from}] : ").strip() or default_from
        date_to   = ui.ask(f"  Sampai tanggal [{today}] : ").strip() or today
        ui.loading("Mengambil data", 0.5)
        rows = reports.user_summary(self.conn, self.user.id, date_from, date_to)
        ui.section(f"Periode  {date_from}  s.d.  {date_to}")
        for direction, title, color in (("IN", "PEMASUKAN", "green"), ("OUT", "PENGELUARAN", "red")):
            cats  = [r for r in rows if r.direction == direction]
            total = sum(r.total for r in cats)
            ui.say()
            ui.say(f"  {ui.c('▐', color)} {ui.c(title, 'bold', color)}  "
                   f"{ui.c(format_rupiah(total), 'yellow', 'bold')}")
            ui.rule("╌")
            if not cats:
                ui.say(ui.c("    (tidak ada data)", "dim"))
            for r in cats:
                share = r.total / total if total else 0
                bar   = ui.progress_bar(r.total, total, width=20)
                label = ui.c(f"{tx_label(r.type, r.direction):<16}", "white")
                amount= ui.c(f"{format_rupiah(r.total):>16}", "yellow")
                ui.say(f"    {label}  {amount}  {bar}")
        ui.say()
        self._show_statistics_chart(date_from, date_to, rows)
        ui.pause()

    # ------------------------------------------------------ aduan pengguna
    def _complaints(self) -> None:
        ui = self.ui
        CATEGORY_LABELS = {
            "1": ("TRANSACTION", "Masalah Transaksi"),
            "2": ("ACCOUNT",     "Masalah Akun"),
            "3": ("QR",          "Masalah QR Code"),
            "4": ("OTHER",       "Lainnya"),
        }
        while True:
            ui.header("ADUAN", "Sampaikan keluhan atau laporan masalah")
            ui.menu_item("1", "Kirim Aduan Baru", "📣")
            ui.menu_item("2", "Lihat Aduan Saya", "📋")
            ui.menu_item("0", "Kembali",           "←")
            ui.say()
            choice = ui.ask("  Pilih (0-2) › ").strip()
            if choice == "0":
                return
            elif choice == "1":
                self._safe(lambda: self._submit_complaint(CATEGORY_LABELS))
            elif choice == "2":
                self._safe(self._list_complaints)
            else:
                ui.error("Pilihan tidak valid.")
                ui.pause()

    def _submit_complaint(self, category_labels: dict) -> None:
        ui = self.ui
        ui.header("KIRIM ADUAN BARU")
        ui.section("Pilih Kategori")
        for key, (_, label) in category_labels.items():
            ui.menu_item(key, label, "📌")
        ui.say()
        cat_choice = ui.ask("  Pilih kategori (1-4) › ").strip()
        if cat_choice not in category_labels:
            raise DataTidakValid("Pilih kategori 1-4.")
        category, cat_label = category_labels[cat_choice]
        ui.say()
        ref = ui.ask("  No. referensi transaksi (Enter = lewati) › ").strip() or None
        ui.say()
        ui.info("Tulis pesan aduan (min 10, maks 1000 karakter).")
        ui.info("Jangan tulis password atau PIN di sini.")
        ui.say()
        message = ui.ask("  Pesan › ").strip()
        ui.say()
        # preview
        ui.detail_box(
            title="Konfirmasi Aduan",
            fields=[
                ("Kategori", cat_label),
                ("Ref Trx",  ref or "-"),
            ],
            body_label="Pesan",
            body_text=message,
        )
        confirm = ui.ask("  Kirim aduan ini? [y/t] › ").strip().lower()
        if confirm != "y":
            ui.info("Aduan dibatalkan.")
            ui.pause()
            return
        item = complaints.create(self.conn, self.user.id, category, message, ref)
        ui.ok(f"Aduan #{item['id']} berhasil dikirim.")
        ui.info("Admin akan meninjau aduan Anda. Pantau di menu Lihat Aduan Saya.")
        ui.pause()

    def _list_complaints(self) -> None:
        ui = self.ui
        ui.header("ADUAN SAYA")
        rows = complaints.list_for_user(self.conn, self.user.id, limit=20)
        if not rows:
            ui.info("Belum ada aduan yang pernah dikirim.")
            ui.pause()
            return
        ui.table(
            ["ID", "Tanggal", "Kategori", "Status", "Ref Trx"],
            [[
                r["id"],
                r["created_at"][:10],
                r["category"],
                r["status"],
                r["transaction_ref"] or "-",
            ] for r in rows],
        )
        ui.say()
        detail_id = ui.ask("  ID aduan untuk detail (Enter = kembali) › ").strip()
        if not detail_id:
            return
        matched = next((r for r in rows if str(r["id"]) == detail_id), None)
        if matched is None:
            ui.error("ID aduan tidak ditemukan di daftar ini.")
            ui.pause()
            return
        ui.say()
        ui.detail_box(
            title=f"Detail Aduan  #{matched['id']}  ·  {matched['category']}",
            fields=[
                ("Status",     matched["status"]),
                ("Ref Trx",    matched["transaction_ref"] or "-"),
                ("Dikirim",    matched["created_at"][:16]),
                ("Diperbarui", matched["updated_at"][:16]),
            ],
            body_label="Pesan aduan",
            body_text=matched["message"],
            footer_label="Catatan admin" if matched.get("admin_note") else "",
            footer_text=matched.get("admin_note") or "",
        )
        ui.pause()

    # ------------------------------------------------------ profil & PIN
    def _profile(self) -> None:
        ui = self.ui
        ui.header("PROFIL PENGGUNA")
        ui.detail_box(
            title=f"  {self.user.name}",
            fields=[
                ("User ID",  self.user.id),
                ("Email",    self.user.email),
                ("Nomor HP", self.user.phone or "-"),
                ("Status",   self.user.status),
                ("Dibuat",   short_datetime(self.user.created_at)),
            ],
        )
        ui.pause()

    def _change_pin(self) -> None:
        ui = self.ui
        ui.header("UBAH / LUPA PIN")
        password = ui.secret(" Password akun Anda : ")
        new_pin = ui.secret(" PIN baru (6 angka) : ")
        if new_pin != ui.secret(" Ulangi PIN baru     : "):
            raise DataTidakValid("Konfirmasi PIN tidak cocok.")
        auth.change_pin(self.conn, self.user.id, password, new_pin)
        ui.ok("PIN berhasil diubah.")
        ui.pause()

    def _print_history(self, rows, filters: dict) -> None:
        """Simpan seluruh hasil filter sebagai bukti teks yang mudah dicetak."""
        all_rows = []
        for page in range(25):
            chunk = wallet.get_history(self.conn, self.user.id, **filters, limit=200, offset=page * 200)
            all_rows.extend(chunk)
            if len(chunk) < 200:
                break
        path = self.export_dir / f"riwayat_{self.user.id}.txt"
        lines = ["BUKTI RIWAYAT TRANSAKSI ELEKTRO WALLET", f"User: {self.user.name} ({self.user.id})", ""]
        lines.append(f"{'Referensi':<12} {'Waktu':<20} {'Jenis':<18} {'Lawan':<16} {'Nominal':>18} {'Status':<10}")
        lines.append("-" * 100)
        for tx in all_rows:
            amount = ("+" if tx.direction == "IN" else "-") + format_rupiah(tx.amount)
            lines.append(f"{tx.ref_no:<12} {short_datetime(tx.created_at):<20} {tx_label(tx.type, tx.direction):<18} {str(tx.counterparty_id or '-'): <16} {amount:>18} {tx.status:<10}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.ui.ok(f"{len(all_rows)} transaksi disimpan untuk dicetak ke {path}")

    def _show_statistics_chart(self, date_from: str, date_to: str, rows) -> None:
        try:
            import matplotlib.pyplot as plt
            import matplotlib.ticker as mticker
        except ImportError:
            self.ui.info("Matplotlib belum terpasang. Jalankan: .\\.venv\\Scripts\\python.exe -m pip install matplotlib")
            return

        COLORS = ["#4cc9a8", "#2d6fd3", "#b6e21a", "#f2a01e", "#e266df"]
        BG     = "#1a1a2e"
        FG     = "#e0e0e0"
        GRID   = "#2e2e4e"

        def fmt_rupiah(val: float) -> str:
            """Format angka menjadi 'Rp 1,5 jt' / 'Rp 500 rb' agar muat di grafik."""
            v = int(val)
            if v >= 1_000_000:
                return f"Rp {v/1_000_000:.1f} jt"
            if v >= 1_000:
                return f"Rp {v/1_000:.0f} rb"
            return f"Rp {v}"

        fig = plt.figure(figsize=(14, 6), dpi=130, facecolor=BG)
        fig.suptitle(
            f"Statistik Transaksi  ·  {self.user.name}  |  {date_from} s.d. {date_to}",
            color=FG, fontsize=13, fontweight="bold", y=0.98,
        )

        from matplotlib.gridspec import GridSpec
        gs = GridSpec(2, 4, figure=fig, hspace=0.45, wspace=0.35)

        for row_idx, (direction, title) in enumerate([("IN", "Pemasukan"), ("OUT", "Pengeluaran")]):
            grouped = [r for r in rows if r.direction == direction and r.total > 0]
            labels  = [tx_label(r.type, r.direction) for r in grouped]
            values  = [r.total for r in grouped]
            total   = sum(values)
            palette = COLORS[:len(values)]

            ax_pie = fig.add_subplot(gs[row_idx, 0])
            ax_bar = fig.add_subplot(gs[row_idx, 1:])
            ax_pie.set_facecolor(BG)
            ax_bar.set_facecolor(BG)

            # ── pie / donat ──────────────────────────────────────
            if values:
                _, _, autotexts = ax_pie.pie(
                    values,
                    labels=None,
                    autopct="%1.0f%%",
                    startangle=90,
                    colors=palette,
                    wedgeprops={"linewidth": 1.5, "edgecolor": BG},
                    pctdistance=0.75,
                )
                for at in autotexts:
                    at.set_color(BG)
                    at.set_fontsize(8)
                    at.set_fontweight("bold")
                ax_pie.add_patch(plt.Circle((0, 0), 0.48, fc=BG))
                ax_pie.text(0, 0, fmt_rupiah(total), ha="center", va="center",
                            color=FG, fontsize=8, fontweight="bold")
            else:
                ax_pie.text(0.5, 0.5, "Belum\nada data", ha="center", va="center",
                            color=FG, fontsize=9, transform=ax_pie.transAxes)
            ax_pie.set_title(title, color=FG, fontsize=10, fontweight="bold", pad=6)

            # ── bar horizontal ───────────────────────────────────
            if values:
                y_pos = list(range(len(labels)))
                bars  = ax_bar.barh(y_pos, values,
                                    color=palette, edgecolor=BG, height=0.5)
                ax_bar.set_yticks(y_pos)
                ax_bar.set_yticklabels(labels, color=FG, fontsize=8)
                ax_bar.invert_yaxis()
                ax_bar.xaxis.set_major_formatter(
                    mticker.FuncFormatter(lambda x, _: fmt_rupiah(x))
                )
                ax_bar.tick_params(axis="x", colors=FG, labelsize=7)
                ax_bar.tick_params(axis="y", colors=FG)
                ax_bar.grid(axis="x", color=GRID, linewidth=0.5, linestyle="--")
                ax_bar.set_axisbelow(True)
                for spine in ax_bar.spines.values():
                    spine.set_color(GRID)
                x_max = max(values)
                for bar, val in zip(bars, values):
                    ax_bar.text(
                        bar.get_width() + x_max * 0.02,
                        bar.get_y() + bar.get_height() / 2,
                        fmt_rupiah(val),
                        va="center", ha="left",
                        color=FG, fontsize=8, fontweight="bold",
                    )
                ax_bar.set_xlim(0, x_max * 1.38)
            else:
                ax_bar.text(0.5, 0.5, "Belum ada data", ha="center", va="center",
                            color=FG, fontsize=9, transform=ax_bar.transAxes)
                ax_bar.set_yticks([])
                ax_bar.set_xticks([])
                for spine in ax_bar.spines.values():
                    spine.set_color(GRID)

            ax_bar.set_title(
                f"Rincian {title}  –  Total {fmt_rupiah(total)}",
                color=FG, fontsize=9, pad=6,
            )

        fig.tight_layout(rect=[0, 0, 1, 0.95])
        plt.show()
        plt.close(fig)
