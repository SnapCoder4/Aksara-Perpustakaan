"""Penyimpanan gambar: folder lokal (default) atau Cloudinary (bila variabel lingkungan diisi).

kind: "covers" (sampul buku) atau "hero" (gambar hero beranda).
Mode lokal sama persis dengan perilaku lama. Mode cloud hanya aktif bila CLOUDINARY_URL
atau ketiga CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET terisi.
"""
import os
import re
from pathlib import Path
from time import sleep

from app.paths import STATIC_DIR

LOCAL_DIR = {"covers": STATIC_DIR / "uploads" / "covers", "hero": STATIC_DIR / "img" / "hero"}
LOCAL_URL = {"covers": "/static/uploads/covers/", "hero": "/static/img/hero/"}
PREFIX = "aksara"
_CLOUD_ID = re.compile(r"^https://res\.cloudinary\.com/([^/]+)/image/upload/(?:v\d+/)?(aksara/.+?)\.webp$")


def enabled() -> bool:
    return bool(os.getenv("CLOUDINARY_URL") or all(
        os.getenv(k) for k in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")))


def _cld():
    import cloudinary  # lazy: paket hanya dibutuhkan di mode cloud; import setelah load_dotenv
    import cloudinary.uploader
    if not os.getenv("CLOUDINARY_URL"):
        cloudinary.config(cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"), api_key=os.getenv("CLOUDINARY_API_KEY"),
                          api_secret=os.getenv("CLOUDINARY_API_SECRET"), secure=True)
    else:
        cloudinary.config(secure=True)
    return cloudinary


def put(kind: str, name: str, data: bytes, overwrite: bool = False) -> str:
    """Simpan gambar WebP. Lokal: mengembalikan nama file. Cloud: mengembalikan URL https penuh.
    Gagal -> OSError (lokal) atau Exception dari SDK (dibungkus pemanggil)."""
    if not enabled():
        folder = LOCAL_DIR[kind]
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f".tmp-{name}"
        tmp.write_bytes(data)
        os.replace(tmp, folder / name)  # atomik: tidak pernah terlihat setengah jadi
        return name
    cld = _cld()
    res = cld.uploader.upload(data, public_id=f"{PREFIX}/{kind}/{Path(name).stem}", resource_type="image",
                              overwrite=overwrite, invalidate=overwrite, unique_filename=False)
    return res["secure_url"]


def remove(kind: str, ref: str | None):
    """Hapus gambar milik kita saja. Nama file lokal dan URL cloud sama-sama diterima; selain itu diabaikan."""
    if not ref:
        return
    m = _CLOUD_ID.match(ref)
    if m:
        if enabled() and m.group(1) == (_cld().config().cloud_name or ""):
            try:
                _cld().uploader.destroy(m.group(2), invalidate=True)
            except Exception:
                pass  # shortcut: gagal hapus di cloud dibiarkan (file yatim), jangan gagalkan request
        return
    if not re.match(r"^[A-Za-z0-9_-]+\.webp$", ref):
        return  # bukan nama buatan sendiri
    for _ in range(10):  # Windows: file bisa masih terbuka sesaat oleh proses lain
        try:
            (LOCAL_DIR[kind] / ref).unlink(missing_ok=True)
            return
        except PermissionError:
            sleep(0.2)
    # shortcut: gagal hapus setelah ~2 dtk dibiarkan (file yatim), upgrade: job pembersih berkala


def url(kind: str, ref: str | None) -> str:
    """URL untuk <img>. Data lama (nama file) dan URL cloud keduanya ditangani."""
    if not ref:
        return ""
    return ref if ref.startswith(("http://", "https://")) else LOCAL_URL[kind] + ref
