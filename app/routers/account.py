import re
import time
from math import ceil
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.auth import hash_password, verify_password
from app.core import flash, get_db, render, require_member, safe_next
from app.models import Book, Borrowing, Librarian, Member, Notification, Wishlist
from app import services

router = APIRouter()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+\-\s]{8,20}$")

# Pembatasan login: dalam memori (per proses). 5 gagal per username / 20 per IP -> kunci 10 menit.
_FAILS: dict[str, list[float]] = {}
WINDOW, LIMITS = 600, {"u": 5, "ip": 20}


def _locked(keys: list[str]) -> bool:
    now = time.time()
    for k in keys:
        _FAILS[k] = [t for t in _FAILS.get(k, []) if now - t < WINDOW]
        if len(_FAILS[k]) >= LIMITS[k.split(":", 1)[0]]:
            return True
    return False


def _fail(keys: list[str]):
    for k in keys:
        _FAILS.setdefault(k, []).append(time.time())
    if len(_FAILS) > 5000:  # cegah memori membengkak
        _FAILS.clear()


def check_password(pw: str) -> str | None:
    if len(pw) < 8:
        return "Kata sandi minimal 8 karakter."
    if len(pw.encode()) > 72:
        return "Kata sandi terlalu panjang (maksimal 72 byte)."
    return None


def validate_profile(db: Session, form: dict, own_id: str | None = None) -> dict:
    errors = {}
    if not (2 <= len(form["nama"]) <= 100):
        errors["nama"] = "Nama wajib diisi (2-100 karakter)."
    if not EMAIL_RE.match(form["email"]) or len(form["email"]) > 120:
        errors["email"] = "Email tidak valid."
    else:
        q = db.query(Member).filter(Member.email == form["email"])
        if own_id:
            q = q.filter(Member.id_member != own_id)
        if q.first():
            errors["email"] = "Email sudah terdaftar."
    if not PHONE_RE.match(form["no_hp"]):
        errors["no_hp"] = "Nomor HP tidak valid."
    return errors


# ---------- Login / register / logout ----------
@router.get("/login")
def login_page(request: Request, next: str = ""):
    user = request.session.get("user")
    if user:
        return RedirectResponse("/admin" if user["role"] == "admin" else "/", 303)
    return render(request, "auth/login.html", next=safe_next(next) or "", identifier="")


@router.post("/login")
def login(request: Request, identifier: str = Form(""), password: str = Form(""),
          next: str = Form(""), db: Session = Depends(get_db)):
    """Satu form untuk semua: username petugas (akun bawaan) atau email/nomor anggota (harus daftar dulu)."""
    identifier = identifier.strip()
    keys = [f"u:{identifier.lower()[:100]}", f"ip:{request.client.host if request.client else '-'}"]
    if _locked(keys):
        return render(request, "auth/login.html", http_status=429, next=safe_next(next) or "",
                      error="Terlalu banyak percobaan gagal. Coba lagi dalam 10 menit.", identifier=identifier)
    error, user = "Username atau kata sandi salah.", None
    if identifier and password and len(password.encode()) <= 72:
        staff = db.query(Librarian).filter(Librarian.username == identifier).first()
        if staff:
            if verify_password(password, staff.password) and staff.aktif:
                user = {"role": "admin", "id": staff.id, "name": staff.full_name, "username": staff.username}
        else:
            m = db.query(Member).filter((Member.email == identifier.lower()) | (Member.id_member == identifier)).first()
            if m and not m.password:
                error = "Akun ini belum punya kata sandi. Hubungi petugas perpustakaan."
            elif m and verify_password(password, m.password):
                if (m.status or "Aktif") != "Aktif":
                    error = "Keanggotaan tidak aktif. Hubungi petugas perpustakaan."
                else:
                    user = {"role": "member", "id_member": m.id_member, "name": m.nama}
    if not user:
        _fail(keys)
        return render(request, "auth/login.html", http_status=401, next=safe_next(next) or "",
                      error=error, identifier=identifier)
    _FAILS.pop(keys[0], None)
    request.session.clear()
    request.session["user"] = user
    flash(request, f"Selamat datang kembali, {user['name']}.")
    return RedirectResponse(safe_next(next) or ("/admin" if user["role"] == "admin" else "/"), 303)


@router.get("/register")
def register_page(request: Request):
    if user := request.session.get("user"):
        return RedirectResponse("/admin" if user["role"] == "admin" else "/", 303)
    return render(request, "auth/register.html", form={}, errors={})


@router.post("/register")
def register(request: Request, nama: str = Form(""), email: str = Form(""), no_hp: str = Form(""),
             password: str = Form(""), konfirmasi: str = Form(""), db: Session = Depends(get_db)):
    form = {"nama": nama.strip(), "email": email.strip().lower(), "no_hp": no_hp.strip()}
    errors = validate_profile(db, form)
    if (e := check_password(password)):
        errors["password"] = e
    elif password != konfirmasi:
        errors["konfirmasi"] = "Konfirmasi kata sandi tidak sama."
    if errors:
        return render(request, "auth/register.html", http_status=400, form=form, errors=errors)
    m = Member(id_member=services.next_member_id(db), nama=form["nama"], no_hp=form["no_hp"],
               email=form["email"], password=hash_password(password), status="Aktif",
               bergabung=services.today())
    db.add(m)
    services.notify(db, m.id_member, "Selamat datang di Aksara! Telusuri katalog dan pinjam buku pertamamu.")
    db.commit()
    request.session.clear()
    request.session["user"] = {"role": "member", "id_member": m.id_member, "name": m.nama}
    flash(request, "Akun berhasil dibuat. Selamat datang di Aksara.")
    return RedirectResponse("/", 303)


@router.get("/logout")
@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    flash(request, "Anda sudah keluar.")
    return RedirectResponse("/", 303)


# ---------- Area anggota ----------
@router.get("/akun")
def member_dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_member(request)
    idm = user["id_member"]
    s = services.get_settings(db)
    loans = db.query(Borrowing).filter_by(id_member=idm, status="Dipinjam").order_by(Borrowing.jatuh_tempo).all()
    fines = sum(l.denda or 0 for l in db.query(Borrowing).filter_by(id_member=idm, status="Dikembalikan"))
    accruing = sum(services.fine_for(l, s["fine_per_day"]) for l in loans)
    notes = db.query(Notification).filter_by(id_member=idm).order_by(Notification.id.desc()).limit(6).all()
    wishlist = (db.query(Book).join(Wishlist, Wishlist.kode_buku == Book.kode_buku)
                  .filter(Wishlist.id_member == idm).all())
    resp = render(request, "member/dashboard.html", loans=loans, fines=fines, accruing=accruing,
                  notes=notes, wishlist=wishlist, settings=s, total=db.query(Borrowing).filter_by(id_member=idm).count(),
                  member=db.get(Member, idm))
    db.query(Notification).filter_by(id_member=idm, dibaca=0).update({"dibaca": 1})
    db.commit()
    return resp


@router.get("/akun/riwayat")
def member_history(request: Request, status: str = "", page: int = 1, db: Session = Depends(get_db)):
    user = require_member(request)
    q = db.query(Borrowing).filter_by(id_member=user["id_member"]).order_by(Borrowing.id.desc())
    if status in ("Dipinjam", "Dikembalikan"):
        q = q.filter(Borrowing.status == status)
    total = q.count()
    pages = max(1, ceil(total / 10))
    page = min(max(1, page), pages)
    return render(request, "member/history.html", loans=q.offset((page - 1) * 10).limit(10).all(),
                  status=status, page=page, pages=pages, total=total)


@router.get("/akun/profil")
def member_profile(request: Request, db: Session = Depends(get_db)):
    user = require_member(request)
    m = db.get(Member, user["id_member"])
    return render(request, "member/profile.html", member=m, errors={},
                  form={"nama": m.nama, "email": m.email or "", "no_hp": m.no_hp})


@router.post("/akun/profil")
def member_profile_save(request: Request, nama: str = Form(""), email: str = Form(""), no_hp: str = Form(""),
                        password_lama: str = Form(""), password_baru: str = Form(""),
                        db: Session = Depends(get_db)):
    user = require_member(request)
    m = db.get(Member, user["id_member"])
    form = {"nama": nama.strip(), "email": email.strip().lower(), "no_hp": no_hp.strip()}
    errors = validate_profile(db, form, own_id=m.id_member)
    if password_baru:
        if not m.password or not password_lama or len(password_lama.encode()) > 72 \
                or not verify_password(password_lama, m.password):
            errors["password_lama"] = "Kata sandi lama salah."
        elif (e := check_password(password_baru)):
            errors["password_baru"] = e
    if errors:
        return render(request, "member/profile.html", http_status=400, member=m, form=form, errors=errors)
    m.nama, m.email, m.no_hp = form["nama"], form["email"], form["no_hp"]
    if password_baru:
        m.password = hash_password(password_baru)
    db.commit()
    request.session["user"] = {**user, "name": m.nama}
    flash(request, "Profil diperbarui.")
    return RedirectResponse("/akun/profil", 303)
