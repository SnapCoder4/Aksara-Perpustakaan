"""Gambar hiasan hero beranda: static/img/hero/hero-1..3.webp. Terpisah dari sampul buku (static/uploads/covers)."""
from io import BytesIO
from pathlib import Path
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps
from app import storage
from app.paths import STATIC_DIR

HERO_DIR = STATIC_DIR / "img" / "hero"
SLOTS = (1, 2, 3)
MAX_BYTES = 8 * 1024 * 1024
CLOUD_MAX_BYTES = 4 * 1024 * 1024  # Vercel menolak body request di atas 4,5 MB (413), sisakan ruang untuk multipart


def max_bytes() -> int:
    return CLOUD_MAX_BYTES if storage.enabled() else MAX_BYTES
MAX_SIDE = 900
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

_session = None  # model rembg dimuat sekali (unduh ~170 MB saat pertama kali dipakai)


def path(n: int) -> Path:
    return HERO_DIR / f"hero-{n}.webp"


def _cloud_version(db, n: int):
    from app.models import Setting
    row = db.get(Setting, f"hero_{n}")
    return int(row.value) if row and row.value.isdigit() else None


def hero_images(db=None) -> list[str | None]:
    """URL tiap slot, None bila belum ada gambar. Lokal: cek file (?v=mtime). Cloud: versi gambar disimpan di tabel settings."""
    if storage.enabled():
        cloud = storage._cld().config().cloud_name
        from app.models import Setting
        vers = {}
        if db is not None:
            vers = {r.key: r.value for r in db.query(Setting).filter(Setting.key.in_([f"hero_{n}" for n in SLOTS]))}
        out = []
        for n in SLOTS:
            v = int(vers[f"hero_{n}"]) if vers.get(f"hero_{n}", "").isdigit() else None
            out.append(f"https://res.cloudinary.com/{cloud}/image/upload/v{v}/{storage.PREFIX}/hero/hero-{n}.webp" if v else None)
        return out
    return [f"/static/img/hero/hero-{n}.webp?v={int(path(n).stat().st_mtime)}" if path(n).is_file() else None for n in SLOTS]


NO_REMBG = "rembg belum terpasang, jadi gambar disimpan apa adanya tanpa hapus latar. Untuk mengaktifkannya: pip install -r requirements-optional.txt"
NO_REMBG_CLOUD = "Hapus latar hanya tersedia di versi lokal. Gambar disimpan apa adanya."


def no_rembg_msg() -> str:
    return NO_REMBG_CLOUD if storage.enabled() else NO_REMBG


def rembg_available() -> bool:
    if storage.enabled():
        return False  # mode cloud (Vercel): model berat tidak dipasang
    from importlib.util import find_spec  # cek tanpa mengimpor paket berat
    return find_spec("rembg") is not None


def _remove_bg(img: Image.Image) -> Image.Image:
    global _session
    from rembg import new_session, remove  # lazy: hanya dipanggil bila rembg terpasang
    try:
        _session = _session or new_session("u2net")
        out = remove(img, session=_session)
    except Exception as ex:
        raise ValueError(f"Hapus latar gagal ({type(ex).__name__}). Pada pemakaian pertama model diunduh, pastikan ada koneksi internet.")
    box = out.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    return out.crop(box) if box else out  # buang ruang kosong agar buku memenuhi bingkai


async def _read_upload(file: UploadFile) -> bytes:
    """Validasi tipe/ekstensi/ukuran dan baca isi upload. ValueError bila ditolak."""
    if Path(file.filename or "").suffix.lower() not in ALLOWED_EXT or file.content_type not in ALLOWED_TYPES:
        raise ValueError("Format tidak didukung. Gunakan JPG, PNG, atau WEBP.")
    data = bytearray()
    while chunk := await file.read(64 * 1024):
        data += chunk
        if len(data) > max_bytes():
            raise ValueError(f"Ukuran file maksimal {max_bytes() // (1024 * 1024)} MB.")
    if not data:
        raise ValueError("File kosong.")
    return bytes(data)


def _render(data: bytes, remove_bg: bool) -> Image.Image:
    """Isi file dicek Pillow, orientasi EXIF diterapkan, diperkecil, opsional hapus latar (berat: jalankan di thread)."""
    try:
        Image.open(BytesIO(data)).verify()
        img = Image.open(BytesIO(data))
        if img.format not in ALLOWED_FORMATS:
            raise ValueError
        img = ImageOps.exif_transpose(img).convert("RGBA")
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    except Exception:
        raise ValueError("File bukan gambar yang valid atau rusak.")
    return _remove_bg(img) if remove_bg else img


async def save_hero(n: int, file: UploadFile, remove_bg: bool, db=None) -> str | None:
    """Validasi penuh di server, opsional hapus latar, simpan sebagai hero-N.webp. ValueError bila ditolak.
    Mengembalikan catatan (str) bila hapus latar diminta tetapi rembg tidak terpasang; gambar tetap disimpan apa adanya."""
    if n not in SLOTS:
        raise ValueError("Slot tidak dikenal.")
    data = await _read_upload(file)
    note = None
    if remove_bg and not rembg_available():
        remove_bg, note = False, no_rembg_msg()
    img = await run_in_threadpool(_render, data, remove_bg)  # rembg berat: jangan blok event loop
    buf = BytesIO()
    img.save(buf, "WEBP", quality=90)
    try:
        ref = await run_in_threadpool(storage.put, "hero", f"hero-{n}.webp", buf.getvalue(), True)
    except Exception:
        raise ValueError("Gagal menyimpan gambar. Coba lagi sebentar lagi.")
    if storage.enabled() and db is not None:
        from app.services import set_setting
        set_setting(db, f"hero_{n}", int(ref.split("/upload/v", 1)[1].split("/", 1)[0]))
        db.commit()
    return note


async def preview_hero(file: UploadFile) -> bytes:
    """Hasil hapus latar sebagai PNG, tanpa menyimpan apa pun (untuk pratinjau sebelum/sesudah di editor)."""
    data = await _read_upload(file)
    if not rembg_available():
        raise ValueError(no_rembg_msg())
    img = await run_in_threadpool(_render, data, True)
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def delete_hero(n: int, db=None):
    if n not in SLOTS:
        return
    if storage.enabled():
        if db is not None:
            from app.models import Setting
            if (row := db.get(Setting, f"hero_{n}")):
                db.delete(row)
                db.commit()
        storage.remove("hero", f"https://res.cloudinary.com/{storage._cld().config().cloud_name}/image/upload/{storage.PREFIX}/hero/hero-{n}.webp")
    else:
        storage.remove("hero", f"hero-{n}.webp")
