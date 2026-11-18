"""Jalankan console:  .venv\\Scripts\\python.exe -m console

Pengguna biasa memakai menu pengguna; akun ber-role ADMIN otomatis masuk ke menu admin."""
from console.user_cli import ConsoleApp
from core import db


def main() -> None:
    conn = db.connect()
    db.init_db(conn)
    try:
        ConsoleApp(conn).run()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
