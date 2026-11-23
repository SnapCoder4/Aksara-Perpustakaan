"""Hapus latar foto buku untuk hero beranda. Dijalankan MANUAL, bukan bagian dari aplikasi.

Pemakaian (dari folder proyek, di venv terpisah agar tidak mengotori .venv aplikasi):
    pip install -r tools/requirements-dev.txt
    python tools/remove_bg.py FOLDER_FOTO_ASLI            # hasil ke static/img/hero/
    python tools/remove_bg.py FOLDER_FOTO_ASLI -o static/img/hero

Nama file hasil = nama file asal + .webp. Beri nama foto asli hero-1, hero-2, hero-3 (mis. hero-1.jpg)
agar dipakai hero beranda. Hanya aset hiasan hero; tidak menyentuh sampul buku (static/uploads/covers/). Foto asli tidak diubah dan tidak dihapus; file hasil yang sudah ada dilewati
kecuali memakai --timpa.
"""
import argparse
import sys
from pathlib import Path

EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_H = 900  # cukup tajam untuk tampilan hero; menjaga file tetap kecil


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path, help="folder foto asli")
    ap.add_argument("-o", "--out", type=Path, default=Path("static/img/hero"))
    ap.add_argument("--timpa", action="store_true", help="timpa hasil yang sudah ada")
    a = ap.parse_args()
    if not a.src.is_dir():
        sys.exit(f"Folder tidak ditemukan: {a.src}")
    if a.src.resolve() == a.out.resolve():
        sys.exit("Folder asal dan tujuan tidak boleh sama (foto asli tidak boleh tertimpa).")
    from PIL import Image
    from rembg import remove  # impor di sini agar --help tetap jalan tanpa rembg

    a.out.mkdir(parents=True, exist_ok=True)
    files = sorted(f for f in a.src.iterdir() if f.suffix.lower() in EXT)
    if not files:
        sys.exit("Tidak ada file gambar (.jpg/.png/.webp) di folder asal.")
    for f in files:
        dst = a.out / (f.stem + ".webp")
        if dst.exists() and not a.timpa:
            print("lewati (sudah ada):", dst.name)
            continue
        try:
            with Image.open(f) as im:
                im = Image.open(f).convert("RGBA") if im.mode != "RGBA" else im.copy()
            if im.height > MAX_H:
                im = im.resize((round(im.width * MAX_H / im.height), MAX_H), Image.LANCZOS)
            remove(im).save(dst, "WEBP", lossless=True)
            print("ok:", f.name, "->", dst)
        except Exception as ex:  # satu foto gagal tidak menghentikan yang lain
            print("GAGAL:", f.name, ex)


if __name__ == "__main__":
    main()
