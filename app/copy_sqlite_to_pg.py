"""Salin data dari library.db (SQLite) ke database di DATABASE_URL (PostgreSQL).

    python -m app.copy_sqlite_to_pg [path/library.db]

- library.db dibuka read-only dan tidak diubah.
- Aman diulang: bila tabel tujuan sudah berisi data, skrip berhenti tanpa menyalin apa pun.
- Seluruh penyalinan terjadi dalam satu transaksi (gagal di tengah = tidak ada yang tersimpan).
"""
import sqlite3
import sys
from sqlalchemy import inspect, text
from app.database import engine
from app import migrate

SOURCE = sys.argv[1] if len(sys.argv) > 1 else "library.db"
# urutan memenuhi foreign key
TABLES = ["librarians", "categories", "books", "members", "borrowings", "settings", "wishlist", "notifications"]
SERIAL = {"librarians": "id", "categories": "id", "borrowings": "id", "wishlist": "id", "notifications": "id"}


def main():
    if engine.dialect.name == "sqlite":
        sys.exit("DATABASE_URL masih SQLite. Arahkan ke PostgreSQL di .env dulu.")
    migrate.run()  # pastikan tabel dan kolom tujuan lengkap
    src = sqlite3.connect(f"file:{SOURCE}?mode=ro", uri=True)
    src_tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    with engine.begin() as conn:
        for t in ("librarians", "books", "members", "borrowings"):
            if conn.execute(text(f"SELECT 1 FROM {t} LIMIT 1")).first():
                sys.exit(f"Tabel tujuan '{t}' sudah berisi data; tidak ada yang disalin.")
        # buang seed dari migrate.run() (kategori contoh) agar tidak bentrok dengan data sumber
        copied = {}
        for t in TABLES:
            if t not in src_tables:
                continue
            src_cols = [r[1] for r in src.execute(f"PRAGMA table_info({t})")]
            dst_cols = {c["name"] for c in inspect(conn).get_columns(t)}
            cols = [c for c in src_cols if c in dst_cols]
            rows = src.execute(f"SELECT {', '.join(cols)} FROM {t}").fetchall()
            if not rows:
                continue
            if t in ("categories", "settings"):
                conn.execute(text(f"DELETE FROM {t}"))
            conn.execute(text(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"),
                         [dict(zip(cols, r)) for r in rows])
            copied[t] = len(rows)
        for t, col in SERIAL.items():  # sinkronkan sequence setelah insert dengan id eksplisit
            conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{t}', '{col}'), "
                              f"COALESCE((SELECT MAX({col}) FROM {t}), 0) + 1, false)"))
    migrate.run()  # isi jatuh_tempo, kategori buku contoh, pengaturan default
    print("disalin:", copied)


if __name__ == "__main__":
    main()
