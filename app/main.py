import mimetypes
import os
import secrets
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app import migrate, services
from app.paths import STATIC_DIR
from app.auth import hash_password
from app.core import Redirect, render
from app.database import SessionLocal, engine
from app.models import Book, Librarian, Member
from app.routers import account, admin, public

# Database baru (belum ada tabel) dibuat langsung. Database lama yang skemanya
# belum diperbarui TIDAK diubah otomatis: jalankan `python -m app.migrate`.
ON_VERCEL = bool(os.getenv("VERCEL"))  # serverless: tidak ada migrasi/seed otomatis tiap cold start
if not ON_VERCEL:
    _tables = inspect(engine).get_table_names()
    if "books" not in _tables:
        migrate.run()
    elif ("cover_path" not in {c["name"] for c in inspect(engine).get_columns("books")}
          or "role" not in {c["name"] for c in inspect(engine).get_columns("librarians")}):
        raise RuntimeError("Skema database belum dimigrasi. Backup library.db lalu jalankan: python -m app.migrate")

mimetypes.add_type("image/webp", ".webp")  # registri Windows bisa tidak mengenal webp

app = FastAPI(title="Aksara")

_secret = os.getenv("SESSION_SECRET")
if not _secret and ON_VERCEL:
    raise RuntimeError("SESSION_SECRET wajib diisi di Vercel (kunci acak per instance membuat login tidak stabil).")
if not _secret:
    print("PERINGATAN: SESSION_SECRET belum diset di .env; memakai kunci acak sementara (login hilang saat server restart).")
    _secret = secrets.token_hex(32)
app.add_middleware(SessionMiddleware, secret_key=_secret, session_cookie="library_session",
                   same_site="lax", max_age=60 * 60 * 24 * 7)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)  # tidak ada ikon .ico; cegah 404 berisik


def seed_data():
    """Data awal hanya bila tabel kosong (perilaku asli proyek)."""
    db = SessionLocal()
    if not db.query(Librarian).first():
        db.add(Librarian(username="admin", full_name="Petugas Utama", password=hash_password("admin123"), role="super_admin", dibuat=services.today()))
    if not db.query(Book).first():
        db.add_all([
            Book(kode_buku="BK001", judul="Clean Code", penulis="Robert C. Martin", stok=5),
            Book(kode_buku="BK002", judul="Python Crash Course", penulis="Eric Matthes", stok=3),
            Book(kode_buku="BK003", judul="Database System Concepts", penulis="Abraham Silberschatz", stok=4),
        ])
    if not db.query(Member).first():
        db.add_all([
            Member(id_member="MBR001", nama="Andi Saputra", no_hp="081234567890"),
            Member(id_member="MBR002", nama="Citra Lestari", no_hp="089876543210"),
        ])
    db.commit()
    db.close()


if not ON_VERCEL:
    seed_data()


@app.exception_handler(Redirect)
async def _redirect(request: Request, exc: Redirect):
    return RedirectResponse(exc.url, status_code=303)


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    try:
        if exc.status_code == 404:
            return render(request, "public/404.html", http_status=404)
        return render(request, "public/404.html", http_status=exc.status_code, message=str(exc.detail))
    except Exception:  # template/DB bermasalah: jangan ubah 404 menjadi 500
        return PlainTextResponse("Halaman tidak ditemukan" if exc.status_code == 404 else str(exc.detail),
                                 status_code=exc.status_code)


app.include_router(public.router)
app.include_router(account.router)
app.include_router(admin.router)
