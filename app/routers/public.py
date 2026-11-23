from math import ceil
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from app.core import flash, get_db, render, require_member, safe_next
from app.models import Book, Borrowing, Category, Member, Wishlist
from app import services
from app.hero import hero_images, rembg_available

router = APIRouter()
PER_PAGE = 12


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    popular = services.popular_books(db, 5)
    cats = (db.query(Category, func.count(Book.kode_buku))
              .outerjoin(Book, Book.category_id == Category.id)
              .group_by(Category.id).order_by(Category.nama).all())
    latest = db.query(Book).order_by(Book.dibuat.desc().nulls_last(), Book.kode_buku.desc()).limit(4).all()
    stats = [
        (db.query(Book).count(), "Judul koleksi"),
        (db.query(Member).filter(Member.status == "Aktif").count(), "Anggota aktif"),
        (db.query(Category).count(), "Kategori"),
        (db.query(Borrowing).count(), "Total peminjaman"),
    ]
    return render(request, "public/home.html", popular=[b for b, _ in popular], cats=cats,
                  latest=latest, stats=stats, hero=hero_images(db), rembg_ok=rembg_available())


def _urut(urut):
    return urut if urut in ("populer", "judul") else "terbaru"


@router.get("/katalog")
def catalog(request: Request, q: str = "", kategori: int | None = None, urut: str = "terbaru",
            tersedia: int = 0, tampilan: str = "grid", page: int = 1, db: Session = Depends(get_db)):
    q, urut, page = q.strip()[:80], _urut(urut), max(1, page)
    books, has_next = services.search_books(db, q, kategori, urut, bool(tersedia), page, PER_PAGE)
    cats = db.query(Category).order_by(Category.nama).all()
    return render(request, "public/catalog.html", books=books, cats=cats, q=q, kategori=kategori,
                  urut=urut, tersedia=tersedia, tampilan="list" if tampilan == "list" else "grid",
                  page=page, has_next=has_next)


@router.get("/api/katalog")
def catalog_api(q: str = "", kategori: int | None = None, urut: str = "terbaru",
                tersedia: int = 0, page: int = 1, db: Session = Depends(get_db)):
    page = max(1, page)
    books, has_next = services.search_books(db, q, kategori, _urut(urut), bool(tersedia), page, PER_PAGE)
    items = [{"kode": b.kode_buku, "judul": b.judul, "penulis": b.penulis, "penerbit": b.penerbit, "tahun": b.tahun,
              "kategori": b.category.nama if b.category else None, "cover": b.cover_path,
              "stok": b.stok, "cv": len(b.judul) % 6} for b in books]
    return {"items": items, "page": page, "has_next": has_next}


@router.get("/buku/{kode}")
def book_detail(request: Request, kode: str, db: Session = Depends(get_db)):
    book = db.get(Book, kode)
    if not book:
        return render(request, "public/404.html", http_status=404)
    related = []
    if book.category_id:
        related = (db.query(Book).filter(Book.category_id == book.category_id, Book.kode_buku != kode)
                     .order_by(Book.judul).limit(4).all())
    user = request.session.get("user")
    wished = bool(user and user["role"] == "member" and
                  db.query(Wishlist).filter_by(id_member=user["id_member"], kode_buku=kode).first())
    return render(request, "public/book_detail.html", book=book, related=related, wished=wished)


@router.get("/tentang")
def about(request: Request):
    return render(request, "public/about.html")


@router.post("/buku/{kode}/pinjam")
def borrow(request: Request, kode: str, db: Session = Depends(get_db)):
    user = request.session.get("user")
    if not user or user["role"] != "member":
        flash(request, "Masuk sebagai anggota untuk meminjam buku.", "warn")
        return RedirectResponse(f"/login?next=/buku/{kode}", 303)
    try:
        book = db.get(Book, kode)
        services.create_loan(db, book, db.get(Member, user["id_member"]))
        db.commit()
        flash(request, f"Buku \"{book.judul}\" berhasil dipinjam.")
    except ValueError as e:
        db.rollback()
        flash(request, str(e), "err")
    return RedirectResponse(f"/buku/{kode}", 303)


@router.post("/buku/{kode}/wishlist")
def toggle_wishlist(request: Request, kode: str, next: str = Form(""), db: Session = Depends(get_db)):
    user = require_member(request)
    if not db.get(Book, kode):
        return RedirectResponse("/katalog", 303)
    row = db.query(Wishlist).filter_by(id_member=user["id_member"], kode_buku=kode).first()
    if row:
        db.delete(row)
        flash(request, "Dihapus dari wishlist.")
    else:
        db.add(Wishlist(id_member=user["id_member"], kode_buku=kode))
        flash(request, "Ditambahkan ke wishlist.")
    db.commit()
    return RedirectResponse(safe_next(next) or f"/buku/{kode}", 303)
