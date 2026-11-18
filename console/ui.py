# -*- coding: utf-8 -*-
"""Lapisan tampilan console Elektro Wallet.

Desain:
  - Header ASCII-art dengan aksen warna gradient cyan→biru
  - Panel info dengan border tipis, badge status berwarna
  - Tabel zebra (baris selang-seling), kolom kanan rata untuk nominal
  - Spinner Braille non-blocking saat proses berjalan
  - Efek suara via winsound (Windows); fallback senyap di platform lain
  - Semua metode primitif (ask/say/clear) dapat ditimpa oleh kelas uji
"""
import getpass
import os
import re
import sys
import time
import threading

try:
    import msvcrt
except ImportError:
    msvcrt = None

try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False

# ═══════════════════════════════════════════════════════════════
#  KONSTANTA TAMPILAN
# ═══════════════════════════════════════════════════════════════
WIDTH = 68          # lebar total layar
INNER = WIDTH - 2   # lebar isi dalam border

# ── kode warna ANSI ──────────────────────────────────────────
_C: dict[str, str] = {
    "reset":    "\033[0m",
    "bold":     "\033[1m",
    "dim":      "\033[2m",
    "italic":   "\033[3m",
    "ul":       "\033[4m",
    # warna teks
    "black":    "\033[30m",
    "red":      "\033[91m",
    "green":    "\033[92m",
    "yellow":   "\033[93m",
    "blue":     "\033[94m",
    "magenta":  "\033[95m",
    "cyan":     "\033[96m",
    "white":    "\033[97m",
    "gray":     "\033[90m",
    # warna background
    "bg_black":  "\033[40m",
    "bg_red":    "\033[41m",
    "bg_green":  "\033[42m",
    "bg_yellow": "\033[43m",
    "bg_blue":   "\033[44m",
    "bg_magenta":"\033[45m",
    "bg_cyan":   "\033[46m",
    "bg_white":  "\033[47m",
    "bg_dark":   "\033[48;5;234m",
    "bg_navy":   "\033[48;5;17m",
    "bg_teal":   "\033[48;5;23m",
    "bg_olive":  "\033[48;5;58m",
    "bg_ok":     "\033[48;5;22m",
    "bg_err":    "\033[48;5;52m",
    "bg_warn":   "\033[48;5;58m",
    "bg_info":   "\033[48;5;17m",
}

# ── logo ASCII art ────────────────────────────────────────────
_LOGO = r"""
    ___ _      _   _              
   | __| |___ | |_| |_ _ _ ___   
   | _|| / -_)| / /  _| '_/ _ \  
   |___|_\___||_\_\\__|_| \___/  
        W  A  L  L  E  T          
""".strip("\n")

# ═══════════════════════════════════════════════════════════════
#  EFEK SUARA — pakai file WAV sistem Windows agar lebih keras
#  Fallback: winsound.Beep() jika file tidak ditemukan
# ═══════════════════════════════════════════════════════════════
_MEDIA = "C:\\Windows\\Media\\"

_WAV: dict[str, str] = {
    "ok":      _MEDIA + "Windows Foreground.wav",
    "error":   _MEDIA + "Windows Critical Stop.wav",
    "warn":    _MEDIA + "Windows Exclamation.wav",
    "info":    _MEDIA + "Windows Notify.wav",
    "startup": _MEDIA + "Windows Logon.wav",
    "logout":  _MEDIA + "Windows Logoff Sound.wav",
}

def _play(key: str) -> None:
    """Putar file WAV di thread terpisah (non-blocking).
    Jika file tidak ada, fallback ke Beep."""
    if not _HAS_WINSOUND:
        return
    path = _WAV.get(key, "")
    def _run():
        if path and os.path.exists(path):
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            # fallback Beep per jenis
            _FALLBACK = {
                "ok":      [(880,120),(1175,180)],
                "error":   [(440,180),(300,220)],
                "warn":    [(550,200)],
                "info":    [(660,100)],
                "startup": [(523,90),(659,90),(784,90),(1047,90)],
                "logout":  [(784,90),(523,130)],
            }
            for freq, ms in _FALLBACK.get(key, []):
                winsound.Beep(freq, ms)
    threading.Thread(target=_run, daemon=True).start()

def sound_ok()      -> None: _play("ok")
def sound_error()   -> None: _play("error")
def sound_info()    -> None: _play("info")
def sound_startup() -> None: _play("startup")
def sound_logout()  -> None: _play("logout")

# warn dipanggil sinkron karena sering diikuti teks penting
def sound_warn() -> None:
    if not _HAS_WINSOUND:
        return
    path = _WAV["warn"]
    if os.path.exists(path):
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    elif _HAS_WINSOUND:
        threading.Thread(target=lambda: winsound.Beep(550, 200), daemon=True).start()


# ═══════════════════════════════════════════════════════════════
#  KELAS UI UTAMA
# ═══════════════════════════════════════════════════════════════
class UI:
    def __init__(self) -> None:
        self.color = sys.stdout.isatty()
        if os.name == "nt":
            os.system("")           # aktifkan escape ANSI di Windows 10+
        # deteksi apakah terminal mendukung UTF-8
        enc = (sys.stdout.encoding or "ascii").lower()
        self._utf8 = "utf" in enc or "cp65001" in enc

    # ── primitif I/O ─────────────────────────────────────────
    def ask(self, prompt: str = "") -> str:
        return input(self.c(prompt, "dim"))

    def secret(self, prompt: str = "") -> str:
        """Input tersembunyi; tampilkan '*' cyan per karakter di Windows."""
        if os.name != "nt" or msvcrt is None or not sys.stdin.isatty():
            return getpass.getpass(self.c(prompt, "dim"))
        print(self.c(prompt, "dim"), end="", flush=True)
        chars: list[str] = []
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                print(); return "".join(chars)
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch in ("\b", "\x7f"):
                if chars:
                    chars.pop(); print("\b \b", end="", flush=True)
            elif ch.isprintable():
                chars.append(ch)
                print(self.c("●", "cyan"), end="", flush=True)

    def say(self, text: str = "") -> None:
        print(text)

    def clear(self) -> None:
        if sys.stdout.isatty():
            print("\033[2J\033[H", end="", flush=True)

    def pause(self) -> None:
        input(self.c("\n  Tekan [Enter] untuk melanjutkan…  ", "dim"))

    # ── pewarnaan ─────────────────────────────────────────────
    def c(self, text: str, *codes: str) -> str:
        """Terapkan kode ANSI. Jika terminal tidak berwarna, kembalikan teks asli."""
        if not self.color:
            return text
        prefix = "".join(_C.get(k, "") for k in codes)
        return f"{prefix}{text}{_C['reset']}"

    def _u(self, uni: str, fallback: str) -> str:
        """Kembalikan karakter Unicode jika terminal mendukung, fallback ke ASCII."""
        return uni if self._utf8 else fallback

    # ── spinner loading ───────────────────────────────────────
    def loading(self, label: str = "Memproses", duration: float = 0.7) -> None:
        """Spinner Braille non-blocking selama `duration` detik, lalu hapus baris."""
        if not sys.stdout.isatty():
            return
        frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        end_t = time.time() + duration
        i = 0
        while time.time() < end_t:
            f = self.c(frames[i % len(frames)], "cyan", "bold")
            lbl = self.c(f"  {label}…", "dim")
            print(f"\r  {f}{lbl}", end="", flush=True)
            time.sleep(0.075)
            i += 1
        print("\r" + " " * (len(label) + 10) + "\r", end="", flush=True)

    # ── splash screen (startup) ───────────────────────────────
    def splash(self) -> None:
        """Tampilkan logo ASCII art saat pertama kali dibuka (sekali saja)."""
        self.clear()
        for line in _LOGO.splitlines():
            self.say(self.c(line, "cyan", "bold"))
        self.say()
        tagline = self.c("  Dompet Digital Simulasi  ·  v2.0", "dim")
        self.say(tagline)
        self.say()
        time.sleep(0.3)

    def header_logo(self, title: str, subtitle: str = "") -> None:
        """Header dengan logo ASCII art — dipakai di layar awal (menu utama, login, register).
        Layar dalam pakai header() biasa yang menampilkan brand ⚡ ELEKTRO WALLET."""
        self.clear()
        for line in _LOGO.splitlines():
            self.say(self.c(line, "cyan", "bold"))
        self.say()

        tl = self._u("╔", "+"); tr = self._u("╗", "+")
        bl = self._u("╚", "+"); br = self._u("╝", "+")
        ml = self._u("╠", "+"); mr = self._u("╣", "+")
        hz = self._u("═", "=")

        top = tl + hz * INNER + tr
        sep = ml + hz * INNER + mr
        bot = bl + hz * INNER + br

        title_line = f"  {title.upper()}".ljust(INNER)
        self.say(self.c(top, "cyan", "bold"))
        self.say(self.c("║", "cyan", "bold") +
                 self.c(title_line, "white", "bold") +
                 self.c("║", "cyan", "bold"))
        if subtitle:
            sub_line = f"  {subtitle}".ljust(INNER)
            self.say(self.c(sep, "cyan"))
            self.say(self.c("║", "cyan") +
                     self.c(sub_line, "dim") +
                     self.c("║", "cyan"))
        self.say(self.c(bot, "cyan"))
        self.say()

    # ── HEADER ───────────────────────────────────────────────
    def header(self, title: str, subtitle: str = "") -> None:
        """Header utama tiap layar dengan border ganda dan branding."""
        self.clear()

        tl = self._u("╔", "+"); tr = self._u("╗", "+")
        bl = self._u("╚", "+"); br = self._u("╝", "+")
        ml = self._u("╠", "+"); mr = self._u("╣", "+")
        hz = self._u("═", "=")

        top  = tl + hz * INNER + tr
        sep  = ml + hz * INNER + mr
        bot  = bl + hz * INNER + br

        brand = self._u("⚡", "*") + "  ELEKTRO WALLET"
        brand_pad = brand.center(INNER)

        self.say(self.c(top, "cyan", "bold"))
        self.say(self.c("║", "cyan", "bold") +
                 self.c(brand_pad, "cyan", "bold") +
                 self.c("║", "cyan", "bold"))
        self.say(self.c(sep, "cyan"))

        # baris judul — isi rata kiri dengan padding
        title_line = f"  {title.upper()}"
        padded = title_line.ljust(INNER)
        self.say(self.c("║", "cyan") +
                 self.c(padded, "white", "bold") +
                 self.c("║", "cyan"))

        if subtitle:
            sub_line = f"  {subtitle}".ljust(INNER)
            self.say(self.c("║", "cyan") +
                     self.c(sub_line, "dim") +
                     self.c("║", "cyan"))

        self.say(self.c(bot, "cyan"))
        self.say()

    # ── PANEL (kotak info ringan) ─────────────────────────────
    def panel(self, lines: list[str], color: str = "cyan") -> None:
        """Kotak teks sederhana dengan border tipis."""
        tl = self._u("┌", "+"); tr = self._u("┐", "+")
        bl = self._u("└", "+"); br = self._u("┘", "+")
        hz = self._u("─", "-"); vt = self._u("│", "|")

        w = max(len(l) for l in lines) + 4
        self.say(self.c(f"  {tl}{hz*(w-2)}{tr}", color))
        for line in lines:
            inner_line = f" {line} ".ljust(w - 2)
            self.say(self.c(f"  {vt}", color) +
                     self.c(inner_line, "white") +
                     self.c(vt, color))
        self.say(self.c(f"  {bl}{hz*(w-2)}{br}", color))

    # ── SECTION TITLE ─────────────────────────────────────────
    def section(self, title: str) -> None:
        """Sub-judul di dalam layar — garis sisi kiri berwarna."""
        bar = self.c(self._u("▎", "|"), "cyan", "bold")
        self.say(f"  {bar}  {self.c(title, 'cyan', 'bold')}")
        self.say(self.c("  " + self._u("╌", "-") * (WIDTH - 4), "dim"))

    def rule(self, char: str = "─") -> None:
        self.say(self.c("  " + self._u(char, "-") * (WIDTH - 4), "dim"))

    # ── KV & MONEY ───────────────────────────────────────────
    def kv(self, label: str, value, width: int = 20) -> None:
        arrow = self._u("›", ">")
        lbl = self.c(f"{label:<{width}}", "gray")
        val = self.c(str(value), "white")
        self.say(f"  {lbl}  {self.c(arrow,'dim')}  {val}")

    def kv_money(self, label: str, value: str, width: int = 20) -> None:
        """Nominal uang — kuning tebal dengan ikon koin."""
        arrow = self._u("›", ">")
        coin  = self._u("◈", "$")
        lbl = self.c(f"{label:<{width}}", "gray")
        val = self.c(str(value), "yellow", "bold")
        self.say(f"  {lbl}  {self.c(arrow,'dim')}  {self.c(coin,'yellow')} {val}")

    def kv_status(self, label: str, value: str, good: bool, width: int = 20) -> None:
        """KV dengan nilai berwarna hijau/merah sesuai kondisi."""
        arrow = self._u("›", ">")
        lbl = self.c(f"{label:<{width}}", "gray")
        col = "green" if good else "red"
        ico = self._u("●", "*")
        val = self.c(f"{ico} {value}", col)
        self.say(f"  {lbl}  {self.c(arrow,'dim')}  {val}")

    # ── PESAN STATUS ──────────────────────────────────────────
    def ok(self, text: str) -> None:
        sound_ok()
        ico   = self._u("✔", "OK")
        badge = self.c(f" {ico} BERHASIL ", "white", "bold", "bg_ok")
        self.say(f"\n  {badge}  {self.c(text, 'green')}\n")

    def error(self, text: str) -> None:
        sound_error()
        ico   = self._u("✖", "!!")
        badge = self.c(f" {ico} GAGAL ", "white", "bold", "bg_err")
        self.say(f"\n  {badge}  {self.c(text, 'red')}\n")

    def warn(self, text: str) -> None:
        sound_warn()
        ico   = self._u("⚠", "!")
        badge = self.c(f" {ico} PERINGATAN ", "white", "bold", "bg_warn")
        self.say(f"\n  {badge}  {self.c(text, 'yellow')}\n")

    def info(self, text: str) -> None:
        ico = self._u("ℹ", "i")
        self.say(f"  {self.c(ico, 'blue')}  {self.c(text, 'dim')}")

    # ── MENU ITEM ─────────────────────────────────────────────
    def menu_item(self, key: str, label: str, icon: str = "·",
                  hint: str = "") -> None:
        """Satu baris menu: [ nomor ] ikon  Label  hint."""
        num_box = self.c(f"[{key:>2}]", "cyan", "bold")
        ico_str = self.c(self._u(icon, "-"), "cyan")
        lbl_str = self.c(label, "white")
        if hint:
            hint_str = self.c(f"  {hint}", "dim")
            self.say(f"  {num_box}  {ico_str}  {lbl_str}{hint_str}")
        else:
            self.say(f"  {num_box}  {ico_str}  {lbl_str}")

    # ── TABEL ─────────────────────────────────────────────────
    def table(self, headers: list[str], rows: list[list],
              right: tuple[int, ...] = ()) -> None:
        """Tabel dengan header berwarna, zebra striping, kolom kanan rata."""
        text_rows = [[str(c) for c in row] for row in rows]
        widths = [len(h) for h in headers]
        for row in text_rows:
            widths = [max(w, len(c)) for w, c in zip(widths, row)]

        vt  = self._u("│", "|")
        tl  = self._u("┌", "+"); tr = self._u("┐", "+")
        ml  = self._u("├", "+"); mr = self._u("┤", "+")
        bl  = self._u("└", "+"); br = self._u("┘", "+")
        hz  = self._u("─", "-")
        cx  = self._u("┼", "+"); tx = self._u("┬", "+"); bx = self._u("┴", "+")

        col_sep   = hz * 2
        inner_sep = (col_sep + hz * 3).join(hz * w for w in widths)
        top_line  = f"  {tl}{hz}{inner_sep.replace(hz*3, hz+tx+hz)}{hz}{tr}"
        mid_line  = f"  {ml}{hz}{inner_sep.replace(hz*3, hz+cx+hz)}{hz}{mr}"
        bot_line  = f"  {bl}{hz}{inner_sep.replace(hz*3, hz+bx+hz)}{hz}{br}"

        def row_str(cells: list[str], header: bool = False,
                    zebra: bool = False) -> str:
            parts = []
            for i, cell in enumerate(cells):
                w = widths[i]
                padded = cell.rjust(w) if i in right else cell.ljust(w)
                if header:
                    parts.append(self.c(padded, "cyan", "bold"))
                elif zebra:
                    parts.append(self.c(padded, "white"))
                else:
                    parts.append(self.c(padded, "dim", "white"))
            sep = f" {self.c(vt, 'dim')} "
            return f"  {self.c(vt,'dim')} {sep.join(parts)} {self.c(vt,'dim')}"

        self.say(self.c(top_line, "dim"))
        self.say(row_str(headers, header=True))
        self.say(self.c(mid_line, "dim"))
        for idx, row in enumerate(text_rows):
            self.say(row_str(row, zebra=(idx % 2 == 0)))
        self.say(self.c(bot_line, "dim"))

    # ── RECEIPT BOX (struk transaksi) ─────────────────────────
    def receipt_box(self, title: str, lines: list[tuple[str, str]],
                    money_keys: tuple[str, ...] = ()) -> None:
        """Kotak struk dengan border ganda bernuansa emas."""
        tl = self._u("╔", "+"); tr = self._u("╗", "+")
        bl = self._u("╚", "+"); br = self._u("╝", "+")
        ml = self._u("╠", "+"); mr = self._u("╣", "+")
        hz = self._u("═", "="); vt = self._u("║", "|")
        thz= self._u("─", "-")

        inner = WIDTH - 6     # margin kiri-kanan masing-masing 3 spasi
        top  = f"   {tl}{hz * inner}{tr}"
        sep  = f"   {ml}{thz * inner}{mr}"
        bot  = f"   {bl}{hz * inner}{br}"

        def border(text: str) -> str:
            return self.c(f"   {vt} ", "yellow") + text + self.c(f" {vt}", "yellow")

        self.say(self.c(top, "yellow"))
        title_pad = title.center(inner - 2)
        self.say(self.c(f"   {vt}", "yellow") +
                 self.c(title_pad, "yellow", "bold") +
                 self.c(f"{vt}", "yellow"))
        self.say(self.c(sep, "yellow"))

        for label, value in lines:
            is_money = label in money_keys
            lbl_str  = self.c(f"{label:<18}", "dim")
            val_str  = self.c(value, "yellow", "bold") if is_money else self.c(value, "white")
            pad_len  = inner - 2 - 18 - 2 - len(value)
            pad      = " " * max(0, pad_len)
            self.say(self.c(f"   {vt} ", "yellow") +
                     lbl_str + "  " + val_str + pad +
                     self.c(f" {vt}", "yellow"))

        self.say(self.c(bot, "yellow"))
        self.say()

    # ── PROGRESS BAR ─────────────────────────────────────────
    def progress_bar(self, value: int, total: int, width: int = 24) -> str:
        pct    = value / total if total else 0
        filled = round(pct * width)
        full   = self._u("█", "#")
        empty  = self._u("░", "-")
        bar    = self.c(full * filled, "cyan") + self.c(empty * (width - filled), "dim")
        pct_str = self.c(f" {round(pct*100):>3}%", "white")
        return bar + pct_str

    # ── BADGE STATUS ──────────────────────────────────────────
    def status_badge(self, status: str) -> str:
        """Kembalikan badge berwarna untuk status transaksi/aduan."""
        mapping = {
            "BERHASIL":    ("bg_ok",   "white"),
            "GAGAL":       ("bg_err",  "white"),
            "OPEN":        ("bg_warn", "white"),
            "IN_PROGRESS": ("bg_info", "cyan"),
            "RESOLVED":    ("bg_ok",   "white"),
            "REJECTED":    ("bg_err",  "white"),
            "AKTIF":       ("bg_ok",   "white"),
            "BLOKIR":      ("bg_err",  "white"),
        }
        bg, fg = mapping.get(status.upper(), ("bg_dark", "dim"))
        return self.c(f" {status} ", fg, "bold", bg)

    # ── DETAIL BOX (detail aduan / info kompleks) ────────────
    def detail_box(self, title: str, fields: list[tuple[str, str]],
                   body_label: str = "", body_text: str = "",
                   footer_label: str = "", footer_text: str = "") -> None:
        """Kotak detail dengan border tipis berwarna biru."""
        tl = self._u("┌","+" ); tr = self._u("┐","+")
        bl = self._u("└","+");  br = self._u("┘","+")
        ml = self._u("├","+");  mr = self._u("┤","+")
        hz = self._u("─","-");  vt = self._u("│","|")

        inner = WIDTH - 6
        top = f"   {tl}{hz*inner}{tr}"
        sep = f"   {ml}{hz*inner}{mr}"
        bot = f"   {bl}{hz*inner}{br}"

        def vline(content: str) -> None:
            self.say(self.c(f"   {vt} ", "blue") +
                     content +
                     self.c(f" {vt}", "blue"))

        self.say(self.c(top, "blue"))
        vline(self.c(title.center(inner - 2), "cyan", "bold"))
        self.say(self.c(sep, "blue"))

        for label, value in fields:
            lbl = self.c(f"{label:<16}", "gray")
            val = self.c(value, "white")
            vline(f"{lbl}  {val}" + " " * max(0, inner - 2 - 16 - 2 - len(value)))

        if body_label and body_text:
            self.say(self.c(sep, "blue"))
            vline(self.c(f"{body_label}:", "gray"))
            # bungkus teks panjang
            for chunk in _wrap(body_text, inner - 4):
                vline("  " + self.c(chunk, "white"))

        if footer_label and footer_text:
            self.say(self.c(sep, "blue"))
            vline(self.c(f"{footer_label}:", "gray"))
            for chunk in _wrap(footer_text, inner - 4):
                vline("  " + self.c(chunk, "dim"))

        self.say(self.c(bot, "blue"))
        self.say()


# ═══════════════════════════════════════════════════════════════
#  UTILITAS TEKS
# ═══════════════════════════════════════════════════════════════
def _wrap(text: str, width: int) -> list[str]:
    """Pecah teks panjang menjadi baris-baris maksimal `width` karakter."""
    words  = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip()
    if current:
        lines.append(current)
    return lines or [""]


_THOUSANDS = re.compile(r"\d{1,3}(\.\d{3})+")


def normalize_amount_input(text: str) -> str:
    """Toleran terhadap format: 'Rp 50.000' → '50000'.
    Titik hanya dihapus jika berpola ribuan; '10.5' dibiarkan agar ditolak core."""
    cleaned = (text or "").strip()
    if cleaned.lower().startswith("rp"):
        cleaned = cleaned[2:]
    cleaned = cleaned.replace(" ", "")
    if _THOUSANDS.fullmatch(cleaned):
        cleaned = cleaned.replace(".", "")
    return cleaned
