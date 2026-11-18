"""Console admin. Setiap aksi memanggil `core.admin`, yang memeriksa role ADMIN sendiri."""
from console.ui import UI, sound_logout
from core import admin, auth, complaints, security
from core.errors import AkunTidakDitemukan, DataTidakValid, TidakBerhak
from core.formatting import format_rupiah, short_datetime, tx_label

PAGE_SIZE = 10


class AdminConsole:
    def __init__(self, app, admin_user):
        self.app = app  # ConsoleApp: berbagi koneksi, UI, dan helper PIN
        self.admin = admin_user

    @property
    def conn(self):
        return self.app.conn

    @property
    def ui(self) -> UI:
        return self.app.ui

    def run(self) -> None:
        ui = self.ui
        actions = {
            "1": self._summary, "2": self._accounts, "3": self._set_status, "4": self._transactions,
            "5": self._consistency, "6": self._reset_password, "7": self._outbox, "8": self._backup, "9": self._audit,
            "10": self._clear_lockout, "11": self._refund, "12": self._complaints,
        }
        while True:
            ui.header("PANEL ADMIN", f"{self.admin.name}  ·  [{self.admin.id}]")
            ui.menu_item("1",  "Ringkasan sistem",            "📊")
            ui.menu_item("2",  "Daftar / cari akun",          "🔍")
            ui.menu_item("3",  "Blokir / aktifkan akun",      "🔒")
            ui.menu_item("4",  "Daftar transaksi",            "📋")
            ui.menu_item("5",  "Cek konsistensi saldo",       "⚖")
            ui.menu_item("6",  "Reset password pengguna",     "🔑")
            ui.menu_item("7",  "Kotak surat OTP (demo)",      "📨")
            ui.menu_item("8",  "Backup database",             "💾")
            ui.menu_item("9",  "Log audit",                   "🗒")
            ui.menu_item("10", "Lepaskan lockout akun",       "🔓")
            ui.menu_item("11", "Refund transaksi salah kirim","↩")
            ui.menu_item("12", "Kelola aduan pengguna",       "📣")
            ui.menu_item("0",  "Logout dari admin",           "🚪")
            ui.say()
            choice = ui.ask("  Pilih menu (0-12) › ").strip()
            if choice == "0":
                sound_logout()
                ui.say(f"\n  {ui.c('Keluar dari mode admin.', 'dim')}\n")
                return
            action = actions.get(choice)
            if action is None:
                ui.error("Pilihan menu tidak valid.")
                ui.pause()
                continue
            self.app._safe(action)

    # ---------------------------------------------------------------- menu
    def _summary(self) -> None:
        ui = self.ui
        ui.loading("Mengambil data sistem", 0.5)
        s = admin.summary(self.conn, self.admin.id)
        ui.header("RINGKASAN SISTEM")
        ui.section("Akun Pengguna")
        ui.kv("Jumlah akun",     f"{s['users']}  (diblokir: {s['blocked']})",  28)
        ui.kv_money("Total saldo semua akun", format_rupiah(s["total_balance"]), 28)
        ui.section("Transaksi")
        ui.kv("Jumlah transaksi", f"{s['transactions']}  (gagal: {s['failed']})", 28)
        ui.kv_money("Top up hari ini",          format_rupiah(s["topup_today"]),    28)
        ui.kv("Pembayaran/transfer hari ini", s["payments_today"],                28)
        ui.rule()
        ui.pause()

    def _accounts(self) -> None:
        ui = self.ui
        ui.header("DAFTAR / CARI AKUN")
        query = ui.ask(" Cari ID / nama / email (Enter = semua): ").strip()
        page = 0
        while True:
            rows = admin.list_users(self.conn, self.admin.id, query, limit=PAGE_SIZE + 1, offset=page * PAGE_SIZE)
            shown, has_next = rows[:PAGE_SIZE], len(rows) > PAGE_SIZE
            ui.header(f"AKUN - halaman {page + 1}")
            if shown:
                ui.table(
                    ["User ID", "Nama", "Email", "Role", "Status", "Saldo"],
                    [[u.id, u.name, u.email, u.role, u.status, format_rupiah(u.balance)] for u in shown],
                    right=(5,),
                )
            else:
                ui.say(" Tidak ada akun yang cocok.")
            ui.rule()
            options = " [Enter] Kembali"
            if has_next:
                options = " [N] Berikutnya" + options
            if page > 0:
                options = " [P] Sebelumnya" + options
            choice = ui.ask(options + " : ").strip().lower()
            if choice == "n" and has_next:
                page += 1
            elif choice == "p" and page > 0:
                page -= 1
            elif choice == "":
                return

    def _set_status(self) -> None:
        ui = self.ui
        ui.header("BLOKIR / AKTIFKAN AKUN")
        target = ui.ask(" User ID akun : ").strip()
        action = ui.ask(" Aksi [B]lokir / [A]ktifkan : ").strip().lower()
        status = {"b": "BLOKIR", "a": "AKTIF"}.get(action)
        if status is None:
            raise DataTidakValid("Pilih B (blokir) atau A (aktifkan).")
        # Pemeriksaan awal agar PIN tidak diminta untuk aksi yang pasti ditolak (core tetap menegakkan aturan).
        found = auth.get_user(self.conn, target)
        if found is None:
            raise AkunTidakDitemukan()
        if status == "BLOKIR" and found.is_admin:
            raise TidakBerhak("Akun admin tidak dapat diblokir.")
        user = self.app._with_pin(lambda pin: admin.set_status(self.conn, self.admin.id, target, status, pin))
        if user:
            ui.ok(f"Akun '{user.id}' sekarang berstatus {user.status}.")
            ui.pause()

    def _transactions(self) -> None:
        ui = self.ui
        ui.header("DAFTAR TRANSAKSI")
        ui.say(" Filter (Enter = lewati):")
        filters = {
            "user_id": ui.ask("  User ID               : ").strip() or None,
            "type_": ui.ask("  Tipe                  : ").strip().upper() or None,
            "status": ui.ask("  Status                : ").strip().upper() or None,
            "date_from": ui.ask("  Dari (YYYY-MM-DD)     : ").strip() or None,
            "date_to": ui.ask("  Sampai (YYYY-MM-DD)   : ").strip() or None,
        }
        page = 0
        while True:
            rows = admin.list_transactions(
                self.conn, self.admin.id, **filters, limit=PAGE_SIZE + 1, offset=page * PAGE_SIZE
            )
            shown, has_next = rows[:PAGE_SIZE], len(rows) > PAGE_SIZE
            ui.header(f"TRANSAKSI - halaman {page + 1}")
            if shown:
                ui.table(
                    ["Referensi", "Waktu", "Akun", "Jenis", "Lawan", "Nominal", "Status"],
                    [
                        [t.ref_no, short_datetime(t.created_at), t.user_id, tx_label(t.type, t.direction),
                         t.counterparty_id or "-", format_rupiah(t.amount), t.status]
                        for t in shown
                    ],
                    right=(5,),
                )
            else:
                ui.say(" Tidak ada transaksi yang cocok.")
            ui.rule()
            options = " [Enter] Kembali"
            if has_next:
                options = " [N] Berikutnya" + options
            if page > 0:
                options = " [P] Sebelumnya" + options
            choice = ui.ask(options + " : ").strip().lower()
            if choice == "n" and has_next:
                page += 1
            elif choice == "p" and page > 0:
                page -= 1
            elif choice == "":
                return

    def _consistency(self) -> None:
        ui = self.ui
        ui.header("CEK KONSISTENSI SALDO")
        ui.loading("Memeriksa seluruh saldo", 0.8)
        problems = admin.check_consistency(self.conn, self.admin.id)
        if not problems:
            ui.ok("Semua saldo sesuai dengan total mutasi transaksi BERHASIL.")
        else:
            ui.warn(f"{len(problems)} akun ditemukan tidak konsisten:")
            ui.table(
                ["User ID", "Saldo tercatat", "Seharusnya"],
                [[p["user_id"], format_rupiah(p["balance"]), format_rupiah(p["expected"])] for p in problems],
                right=(1, 2),
            )
        ui.pause()

    def _reset_password(self) -> None:
        ui = self.ui
        ui.header("RESET PASSWORD PENGGUNA")
        target = ui.ask(" User ID pengguna : ").strip()
        new_password = ui.secret(" Password baru     : ")
        if new_password != ui.secret(" Ulangi            : "):
            raise DataTidakValid("Konfirmasi password tidak cocok.")
        security.validate_password(new_password)
        if auth.get_user(self.conn, target) is None:
            raise AkunTidakDitemukan()
        done = self.app._with_pin(
            lambda pin: admin.reset_password(self.conn, self.admin.id, target, new_password, pin) or True
        )
        if done:
            ui.ok(f"Password '{target}' diubah. Sampaikan password baru ke pemiliknya dengan aman.")
            ui.pause()

    def _outbox(self) -> None:
        ui = self.ui
        ui.header("KOTAK SURAT OTP (DEMO)")
        lines = admin.read_outbox(self.conn, self.admin.id, 10)
        if not lines:
            ui.say(" Belum ada kode OTP yang dikirim.")
        for line in lines:
            ui.say(f" {line}")
        ui.pause()

    def _backup(self) -> None:
        ui = self.ui
        ui.header("BACKUP DATABASE")
        ui.loading("Membuat cadangan database", 1.0)
        path = admin.backup_database(self.conn, self.admin.id)
        ui.ok(f"Cadangan disimpan di: {path}")
        ui.info("Simpan juga data\\secret.key; tanpa kunci itu password dan PIN tidak bisa diverifikasi.")
        ui.pause()

    def _audit(self) -> None:
        ui = self.ui
        ui.header("LOG AUDIT (30 TERBARU)")
        rows = admin.recent_audit(self.conn, self.admin.id, 30)
        if rows:
            ui.table(["Waktu", "Pelaku", "Aksi", "Detail"], [[r["created_at"], r["actor"], r["action"], r["detail"] or ""] for r in rows])
        else:
            ui.say(" Log audit masih kosong.")
        ui.pause()

    def _clear_lockout(self) -> None:
        ui = self.ui
        ui.header("LEPASKAN LOCKOUT AKUN")
        target = ui.ask(" User ID akun (B = kembali): ").strip()
        if target.lower() == "b":
            return
        if auth.get_user(self.conn, target) is None:
            raise AkunTidakDitemukan()
        user = self.app._with_pin(lambda pin: admin.clear_lockout(self.conn, self.admin.id, target, pin))
        if user:
            ui.ok(f"Lockout akun '{user.id}' dilepaskan. Status akun: {user.status}.")
            ui.pause()

    def _refund(self) -> None:
        ui = self.ui
        ui.header("REFUND TRANSAKSI SALAH KIRIM")
        ref_no = ui.ask(" Ref transaksi OUT (B = kembali): ").strip()
        if ref_no.lower() == "b":
            return
        reason = ui.ask(" Alasan refund: ").strip()
        ui.info("Refund harus penuh dan akan mengurangi saldo penerima saat ini.")
        refund_ref = self.app._with_pin(
            lambda pin: (self.ui.loading("Memproses refund"), admin.refund_transaction(self.conn, self.admin.id, ref_no, reason, pin))[1]
        )
        if refund_ref:
            ui.ok(f"Refund berhasil. Referensi refund: {refund_ref}")
            ui.pause()

    def _complaints(self) -> None:
        ui = self.ui
        STATUS_MAP = {"i": "IN_PROGRESS", "r": "RESOLVED", "x": "REJECTED"}
        STATUS_LABELS = {
            "OPEN": "Menunggu",
            "IN_PROGRESS": "Diproses",
            "RESOLVED": "Selesai",
            "REJECTED": "Ditolak",
        }
        ui.header("KELOLA ADUAN PENGGUNA")
        ui.say(" Filter status:")
        ui.say("  1. Semua aduan")
        ui.say("  2. OPEN       — belum ditangani")
        ui.say("  3. IN_PROGRESS — sedang diproses")
        ui.say("  4. RESOLVED   — sudah selesai")
        ui.say("  5. REJECTED   — ditolak")
        status_choice = ui.ask(" Pilih filter (1-5, B = kembali): ").strip()
        status_filter = {
            "1": None, "2": "OPEN", "3": "IN_PROGRESS", "4": "RESOLVED", "5": "REJECTED"
        }.get(status_choice)
        if status_choice.lower() == "b" or status_choice not in ("1","2","3","4","5"):
            return
        rows = complaints.list_for_admin(self.conn, self.admin.id, status_filter, limit=50)
        if not rows:
            ui.say(" Belum ada aduan yang cocok.")
            ui.pause()
            return
        ui.table(
            ["ID", "Tanggal", "Pelapor", "Kategori", "Status", "Ref Trx"],
            [[
                r["id"],
                r["created_at"][:10],
                f"{r['reporter_id']} ({r.get('reporter_name', '-')})",
                r["category"],
                STATUS_LABELS.get(r["status"], r["status"]),
                r["transaction_ref"] or "-",
            ] for r in rows],
        )
        ui.rule()
        detail_id = ui.ask(" ID aduan untuk ditangani (Enter = kembali): ").strip()
        if not detail_id:
            return
        matched = next((r for r in rows if str(r["id"]) == detail_id), None)
        if matched is None:
            ui.error("ID aduan tidak ditemukan di daftar di atas.")
            ui.pause()
            return
        # Tampilkan detail lengkap sebelum admin mengambil tindakan
        ui.say()
        ui.detail_box(
            title=f"Detail Aduan  #{matched['id']}  ·  {matched['category']}",
            fields=[
                ("Pelapor",  f"{matched['reporter_id']} ({matched.get('reporter_name','-')})"),
                ("Status",   STATUS_LABELS.get(matched["status"], matched["status"])),
                ("Ref Trx",  matched["transaction_ref"] or "-"),
                ("Dikirim",  matched["created_at"][:16]),
            ],
            body_label="Isi aduan",
            body_text=matched["message"],
            footer_label="Catatan admin sebelumnya" if matched.get("admin_note") else "",
            footer_text=matched.get("admin_note") or "",
        )
        ui.say()
        ui.say(" Perbarui status aduan ini:")
        ui.say("  [I] IN_PROGRESS — mulai ditangani")
        ui.say("  [R] RESOLVED    — aduan selesai ditangani")
        ui.say("  [X] REJECTED    — aduan ditolak")
        ui.say("  [B] Batal")
        new_status_input = ui.ask(" Pilih tindakan: ").strip().lower()
        if new_status_input == "b" or new_status_input not in STATUS_MAP:
            ui.info("Tidak ada perubahan.")
            return
        note = ui.ask(" Catatan admin (wajib diisi): ").strip()
        if not note:
            raise DataTidakValid("Catatan admin tidak boleh kosong.")
        updated = self.app._with_pin(
            lambda pin: complaints.update_status(
                self.conn, self.admin.id, int(detail_id), STATUS_MAP[new_status_input], note, pin
            )
        )
        if updated:
            ui.ok(f"Aduan #{updated['id']} diperbarui menjadi {updated['status']}.")
            ui.pause()
