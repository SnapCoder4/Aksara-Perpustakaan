"""Logika bisnis perpustakaan (tanpa urusan tampilan)."""
from datetime import date, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core import BULAN, env
from app.models import Book, Borrowing, Category, Member, Notification, Setting

DEFAULTS = {"loan_days": 7, "fine_per_day": 1000, "max_loans": 3}


def today() -> str:
    return str(date.today())


def get_settings(db: Session) -> dict:
    s = dict(DEFAULTS)
    for row in db.query(Setting).all():
        try:
            s[row.key] = int(row.value)
        except ValueError:
            pass
    return s


def set_setting(db: Session, key: str, value: int):
    row = db.get(Setting, key)
    if row:
        row.value = str(value)
    else:
        db.add(Setting(key=key, value=str(value)))


def notify(db: Session, id_member: str, pesan: str):
    db.add(Notification(id_member=id_member, pesan=pesan, dibaca=0, dibuat=today()))


def loan_status(loan: Borrowing) -> str:
    if loan.status == "Dipinjam" and (loan.jatuh_tempo or "9999") < today():
        return "Terlambat"
    return loan.status or "Dipinjam"


def fine_for(loan: Borrowing, fine_per_day: int, until: str | None = None) -> int:
    """Denda = hari keterlambatan x tarif. Untuk pinjaman aktif dihitung sampai hari ini."""
    end = until or loan.tanggal_kembali or today()
    try:
        late = (date.fromisoformat(end) - date.fromisoformat(loan.jatuh_tempo)).days
    except (ValueError, TypeError):
        return 0
    return max(0, late) * fine_per_day


def create_loan(db: Session, book: Book | None, member: Member | None,
                librarian_id: int | None = None, tanggal: str | None = None) -> Borrowing:
    """Buat peminjaman dan kurangi stok. ValueError bila aturan dilanggar."""
    if not book:
        raise ValueError("Buku tidak ditemukan.")
    if not member:
        raise ValueError("Anggota tidak ditemukan.")
    if (member.status or "Aktif") != "Aktif":
        raise ValueError("Keanggotaan tidak aktif.")
    if book.stok <= 0:
        raise ValueError("Stok buku habis.")
    s = get_settings(db)
    active = db.query(Borrowing).filter(Borrowing.id_member == member.id_member,
                                        Borrowing.status == "Dipinjam")
    if active.count() >= s["max_loans"]:
        raise ValueError(f"Batas peminjaman {s['max_loans']} buku sekaligus sudah tercapai.")
    if active.filter(Borrowing.kode_buku == book.kode_buku).first():
        raise ValueError("Buku ini sedang dipinjam oleh anggota yang sama.")
    try:
        start = date.fromisoformat(tanggal) if tanggal else date.today()
    except ValueError:
        raise ValueError("Format tanggal tidak valid.")
    due = start + timedelta(days=s["loan_days"])
    book.stok -= 1
    loan = Borrowing(kode_buku=book.kode_buku, id_member=member.id_member, librarian_id=librarian_id,
                     tanggal_pinjam=str(start), jatuh_tempo=str(due), status="Dipinjam", denda=0)
    db.add(loan)
    notify(db, member.id_member, f"Anda meminjam \"{book.judul}\". Kembalikan sebelum {due.day} {BULAN[due.month-1]} {due.year}.")
    return loan


def return_loan(db: Session, loan: Borrowing) -> int:
    """Tandai kembali, tambah stok, hitung denda. Mengembalikan jumlah denda."""
    if loan.status != "Dipinjam":
        return loan.denda or 0
    s = get_settings(db)
    loan.status = "Dikembalikan"
    loan.tanggal_kembali = today()
    loan.denda = fine_for(loan, s["fine_per_day"], loan.tanggal_kembali)
    if loan.book:
        loan.book.stok += 1
    msg = f"Buku \"{loan.book.judul if loan.book else loan.kode_buku}\" sudah dikembalikan."
    if loan.denda:
        msg += f" Denda keterlambatan: Rp {loan.denda:,}".replace(",", ".")
    notify(db, loan.id_member, msg)
    return loan.denda


def next_member_id(db: Session) -> str:
    n = 1
    for (idm,) in db.query(Member.id_member).all():
        if idm.startswith("MBR") and idm[3:].isdigit():
            n = max(n, int(idm[3:]) + 1)
    return f"MBR{n:03d}"


def search_books(db: Session, q: str = "", kategori: int | None = None, urut: str = "terbaru",
                 tersedia: bool = False, page: int = 1, per: int = 12) -> tuple[list[Book], bool]:
    """Cari di database. Ambil per+1 baris untuk tahu ada halaman berikutnya (tanpa COUNT)."""
    from sqlalchemy import or_
    from sqlalchemy.orm import joinedload, load_only
    query = db.query(Book).options(
        load_only(Book.kode_buku, Book.judul, Book.penulis, Book.penerbit, Book.tahun, Book.stok,
                  Book.cover_path, Book.category_id),  # tanpa sinopsis
        joinedload(Book.category))
    q = q.strip()[:80]
    if q:
        query = query.filter(or_(Book.judul.icontains(q, autoescape=True), Book.penulis.icontains(q, autoescape=True),
                                 Book.isbn.startswith(q, autoescape=True)))
    if kategori:
        query = query.filter(Book.category_id == kategori)
    if tersedia:
        query = query.filter(Book.stok > 0)
    if urut == "populer":
        cnt = (db.query(Borrowing.kode_buku.label("kode"), func.count().label("n"))
                 .group_by(Borrowing.kode_buku).subquery())
        query = (query.outerjoin(cnt, cnt.c.kode == Book.kode_buku)
                      .order_by(func.coalesce(cnt.c.n, 0).desc(), Book.judul, Book.kode_buku))
    elif urut == "judul":
        query = query.order_by(Book.judul, Book.kode_buku)
    else:
        query = query.order_by(Book.dibuat.desc().nulls_last(), Book.kode_buku.desc())
    rows = query.offset((max(1, page) - 1) * per).limit(per + 1).all()
    return rows[:per], len(rows) > per


def availability(book: Book) -> tuple[str, str]:
    """(teks, kelas css)"""
    return (f"Tersedia {book.stok}", "ok") if book.stok > 0 else ("Dipinjam semua", "warn")


def monthly_activity(db: Session, months: int = 12) -> list[dict]:
    d = date.today().replace(day=1)
    keys = []
    for _ in range(months):
        keys.append((d.year, d.month))
        d = (d - timedelta(days=1)).replace(day=1)
    keys.reverse()
    pinjam, kembali, telat = {}, {}, {}
    for l in db.query(Borrowing).all():
        pinjam[(l.tanggal_pinjam or "")[:7]] = pinjam.get((l.tanggal_pinjam or "")[:7], 0) + 1
        if l.tanggal_kembali:
            kembali[l.tanggal_kembali[:7]] = kembali.get(l.tanggal_kembali[:7], 0) + 1
        if (l.denda or 0) > 0 and l.tanggal_kembali:
            telat[l.tanggal_kembali[:7]] = telat.get(l.tanggal_kembali[:7], 0) + 1
    out = []
    for y, m in keys:
        k = f"{y}-{m:02d}"
        out.append({"label": BULAN[m - 1], "pinjam": pinjam.get(k, 0),
                    "kembali": kembali.get(k, 0), "telat": telat.get(k, 0)})
    return out


def home_stats(db: Session) -> list[tuple[int, str]]:
    """Empat hitungan beranda dalam SATU query."""
    from sqlalchemy import select
    sc = lambda m, *w: select(func.count()).select_from(m).where(*w).scalar_subquery()
    a, b, c, d = db.execute(select(sc(Book), sc(Member, Member.status == "Aktif"), sc(Category), sc(Borrowing))).one()
    return [(a, "Judul koleksi"), (b, "Anggota aktif"), (c, "Kategori"), (d, "Total peminjaman")]


def home_categories(db: Session) -> list[tuple]:
    """(kategori, jumlah buku) sebagai objek sederhana, aman disimpan di cache."""
    from types import SimpleNamespace
    rows = (db.query(Category.id, Category.nama, func.count(Book.kode_buku))
              .outerjoin(Book, Book.category_id == Category.id)
              .group_by(Category.id).order_by(Category.nama).all())
    return [(SimpleNamespace(id=i, nama=nm), n) for i, nm, n in rows]


def category_list(db: Session) -> list:
    from types import SimpleNamespace
    return [SimpleNamespace(id=i, nama=n) for i, n in db.query(Category.id, Category.nama).order_by(Category.nama).all()]


def popular_books(db: Session, limit: int = 5) -> list[tuple[Book, int]]:
    rows = (db.query(Book, func.count(Borrowing.id).label("n"))
              .outerjoin(Borrowing, Borrowing.kode_buku == Book.kode_buku)
              .group_by(Book.kode_buku).order_by(func.count(Borrowing.id).desc(), Book.judul)
              .limit(limit).all())
    return [(b, n) for b, n in rows]


def category_loans(db: Session) -> list[tuple[str, int]]:
    rows = (db.query(func.coalesce(Category.nama, "Tanpa kategori"), func.count(Borrowing.id))
              .select_from(Borrowing).join(Book, Book.kode_buku == Borrowing.kode_buku)
              .outerjoin(Category, Category.id == Book.category_id)
              .group_by(Category.nama).order_by(func.count(Borrowing.id).desc()).all())
    return [(n, c) for n, c in rows]


def donut_segments(items: list[tuple[str, int]], r: int = 76) -> list[dict]:
    total = sum(v for _, v in items) or 1
    circ = 2 * 3.14159265 * r
    colors = ["var(--gold-ch)", "var(--royal)", "var(--mist)", "var(--sage)", "var(--rose)"]
    segs, offset = [], 0.0
    for i, (name, v) in enumerate(items[:5]):
        length = circ * v / total
        segs.append({"name": name, "value": v, "color": colors[i % len(colors)],
                     "dash": f"{length:.1f} {circ - length:.1f}", "offset": f"{-offset:.1f}"})
        offset += length
    return segs


# Fungsi yang dipanggil langsung dari template
env.globals.update(loan_status=loan_status, availability=availability, fine_for=fine_for)
