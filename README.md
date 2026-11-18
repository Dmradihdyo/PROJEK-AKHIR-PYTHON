# Elektro Wallet (Python) — Ide dan Rancangan Proyek Akhir

> Dompet digital berbasis **Python** dengan dua antarmuka untuk pengguna biasa: **Web** dan **Console**. Console juga memiliki mode **Admin**. Keduanya memakai satu inti program (core) dan satu database SQLite. Fitur terinspirasi dari e-wallet populer seperti GoPay.
>
> **Status (3 Nov 2026):** Fase 1–6 inti selesai: fondasi, core, web (Flask), QR (termasuk QR nominal tetap), console pengguna dan admin, serta fitur admin lanjutan (refund, lepas lockout) dan aduan pengguna. 273 tes otomatis lulus. Tampilan web mengikuti gaya `UI.jpg` (minimalis, lime/mint/hitam). Scan QR memakai Google Lens / kamera bawaan HP (bukan kamera browser). Layanan simulasi lanjutan (pulsa, tagihan, voucher) belum dikerjakan. Lihat bagian 9.

| | |
|---|---|
| **Nama proyek** | Elektro Wallet |
| **Bahasa** | Python 3.11+ (dikembangkan di 3.14) |
| **Backend web** | Flask |
| **Database** | SQLite (`sqlite3` bawaan Python) |
| **Tampilan web** | HTML + Bootstrap 5 (grid dan formulir) + CSS dan JavaScript |
| **Console** |  (menu teks, `getpass` untuk input tersamar, tanpa library tambahan) |
| **Hash** | Argon2id (`argon2-cffi`) + pepper HMAC dari kunci aplikasi |

---

## 1. Latar Belakang dan Tujuan

Versi awal Elektro Wallet ditulis dalam program C++ dengan menu konsol dan web server tertanam untuk pembayaran QR. Versi itu berjalan, tetapi memiliki keterbatasan: penyimpanan file teks yang rawan rusak, hashing lemah, saldo bertipe `double`, dan seluruh kode berada dalam satu file.

Versi Python ini bertujuan:
1. Mempertahankan semua fitur versi C++ (registrasi, login, top up, transfer, QR, riwayat, PIN).
2. Memperbaiki kelemahan keamanan dan integritas data.

---

## 2. Konsep Utama: Satu Inti, Dua Antarmuka

Console dan web **tidak memiliki logika sendiri**. Keduanya memanggil fungsi yang sama di `core/`. Dengan begitu aturan seperti "saldo harus cukup" atau "PIN wajib" hanya ditulis sekali dan perilaku keduanya selalu sama.

```
┌──────────────────┐        ┌──────────────────┐
│ CONSOLE          │        │ WEB              │
│ pengguna + admin │        │ Flask + HTML     │
└────────┬─────────┘        └────────┬─────────┘
         └─────────────┬─────────────┘
                       ▼
          ┌──────────────────────────┐
          │ CORE / SERVICE           │
          │ auth · wallet · payment  │
          │ qr · report · security   │
          └────────────┬─────────────┘
                       ▼
               ┌───────────────┐
               │ SQLite (.db)  │
               └───────────────┘
```

### Pembagian peran
| Antarmuka | Pengguna | Fungsi |
|---|---|---|
| **Web** | Pengguna biasa | Registrasi, login, cek saldo, top up, transfer, tampilkan QR (nominal bebas/tetap), bayar QR (dipindai dari HP), riwayat, statistik, aduan, profil, ubah PIN |
| **Console** | Pengguna biasa | Fitur versi C++ plus tambahan: registrasi, login, lupa password, saldo, top up, transfer, tampilkan QR di terminal (nominal bebas/tetap), bayar dengan User ID atau tempel URL QR, riwayat (filter, ekspor CSV, cetak TXT), statistik (diagram Matplotlib), profil, ubah PIN |
| **Console (mode Admin)** | Admin | Ringkasan sistem, cari akun, blokir/aktifkan akun, lihat semua transaksi, cek konsistensi saldo, reset password, kotak surat OTP, backup, log audit, lepas lockout, refund salah kirim, kelola aduan |

> **Keputusan (ketentuan dosen belum jelas):** pengguna biasa dapat memakai Web maupun Console. Karena inti program dipakai bersama, kedua antarmuka memanggil fungsi `core/` yang sama dan perilakunya identik. Satu-satunya hal yang hanya bisa lewat Web adalah memindai QR dengan kamera HP.

---

## 3. Fitur

### 3.1 Fitur Inti 
| Fitur | Antarmuka | Keterangan |
|---|---|---|
| Registrasi | Web + Console | Validasi User ID (3–20 karakter huruf/angka/_), password (min 8, huruf besar, kecil, angka), dan PIN 6 digit |
| Login / logout | Web + Console | Sesi aman, batas percobaan gagal tersimpan di database |
| Lupa password | Web + Console | Verifikasi User ID + email, lalu OTP (simulasi: kode muncul di log server / console admin, bukan di layar pengguna) |
| Cek saldo | Web + Console | Ditampilkan di dashboard |
| Top up | Web + Console | Dikonfirmasi PIN; batas per transaksi dan per hari; metode simulasi |
| Transfer antar pengguna | Web + Console | Dikonfirmasi PIN, ada catatan transfer |
| QR Code penerimaan | Web + Console | QR milik pengguna (di terminal untuk Console) |
| QR nominal tetap | Web + Console | Penerima mengisi nominal; ditandatangani HMAC, berlaku 5 menit, tidak bisa diubah pembayar |
| Scan QR untuk membayar | Google Lens / kamera bawaan HP | Aplikasi tidak memanggil kamera browser; halaman "Scan" berisi petunjuk + fallback User ID / tempel URL QR |
| Bayar via QR | Web (HP) / Console | Pembayar login sebagai dirinya; penerima terisi otomatis dari QR. Web: review + PIN (nominal tetap) atau isi nominal dulu. Console: masukkan ID penerima atau tempel URL QR. Alur sama (`create_pay_session` + `confirm_payment`) |
| Riwayat transaksi | Web + Console | Filter tanggal dan tipe, ekspor CSV, cetak TXT (Console) |
| Statistik | Web + Console | Web: diagram donat. Console: batang teks + diagram lingkaran Matplotlib (PNG) |
| Aduan | Web (buat) + Console admin (kelola) | Pengguna mengadu dari menu Profil; admin menangani lewat Console |
| Profil dan ubah PIN | Web + Console | Verifikasi password sebelum ganti PIN. Input rahasia Console tampil `*` |


### 3.3 Fitur Admin (Console)
```
================ ELEKTRO WALLET - ADMIN ================
 1. Ringkasan sistem (jumlah akun, total saldo, transaksi gagal, top up hari ini)
 2. Daftar / cari akun (ID, nama, email) dengan halaman
 3. Blokir / aktifkan akun                (wajib PIN admin)
 4. Daftar transaksi (filter akun, tipe, status, tanggal)
 5. Cek konsistensi saldo (saldo = total mutasi BERHASIL)
 6. Reset password pengguna               (wajib PIN admin)
 7. Kotak surat OTP (demo)                (kode lupa password)
 8. Backup database                       (data\backups\ewallet_backup_*.db)
 9. Log audit (30 terbaru)
10. Lepaskan lockout akun                 (wajib PIN admin)
11. Refund transaksi salah kirim          (penuh, atomik, wajib PIN admin)
12. Kelola aduan pengguna                 (ubah status + catatan, wajib PIN admin)
 0. Logout
```
Admin harus login dengan role `ADMIN`. Akun admin pertama dibuat oleh `scripts/init_db.py` dan password-nya selalu ditanyakan (tidak ada password bawaan). Setiap aksi admin dicatat di `audit_log`.

---

## 4. Arsitektur dan Struktur Folder

Legenda: ✅ sudah ada · ⬜ belum dikerjakan

```
elektro_wallet/
├── requirements.txt          ✅ versi sudah dikunci
├── pytest.ini                ✅
├── config.py                 ✅ port, path DB, batas nominal, TTL sesi, batas percobaan, kunci rahasia
├── core/                     # LOGIKA BERSAMA (tanpa tampilan)
│   ├── db.py                 ✅ koneksi SQLite, skema, immediate_tx() (BEGIN IMMEDIATE)
│   ├── models.py             ✅ dataclass User, Transaction, Receipt, PaySession (tanpa hash)
│   ├── security.py           ✅ Argon2id + pepper, token/OTP acak, semua validasi input
│   ├── auth.py               ✅ register, login, verify_pin, change_pin, lupa password (OTP), lockout
│   ├── wallet.py             ✅ top up, transfer atomik, batas harian, riwayat
│   ├── payment.py            ✅ sesi bayar QR sekali pakai, konfirmasi dengan PIN
│   ├── reports.py            ✅ cek konsistensi saldo (laporan lain menyusul)
│   ├── errors.py             ✅ exception kustom (SaldoTidakCukup, PinSalah, ...)
│   ├── clock.py              ✅ sumber waktu tunggal (mudah diganti saat pengujian)
│   ├── audit.py              ✅ tulis ke audit_log
│   ├── formatting.py         ✅ format Rupiah
│   ├── netinfo.py            ✅ deteksi IP LAN untuk URL QR (port dari versi C++)
│   ├── qr.py                 ✅ URL bayar, QR sebagai SVG (web) dan teks ANSI (terminal)
│   ├── admin.py              ✅ fungsi admin; tiap fungsi memeriksa role ADMIN sendiri
│   ├── outbox.py             ✅ "kotak surat" simulasi untuk kode OTP (outbox.txt)
│   └── export.py             ✅ ekspor CSV (aman dari injeksi formula), dipakai web dan console
├── run.py                    ✅ menjalankan web di 0.0.0.0 (bisa diakses dari HP)
├── web/                      ✅ ANTARMUKA WEB
│   ├── app.py                #   app factory, CSRF, header keamanan (CSP), penanganan error
│   ├── helpers.py            #   koneksi per request, login_required, redirect aman
│   ├── routes/               #   auth_routes, wallet_routes (/qr, /scan, /complaints), pay_routes
│   ├── templates/            #   19 halaman (Jinja2, di-escape otomatis)
│   └── static/               #   Bootstrap 5.3.3 (lokal, tanpa CDN), app.css (gaya UI.jpg), app.js
├── console/                  ✅ ANTARMUKA CONSOLE
│   ├── ui.py                 #   input/output teks (bisa diganti saat pengujian)
│   ├── user_cli.py           #   menu pengguna: login, top up, transfer, QR, bayar, riwayat, statistik, PIN
│   ├── admin_cli.py          #   menu admin (otomatis untuk akun ber-role ADMIN)
│   └── __main__.py           #   dijalankan dengan:  python -m console
├── scripts/
│   └── init_db.py            ✅ buat tabel + akun admin pertama
├── data/                     # ewallet.db dan secret.key (dibuat otomatis, tidak masuk git)
└── tests/                    ✅ test_auth, test_wallet, test_payment, test_netinfo_qr, test_reports_charts,
                                 test_web, test_admin, test_console, test_scanner_asset (273 tes)
```

### Aturan emas arsitektur
- `web/` dan `console/` **hanya** memanggil `core/`; tidak boleh menjalankan SQL sendiri.
- `core/` **tidak** tahu apa-apa soal HTML atau `print()`; ia mengembalikan data atau melempar exception.
- Semua uang berupa **bilangan bulat Rupiah** (`int`), tidak pernah `float`.
- Setiap fungsi yang memindahkan saldo (`top_up`, `transfer`, `confirm_payment`) **menerima PIN sebagai parameter wajib** dan memverifikasinya sendiri. Antarmuka tidak bisa lupa meminta PIN.

---

## 5. Desain Database (SQLite)

Sumber kebenaran skema ada di `core/db.py`. Ringkasan dan perbedaan penting dari rancangan awal:

```sql
CREATE TABLE users (
  id            TEXT PRIMARY KEY COLLATE NOCASE,   -- 'Damar' dan 'damar' dianggap sama
  name          TEXT NOT NULL,
  email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
  phone         TEXT UNIQUE,
  password_hash TEXT NOT NULL,                     -- Argon2id (salt acak di dalam string hash)
  pin_hash      TEXT NOT NULL,
  balance       INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),   -- Rupiah bulat
  role          TEXT NOT NULL DEFAULT 'USER'  CHECK (role IN ('USER','MERCHANT','ADMIN')),
  status        TEXT NOT NULL DEFAULT 'AKTIF' CHECK (status IN ('AKTIF','BLOKIR')),
  created_at    TEXT NOT NULL
);

-- Satu transfer = dua baris. ref_no unik per baris, group_ref sama untuk pasangannya.
CREATE TABLE transactions (
  id INTEGER PRIMARY KEY, ref_no TEXT NOT NULL UNIQUE, group_ref TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(id),
  type      TEXT NOT NULL,    -- TOPUP | TRANSFER | QR_PAYMENT | BILL | PULSA
  direction TEXT NOT NULL,    -- IN | OUT
  amount INTEGER NOT NULL CHECK (amount > 0), fee INTEGER NOT NULL DEFAULT 0,
  counterparty_id TEXT, note TEXT,
  status TEXT NOT NULL,       -- BERHASIL | GAGAL | MENUNGGU
  created_at TEXT NOT NULL
);

CREATE TABLE pay_sessions (token TEXT PRIMARY KEY, sender_id TEXT, merchant_id TEXT,
  amount INTEGER, expires_at INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0);

-- Pembatasan percobaan (login, PIN, ganti PIN, reset password). Pengganti kolom
-- users.failed_logins / locked_until dari rancangan awal.
CREATE TABLE attempts (kind TEXT, subject TEXT, failed INTEGER, lock_count INTEGER,
  locked_until INTEGER, last_failed INTEGER, PRIMARY KEY (kind, subject));

CREATE TABLE otp_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, code_hash TEXT,
  expires_at INTEGER, failed INTEGER DEFAULT 0, used INTEGER DEFAULT 0);

CREATE TABLE payment_requests (...);   -- disiapkan untuk fitur tambahan
CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT, detail TEXT, created_at TEXT);
```

### Mengapa berbeda dari rancangan awal
| Perubahan | Alasan |
|---|---|
| `transactions.ref_no` unik per baris + kolom `group_ref` | Rancangan awal menaruh `ref_no UNIQUE` tetapi satu transfer menulis dua baris, sehingga baris kedua akan ditolak database |
| Tabel `attempts` menggantikan `users.failed_logins/locked_until` | Kunci per (User ID, IP) mencegah orang lain mengunci akun korban; ada juga kunci per IP dan kunci PIN |
| Tabel `otp_codes` | Lupa password dengan OTP butuh tempat menyimpan kode (disimpan sebagai hash, kedaluwarsa 5 menit, maks. 5 salah) |
| `COLLATE NOCASE` pada ID dan email | Mencegah dua akun `Damar` dan `damar` |
| Waktu disimpan sebagai teks lokal `YYYY-MM-DD HH:MM:SS` | Mudah dibaca dan dipakai untuk batas harian |

### Relasi singkat
```
users 1 ──── n transactions
users 1 ──── n pay_sessions (sebagai pengirim / merchant)
users 1 ──── n payment_requests
users 1 ──── n otp_codes
```

### Transfer yang atomik (inti proyek)
Perpindahan saldo harus satu kesatuan: kurangi pengirim, tambah penerima, catat dua baris transaksi. Jika salah satu gagal, semuanya dibatalkan.

Koneksi dibuka dengan `isolation_level=None` dan transaksi dimulai eksplisit lewat `immediate_tx()` (`BEGIN IMMEDIATE`), sehingga kunci tulis diambil sejak awal dan dua transfer bersamaan dari saldo yang sama tidak bisa saling menyalip. Saya menguji ini dengan merusak `BEGIN IMMEDIATE` menjadi `BEGIN` biasa: tes konkurensi langsung gagal dengan `database is locked`.

```python
# core/wallet.py (disederhanakan)
with immediate_tx(conn):                      # BEGIN IMMEDIATE ... COMMIT / ROLLBACK
    ... cek status akun, saldo, batas harian ...
    cur = conn.execute("UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?", ...)
    if cur.rowcount != 1: raise SaldoTidakCukup()
    conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", ...)
    ref_out = _insert_tx(... direction="OUT" ...)
    _insert_tx(... direction="IN", group_ref=ref_out)
# kegagalan bisnis (saldo kurang, batas harian, akun tidak aktif) dicatat sebagai baris GAGAL
# SETELAH rollback, sehingga tidak ikut dibatalkan
```

---

## 6. Alur Utama

### 6.1 Pembayaran QR (dari HP)
```
Penerima membuka halaman "QR Saya"
        │  core.qr membuat QR dari URL  http://<IP-LAN>:8080/pay?merchant=<id>
        ▼
Pembayar memindai QR dengan Google Lens / kamera bawaan HP (bukan kamera browser)
        │  HP membaca URL QR dan membukanya di browser
        ▼
Browser membuka /pay?merchant=ID (penerima terisi otomatis; nominal tetap bila ada tanda tangan HMAC)
        ▼
GET  /pay?merchant=ID        → get_merchant_for_qr()   (tampil penerima; login jika belum masuk)
POST /pay/review             → create_pay_session()    (isi nominal, tampil ringkasan)
POST /pay/confirm            → confirm_payment()       (masukkan PIN → transfer)
        ▼
Bukti pembayaran (No. Referensi, waktu, nominal, status)
```
Aturan:
- Sesi pembayaran berlaku 5 menit dan sekali pakai.
- PIN wajib di langkah konfirmasi.
- Nominal minimal Rp 1.000.
- Penandaan sesi "terpakai" dan transfer berada dalam **satu transaksi database**, jadi refresh atau klik ganda tidak menggandakan pembayaran (diuji dengan 6 thread yang mengonfirmasi bersamaan: tepat 1 berhasil).
- PIN salah tidak menghabiskan sesi. Jika saldo ternyata kurang saat konfirmasi, transaksi di-rollback dan sesi masih bisa dipakai setelah top up.
- URL QR memakai **HTTP dan IP LAN laptop** (bukan `localhost`, karena HP akan menganggap `localhost` sebagai HP itu sendiri). Untuk demo lokal ini cukup; produksi wajib HTTPS.

### 6.2 Login dengan pembatasan
```
Input ID + password
   ├─ kunci aktif untuk (ID, IP) atau untuk IP?  → AkunTerkunci(sisa detik)
   ├─ cocok → hapus hitungan (ID, IP) → sesi → dashboard
   └─ salah → catat kegagalan untuk (ID, IP) dan untuk IP
              └ 5 kali (ID, IP) atau 20 kali (IP) → terkunci 60 detik,
                berlipat dua pada kunci berulang, maksimal 15 menit
```
Hitungan disimpan di database sehingga tidak hilang saat server dimulai ulang. Kunci per (ID, IP) berarti penyerang di IP lain tidak bisa mengunci akun korban. Baris lama dibersihkan satu per satu dan tabel tidak pernah dikosongkan sekaligus (bug yang ada di versi C++).

---

## 7. Keamanan

| Aspek | Penerapan | Status |
|---|---|---|
| Hash password dan PIN | Argon2id, salt acak per pengguna, ditambah pepper HMAC-SHA256 dari kunci aplikasi (`data/secret.key` atau `EWALLET_SECRET_KEY`). Jika database bocor tanpa kunci, PIN 6 digit tidak bisa ditebak offline | ✅ |
| Penebakan User ID lewat waktu respons | Verifikasi dummy saat User ID tidak ada; pesan galat sama | ✅ |
| Token sesi bayar dan OTP | Modul `secrets` | ✅ |
| Brute-force | Lockout di database untuk login, PIN, ganti PIN, dan permintaan OTP | ✅ |
| SQL Injection | Query berparameter; filter riwayat divalidasi daftar putih | ✅ (diuji) |
| Validasi input | User ID, nama, email, nominal (hanya digit, tanpa `1e9`/negatif/desimal), catatan | ✅ |
| Batas transaksi | Per transaksi dan per hari (top up dan transaksi keluar) | ✅ |
| Audit | REGISTER, PIN_CHANGE, PASSWORD_RESET, LOCKOUT, dan aksi admin (SET_STATUS, RESET_PASSWORD, CLEAR_LOCKOUT, REFUND, BACKUP, COMPLAINT) masuk `audit_log` | ✅ |
| QR nominal tetap | Nominal ditandatangani HMAC-SHA256 dengan kunci aplikasi + masa berlaku 5 menit; pembayar tidak dapat mengubah nominal tanpa terdeteksi | ✅ (diuji) |
| Refund admin | Penuh, atomik, idempotent (tabel `refunds`), ditolak bila saldo penerima kurang; wajib PIN admin + audit | ✅ (diuji) |
| Lepas lockout admin | Hanya menghapus lockout akun target (LOGIN/PIN/PWD/RESET), bukan lockout IP global; wajib PIN admin + audit | ✅ (diuji) |
| Admin hanya via Console | Login admin di Web ditolak (403), tidak ada sesi web admin | ✅ (diuji) |
| CSRF | `Flask-WTF`: token di setiap form POST, POST tanpa token ditolak (400) | ✅ (diuji) |
| XSS | Jinja2 meng-escape otomatis. Catatan transfer berisi `<script>` tampil sebagai teks di semua halaman. Satu-satunya HTML mentah adalah SVG QR yang dibuat server dari angka koordinat | ✅ (diuji) |
| Content-Security-Policy | `script-src 'self'; style-src 'self'`: tidak ada skrip atau style inline di halaman mana pun (diuji untuk semua halaman) | ✅ |
| Header lain | `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` untuk HTML | ✅ |
| Cookie sesi | `HttpOnly`, `SameSite=Lax`, kedaluwarsa 15 menit tidak aktif, sesi baru setiap login (anti session fixation); `Secure` aktif dengan `EWALLET_COOKIE_SECURE=1` | ✅ |
| Open redirect | Parameter `?next=` hanya menerima path lokal (menolak `https://`, `//host`, `\`, `javascript:`) | ✅ (diuji) |
| IDOR | Struk milik orang lain dijawab 404; token sesi bayar terikat ke pengirim | ✅ (diuji) |
| Akun diblokir | Sesi langsung tidak berlaku (status dicek ke database di setiap request) | ✅ (diuji) |
| Ekspor CSV | Sel berawalan `= + - @` diberi tanda `'` agar tidak dibaca Excel sebagai rumus | ✅ (diuji) |
| Pesan lupa password | Sama untuk akun yang ada dan tidak ada | ✅ (diuji) |
| Otorisasi admin | Setiap fungsi `core/admin.py` memeriksa role ADMIN (aktor tidak ada, bukan admin, atau admin diblokir = ditolak). Blokir, reset password, dan backup juga mewajibkan PIN admin dan dicatat di audit_log. Admin tidak bisa memblokir admin, dan password admin lain tidak bisa direset | ✅ (diuji) |
| Pencarian akun admin | Karakter `%` dan `_` pada kata kunci dianggap huruf biasa (tidak menjadi wildcard LIKE) | ✅ (diuji) |
| HTTPS | Demo lokal memakai HTTP; catat bahwa produksi wajib HTTPS | dokumentasi |

Batasan yang diketahui: penyerang terdistribusi (banyak IP) terhadap satu akun tidak dihentikan oleh kunci per IP. Untuk demo di jaringan lokal ini diterima.

---

## 8. Teknologi dan Library

`requirements.txt` (versi sudah dikunci):
```
Flask==3.1.3
Flask-WTF==1.3.0
argon2-cffi==25.1.0
qrcode[pil]==8.2
python-dotenv==1.2.4
pytest==9.2.0
```

Cara menjalankan (Windows PowerShell; perintah `python` di komputer ini adalah shortcut Microsoft Store, jadi gunakan `py`):
```powershell
cd elektro_wallet
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\init_db.py          # buat tabel + akun admin
.\.venv\Scripts\python.exe -m pytest -q                # jalankan pengujian
.\.venv\Scripts\python.exe run.py                      # web di http://localhost:8080 (dan http://<IP-LAN>:8080 untuk HP)
.\.venv\Scripts\python.exe -m console                  # console (pengguna; akun admin otomatis masuk menu admin)
```

Kode OTP lupa password (mode demo, tanpa email sungguhan) ditulis ke `data\outbox.txt`. Di web kode juga muncul di terminal tempat `run.py` berjalan; di console admin dapat membacanya lewat menu "Kotak surat OTP".

Variabel lingkungan opsional: `EWALLET_PORT` (default 8080), `EWALLET_HOST_IP` (paksa IP di QR), `EWALLET_DATA_DIR`, `EWALLET_DB`, `EWALLET_COOKIE_SECURE`.

Satu tes (`test_qr_terbaca_oleh_decoder_nyata`) memakai OpenCV untuk membuktikan QR terbaca decoder sungguhan. OpenCV tidak ada di `requirements.txt`; tes itu otomatis dilewati bila tidak terpasang (`pip install opencv-python-headless` untuk menjalankannya).

Saat pertama menjalankan `run.py`, Windows akan menanyakan izin firewall untuk Python. Pilih **jaringan Private**, kalau tidak HP tidak bisa membuka halaman bayar.

---

## 9. Rencana Pengerjaan (Roadmap)

| Fase | Isi | Status |
|---|---|---|
| **1. Fondasi** | Struktur folder, `db.py`, skema, `security.py`, `init_db.py` | ✅ Selesai |
| **2. Core** | `auth.py`, `wallet.py` (top up, transfer atomik), `payment.py`, pengujian | ✅ Selesai |
| **3. Web dasar** | Template, registrasi, login, lupa password, dashboard, top up, transfer (2 langkah + PIN), riwayat (filter, halaman, ekspor CSV), struk, profil, ubah PIN | ✅ Selesai |
| **4. QR** | `netinfo.py`, `qr.py`, halaman "QR Saya" (pilihan IP, nominal tetap), halaman "Scan" (petunjuk Google Lens/kamera bawaan + fallback User ID), alur bayar dari HP: pindai, login, review, PIN, struk | ✅ Selesai |
| **5. Console** | Console pengguna (statistik + diagram Matplotlib, ekspor CSV, cetak TXT, bayar via URL QR, input rahasia `*`) dan console admin (`core/admin.py`) | ✅ Selesai |
| **6. Fitur tambahan** | QR nominal tetap (HMAC), refund admin, lepas lockout admin, aduan pengguna | ✅ Inti selesai (payment request & split bill belum) |
| **7. Layanan simulasi** | Pulsa, tagihan, voucher, poin (pilih sesuai waktu) | ⬜ |
| **8. Finalisasi** | Pengujian menyeluruh, perapian tampilan, README, data demo | 🟡 README & dokumen sudah; data demo belum |

> Fase 1–6 inti sudah membentuk proyek utuh: web + console pengguna + console admin + QR nominal tetap + refund + aduan. Payment request, split bill, dan layanan simulasi dikerjakan sesuai sisa waktu.

---

## 10. Pengujian

Pengujian otomatis ada di `tests/` (273 tes, ±12 detik): `.\.venv\Scripts\python.exe -m pytest -q`.

### Yang sudah tercakup
- Registrasi menolak password lemah, PIN salah format, ID/email ganda (tidak peka huruf besar), ID/nama berisi karakter berbahaya (`|`, `<script>`).
- Hash memakai Argon2id dan dua akun dengan PIN sama menghasilkan hash berbeda.
- Login salah 5 kali mengunci, kunci berlipat, kunci tersimpan di database, penyerang di IP lain tidak bisa mengunci korban, kunci per IP, dan membanjiri tabel percobaan tidak menghapus kunci korban.
- PIN salah 3 kali mengunci (PIN benar pun ditolak selama kunci); PIN benar mereset hitungan.
- Lupa password: OTP sekali pakai, kedaluwarsa, dibatasi percobaannya, OTP baru membatalkan yang lama, permintaan dibatasi.
- Top up dan transfer: saldo cukup berhasil, saldo kurang ditolak (dan dicatat `GAGAL`), ke diri sendiri ditolak, akun diblokir ditolak, nominal tidak valid (`0`, negatif, `1e9`, desimal, spasi, angka non-ASCII) ditolak, batas harian.
- **Transfer atomik:** jika gagal di tengah (disimulasikan), saldo dan riwayat tidak berubah.
- **Konkurensi:** 8 thread mentransfer bersamaan dari saldo yang sama, dan 6 thread mengonfirmasi satu sesi QR bersamaan. Tidak ada saldo negatif dan hanya satu yang berhasil. Ada juga tes deterministik untuk penjaga atomik sesi. Ketiganya terbukti gagal jika penjaganya sengaja dirusak (`BEGIN IMMEDIATE` diganti `BEGIN`, atau `used = 0` dihapus).
- Sesi bayar: kedaluwarsa, tidak bisa dipakai dua kali, tidak bisa dipakai pengguna lain, penerima tidak ada/diblokir.
- Konsistensi: saldo setiap akun = total mutasi `BERHASIL`; total saldo = total top up; penyimpangan yang disuntikkan langsung ke database terdeteksi.
- Riwayat: filter tipe/status/tanggal, paginasi, tidak bocor antar pengguna, filter berisi SQL injection ditolak.

### Tercakup untuk web dan QR (`test_web.py`, `test_netinfo_qr.py`)
- Registrasi, login, logout (hanya POST), lupa password dengan OTP, ubah PIN, top up, transfer dua langkah, riwayat, struk.
- POST tanpa token CSRF ditolak; halaman terlindungi mengarah ke login; login salah 401 lalu terkunci 429.
- Redirect `?next=` aman (lima bentuk URL berbahaya ditolak); cookie `HttpOnly` + `SameSite`; header keamanan; tidak ada skrip/style inline.
- Catatan berisi `<script>` di-escape di semua halaman; struk orang lain 404; ekspor CSV aman dari formula.
- Halaman `/scan`: terlindungi login, berisi petunjuk Google Lens / kamera bawaan + fallback User ID / tempel URL QR, tanpa kamera browser, tanpa skrip inline.
- QR nominal tetap: tanda tangan valid diterima, nominal yang diubah ditolak, payload kedaluwarsa ditolak; di Web pembayar hanya melihat ringkasan (tanpa input nominal).
- Admin lanjutan: lepas lockout hanya untuk akun target, refund penuh/atomik/idempotent, refund ditolak saat saldo penerima kurang, serta aduan dibuat pengguna dan ditangani admin.
- Admin ditolak login di Web (403).
- QR decoder OpenCV bersifat opsional; jika tidak terpasang satu tes dilewati.

### Uji manual yang masih perlu Anda lakukan
- Pindai QR (nominal bebas dan nominal tetap) dengan Google Lens / kamera bawaan HP, lalu selesaikan pembayaran dari HP.
- Firewall Windows tetap diperlukan agar HP dapat mengakses server laptop; pemindaian QR memakai kamera HP langsung dan HP harus satu jaringan dengan laptop.
- Buka diagram lingkaran statistik Console (file PNG di folder proyek) dan periksa tampilannya.
- Periksa tampilan di layar HP. Saya sudah memeriksa screenshot browser pada lebar 500 px, tetapi belum perangkat HP sungguhan.
- Coba console secara interaktif di terminal (registrasi, login, top up, QR di terminal). Alur console sudah diuji otomatis dengan input terskrip, dan layar utamanya sudah tampil benar di terminal asli.

---

## 11. Skenario Demo (untuk Presentasi)

1. Buka web di laptop, daftar dua akun (Damar dan Syafira).
2. Top up saldo Damar (PIN dikonfirmasi), tunjukkan bukti dan riwayat.
3. Damar membuka "QR Saya".
4. Dari HP, Syafira memindai QR, login, mengisi nominal, memasukkan PIN, dan bukti muncul.
5. Kembali ke laptop: saldo dan riwayat keduanya berubah.
6. Tunjukkan bahwa **console pengguna** menampilkan saldo dan riwayat yang sama (satu database, satu core).
7. Buka **console admin**: tampilkan daftar transaksi, jalankan "cek konsistensi saldo", blokir satu akun, lalu coba transaksi dari akun itu (ditolak).
8. Tunjukkan fitur tambahan (misalnya payment request atau split bill).

---

## 12. Data Lama dari Versi C++

**Tidak ada migrasi.** Sesuai keputusan, versi Python dimulai dari database kosong. Dua akun contoh di `users.txt` (`dmr123`, `fira123`) dan lima transaksinya tidak dibawa. File C++ dan `.txt` tetap ada di folder induk sebagai arsip dan tidak diubah. Hash FNV-1a lama memang tidak kompatibel dengan Argon2.

---

## 13. Perbandingan Versi

| Aspek | C++ (v1) | Python |
|---|---|---|
| Penyimpanan | File teks, ditulis ulang tiap transaksi | SQLite dengan transaksi database |
| Hash | FNV-1a + salt statis | Argon2id + salt acak + pepper |
| Saldo | `double` | `int` (Rupiah bulat) + `CHECK (balance >= 0)` |
| PIN saat bayar QR | Tidak diminta | Wajib (di level core) |
| Lockout | Di memori, per User ID, bisa di-flush | Di database, per (ID, IP) dan per IP, tidak pernah di-flush |
| Transaksi gagal | Tidak dicatat | Dicatat sebagai `GAGAL` |
| Batas nominal | Hanya di web | Satu aturan di core untuk web dan console |
| Antarmuka | Console + web tertanam | Web + Console (pengguna) + Console Admin |
| QR Code | Generator manual ±400 baris | Library `qrcode` |
| Struktur kode | Satu file ±2.800 baris | Modul terpisah (`core`, `web`, `console`) |
| Pengujian | Manual | Otomatis dengan `pytest` (263 tes) |

---

## 14. Catatan dan Batasan

- Proyek ini adalah **simulasi** untuk pembelajaran: tidak terhubung ke bank, payment gateway, atau penyedia layanan sungguhan. Top up, pulsa, tagihan, dan transfer bank bersifat simulasi.
- Fitur dan istilah terinspirasi dari e-wallet populer; bukan salinan produk atau spesifikasi resmi pihak mana pun.
- OTP lupa password hanyalah simulasi: tidak ada email yang dikirim.
- Sebelum dikerjakan lebih jauh, pastikan ketentuan dosen (bentuk antarmuka, dokumen yang diminta) selaras dengan rancangan ini.
