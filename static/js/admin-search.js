// Live search daftar buku admin (pola sama dengan search.js katalog). Tanpa JS, form GET biasa tetap bekerja.
// Server mengirim potongan HTML yang sudah di-escape Jinja; tidak ada string mentah dari pengguna di sini.
(() => {
  const form = document.getElementById("cari-form");
  const input = document.getElementById("q");
  const box = document.getElementById("hasil");
  const status = document.getElementById("cari-status");
  if (!form || !input || !box) return;

  let timer = null, ctrl = null;

  async function load(url, q) {
    clearTimeout(timer);
    if (ctrl) ctrl.abort();                       // batalkan request lama
    const mine = ctrl = new AbortController();
    history.replaceState(null, "", url);
    box.setAttribute("aria-busy", "true"); box.style.opacity = ".5"; box.style.transition = "opacity .15s";
    status.textContent = "Mencari…";
    try {
      const r = await fetch(url, { signal: mine.signal, headers: { "X-Partial": "1" }, credentials: "same-origin" });
      if (r.status === 401) { location.href = "/login?next=" + encodeURIComponent(url); return; }
      if (!r.ok) throw new Error(r.status);
      box.innerHTML = await r.text();             // HTML dari template server (sudah di-escape)
      status.textContent = q ? `Hasil untuk "${q}"` : "";
    } catch (e) {
      if (e.name === "AbortError") return;        // digantikan request yang lebih baru
      status.textContent = "Gagal memuat hasil. Periksa koneksi lalu coba lagi.";
    } finally {
      if (!mine.signal.aborted) { box.removeAttribute("aria-busy"); box.style.opacity = ""; }
    }
  }

  const search = () => {
    const q = input.value.trim();
    load(location.pathname + (q ? "?q=" + encodeURIComponent(q) : ""), q);
  };

  input.addEventListener("input", () => {
    clearTimeout(timer);
    if (input.value.trim().length === 1) return;  // minimal 2 karakter (kosong = daftar penuh)
    timer = setTimeout(search, 300);
  });
  form.addEventListener("submit", e => { e.preventDefault(); search(); });

  // Pagination: delegasi, jadi tetap aktif setelah hasil diganti. Edit/Hapus ditangani ui.js (delegasi di document).
  box.addEventListener("click", e => {
    const a = e.target.closest(".pager a[href]");
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
    e.preventDefault();
    load(a.getAttribute("href"), input.value.trim());
  });
})();
