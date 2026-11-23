"""Lokasi folder proyek, dihitung dari lokasi file ini (bukan dari folder kerja proses).
Di Vercel folder kerja bukan root proyek, jadi path relatif seperti "templates" tidak bisa dipakai."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
