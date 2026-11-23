"""Upload sampul buku. Semua validasi dilakukan di server."""
import re
from time import sleep
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from fastapi import UploadFile
from PIL import Image, ImageOps

COVER_DIR = Path("static/uploads/covers")
MAX_BYTES = 2 * 1024 * 1024
MAX_WIDTH = 600
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_W, MAX_H, MIN_W = 1200, 1800, 200  # hasil crop dari browser 600x900; lebih dari ini tidak wajar
RATIO, RATIO_TOL = 2 / 3, 0.02
_NAME = re.compile(r"^[0-9a-f]{32}\.webp$")

Image.MAX_IMAGE_PIXELS = 25_000_000  # tolak gambar raksasa (decompression bomb)


class _Reject(Exception):
    pass


async def save_cover(file: UploadFile) -> str:
    """Validasi dan simpan sampul. Mengembalikan nama file baru; ValueError bila ditolak."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT or file.content_type not in ALLOWED_TYPES:
        raise ValueError("Format tidak didukung. Gunakan JPG, PNG, atau WEBP.")
    data = bytearray()
    while chunk := await file.read(64 * 1024):
        data += chunk
        if len(data) > MAX_BYTES:
            raise ValueError("Ukuran file maksimal 2 MB.")
    if not data:
        raise ValueError("File kosong.")
    try:
        Image.open(BytesIO(data)).verify()
        img = Image.open(BytesIO(data))  # verify() menutup objek, buka ulang
        if img.format not in ALLOWED_FORMATS:
            raise ValueError
        img = ImageOps.exif_transpose(img)
        if img.width > MAX_W or img.height > MAX_H:
            raise _Reject(f"Dimensi gambar terlalu besar (maksimal {MAX_W} x {MAX_H} px). Gunakan editor crop.")
        if img.width < MIN_W or abs(img.width / img.height - RATIO) > RATIO * RATIO_TOL:
            raise _Reject("Gambar harus berasio 2:3 dan minimal 200 px lebar. Gunakan editor crop.")
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
        if img.width > MAX_WIDTH:
            img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)), Image.LANCZOS)
    except _Reject as ex:
        raise ValueError(str(ex))
    except Exception:
        raise ValueError("File bukan gambar yang valid atau rusak.")
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    name = uuid4().hex + ".webp"
    img.save(COVER_DIR / name, "WEBP", quality=85)
    return name


def delete_cover(name: str | None):
    """Hapus hanya file bernama buatan sendiri di folder covers."""
    if not (name and _NAME.match(name)):
        return
    for _ in range(10):  # Windows: file bisa masih terbuka sesaat oleh proses lain
        try:
            (COVER_DIR / name).unlink(missing_ok=True)
            return
        except PermissionError:
            sleep(0.2)
    # shortcut: gagal hapus setelah ~2 dtk dibiarkan (file yatim), jangan gagalkan request; upgrade: job pembersih berkala
