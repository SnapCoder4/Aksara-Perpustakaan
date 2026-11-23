# Prompt Implementasi: Perpustakaan Digital (FastAPI + Jinja2)

Salin seluruh isi file ini ke AI agent. Lampirkan juga `aksara-design.zip` (desain) dan buka folder proyek CRUD yang sudah ada.

---

## PERAN

Kamu adalah senior full-stack engineer. Tugasmu mengimplementasikan desain UI/UX "Aksara" (perpustakaan digital bergaya nasional, tema navy dan emas) ke proyek FastAPI + Jinja2 yang sudah ada. Desain sudah disetujui. Fokusnya sekarang adalah menerjemahkan desain itu ke template dan CSS, lalu menambah fitur upload foto sampul buku.

## KONTEKS PROYEK

- Stack: FastAPI, Jinja2, database `library.db` (SQLite), tugas kuliah CRUD.
- Desain acuan ada di `aksara-design.zip`. Isinya file `.dc.html` (artboard desain). File itu bukan kode produksi. Baca HTML, CSS, dan nilai variabelnya sebagai spesifikasi visual, lalu tulis ulang sebagai template Jinja2.
- Daftar halaman desain:
  - Publik: Beranda, Katalog, Detail Buku, Tentang, Login/Register (versi Login Premium), 404
  - Anggota: Dashboard, Riwayat Peminjaman, Profil
  - Admin: Dashboard, Daftar Buku, Form Tambah Buku, Form Edit Buku, Kategori, Anggota, Peminjaman, Laporan, Pengaturan

## ATURAN KERJA (WAJIB)

1. Sebelum mengubah apa pun, baca struktur proyek dan tulis ringkasan temuanmu: daftar route, model/tabel, template yang ada, dan struktur folder static. Tunggu persetujuan saya atas rencana itu.
2. Kerjakan bertahap per fase (lihat bagian FASE). Setelah tiap fase selesai, berhenti, jelaskan apa yang berubah, dan tunggu konfirmasi.
3. Jangan menghapus file yang sudah ada. Kalau sebuah file perlu diganti, buat versi baru dan simpan yang lama sebagai `*.bak` atau pindahkan ke folder `_old/`.
4. Jangan refactor logika yang tidak berhubungan dengan tugas. Perubahan harus minimal dan terarah.
5. Jangan mengubah skema database sebelum saya setuju. Sebelum menyentuh `library.db`, buat cadangan `library.db.bak`, lalu tampilkan perubahan skema (SQL) untuk saya setujui.
6. Jangan pernah menyimpan rahasia (client secret, key) di kode. Pakai file `.env` dan sertakan `.env.example`.
7. Kalau ada hal yang ambigu, tanya. Jangan menebak.

## DESIGN SYSTEM (ambil dari artboard "Design System")

Gunakan CSS variables di satu file `static/css/tokens.css`. Mode gelap adalah tampilan awal, mode terang sebagai pilihan. Tema diganti lewat atribut `data-theme` pada elemen root, dan pilihan pengguna disimpan di `localStorage`.

| Token | Gelap | Terang |
|---|---|---|
| `--page` (latar) | #0B1733 (Midnight Navy) | #F6F2E9 (ivory) |
| `--card` | #10264A (Deep Navy) | #FFFFFF |
| `--pri` (tombol utama) | #D9B66F (Champagne Gold) | #10264A |
| `--onpri` (teks di atas tombol utama) | #0B1733 | #FBF8F2 |
| `--link` | #F2D49A | #183E70 |
| teks redup | #A9B7D0 | #4A5873 |

Variabel lain (`--paper`, `--soft`, `--bd`, `--bd2`, `--ink`, `--ink2`, `--mut`, `--strong`, `--gold`, `--ok`, `--warn`, `--err`, dan seterusnya) nilainya ada di blok `.t` pada file desain. Salin nilainya persis.

Tipografi: Fraunces untuk judul (serif), Inter untuk isi. Halaman login premium memakai Cormorant Garamond untuk judul. Muat font lewat Google Fonts dengan `display=swap`.

Aturan visual: sudut membulat konsisten, bayangan lembut, glassmorphism hanya di halaman login, kontras teks minimal WCAG AA.

## STRUKTUR FRONTEND

Usulan struktur (sesuaikan dengan folder yang sudah ada, jangan memindahkan file lama):

```
app/
  templates/
    base.html              # layout dasar, memuat tokens.css, font, toggle tema
    partials/
      navbar.html  footer.html  book_card.html  stat_card.html
      sidebar_admin.html  sidebar_member.html  toast.html  modal.html
    public/   home.html  catalog.html  book_detail.html  about.html  404.html
    auth/     login.html  register.html
    member/   dashboard.html  history.html  profile.html
    admin/    dashboard.html  books.html  book_form.html  categories.html
              members.html  loans.html  reports.html  settings.html
  static/
    css/  tokens.css  base.css  components.css  pages/*.css
    js/   theme.js  upload.js  toast.js  charts.js
    uploads/covers/        # foto sampul buku (lihat bagian upload)
```

Komponen yang dipakai ulang: tombol (primary, ghost, danger), input dan field dengan state error, kartu buku, kartu statistik, tabel dengan badge status, modal, toast, tab, pagination, sidebar, dan dropzone upload.

## FITUR UPLOAD FOTO SAMPUL BUKU

Desain: artboard "Admin: Form Tambah Buku" dan "Admin: Edit Buku". Dropzone punya empat state: kosong, mengunggah (progress), pratinjau, dan error.

### Frontend (`static/js/upload.js`)
- Dropzone mendukung klik, drag and drop, dan tombol "Ganti foto".
- Validasi di sisi klien sebelum kirim: tipe `image/jpeg`, `image/png`, `image/webp`; ukuran maksimal 2 MB; pesan error jelas dalam Bahasa Indonesia.
- Pratinjau memakai `URL.createObjectURL`, rasio sampul 2:3 (`object-fit: cover`).
- Tombol hapus pratinjau, dan teks alternatif (`alt`) diisi judul buku.
- Form memakai `enctype="multipart/form-data"`.
- Sediakan bayangan placeholder (sampul gradasi navy dan emas dengan judul) saat buku belum punya foto.

### Backend (FastAPI)
- Install: `python-multipart` dan `Pillow`.
- Endpoint tambah dan edit buku menerima `cover: UploadFile | None = File(None)`.
- Validasi di server (jangan percaya klien):
  - Cek `content_type` dan juga isi file dengan `Pillow` (`Image.open(...).verify()`).
  - Batasi ukuran (2 MB) dengan membaca stream bertahap.
  - Tolak ekstensi di luar jpg, jpeg, png, webp.
- Penyimpanan:
  - Nama file baru yang aman dan unik (`uuid4().hex + ekstensi`). Jangan pakai nama asli dari pengguna.
  - Simpan ke `static/uploads/covers/`.
  - Opsional: ubah ukuran ke lebar maksimal 600 px dan simpan sebagai WebP.
  - Jalankan `app.mount("/static", StaticFiles(directory="static"))` bila belum ada.
- Edit buku: kalau foto diganti, hapus file sampul lama dari disk (hanya file hasil upload, di dalam folder covers). Kalau tidak ada foto baru, pertahankan yang lama.
- Hapus buku: hapus juga file sampulnya.
- Pencegahan path traversal: bangun path hanya dari nama file yang dibuat sendiri, jangan pernah dari input pengguna.

### Database (butuh persetujuan saya dulu)
- Tambah kolom `cover_path TEXT NULL` pada tabel buku (cek dulu nama tabel dan kolom yang sebenarnya).
- Tampilkan SQL migrasinya, buat `library.db.bak`, tunggu persetujuan, baru jalankan. Data lama tidak boleh hilang.
- Template menampilkan `cover_path` bila ada, kalau tidak pakai placeholder.

## LOGIN DAN GOOGLE (FASE TERPISAH, SETELAH UI SELESAI)

- Halaman login mengikuti desain Login Premium: toggle Anggota/Admin, tampilkan/sembunyikan password, validasi, state loading, toast.
- Tombol "Lanjutkan dengan Google" memakai OAuth 2.0 via Authlib. Route `/auth/google/login` dan `/auth/google/callback`.
- Cocokkan email Google dengan tabel anggota. Kalau belum terdaftar, tawarkan pendaftaran. Admin tidak boleh login lewat Google kecuali emailnya terdaftar sebagai admin.
- Siapkan `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET` di `.env`.
- Jangan mulai fase ini sebelum saya bilang lanjut.

## ANIMASI

Durasi 150 sampai 400 ms, easing `cubic-bezier(.2,.7,.2,1)`. Hover kartu naik 2 sampai 4 px, modal fade dan scale, toast slide, tombol punya state loading. Hormati `prefers-reduced-motion` (matikan animasi dekoratif dan parallax).

## RESPONSIF

Breakpoint: desktop ≥ 1024 px, tablet 640 sampai 1023 px, mobile < 640 px. Sidebar admin menjadi drawer di mobile, tabel menjadi kartu atau scroll horizontal, grid katalog 4 / 3 / 2 kolom. Target sentuh minimal 44 px.

## FASE KERJA

1. **Audit (baca saja):** ringkas struktur proyek dan rencana pemetaan desain ke template. Tunggu persetujuan.
2. **Fondasi:** `tokens.css`, `base.html`, toggle tema, font, partial navbar dan footer. Tunjukkan hasilnya.
3. **Halaman publik:** Beranda, Katalog, Detail, Tentang, 404.
4. **Auth UI:** login dan register (tanpa Google).
5. **Anggota:** dashboard, riwayat, profil.
6. **Admin:** dashboard, daftar buku, kategori, anggota, peminjaman, laporan, pengaturan.
7. **Upload foto sampul:** form tambah dan edit buku, validasi, migrasi `cover_path` (dengan persetujuan).
8. **Google OAuth** (hanya bila saya setuju).
9. **QA:** uji semua halaman di tiga ukuran layar dan dua tema, cek kontras, uji upload (file besar, file bukan gambar, file rusak, ganti dan hapus foto).

Setiap fase diakhiri ringkasan singkat: file yang dibuat atau diubah, cara menjalankan, dan hal yang perlu saya cek.

## KRITERIA SELESAI

- Tampilan sesuai desain di mode gelap dan terang.
- Semua fitur CRUD lama tetap berjalan.
- Foto sampul bisa ditambah, diganti, dan dihapus, dan tampil di katalog, detail, dan dashboard admin.
- Tidak ada file lama yang terhapus dan tidak ada data yang hilang.
- Tidak ada secret di dalam repo.
