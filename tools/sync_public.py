"""Salin static/ (css, js, img) ke public/static agar Vercel melayani lewat CDN, bukan lewat fungsi Python.
Jalankan ulang setiap mengubah file di static/:  python tools/sync_public.py
static/uploads TIDAK disalin (isi unggahan; di Vercel disimpan di Cloudinary)."""
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
dst = BASE / "public" / "static"
if dst.exists():
    shutil.rmtree(dst)
for sub in ("css", "js", "img"):
    shutil.copytree(BASE / "static" / sub, dst / sub)
print("disalin ke", dst)
