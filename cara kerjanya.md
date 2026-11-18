# Elektro Wallet (Python)

Dompet digital simulasi dengan dua antarmuka untuk pengguna, **Web** dan **Console**, yang memakai satu inti program (`core/`) dan satu database SQLite. Pembayaran bisa dilakukan dengan memindai QR Code dari HP. Proyek ini adalah pengembangan ulang dari versi C++ (`ElektroWalletSystem.cpp` di folder induk).

> Ini simulasi untuk pembelajaran. Tidak terhubung ke bank atau payment gateway; top up dan pengiriman OTP bersifat simulasi.

Rancangan lengkap ada di `docs\ElektroWallet_Python_Rancangan.md`. Gambar acuan tampilan ada di `docs\UI_referensi.jpg`.

---

## 1. Persiapan pertama kali (Windows PowerShell)

Ikuti langkah ini dari awal jika proyek belum pernah dijalankan.

### Langkah 1: buka folder proyek yang benar

Buka PowerShell, lalu jalankan:

```powershell
cd "C:\C_C++\Projek_Akhir\ElektroWallet_Python"
```

Pastikan folder yang terbuka berisi `run.py`, `config.py`, `core`, `web`, dan `console`:

```powershell
Get-ChildItem
```

> Jangan gunakan folder `elektro_wallet` lama jika ingin menjalankan salinan proyek yang sudah dirapikan ini.

### Langkah 2: pastikan Python tersedia

```powershell
py --version
```

Python yang didukung adalah Python 3.11 atau lebih baru. Komputer Windows tertentu tidak mengenali perintah `python`, jadi panduan ini memakai `py` dan `.\.venv\Scripts\python.exe`.

### Langkah 3: buat virtual environment

Jalankan sekali saja:

```powershell
py -m venv .venv
```

Perintah ini membuat folder `.venv` khusus untuk dependensi proyek.

### Langkah 4: pasang dependensi

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Jika instalasi berhasil, Flask, Argon2, QR Code, Matplotlib, dan pytest tersedia di proyek ini. Matplotlib dipakai untuk diagram lingkaran statistik di Console.

### Langkah 5: buat database dan akun admin

```powershell
.\.venv\Scripts\python.exe scripts\init_db.py
```

Program akan menanyakan:

- User ID admin
- Nama admin
- Email admin
- Password admin dua kali
- PIN admin dua kali

Tidak ada password admin bawaan. Simpan kredensial tersebut dengan aman.

Setelah selesai, folder `data\` dibuat otomatis:

| File | Isi |
|---|---|
| `data\ewallet.db` | Database SQLite |
| `data\secret.key` | Kunci cookie dan hash password/PIN. **Jangan hapus atau pisahkan dari database.** |
| `data\outbox.txt` | Kode OTP simulasi lupa password |
| `data\backups\` | Backup dari menu admin |

## 2. Menjalankan aplikasi

### Pilihan A: menjalankan Web

Dari folder `ElektroWallet_Python`, jalankan:

```powershell
.\.venv\Scripts\python.exe run.py
```

Jangan tutup jendela PowerShell tersebut selama web dipakai. Jika berhasil, terminal menampilkan alamat seperti:

```text
Laptop : http://localhost:8080
HP     : http://192.168.1.8:8080
```

Buka alamat berikut di browser laptop:

```text
http://localhost:8080
```

Untuk membuka dari HP:

1. Sambungkan HP dan laptop ke Wi-Fi atau hotspot yang sama.
2. Gunakan alamat `http://<IP-LAN>:8080` yang dicetak oleh `run.py`.
3. Jika Windows Firewall bertanya, izinkan Python untuk jaringan **Private**.
4. Daftar atau login di web.
5. Penerima membuka menu **QR Saya**, boleh mengisi nominal tetap, lalu menampilkan QR.
6. Pembayar memindai QR itu dengan **Google Lens atau kamera bawaan HP**, bukan kamera di dalam browser.
7. HP membuka halaman pembayaran. Pembayar login sebagai dirinya sendiri (penerima sudah terisi otomatis dari QR), lalu konfirmasi dengan PIN. Jika QR nominal tetap, pembayar tinggal meninjau dan memasukkan PIN.
8. Untuk menghentikan web, kembali ke PowerShell lalu tekan `Ctrl+C`.

### Pilihan B: menjalankan Console pengguna atau admin

Buka **PowerShell kedua**. Jangan hentikan PowerShell yang sedang menjalankan Web jika ingin memakai keduanya bersamaan.

Masuk ke folder yang sama:

```powershell
cd "C:\C_C++\Projek_Akhir\ElektroWallet_Python"
```

Jalankan console:

```powershell
.\.venv\Scripts\python.exe -m console
```

Di menu utama:

- Login dengan akun biasa untuk membuka menu pengguna.
- Login dengan akun yang dibuat melalui `init_db.py` untuk membuka menu admin.
- Akun admin otomatis diarahkan ke menu admin. **Admin hanya bisa masuk lewat Console; login admin di Web ditolak.**
- Saat mengetik password atau PIN, karakter ditampilkan sebagai `*`.

Untuk menghentikan console, pilih menu **4. Keluar Program**, atau tekan `Ctrl+C`.

### Pilihan C: menjalankan pengujian

Buka PowerShell ketiga atau hentikan aplikasi terlebih dahulu, lalu jalankan:

```powershell
cd "C:\C_C++\Projek_Akhir\ElektroWallet_Python"
.\.venv\Scripts\python.exe -m pytest -q
```

Hasil normalnya adalah sekitar 273 tes, dengan satu tes QR yang dilewati jika `opencv-python-headless` tidak dipasang. OpenCV bersifat opsional. Untuk menjalankan tes decoder QR juga:

```powershell
.\.venv\Scripts\python.exe -m pip install opencv-python-headless
.\.venv\Scripts\python.exe -m pytest -q
```

Web dan Console memakai `data\ewallet.db` yang sama. Jika top up dilakukan dari Web, saldo yang sama akan terlihat saat login lewat Console.

---

## 3. Fitur

| Fitur | Web | Console |
|---|:-:|:-:|
| Registrasi, login, logout | ✅ | ✅ |
| Lupa password (OTP simulasi) | ✅ | ✅ |
| Cek saldo, profil, ubah PIN | ✅ | ✅ |
| Top up (dengan PIN) | ✅ | ✅ |
| Transfer antar pengguna (dengan PIN) | ✅ | ✅ |
| QR Code untuk menerima pembayaran | ✅ (SVG, nominal bebas atau tetap) | ✅ (teks di terminal, nominal bebas atau tetap) |
| Scan QR untuk membayar | Via Google Lens / kamera bawaan HP | Tempel URL QR atau ketik User ID |
| Bayar via QR | ✅ (penerima otomatis; nominal + PIN) | ✅ (ketik User ID atau tempel URL QR) |
| Riwayat dengan filter, halaman, ekspor CSV, cetak TXT | ✅ | ✅ |
| Statistik pemasukan/pengeluaran | ✅ (grafik donat) | ✅ (batang teks + diagram lingkaran PNG) |
| Buat aduan | ✅ (dari menu Profil) | – |
| Menu admin | – | ✅ |

**Menu admin (console):** ringkasan sistem, cari akun, blokir/aktifkan akun, daftar transaksi, cek konsistensi saldo, reset password pengguna, kotak surat OTP, backup database, log audit, **lepaskan lockout akun**, **refund transaksi salah kirim**, dan **kelola aduan pengguna**. Admin tidak dapat diakses lewat Web.

### QR nominal tetap
Penerima dapat mengisi nominal sebelum menampilkan QR. Nominal itu ditandatangani dengan HMAC dan berlaku 5 menit, sehingga pembayar tidak dapat mengubahnya. Jika nominal tetap, pembayar hanya meninjau lalu memasukkan PIN (seperti alur GoPay). Jika nominal dikosongkan, pembayar mengisi nominal sendiri.

### Refund (admin)
Admin dapat mengembalikan transaksi salah kirim lewat Console. Refund bersifat penuh, atomik, dan hanya bisa sekali per transaksi. Refund ditolak jika saldo penerima saat ini tidak mencukupi.

### Aturan penting
- Uang disimpan sebagai bilangan bulat Rupiah. Nominal minimal **Rp 1.000**.
- Batas: top up maks Rp 5.000.000 per transaksi dan Rp 10.000.000 per hari; transfer/bayar maks Rp 10.000.000 per transaksi dan Rp 20.000.000 per hari (diatur di `config.py`).
- **PIN wajib** untuk top up, transfer, dan bayar QR, di Web maupun Console.
- Password: minimal 8 karakter dengan huruf besar, huruf kecil, dan angka. PIN: tepat 6 angka.
- Sesi pembayaran QR berlaku 5 menit dan hanya bisa dipakai sekali.
- Sesi web habis setelah 15 menit tidak aktif.

### Pembatasan percobaan (tersimpan di database)
| Kasus | Batas | Kunci |
|---|---|---|
| Login salah | 5 kali per (User ID, IP) atau 20 kali per IP | 60 detik, berlipat dua pada kunci berulang, maks 15 menit |
| PIN salah | 3 kali per akun | sama |
| OTP lupa password | 5 kali salah, berlaku 5 menit | OTP tidak bisa dipakai lagi; minta kode baru |

---

## 4. Skenario demo

1. Jalankan `run.py`, buka `http://localhost:8080`, lalu **Daftar** dua akun (misalnya `damar` sebagai penerima dan `syafira` sebagai pembayar).
2. Login sebagai `syafira`, **Top Up** Rp 100.000 dengan PIN, lihat struk di Riwayat.
3. Di jendela lain (atau setelah logout), login sebagai `damar` dan buka **QR Saya**. Isi nominal tetap (mis. Rp 25.000) atau biarkan kosong, lalu tampilkan QR.
4. Di HP (Wi-Fi yang sama), pindai QR milik `damar` dengan Google Lens atau kamera bawaan HP. Login sebagai `syafira`, lalu konfirmasi dengan PIN. Jika nominal tetap, `syafira` tinggal meninjau; jika tidak, isi nominal dulu.
5. Kembali ke laptop: saldo dan riwayat keduanya berubah (`damar` bertambah, `syafira` berkurang). Buka **Statistik** untuk melihat grafik donat.
6. Buka **Console** (`-m console`), login sebagai `damar`: saldo dan riwayat sama dengan di web. Coba Transfer, menu QR di terminal, dan **Statistik** (menghasilkan diagram lingkaran PNG di folder proyek).
7. Login sebagai **admin** di Console: lihat Ringkasan, jalankan **Cek konsistensi saldo**, **Blokir** satu akun lalu coba login akun itu (ditolak), **Refund** transaksi salah kirim, dan **Kelola aduan** yang dikirim pengguna dari menu Profil.

---

## 5. Konfigurasi (opsional)

Lewat variabel lingkungan (PowerShell: `$env:NAMA = "nilai"` sebelum menjalankan):

| Variabel | Fungsi | Bawaan |
|---|---|---|
| `EWALLET_PORT` | Port web | `8080` |
| `EWALLET_HOST_IP` | Paksa IP yang ditanam di QR | deteksi otomatis |
| `EWALLET_DATA_DIR` | Folder data | `data\` |
| `EWALLET_DB` | Lokasi file database | `data\ewallet.db` |
| `EWALLET_SECRET_KEY` | Kunci rahasia (menggantikan `secret.key`) | file otomatis |
| `EWALLET_COOKIE_SECURE` | `1` jika disajikan lewat HTTPS | tidak aktif |

## 6. Cara memindai QR (HTTP lokal)

Pemindaian memakai **Google Lens atau kamera bawaan HP**, bukan kamera di dalam browser. Aplikasi ini sengaja tidak memanggil kamera lewat JavaScript, karena browser biasanya menolak akses kamera pada halaman HTTP non-`localhost`.

1. Jalankan `run.py` di laptop.
2. Penerima membuka **QR Saya**, mengisi nominal tetap bila perlu, lalu menampilkan QR.
3. Pembayar membuka Google Lens atau aplikasi Kamera HP dan mengarahkannya ke QR.
4. HP membaca URL seperti `http://192.168.1.8:8080/pay?merchant=damar` (atau dengan nominal tetap bertanda tangan).
5. Pembayar menekan URL itu, browser HP membuka halaman pembayaran.
6. Pembayar login sebagai dirinya sendiri; penerima sudah terisi otomatis dari QR.
7. Pembayar meninjau nominal lalu memasukkan PIN.

Halaman **Scan** di aplikasi hanya berisi petunjuk ini plus kolom fallback untuk menempel URL QR atau mengetik User ID penerima.

> Firewall dan kamera adalah dua hal berbeda. Firewall mengatur apakah HP dapat menjangkau server di laptop; pemindaian QR memakai kamera HP langsung. HP dan laptop tetap harus berada di jaringan yang sama.

## 7. Jika ada masalah

| Gejala | Penyebab / solusi |
|---|---|
| HP tidak bisa membuka halaman bayar | Pastikan satu Wi-Fi dengan laptop; izinkan Python di Windows Firewall (jaringan Private); jika laptop punya beberapa IP, pilih IP yang benar di halaman **QR Saya** |
| Pembayar tidak bisa membuka URL dari QR | Pastikan HP satu jaringan dengan laptop dan URL memakai IP LAN (bukan `localhost`). Gunakan Google Lens atau kamera bawaan HP |
| "QR nominal tetap tidak valid atau kedaluwarsa" | QR nominal tetap berlaku 5 menit. Minta penerima menampilkan QR baru |
| QR tidak muncul / "IP LAN tidak terdeteksi" | Laptop belum tersambung ke Wi-Fi/hotspot. Atur `EWALLET_HOST_IP` (contoh `192.168.1.10`). `localhost` tidak bisa dipakai di QR |
| `python` tidak dikenali | Gunakan `py`, atau jalur penuh `.\.venv\Scripts\python.exe` |
| Port 8080 dipakai program lain | Atur `EWALLET_PORT`, mis. `$env:EWALLET_PORT = "8090"` |
| Password/PIN semua akun ditolak setelah memindahkan database | `data\secret.key` tidak ikut dipindahkan |
| Akun terkunci "Coba lagi dalam N detik" | Tunggu sampai waktu habis; admin dapat mereset password lewat console |

---

## 8. Struktur proyek

```
ElektroWallet_Python/
├── config.py            pengaturan dan batas nominal
├── run.py               menjalankan web
├── core/                logika bersama (auth, wallet, payment, admin, reports, qr, netinfo, ...)
├── web/                 antarmuka web (Flask: routes, templates, static)
├── console/             antarmuka console (user_cli, admin_cli)
├── scripts/init_db.py   membuat database dan admin pertama
├── docs/                dokumen rancangan dan gambar acuan tampilan
├── tests/               273 tes otomatis
└── data/                database, kunci, outbox, backup (dibuat otomatis)
```

Aturan arsitektur: `web/` dan `console/` hanya memanggil `core/`; SQL hanya ada di `core/`. Aturan seperti "PIN wajib", batas harian, dan pemeriksaan hak admin ada di `core/`, sehingga tidak bisa terlewat oleh antarmuka mana pun.

## 9. Batasan yang diketahui

- Server web adalah server pengembangan Flask: cukup untuk demo lokal, bukan untuk produksi. HTTP polos; produksi wajib HTTPS.
- Penyerang dari banyak IP sekaligus terhadap satu akun tidak dihentikan oleh kunci per IP (diterima untuk demo jaringan lokal).
- OTP lupa password hanya simulasi: tidak ada email atau SMS yang dikirim.
- Pemindaian QR memakai Google Lens atau kamera bawaan HP. Aplikasi tidak memanggil kamera lewat browser agar tidak bergantung pada HTTPS. Pembayaran tidak terjadi otomatis; pembayar tetap melalui ringkasan dan PIN.
- Pembayar tetap login sebagai dirinya sendiri untuk membayar (saldo yang dipakai adalah saldo pembayar). Yang otomatis dari QR adalah data penerima, bukan identitas pembayar.
- Diagram lingkaran statistik di Console disimpan sebagai berkas PNG di folder proyek, lalu dibuka manual; Console tidak menampilkan jendela grafik.
- Tampilan sudah diperiksa lewat screenshot browser pada lebar 500 px, tetapi belum di perangkat HP sungguhan.
