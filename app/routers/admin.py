import csv
import io
import logging
import re
from datetime import date
from math import ceil
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile
from app import hero, services
from app.auth import hash_password, verify_password
from app.core import Redirect, env, flash, get_db, render, require_admin
from app.database import SessionLocal
from app.models import Book, Borrowing, Category, Librarian, Member, Notification, Wishlist
from app.routers.account import check_password, validate_profile
from app.uploads import delete_cover, save_cover

router = APIRouter(prefix="/admin")
PER_PAGE = 10
LABEL = {"loan_days": "masa pinjam", "fine_per_day": "denda per hari", "max_loans": "maksimal pinjaman"}
KODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
ISBN_RE = re.compile(r"^[0-9Xx-]{0,20}$")


def paginate(query, page: int, per: int = PER_PAGE):
    total = query.count()
    pages = max(1, ceil(total / per))
    page = min(max(1, page), pages)
    return query.offset((page - 1) * per).limit(per).all(), page, pages, total


audit = logging.getLogger("uvicorn.error")


def _staff_now(request: Request):
    """Petugas dari database (bukan dari cookie): akun nonaktif/dihapus langsung kehilangan akses."""
    u = request.session.get("user")
    if not u or u.get("role") != "admin":
        return None
    with SessionLocal() as db:
        s = db.get(Librarian, u.get("id"))
        if s and s.aktif:
            db.expunge(s)
            return s
    return None


def guard(request: Request, pending_ok: bool = False) -> Librarian:
    require_admin(request)
    s = _staff_now(request)
    if not s:
        request.session.clear()
        raise Redirect("/login")
    if s.must_change and not pending_ok:
        flash(request, "Ganti kata sandi sementara Anda dulu di Pengaturan.", "warn")
        raise Redirect("/admin/pengaturan")
    return s


def super_guard(request: Request) -> Librarian:
    s = guard(request)
    if s.role != "super_admin":
        raise HTTPException(403, "Hanya super admin yang boleh melakukan ini.")
    return s


def same_origin(request: Request):
    """Tolak POST lintas-situs (tambahan di atas cookie SameSite=lax)."""
    o = request.headers.get("origin")
    if o and urlparse(o).netloc != request.headers.get("host"):
        raise HTTPException(403, "Permintaan ditolak.")


def pct(now: int, prev: int):
    return None if prev == 0 else round((now - prev) * 100 / prev)


# ---------- Dashboard ----------
@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db)):
    guard(request)
    months = services.monthly_activity(db)
    cur, prev = months[-1], months[-2]
    cats = services.category_loans(db)
    overdue = db.query(Borrowing).filter(Borrowing.status == "Dipinjam", Borrowing.jatuh_tempo < services.today()).count()
    recent = db.query(Borrowing).order_by(Borrowing.id.desc()).limit(5).all()
    peak = max([m["pinjam"] + m["kembali"] + m["telat"] for m in months] + [1])
    return render(request, "admin/dashboard.html", months=months, peak=peak, cur=cur,
                  d_pinjam=pct(cur["pinjam"], prev["pinjam"]), d_kembali=pct(cur["kembali"], prev["kembali"]),
                  members_active=db.query(Member).filter(Member.status == "Aktif").count(),
                  books_total=db.query(Book).count(), overdue=overdue, recent=recent,
                  segs=services.donut_segments(cats), cat_total=sum(v for _, v in cats),
                  top=services.popular_books(db, 5), active_menu="dashboard")


# ---------- Buku ----------
def book_form_data(form) -> dict:
    g = lambda k: (str(form.get(k) or "")).strip()
    return {"kode_buku": g("kode_buku"), "judul": g("judul"), "penulis": g("penulis"), "penerbit": g("penerbit"),
            "isbn": g("isbn"), "tahun": g("tahun"), "category_id": g("category_id"), "stok": g("stok"),
            "sinopsis": g("sinopsis")}


def validate_book(db: Session, d: dict, creating: bool) -> dict:
    e = {}
    if creating:
        if not KODE_RE.match(d["kode_buku"]):
            e["kode_buku"] = "Kode 1-20 karakter: huruf, angka, - atau _."
        elif db.get(Book, d["kode_buku"]):
            e["kode_buku"] = f"Kode {d['kode_buku']} sudah ada."
    if not d["judul"] or len(d["judul"]) > 150:
        e["judul"] = "Judul wajib diisi (maksimal 150 karakter)."
    if not d["penulis"] or len(d["penulis"]) > 100:
        e["penulis"] = "Penulis wajib diisi (maksimal 100 karakter)."
    if len(d["penerbit"]) > 100:
        e["penerbit"] = "Maksimal 100 karakter."
    if not ISBN_RE.match(d["isbn"]):
        e["isbn"] = "ISBN hanya boleh angka, X, dan tanda hubung."
    if d["tahun"] and not (d["tahun"].isdigit() and 1000 <= int(d["tahun"]) <= date.today().year + 1):
        e["tahun"] = "Tahun tidak valid."
    if not (d["stok"].isdigit() and int(d["stok"]) <= 100000):
        e["stok"] = "Stok harus angka 0 atau lebih."
    if len(d["sinopsis"]) > 3000:
        e["sinopsis"] = "Maksimal 3000 karakter."
    if d["category_id"] and not (d["category_id"].isdigit() and db.get(Category, int(d["category_id"]))):
        e["category_id"] = "Kategori tidak ditemukan."
    return e


@router.get("/buku")
def books(request: Request, q: str = "", page: int = 1, db: Session = Depends(get_db)):
    partial = request.headers.get("x-partial") == "1"   # live search: hanya tabel + jumlah
    if partial and (request.session.get("user") or {}).get("role") != "admin":
        return Response("Sesi berakhir. Masuk kembali sebagai admin.", 401)
    guard(request)
    query = db.query(Book).order_by(Book.kode_buku)
    q = q.strip()[:80]
    if q:
        query = query.filter(or_(Book.judul.icontains(q, autoescape=True), Book.penulis.icontains(q, autoescape=True),
                                 Book.kode_buku.icontains(q, autoescape=True), Book.isbn.icontains(q, autoescape=True)))
    rows, page, pages, total = paginate(query, page)
    if partial:
        html = env.get_template("admin/_books_results.html").render(request=request, books=rows, q=q, page=page,
                                                                    pages=pages, total=total)
        return HTMLResponse(html, headers={"Cache-Control": "no-store", "Vary": "X-Partial"})
    return render(request, "admin/books.html", books=rows, q=q, page=page, pages=pages, total=total, active_menu="buku")


def _form_page(request, db, *, book, form, errors, http_status=200):
    return render(request, "admin/book_form.html", http_status=http_status, book=book, form=form, errors=errors,
                  cats=db.query(Category).order_by(Category.nama).all(), active_menu="buku")


@router.get("/buku/tambah")
def book_new(request: Request, db: Session = Depends(get_db)):
    guard(request)
    return _form_page(request, db, book=None, form={"stok": "1"}, errors={})


@router.post("/buku/tambah")
async def book_create(request: Request, db: Session = Depends(get_db)):
    guard(request)
    form = await request.form()
    d = book_form_data(form)
    errors = validate_book(db, d, creating=True)
    cover = form.get("cover")
    cover_name = None
    if isinstance(cover, UploadFile) and cover.filename and not errors.get("cover"):
        try:
            cover_name = await save_cover(cover)
        except ValueError as ex:
            errors["cover"] = str(ex)
    if errors:
        delete_cover(cover_name)
        return _form_page(request, db, book=None, form=d, errors=errors, http_status=400)
    db.add(Book(kode_buku=d["kode_buku"], judul=d["judul"], penulis=d["penulis"], penerbit=d["penerbit"] or None,
                isbn=d["isbn"] or None, tahun=int(d["tahun"]) if d["tahun"] else None, sinopsis=d["sinopsis"] or None,
                category_id=int(d["category_id"]) if d["category_id"] else None, stok=int(d["stok"]),
                cover_path=cover_name, dibuat=services.today()))
    db.commit()
    flash(request, f"Buku \"{d['judul']}\" ditambahkan.")
    return RedirectResponse("/admin/buku", 303)


@router.get("/buku/{kode}/edit")
def book_edit(request: Request, kode: str, db: Session = Depends(get_db)):
    guard(request)
    b = db.get(Book, kode)
    if not b:
        return render(request, "public/404.html", http_status=404)
    form = {"kode_buku": b.kode_buku, "judul": b.judul, "penulis": b.penulis, "penerbit": b.penerbit or "",
            "isbn": b.isbn or "", "tahun": b.tahun or "", "category_id": str(b.category_id or ""),
            "stok": str(b.stok), "sinopsis": b.sinopsis or ""}
    return _form_page(request, db, book=b, form=form, errors={})


@router.post("/buku/{kode}/edit")
async def book_update(request: Request, kode: str, db: Session = Depends(get_db)):
    guard(request)
    b = db.get(Book, kode)
    if not b:
        return render(request, "public/404.html", http_status=404)
    form = await request.form()
    d = book_form_data(form)
    d["kode_buku"] = kode
    errors = validate_book(db, d, creating=False)
    cover = form.get("cover")
    new_cover = None
    if isinstance(cover, UploadFile) and cover.filename:
        try:
            new_cover = await save_cover(cover)
        except ValueError as ex:
            errors["cover"] = str(ex)
    if errors:
        delete_cover(new_cover)
        return _form_page(request, db, book=b, form=d, errors=errors, http_status=400)
    old_cover = b.cover_path
    b.judul, b.penulis, b.penerbit, b.isbn = d["judul"], d["penulis"], d["penerbit"] or None, d["isbn"] or None
    b.tahun = int(d["tahun"]) if d["tahun"] else None
    b.sinopsis = d["sinopsis"] or None
    b.category_id = int(d["category_id"]) if d["category_id"] else None
    b.stok = int(d["stok"])
    if new_cover:
        b.cover_path = new_cover
    elif form.get("hapus_cover") == "1":
        b.cover_path = None
    db.commit()
    if b.cover_path != old_cover:
        delete_cover(old_cover)
    flash(request, "Buku diperbarui.")
    return RedirectResponse("/admin/buku", 303)


@router.post("/buku/{kode}/hapus")
def book_delete(request: Request, kode: str, db: Session = Depends(get_db)):
    guard(request)
    b = db.get(Book, kode)
    if b:
        if db.query(Borrowing).filter_by(kode_buku=kode).first():
            flash(request, "Buku punya riwayat peminjaman, tidak bisa dihapus. Set stok ke 0 bila tidak dipinjamkan lagi.", "err")
        else:
            cover = b.cover_path
            db.query(Wishlist).filter_by(kode_buku=kode).delete()
            db.delete(b)
            db.commit()
            delete_cover(cover)
            flash(request, "Buku dihapus.")
    return RedirectResponse("/admin/buku", 303)


# ---------- Gambar hero beranda ----------
@router.get("/hero")
def hero_page(request: Request, db: Session = Depends(get_db)):
    guard(request)
    return render(request, "admin/hero.html", slots=list(zip(hero.SLOTS, hero.hero_images(db))), rembg_ok=hero.rembg_available(), active_menu="hero")


def _wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def _hero_api_denied(request: Request):
    """Pengecekan untuk panggilan fetch (editor di beranda). Mengembalikan JSONResponse bila ditolak.
    CSRF: cookie sesi SameSite=lax + header kustom (tidak bisa dikirim lintas-situs tanpa CORS) + cek Origin."""
    user = request.session.get("user")
    if not user:
        return JSONResponse({"ok": False, "error": "Sesi berakhir. Masuk kembali sebagai admin."}, 401)
    if user.get("role") != "admin" or not _staff_now(request):
        return JSONResponse({"ok": False, "error": "Hanya admin yang boleh mengubah gambar hero."}, 403)
    origin = request.headers.get("origin")
    if request.headers.get("x-requested-with") != "fetch" or (origin and urlparse(origin).netloc != request.headers.get("host")):
        return JSONResponse({"ok": False, "error": "Permintaan ditolak."}, 403)
    return None


@router.post("/hero/preview")
async def hero_preview(request: Request):
    if (denied := _hero_api_denied(request)):
        return denied
    f = (await request.form()).get("gambar")
    if not (isinstance(f, UploadFile) and f.filename):
        return JSONResponse({"ok": False, "error": "Pilih gambar terlebih dahulu."}, 400)
    try:
        return Response(await hero.preview_hero(f), media_type="image/png", headers={"Cache-Control": "no-store"})
    except ValueError as ex:
        return JSONResponse({"ok": False, "error": str(ex)}, 422)


@router.post("/hero/{n}")
async def hero_save(request: Request, n: int, db: Session = Depends(get_db)):
    api = _wants_json(request)
    if api and (denied := _hero_api_denied(request)):
        return denied
    if not api:
        guard(request)
    form = await request.form()
    f = form.get("gambar")
    note = err = None
    if not (isinstance(f, UploadFile) and f.filename):
        err = "Pilih gambar terlebih dahulu."
    else:
        try:
            note = await hero.save_hero(n, f, form.get("hapus_latar") == "1", db)
        except ValueError as ex:
            err = str(ex)
    if api:
        if err:
            return JSONResponse({"ok": False, "error": err}, 422)
        return {"ok": True, "url": hero.hero_images(db)[n - 1], "note": note}
    if err:
        flash(request, err, "err")
    elif note:
        flash(request, f"Gambar hero {n} disimpan. {note}", "warn")
    else:
        flash(request, f"Gambar hero {n} diperbarui.")
    return RedirectResponse("/admin/hero", 303)


@router.post("/hero/{n}/hapus")
def hero_delete(request: Request, n: int, db: Session = Depends(get_db)):
    api = _wants_json(request)
    if api and (denied := _hero_api_denied(request)):
        return denied
    if not api:
        guard(request)
    hero.delete_hero(n, db)
    if api:
        return {"ok": True, "url": None}
    flash(request, f"Gambar hero {n} dihapus; beranda memakai sampul gradasi.")
    return RedirectResponse("/admin/hero", 303)


# ---------- Kategori ----------
@router.get("/kategori")
def categories(request: Request, db: Session = Depends(get_db)):
    guard(request)
    rows = (db.query(Category, func.count(Book.kode_buku)).outerjoin(Book, Book.category_id == Category.id)
              .group_by(Category.id).order_by(Category.nama).all())
    return render(request, "admin/categories.html", rows=rows, active_menu="kategori")


def _cat_name(db, nama: str, own_id: int | None = None):
    nama = nama.strip()
    if not (1 <= len(nama) <= 60):
        return None, "Nama kategori wajib diisi (maksimal 60 karakter)."
    q = db.query(Category).filter(func.lower(Category.nama) == nama.lower())
    if own_id:
        q = q.filter(Category.id != own_id)
    if q.first():
        return None, "Kategori sudah ada."
    return nama, None


@router.post("/kategori/tambah")
def category_create(request: Request, nama: str = Form(""), db: Session = Depends(get_db)):
    guard(request)
    n, err = _cat_name(db, nama)
    if err:
        flash(request, err, "err")
    else:
        db.add(Category(nama=n))
        db.commit()
        flash(request, "Kategori ditambahkan.")
    return RedirectResponse("/admin/kategori", 303)


@router.post("/kategori/{cid}/ubah")
def category_update(request: Request, cid: int, nama: str = Form(""), db: Session = Depends(get_db)):
    guard(request)
    c = db.get(Category, cid)
    n, err = _cat_name(db, nama, cid)
    if c and err:
        flash(request, err, "err")
    elif c:
        c.nama = n
        db.commit()
        flash(request, "Kategori diperbarui.")
    return RedirectResponse("/admin/kategori", 303)


@router.post("/kategori/{cid}/hapus")
def category_delete(request: Request, cid: int, db: Session = Depends(get_db)):
    guard(request)
    c = db.get(Category, cid)
    if c:
        if db.query(Book).filter_by(category_id=cid).first():
            flash(request, "Kategori masih dipakai buku, tidak bisa dihapus.", "err")
        else:
            db.delete(c)
            db.commit()
            flash(request, "Kategori dihapus.")
    return RedirectResponse("/admin/kategori", 303)


# ---------- Anggota ----------
def _member_form(request, *, member, form, errors, http_status=200):
    return render(request, "admin/member_form.html", http_status=http_status, member=member, form=form, errors=errors,
                  active_menu="anggota")


@router.get("/anggota")
def members(request: Request, q: str = "", page: int = 1, db: Session = Depends(get_db)):
    guard(request)
    query = db.query(Member).order_by(Member.id_member)
    q = q.strip()[:80]
    if q:
        query = query.filter(or_(Member.nama.icontains(q, autoescape=True), Member.id_member.icontains(q, autoescape=True),
                                 Member.email.icontains(q, autoescape=True)))
    rows, page, pages, total = paginate(query, page)
    active = dict(db.query(Borrowing.id_member, func.count(Borrowing.id)).filter(Borrowing.status == "Dipinjam")
                    .group_by(Borrowing.id_member).all())
    return render(request, "admin/members.html", members=rows, active=active, q=q, page=page, pages=pages,
                  total=total, active_menu="anggota")


@router.get("/anggota/tambah")
def member_new(request: Request, db: Session = Depends(get_db)):
    guard(request)
    return _member_form(request, member=None, form={"id_member": services.next_member_id(db), "status": "Aktif"}, errors={})


@router.post("/anggota/tambah")
def member_create(request: Request, id_member: str = Form(""), nama: str = Form(""), no_hp: str = Form(""),
                  email: str = Form(""), status: str = Form("Aktif"), password: str = Form(""),
                  db: Session = Depends(get_db)):
    guard(request)
    form = {"id_member": id_member.strip(), "nama": nama.strip(), "no_hp": no_hp.strip(),
            "email": email.strip().lower(), "status": status}
    errors = validate_profile(db, form)
    if not KODE_RE.match(form["id_member"]):
        errors["id_member"] = "ID 1-20 karakter: huruf, angka, - atau _."
    elif db.get(Member, form["id_member"]):
        errors["id_member"] = f"ID {form['id_member']} sudah terdaftar."
    if password and (e := check_password(password)):
        errors["password"] = e
    if errors:
        return _member_form(request, member=None, form=form, errors=errors, http_status=400)
    db.add(Member(id_member=form["id_member"], nama=form["nama"], no_hp=form["no_hp"], email=form["email"],
                  status="Nonaktif" if status == "Nonaktif" else "Aktif",
                  password=hash_password(password) if password else None, bergabung=services.today()))
    db.commit()
    flash(request, "Anggota ditambahkan.")
    return RedirectResponse("/admin/anggota", 303)


@router.get("/anggota/{idm}/edit")
def member_edit(request: Request, idm: str, db: Session = Depends(get_db)):
    guard(request)
    m = db.get(Member, idm)
    if not m:
        return render(request, "public/404.html", http_status=404)
    return _member_form(request, member=m, errors={},
                        form={"id_member": m.id_member, "nama": m.nama, "no_hp": m.no_hp, "email": m.email or "",
                              "status": m.status or "Aktif"})


@router.post("/anggota/{idm}/edit")
def member_update(request: Request, idm: str, nama: str = Form(""), no_hp: str = Form(""), email: str = Form(""),
                  status: str = Form("Aktif"), password: str = Form(""), db: Session = Depends(get_db)):
    guard(request)
    m = db.get(Member, idm)
    if not m:
        return render(request, "public/404.html", http_status=404)
    form = {"id_member": idm, "nama": nama.strip(), "no_hp": no_hp.strip(), "email": email.strip().lower(), "status": status}
    errors = validate_profile(db, form, own_id=idm)
    if password and (e := check_password(password)):
        errors["password"] = e
    if errors:
        return _member_form(request, member=m, form=form, errors=errors, http_status=400)
    m.nama, m.no_hp, m.email = form["nama"], form["no_hp"], form["email"]
    m.status = "Nonaktif" if status == "Nonaktif" else "Aktif"
    if password:
        m.password = hash_password(password)
    db.commit()
    flash(request, "Anggota diperbarui.")
    return RedirectResponse("/admin/anggota", 303)


@router.post("/anggota/{idm}/hapus")
def member_delete(request: Request, idm: str, db: Session = Depends(get_db)):
    guard(request)
    m = db.get(Member, idm)
    if m:
        if db.query(Borrowing).filter_by(id_member=idm).first():
            flash(request, "Anggota punya riwayat peminjaman, tidak bisa dihapus. Ubah status menjadi Nonaktif.", "err")
        else:
            db.query(Wishlist).filter_by(id_member=idm).delete()
            db.query(Notification).filter_by(id_member=idm).delete()
            db.delete(m)
            db.commit()
            flash(request, "Anggota dihapus.")
    return RedirectResponse("/admin/anggota", 303)


# ---------- Peminjaman & pengembalian ----------
@router.get("/peminjaman")
def loans(request: Request, status: str = "", page: int = 1, db: Session = Depends(get_db)):
    guard(request)
    query = db.query(Borrowing).order_by(Borrowing.id.desc())
    if status == "Terlambat":
        query = query.filter(Borrowing.status == "Dipinjam", Borrowing.jatuh_tempo < services.today())
    elif status in ("Dipinjam", "Dikembalikan"):
        query = query.filter(Borrowing.status == status)
    rows, page, pages, total = paginate(query, page)
    return render(request, "admin/loans.html", loans=rows, status=status, page=page, pages=pages, total=total,
                  settings=services.get_settings(db), active_menu="peminjaman")


@router.get("/peminjaman/baru")
def loan_new(request: Request, db: Session = Depends(get_db)):
    guard(request)
    return render(request, "admin/loan_form.html", books=db.query(Book).filter(Book.stok > 0).order_by(Book.judul).all(),
                  members=db.query(Member).filter(Member.status == "Aktif").order_by(Member.nama).all(),
                  today=services.today(), active_menu="peminjaman")


@router.post("/peminjaman/baru")
def loan_create(request: Request, kode_buku: str = Form(""), id_member: str = Form(""),
                tanggal_pinjam: str = Form(""), db: Session = Depends(get_db)):
    user = guard(request)
    try:
        services.create_loan(db, db.get(Book, kode_buku), db.get(Member, id_member), user["id"], tanggal_pinjam or None)
        db.commit()
        flash(request, "Peminjaman dicatat.")
    except ValueError as e:
        db.rollback()
        flash(request, str(e), "err")
        return RedirectResponse("/admin/peminjaman/baru", 303)
    return RedirectResponse("/admin/peminjaman", 303)


@router.post("/peminjaman/{lid}/kembali")
def loan_return(request: Request, lid: int, db: Session = Depends(get_db)):
    guard(request)
    loan = db.get(Borrowing, lid)
    if loan and loan.status == "Dipinjam":
        fine = services.return_loan(db, loan)
        db.commit()
        flash(request, "Buku dikembalikan." + (f" Denda: {fine:,}".replace(",", ".") if fine else ""))
    return RedirectResponse("/admin/peminjaman", 303)


@router.post("/peminjaman/{lid}/hapus")
def loan_delete(request: Request, lid: int, db: Session = Depends(get_db)):
    guard(request)
    loan = db.get(Borrowing, lid)
    if loan:
        if loan.status == "Dipinjam" and loan.book:
            loan.book.stok += 1
        db.delete(loan)
        db.commit()
        flash(request, "Transaksi dihapus.")
    return RedirectResponse("/admin/peminjaman", 303)


# ---------- Laporan ----------
def _range(dari: str, sampai: str):
    try:
        a = date.fromisoformat(dari)
    except ValueError:
        a = date.today().replace(day=1)
    try:
        b = date.fromisoformat(sampai)
    except ValueError:
        b = date.today()
    return str(a), str(b)


@router.get("/laporan")
def reports(request: Request, dari: str = "", sampai: str = "", db: Session = Depends(get_db)):
    guard(request)
    a, b = _range(dari, sampai)
    out = db.query(Borrowing).filter(Borrowing.tanggal_pinjam >= a, Borrowing.tanggal_pinjam <= b)
    ret = db.query(Borrowing).filter(Borrowing.tanggal_kembali >= a, Borrowing.tanggal_kembali <= b)
    top_books = (db.query(Book.judul, Book.penulis, func.count(Borrowing.id)).join(Borrowing, Borrowing.kode_buku == Book.kode_buku)
                   .filter(Borrowing.tanggal_pinjam >= a, Borrowing.tanggal_pinjam <= b)
                   .group_by(Book.kode_buku).order_by(func.count(Borrowing.id).desc()).limit(5).all())
    top_members = (db.query(Member.nama, Member.id_member, func.count(Borrowing.id)).join(Borrowing, Borrowing.id_member == Member.id_member)
                     .filter(Borrowing.tanggal_pinjam >= a, Borrowing.tanggal_pinjam <= b)
                     .group_by(Member.id_member).order_by(func.count(Borrowing.id).desc()).limit(5).all())
    overdue = (db.query(Borrowing).filter(Borrowing.status == "Dipinjam", Borrowing.jatuh_tempo < services.today())
                 .order_by(Borrowing.jatuh_tempo).all())
    fines = db.query(func.coalesce(func.sum(Borrowing.denda), 0)).filter(Borrowing.tanggal_kembali >= a, Borrowing.tanggal_kembali <= b).scalar()
    return render(request, "admin/reports.html", dari=a, sampai=b, n_out=out.count(), n_ret=ret.count(), fines=fines,
                  top_books=top_books, top_members=top_members, overdue=overdue,
                  settings=services.get_settings(db), active_menu="laporan")


def _csv_safe(v):
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


@router.get("/laporan.csv")
def reports_csv(request: Request, dari: str = "", sampai: str = "", db: Session = Depends(get_db)):
    guard(request)
    a, b = _range(dari, sampai)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Kode buku", "Judul", "ID anggota", "Anggota", "Tanggal pinjam", "Jatuh tempo", "Tanggal kembali", "Status", "Denda"])
    for l in (db.query(Borrowing).filter(Borrowing.tanggal_pinjam >= a, Borrowing.tanggal_pinjam <= b)
                .order_by(Borrowing.tanggal_pinjam).all()):
        w.writerow([_csv_safe(x) for x in (l.id, l.kode_buku, l.book.judul if l.book else "", l.id_member,
                                           l.member.nama if l.member else "", l.tanggal_pinjam, l.jatuh_tempo,
                                           l.tanggal_kembali, services.loan_status(l), l.denda or 0)])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="laporan-{a}-{b}.csv"'})


# ---------- Pengaturan ----------
@router.get("/pengaturan")
def settings_page(request: Request, db: Session = Depends(get_db)):
    me = guard(request, pending_ok=True)
    staff = db.query(Librarian).order_by(Librarian.id).all() if me.role == "super_admin" else [db.get(Librarian, me.id)]
    return render(request, "admin/settings.html", settings=services.get_settings(db), staff=staff, me=me,
                  is_super=me.role == "super_admin", errors={}, active_menu="pengaturan")


@router.post("/pengaturan")
def settings_save(request: Request, loan_days: str = Form(""), fine_per_day: str = Form(""), max_loans: str = Form(""),
                  db: Session = Depends(get_db)):
    guard(request)
    vals = {"loan_days": (loan_days, 1, 90), "fine_per_day": (fine_per_day, 0, 1000000), "max_loans": (max_loans, 1, 50)}
    for k, (v, lo, hi) in vals.items():
        if not (v.isdigit() and lo <= int(v) <= hi):
            flash(request, f"Nilai {LABEL[k]} harus angka {lo}-{hi}.", "err")
            return RedirectResponse("/admin/pengaturan", 303)
    for k, (v, _, _) in vals.items():
        services.set_setting(db, k, int(v))
    db.commit()
    flash(request, "Pengaturan disimpan.")
    return RedirectResponse("/admin/pengaturan", 303)


def _back(request: Request, msg: str, kind: str = "ok"):
    flash(request, msg, kind)
    return RedirectResponse("/admin/pengaturan", 303)


def _active_supers(db: Session, excluding: int | None = None) -> int:
    q = db.query(Librarian).filter(Librarian.role == "super_admin", Librarian.aktif.is_(True))
    return (q.filter(Librarian.id != excluding) if excluding else q).count()


@router.post("/pengaturan/sandi")
def password_change(request: Request, lama: str = Form(""), baru: str = Form(""), ulang: str = Form(""),
                    db: Session = Depends(get_db)):
    me = guard(request, pending_ok=True)
    same_origin(request)
    s = db.get(Librarian, me.id)
    if len(lama.encode()) > 72 or not verify_password(lama, s.password):
        return _back(request, "Kata sandi lama salah.", "err")
    if (e := check_password(baru)):
        return _back(request, e, "err")
    if baru != ulang:
        return _back(request, "Konfirmasi kata sandi baru tidak sama.", "err")
    s.password, s.must_change = hash_password(baru), False
    db.commit()
    audit.info("AUDIT %s ganti-sandi petugas=%s", services.today(), s.username)
    return _back(request, "Kata sandi diganti.")


@router.post("/pengaturan/petugas")
def staff_create(request: Request, username: str = Form(""), full_name: str = Form(""), password: str = Form(""),
                 role: str = Form("admin"), db: Session = Depends(get_db)):
    me = super_guard(request)
    same_origin(request)
    username, full_name = username.strip(), full_name.strip()
    if not re.match(r"^[A-Za-z0-9_.-]{3,50}$", username) or not (2 <= len(full_name) <= 100):
        return _back(request, "Username 3-50 karakter (huruf, angka, . _ -) dan nama lengkap wajib diisi.", "err")
    if (e := check_password(password)):
        return _back(request, e, "err")
    if db.query(Librarian).filter(Librarian.username == username).first():
        return _back(request, "Username sudah dipakai.", "err")
    role = role if role in ("admin", "super_admin") else "admin"
    db.add(Librarian(username=username, full_name=full_name, password=hash_password(password), role=role,
                     must_change=True, dibuat=services.today()))
    db.commit()
    audit.info("AUDIT %s tambah-petugas oleh=%s baru=%s peran=%s", services.today(), me.username, username, role)
    return _back(request, "Petugas ditambahkan. Kata sandi sementara wajib diganti saat login pertama.")


def _target(db: Session, sid: int) -> Librarian:
    t = db.get(Librarian, sid)
    if not t:
        raise HTTPException(404)
    return t


@router.post("/pengaturan/petugas/{sid}/status")
def staff_status(request: Request, sid: int, aktif: str = Form("0"), db: Session = Depends(get_db)):
    me = super_guard(request)
    same_origin(request)
    t, on = _target(db, sid), aktif == "1"
    if not on and t.role == "super_admin" and _active_supers(db, excluding=t.id) == 0:
        return _back(request, "Tidak bisa menonaktifkan satu-satunya super admin.", "err")
    t.aktif = on
    db.commit()
    audit.info("AUDIT %s %s oleh=%s target=%s", services.today(), "aktifkan" if on else "nonaktifkan", me.username, t.username)
    return _back(request, "Petugas diaktifkan." if on else "Petugas dinonaktifkan.")


@router.post("/pengaturan/petugas/{sid}/peran")
def staff_role(request: Request, sid: int, role: str = Form(""), db: Session = Depends(get_db)):
    me = super_guard(request)
    same_origin(request)
    t = _target(db, sid)
    if role not in ("admin", "super_admin"):
        return _back(request, "Peran tidak valid.", "err")
    if role == "admin" and t.role == "super_admin" and _active_supers(db, excluding=t.id) == 0:
        return _back(request, "Tidak bisa menurunkan satu-satunya super admin.", "err")
    t.role = role
    db.commit()
    audit.info("AUDIT %s ubah-peran oleh=%s target=%s peran=%s", services.today(), me.username, t.username, role)
    return _back(request, "Peran diperbarui.")


@router.post("/pengaturan/petugas/{sid}/reset")
def staff_reset(request: Request, sid: int, password: str = Form(""), db: Session = Depends(get_db)):
    me = super_guard(request)
    same_origin(request)
    t = _target(db, sid)
    if t.id == me.id:
        return _back(request, "Ganti kata sandi sendiri lewat form di bawah.", "err")
    if (e := check_password(password)):
        return _back(request, e, "err")
    t.password, t.must_change = hash_password(password), True
    db.commit()
    audit.info("AUDIT %s reset-sandi oleh=%s target=%s", services.today(), me.username, t.username)
    return _back(request, f"Kata sandi sementara untuk {t.username} ditetapkan. Wajib diganti saat login.")
