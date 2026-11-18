"""Exception kustom. Lapisan web/console cukup menampilkan `str(error)`."""


class EWalletError(Exception):
    default_message = "Terjadi kesalahan."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.default_message)


# --- Validasi input ---
class DataTidakValid(EWalletError):
    default_message = "Data yang dimasukkan tidak valid."


class PasswordLemah(DataTidakValid):
    default_message = "Password minimal 8 karakter dan wajib berisi huruf besar, huruf kecil, dan angka."


class PinTidakValid(DataTidakValid):
    default_message = "PIN harus tepat 6 digit angka."


class NominalTidakValid(DataTidakValid):
    default_message = "Nominal tidak valid."


# --- Akun ---
class IdSudahAda(EWalletError):
    default_message = "User ID sudah terdaftar."


class EmailSudahAda(EWalletError):
    default_message = "Email sudah terdaftar."


class KredensialSalah(EWalletError):
    default_message = "User ID atau password salah."


class AkunTidakAktif(EWalletError):
    default_message = "Akun tidak aktif atau diblokir."


class AkunTidakDitemukan(EWalletError):
    default_message = "Akun tidak ditemukan."


class TidakBerhak(EWalletError):
    default_message = "Anda tidak berhak melakukan aksi ini."


class AkunTerkunci(EWalletError):
    """Terlalu banyak percobaan gagal. `sisa_detik` = waktu tunggu."""

    def __init__(self, sisa_detik: int):
        self.sisa_detik = sisa_detik
        super().__init__(f"Terlalu banyak percobaan. Coba lagi dalam {sisa_detik} detik.")


class PinSalah(EWalletError):
    def __init__(self, sisa_percobaan: int):
        self.sisa_percobaan = sisa_percobaan
        super().__init__(f"PIN salah. Sisa percobaan: {sisa_percobaan}.")


class OtpTidakValid(EWalletError):
    default_message = "Kode OTP salah atau sudah kedaluwarsa."


# --- Dompet ---
class SaldoTidakCukup(EWalletError):
    default_message = "Saldo tidak mencukupi."


class PenerimaTidakDitemukan(EWalletError):
    default_message = "Penerima tidak ditemukan."


class TransferKeDiriSendiri(EWalletError):
    default_message = "Tidak dapat mengirim ke akun sendiri."


class BatasTransaksiTerlampaui(EWalletError):
    default_message = "Batas transaksi terlampaui."


# --- Pembayaran QR ---
class SesiTidakValid(EWalletError):
    default_message = "Sesi pembayaran tidak valid, sudah dipakai, atau kedaluwarsa. Pindai ulang QR Code."
