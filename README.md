# Aksara: Aplikasi Perpustakaan

Aplikasi web perpustakaan (tugas UAS Web Dev Python). Anggota menelusuri katalog dan meminjam buku. Petugas mengelola koleksi, anggota, dan peminjaman lewat panel admin.

**Teknologi:** FastAPI, Jinja2, SQLAlchemy, PostgreSQL (SQLite untuk uji lokal), session cookie.

## Fitur
- Katalog publik dengan live search, filter kategori, dan wishlist
- Daftar dan login anggota; dashboard, riwayat pinjam, dan profil
- Panel admin: buku (live search), kategori, anggota, peminjaman dan pengembalian, denda, laporan, pengaturan, gambar hero

## Menjalankan lokal
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

copy .env.example .env          # lalu isi SESSION_SECRET dan DATABASE_URL
python -m app.migrate
uvicorn app.main:app --port 8000
```
Buka http://localhost:8000.

Tanpa `DATABASE_URL`, aplikasi memakai SQLite (`library.db`). Live search yang memakai index `pg_trgm` hanya aktif di PostgreSQL.

## Konfigurasi (`.env`)
| Variabel | Keterangan |
|---|---|
| `SESSION_SECRET` | Teks acak panjang untuk menandatangani session |
| `DATABASE_URL` | Contoh: `postgresql+psycopg://user:pass@localhost:5432/library_app` |

## Akun admin bawaan
Username `admin`, kata sandi `admin123`. **Ganti sebelum dipakai di server publik.**

## Opsional
`pip install -r requirements-optional.txt` mengaktifkan hapus latar gambar hero (rembg, berat). Aplikasi tetap berjalan tanpanya.

## Struktur
- `app/`: router (`routers/`), model, layanan, migrasi
- `templates/`: template Jinja
- `static/`: CSS, JS, upload sampul
