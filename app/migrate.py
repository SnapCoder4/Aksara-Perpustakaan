"""Migrasi additive (idempotent, aman dijalankan berulang). Jalan di PostgreSQL dan SQLite.

Tidak ada data yang dihapus. Yang dilakukan:
  1. buat tabel yang belum ada (categories, settings, wishlist, notifications, dst.)
  2. ALTER TABLE ADD COLUMN untuk kolom baru di books, members, borrowings
  3. borrowings.librarian_id dibuat nullable (peminjaman mandiri anggota tidak punya petugas)
  4. isi nilai awal: jatuh_tempo, denda, kategori contoh, pengaturan default
"""
from datetime import date, timedelta
from sqlalchemy import inspect, text
from app.database import engine, Base
from app import models  # noqa: F401  (daftarkan semua model)

NEW_COLUMNS = {
    "books": [
        ("penerbit", "VARCHAR(100)"), ("isbn", "VARCHAR(20)"), ("tahun", "INTEGER"),
        ("sinopsis", "TEXT"), ("category_id", "INTEGER REFERENCES categories(id)"),
        ("cover_path", "VARCHAR(255)"), ("dibuat", "VARCHAR(20)"),
    ],
    "members": [
        ("email", "VARCHAR(120)"), ("password", "VARCHAR(255)"),
        ("status", "VARCHAR(20) DEFAULT 'Aktif'"), ("bergabung", "VARCHAR(20)"),
    ],
    "librarians": [
        ("role", "VARCHAR(20) NOT NULL DEFAULT 'admin'"), ("aktif", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ("must_change", "BOOLEAN NOT NULL DEFAULT FALSE"), ("dibuat", "VARCHAR(20)"),
    ],
    "borrowings": [("jatuh_tempo", "VARCHAR(20)"), ("denda", "INTEGER DEFAULT 0")],
}

DEFAULT_CATEGORIES = ["Sejarah", "Sastra", "Teknologi", "Sains", "Ekonomi", "Bahasa"]
SEED_BOOK_CATEGORY = {"BK001": "Teknologi", "BK002": "Teknologi", "BK003": "Teknologi"}
DEFAULT_SETTINGS = {"loan_days": "7", "fine_per_day": "1000", "max_loans": "3"}


def _cols(conn, table):
    return {c["name"]: c for c in inspect(conn).get_columns(table)}


def _make_librarian_nullable(conn):
    if engine.dialect.name != "sqlite":
        conn.execute(text("ALTER TABLE borrowings ALTER COLUMN librarian_id DROP NOT NULL"))
        return
    # SQLite tidak bisa ALTER COLUMN: rebuild tabel dalam satu transaksi
    conn.execute(text("""CREATE TABLE borrowings_new (
        id INTEGER PRIMARY KEY,
        kode_buku VARCHAR(20) NOT NULL REFERENCES books(kode_buku),
        id_member VARCHAR(20) NOT NULL REFERENCES members(id_member),
        librarian_id INTEGER REFERENCES librarians(id),
        tanggal_pinjam VARCHAR(20) NOT NULL,
        tanggal_kembali VARCHAR(20),
        status VARCHAR(20),
        jatuh_tempo VARCHAR(20),
        denda INTEGER DEFAULT 0)"""))
    conn.execute(text("""INSERT INTO borrowings_new
        (id,kode_buku,id_member,librarian_id,tanggal_pinjam,tanggal_kembali,status,jatuh_tempo,denda)
        SELECT id,kode_buku,id_member,librarian_id,tanggal_pinjam,tanggal_kembali,status,jatuh_tempo,denda
        FROM borrowings"""))
    conn.execute(text("DROP TABLE borrowings"))
    conn.execute(text("ALTER TABLE borrowings_new RENAME TO borrowings"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_borrowings_id ON borrowings(id)"))


# Index pencarian katalog (hanya PostgreSQL; SQLite tidak punya pg_trgm). Idempotent.
SEARCH_INDEXES = [
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE INDEX IF NOT EXISTS ix_books_judul_trgm   ON books USING gin (judul gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_books_penulis_trgm ON books USING gin (penulis gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_books_kode_trgm    ON books USING gin (kode_buku gin_trgm_ops)",  # admin: cari '%q%'
    "CREATE INDEX IF NOT EXISTS ix_books_isbn_trgm    ON books USING gin (isbn gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_books_isbn         ON books (isbn text_pattern_ops)",
    "CREATE INDEX IF NOT EXISTS ix_books_category     ON books (category_id)",
    "CREATE INDEX IF NOT EXISTS ix_books_dibuat       ON books (dibuat DESC NULLS LAST, kode_buku DESC)",
]


def search_indexes(conn):
    if conn.dialect.name == "postgresql":
        for sql in SEARCH_INDEXES:
            conn.execute(text(sql))


def run():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table, cols in NEW_COLUMNS.items():
            have = _cols(conn, table)
            for name, ddl in cols:
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

        if not _cols(conn, "borrowings")["librarian_id"]["nullable"]:
            _make_librarian_nullable(conn)

        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_members_email ON members(email) WHERE email IS NOT NULL"))
        conn.execute(text("""UPDATE librarians SET role = 'super_admin'
                             WHERE id = (SELECT MIN(id) FROM librarians)
                               AND NOT EXISTS (SELECT 1 FROM librarians WHERE role = 'super_admin')"""))
        conn.execute(text("UPDATE borrowings SET denda = 0 WHERE denda IS NULL"))
        conn.execute(text("UPDATE members SET status = 'Aktif' WHERE status IS NULL"))

        for bid, tp in conn.execute(text("SELECT id, tanggal_pinjam FROM borrowings WHERE jatuh_tempo IS NULL")).all():
            try:
                due = str(date.fromisoformat(tp) + timedelta(days=7))
            except ValueError:
                due = tp
            conn.execute(text("UPDATE borrowings SET jatuh_tempo = :d WHERE id = :i"), {"d": due, "i": bid})

        if not conn.execute(text("SELECT 1 FROM categories LIMIT 1")).first():
            for n in DEFAULT_CATEGORIES:
                conn.execute(text("INSERT INTO categories (nama) VALUES (:n)"), {"n": n})
        for kode, cat in SEED_BOOK_CATEGORY.items():
            conn.execute(text("""UPDATE books SET category_id = (SELECT id FROM categories WHERE nama = :c)
                                 WHERE kode_buku = :k AND category_id IS NULL"""), {"c": cat, "k": kode})
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute(text("""INSERT INTO settings (key, value)
                                 SELECT CAST(:k AS VARCHAR), CAST(:v AS VARCHAR) WHERE NOT EXISTS (SELECT 1 FROM settings WHERE key = CAST(:k AS VARCHAR))"""),
                         {"k": k, "v": v})
        search_indexes(conn)


if __name__ == "__main__":
    run()
    print("migrasi selesai")
