"""Deteksi alamat IP LAN laptop untuk ditanam di URL QR Code.

Alamat loopback (127.0.0.1 / localhost) TIDAK PERNAH dipakai: HP akan
menganggapnya sebagai HP itu sendiri, bukan laptop. Logika diport dari versi C++.
"""
import ipaddress
import socket

import config


def normalize_ip(text: str | None) -> str | None:
    """Kembalikan IPv4 yang bisa dipakai di QR, atau None bila tidak valid
    (bukan IPv4, loopback, 0.0.0.0, link-local/APIPA, multicast, reserved)."""
    try:
        ip = ipaddress.ip_address((text or "").strip())
    except ValueError:
        return None
    if ip.version != 4 or ip.is_loopback or ip.is_unspecified or ip.is_link_local:
        return None
    if ip.is_multicast or ip.is_reserved:
        return None
    return str(ip)


def rank(ip: str) -> int:
    """Makin kecil makin disukai: LAN/hotspot lebih baik daripada adaptor virtual."""
    a, b, c, _ = (int(x) for x in ip.split("."))
    if a == 192 and b == 168 and c in (56, 99):
        return 8  # VirtualBox / docker-machine
    if a == 172 and b == 17:
        return 8  # docker0
    if a == 192 and b == 168:
        return 1
    if a == 172 and 16 <= b <= 31:
        return 2
    if a == 10:
        return 3
    return 5


def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """Apakah ada server yang mendengarkan di host:port (dipakai console untuk menunjukkan
    apakah web server `run.py` sedang berjalan)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def route_ip() -> str:
    """IP interface yang dipakai untuk rute keluar (UDP connect tidak mengirim paket)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 53))
            return sock.getsockname()[0]
    except OSError:
        return ""


def candidates() -> list[str]:
    """Semua IPv4 aktif di laptop (tanpa loopback), diurutkan dari yang terbaik."""
    found: list[str] = []
    try:
        hostname = socket.gethostname()
        addresses = socket.gethostbyname_ex(hostname)[2]
        addresses += [info[4][0] for info in socket.getaddrinfo(hostname, None, socket.AF_INET)]
    except OSError:
        addresses = []
    for address in addresses:
        ip = normalize_ip(address)
        if ip and ip not in found:
            found.append(ip)
    found.sort(key=rank)  # sort stabil: urutan asli dipertahankan untuk rank sama
    return found


def detect_lan_ip() -> str:
    """IP LAN terbaik, atau '' bila tidak ada (sengaja TIDAK jatuh ke 127.0.0.1)."""
    route = normalize_ip(route_ip())
    if route and rank(route) < 8:
        return route
    options = candidates()
    if options:
        return options[0]
    return route or ""


def host_for_qr(override: str | None = None) -> str:
    """Prioritas: pilihan pengguna (override) > EWALLET_HOST_IP > deteksi otomatis."""
    for choice in (override, config.HOST_IP):
        ip = normalize_ip(choice)
        if ip:
            return ip
    return detect_lan_ip()
