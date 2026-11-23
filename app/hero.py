"""Gambar hiasan hero beranda: static/img/hero/hero-1..3.webp. Terpisah dari sampul buku (static/uploads/covers)."""
import os
from io import BytesIO
from pathlib import Path
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps

HERO_DIR = Path("static/img/hero")
SLOTS = (1, 2, 3)
MAX_BYTES = 8 * 1024 * 1024
MAX_SIDE = 900
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

_session = None  # model rembg dimuat sekali (unduh ~170 MB saat pertama kali dipakai)


def path(n: int) -> Path:
    return HERO_DIR / f"hero-{n}.webp"


def hero_images() -> list[str | None]:
    """URL tiap slot (dengan ?v=mtime agar cache browser ikut berganti), None bila file belum ada."""
    return [f"/static/img/hero/hero-{n}.webp?v={int(path(n).stat().st_mtime)}" if path(n).is_file() else None for n in SLOTS]


NO_REMBG = "rembg belum terpasang, jadi gambar disimpan apa adanya tanpa hapus latar. Untuk mengaktifkannya: pip install -r requirements-optional.txt"


def rembg_available() -> bool:
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
        if len(data) > MAX_BYTES:
            raise ValueError("Ukuran file maksimal 8 MB.")
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


async def save_hero(n: int, file: UploadFile, remove_bg: bool) -> str | None:
    """Validasi penuh di server, opsional hapus latar, simpan sebagai hero-N.webp. ValueError bila ditolak.
    Mengembalikan catatan (str) bila hapus latar diminta tetapi rembg tidak terpasang; gambar tetap disimpan apa adanya."""
    if n not in SLOTS:
        raise ValueError("Slot tidak dikenal.")
    data = await _read_upload(file)
    note = None
    if remove_bg and not rembg_available():
        remove_bg, note = False, NO_REMBG
    img = await run_in_threadpool(_render, data, remove_bg)  # rembg berat: jangan blok event loop
    HERO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = HERO_DIR / f".tmp-{n}.webp"
    img.save(tmp, "WEBP", quality=90)
    os.replace(tmp, path(n))  # atomik: beranda tidak pernah melihat file setengah jadi
    return note


async def preview_hero(file: UploadFile) -> bytes:
    """Hasil hapus latar sebagai PNG, tanpa menyimpan apa pun (untuk pratinjau sebelum/sesudah di editor)."""
    data = await _read_upload(file)
    if not rembg_available():
        raise ValueError(NO_REMBG)
    img = await run_in_threadpool(_render, data, True)
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def delete_hero(n: int):
    if n in SLOTS:
        path(n).unlink(missing_ok=True)
