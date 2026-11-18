"""Jalankan web Elektro Wallet.

    .venv\\Scripts\\python.exe run.py

Server mendengarkan di 0.0.0.0 agar HP di Wi-Fi/hotspot yang sama bisa membuka halaman
pembayaran dari QR Code. Ini server pengembangan Flask: cukup untuk demo, bukan produksi.
"""
import config
from core import netinfo
from web.app import create_app

app = create_app()

if __name__ == "__main__":
    lan_ip = netinfo.host_for_qr()
    print("=" * 60)
    print(" Elektro Wallet - web")
    print(f" Laptop : http://localhost:{config.PORT}")
    if lan_ip:
        print(f" HP     : http://{lan_ip}:{config.PORT}   (satu Wi-Fi/hotspot)")
    else:
        print(" HP     : IP LAN tidak terdeteksi (set EWALLET_HOST_IP)")
    print(" Jika HP tidak bisa membuka: izinkan Python di Windows Firewall (jaringan Private).")
    print(" Kode OTP lupa password (mode demo) muncul di jendela ini.")
    print("=" * 60)
    app.run(host="0.0.0.0", port=config.PORT, threaded=True, debug=False)
