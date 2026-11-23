// Pencarian katalog real-time. Tanpa JS, form GET biasa tetap bekerja.
(() => {
  const form = document.getElementById("cari-form");
  const input = document.getElementById("q");
  const box = document.getElementById("hasil");
  const pager = document.getElementById("cari-pager");
  const status = document.getElementById("cari-status");
  if (!form || !input || !box || !pager) return;

  let timer = null, ctrl = null, page = Number(new URLSearchParams(location.search).get("page")) || 1;

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;   // teks pengguna selalu lewat textContent
    return n;
  };

  function cover(b, size) {
    const c = el("div", `cover cv-${b.cv} ${size || ""}`.trim());
    if (b.cover) {
      const img = el("img");
      img.src = /^https?:\/\//.test(b.cover) ? b.cover : "/static/uploads/covers/" + encodeURIComponent(b.cover);
      img.alt = "Sampul " + b.judul;
      img.loading = "lazy";
      c.append(img);
    } else {
      c.append(el("span", "ct", b.kategori || "Buku"), el("span", "cn", b.judul), el("span", "ca", b.penulis));
    }
    return c;
  }

  const avail = b => el("span", "avail " + (b.stok > 0 ? "ok" : "warn"), b.stok > 0 ? `Tersedia ${b.stok}` : "Dipinjam semua");

  function card(b) {
    const a = el("a", "book-card"); a.href = "/buku/" + encodeURIComponent(b.kode);
    const s = el("span", "stack"); s.style.gap = "3px";
    s.append(el("span", "t", b.judul), el("span", "a", b.penulis + (b.tahun ? " · " + b.tahun : "")), avail(b));
    a.append(cover(b), s);
    return a;
  }

  function row(b) {
    const a = el("a", "book-row"); a.href = "/buku/" + encodeURIComponent(b.kode);
    const m = el("span", "meta"), t = el("span", null, b.judul);
    t.style.cssText = "font-weight:600;font-size:16px";
    const d = el("span", "muted", b.penulis + (b.tahun ? " · " + b.tahun : "") + (b.penerbit ? " · " + b.penerbit : ""));
    d.style.fontSize = "14px";
    m.append(t, d);
    const k = el("span", "muted hide-m", b.kategori || ""); k.style.fontSize = "13px";
    a.append(cover(b, "sm"), m, k, avail(b));
    return a;
  }

  function message(text, cls) {
    box.replaceChildren();
    const d = el("div", "empty card " + (cls || ""));
    d.append(el("span", "serif", text));
    box.append(d);
  }

  function renderPager(hasNext) {
    pager.replaceChildren();
    const mk = (label, dir) => {
      const a = el("a", null, label); a.href = "#";
      a.addEventListener("click", e => { e.preventDefault(); page += dir; run(true); });
      return a;
    };
    if (page > 1) pager.append(mk("‹ Sebelumnya", -1));
    const cur = el("span", "on", String(page)); cur.setAttribute("aria-current", "page");
    pager.append(cur);
    if (hasNext) pager.append(mk("Berikutnya ›", 1));
    pager.hidden = page === 1 && !hasNext;
  }

  function params() {
    const p = new URLSearchParams(location.search);
    p.delete("q"); p.delete("page");
    const q = input.value.trim();
    if (q) p.set("q", q);
    if (page > 1) p.set("page", page);
    return p;
  }

  async function run(scroll) {
    clearTimeout(timer);
    if (ctrl) ctrl.abort();                       // batalkan request lama
    ctrl = new AbortController();
    const q = input.value.trim();
    const p = params();
    history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : ""));
    box.setAttribute("aria-busy", "true"); box.style.opacity = ".5";
    status.textContent = "Mencari…";
    try {
      const r = await fetch("/api/katalog?" + p, { signal: ctrl.signal, headers: { Accept: "application/json" } });
      if (!r.ok) throw new Error(r.status);
      const data = await r.json();
      box.replaceChildren();
      if (!data.items.length) message("Tidak ada buku yang cocok");
      else {
        const list = el("div", box.dataset.view === "list" ? "catalog-list" : "catalog-grid");
        list.append(...data.items.map(box.dataset.view === "list" ? row : card));
        box.append(list);
      }
      renderPager(data.has_next);
      status.textContent = q ? `Hasil untuk "${q}"` : "";
      if (scroll) box.scrollIntoView({ block: "start", behavior: "smooth" });
    } catch (e) {
      if (e.name === "AbortError") return;        // digantikan request yang lebih baru
      message("Gagal memuat hasil. Periksa koneksi lalu coba lagi.", "error");
      pager.hidden = true; status.textContent = "";
    } finally {
      if (!ctrl.signal.aborted) { box.removeAttribute("aria-busy"); box.style.opacity = ""; }
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    const n = input.value.trim().length;
    if (n === 1) return;                          // minimal 2 karakter (kosong = kembali ke daftar)
    timer = setTimeout(() => { page = 1; run(); }, 300);
  });
  form.addEventListener("submit", e => { e.preventDefault(); page = 1; run(); });
})();
