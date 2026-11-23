// Editor gambar hero di beranda (hanya dimuat untuk admin). Hak akses dicek ulang di server pada setiap endpoint.
// Pratinjau memakai /admin/hero/preview (rembg di server); simpan memakai /admin/hero/{n} yang sama dengan halaman admin.
(function () {
  var stage = document.querySelector("[data-hero-admin]");
  var dlg = document.getElementById("hero-modal");
  if (!stage || !dlg) return;
  var HDR = { "X-Requested-With": "fetch" };
  var MAX = 8 * 1048576, TYPES = ["image/jpeg", "image/png", "image/webp"];
  var rembgOk = stage.getAttribute("data-rembg") === "1";
  var $ = function (id) { return document.getElementById(id); };
  var el = { slot: $("hm-slot"), drop: $("hm-drop"), pick: $("hm-pick"), file: $("hm-file"), rembg: $("hm-rembg"), note: $("hm-rembg-note"),
    before: $("hm-before"), after: $("hm-after"), status: $("hm-status"), err: $("hm-err"), asis: $("hm-asis"),
    reset: $("hm-reset"), cancel: $("hm-cancel"), save: $("hm-save") };
  var slot = 0, book = null, orig = null, processed = null, urls = [], ctrl = null, busy = false, failed = false, resetArm = null;

  function revoke() { urls.forEach(function (u) { URL.revokeObjectURL(u); }); urls = []; }
  function blobUrl(b) { var u = URL.createObjectURL(b); urls.push(u); return u; }
  function showImg(panel, src, alt) {
    panel.replaceChildren();
    var i = document.createElement("img"); i.src = src; i.alt = alt || ""; panel.append(i);
  }
  function showText(panel, text) {
    panel.replaceChildren();
    var s = document.createElement("span"); s.className = "muted"; s.textContent = text; panel.append(s);
  }
  function setBusy(on, msg) {
    busy = on; el.after.classList.toggle("busy", on);
    el.status.textContent = on ? msg : "";
    el.rembg.disabled = on || !rembgOk; el.pick.disabled = on; el.reset.disabled = on; refresh();
  }
  function setErr(msg, offerAsIs) { el.err.textContent = msg || ""; el.asis.hidden = !offerAsIs; failed = !!offerAsIs; refresh(); }
  function wantsRemoval() { return rembgOk && el.rembg.checked; }
  function refresh() {
    el.save.disabled = busy || !orig || failed || (wantsRemoval() && !processed);
    el.save.textContent = busy ? "Memproses..." : "Simpan";
  }
  function currentImg() { var i = book && book.querySelector("img"); return i ? i.getAttribute("src") : null; }

  function open(b) {
    book = b; slot = parseInt(b.getAttribute("data-slot"), 10);
    orig = processed = null; failed = false; revoke(); setErr("");
    el.slot.textContent = slot; el.file.value = "";
    el.rembg.checked = rembgOk; el.rembg.disabled = !rembgOk; el.note.hidden = rembgOk;
    el.reset.hidden = b.getAttribute("data-has") !== "1"; el.reset.textContent = "Kembalikan ke bawaan"; resetArm = null;
    showText(el.before, "Pilih foto");
    var cur = currentImg(); if (cur) showImg(el.after, cur, "Gambar hero saat ini"); else showText(el.after, "Belum ada gambar (memakai sampul bawaan)");
    setBusy(false); dlg.showModal();
  }

  function preview() {
    if (ctrl) ctrl.abort();
    ctrl = new AbortController(); processed = null; failed = false; setErr("");
    showText(el.after, "");
    setBusy(true, "Menghapus latar belakang... Unggahan pertama bisa belasan detik karena model diunduh.");
    var fd = new FormData(); fd.append("gambar", orig);
    var mine = ctrl;
    fetch("/admin/hero/preview", { method: "POST", body: fd, headers: HDR, signal: mine.signal, credentials: "same-origin" })
      .then(function (r) {
        if (r.ok) return r.blob().then(function (b) { processed = b; showImg(el.after, blobUrl(b), "Hasil tanpa latar"); });
        return r.json().catch(function () { return {}; }).then(function (j) { throw new Error(j.error || "Gagal memproses foto (" + r.status + ")."); });
      })
      .catch(function (e) {
        if (e.name === "AbortError") return;
        showImg(el.after, blobUrl(orig), "Foto asli");
        setErr(e.message + " Anda bisa menyimpan foto apa adanya.", true);
      })
      .then(function () { if (ctrl === mine) setBusy(false); });
  }

  function choose(f) {
    setErr("");
    if (!f) return;
    if (TYPES.indexOf(f.type) === -1) return setErr("File bukan gambar yang didukung. Gunakan JPG, PNG, atau WEBP.");
    if (f.size > MAX) return setErr("Ukuran file maksimal 8 MB.");
    if (ctrl) ctrl.abort();
    revoke(); orig = f; processed = null; failed = false;
    showImg(el.before, blobUrl(f), "Foto asli");
    if (wantsRemoval()) preview(); else { showImg(el.after, blobUrl(f), "Foto asli"); setBusy(false); }
  }

  function send(url, fd, onOk) {
    setBusy(true, "Menyimpan...");
    fetch(url, { method: "POST", body: fd, headers: Object.assign({ Accept: "application/json" }, HDR), credentials: "same-origin" })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok || !j.ok) throw new Error(j.error || "Gagal menyimpan (" + r.status + ")."); return j; }); })
      .then(function (j) { onOk(j); setBusy(false); dlg.close(); })
      .catch(function (e) { setBusy(false); setErr(e.message, false); });
  }

  function put(url) {  // ganti isi slot di hero tanpa muat ulang
    book.querySelectorAll("img, .cover").forEach(function (n) { n.remove(); });
    var first = book.firstChild, node;
    if (url) {
      node = document.createElement("img"); node.src = url; node.alt = ""; node.width = 210; node.height = 315; node.loading = "eager";
    } else {
      node = document.createElement("div"); node.className = "cover cv-" + (slot * 2);
      var s = document.createElement("span"); s.className = "ct"; s.textContent = "Aksara"; node.append(s);
    }
    book.insertBefore(node, first);
    book.setAttribute("data-has", url ? "1" : "0");
  }

  function save(asIs) {
    if (!orig) return;
    var fd = new FormData(), useProcessed = !asIs && wantsRemoval() && processed;
    fd.append("gambar", useProcessed ? new File([processed], "hero.png", { type: "image/png" }) : orig);
    fd.append("hapus_latar", "0");  // pembersihan latar sudah dilakukan di pratinjau; server tetap memvalidasi file
    send("/admin/hero/" + slot, fd, function (j) { put(j.url); });
  }

  // buka editor: klik atau Enter/Spasi
  stage.addEventListener("click", function (e) { var b = e.target.closest(".hero-edit"); if (b) open(b); });
  stage.addEventListener("keydown", function (e) {
    var b = e.target.closest(".hero-edit");
    if (b && b === e.target && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); open(b); }
  });

  el.pick.addEventListener("click", function () { el.file.click(); });
  el.file.addEventListener("change", function () { choose(el.file.files[0]); });
  ["dragenter", "dragover"].forEach(function (n) { el.drop.addEventListener(n, function (e) { e.preventDefault(); el.drop.classList.add("drag"); }); });
  ["dragleave", "drop"].forEach(function (n) { el.drop.addEventListener(n, function (e) { e.preventDefault(); el.drop.classList.remove("drag"); }); });
  el.drop.addEventListener("drop", function (e) { if (!busy) choose(e.dataTransfer.files[0]); });
  el.rembg.addEventListener("change", function () {
    if (!orig) return refresh();
    setErr("");
    if (wantsRemoval()) { if (processed) showImg(el.after, blobUrl(processed), "Hasil tanpa latar"); else preview(); }
    else { if (ctrl) ctrl.abort(); setBusy(false); showImg(el.after, blobUrl(orig), "Foto asli"); }
  });
  el.save.addEventListener("click", function () { save(false); });
  el.asis.addEventListener("click", function () { save(true); });
  el.cancel.addEventListener("click", function () { dlg.close(); });
  el.reset.addEventListener("click", function () {  // dua langkah agar tidak terhapus tak sengaja
    if (!resetArm) {
      el.reset.textContent = "Yakin? Klik lagi"; resetArm = setTimeout(function () { resetArm = null; el.reset.textContent = "Kembalikan ke bawaan"; }, 4000); return;
    }
    clearTimeout(resetArm); resetArm = null;
    send("/admin/hero/" + slot + "/hapus", new FormData(), function () { put(null); });
  });
  dlg.addEventListener("close", function () { if (ctrl) ctrl.abort(); clearTimeout(resetArm); revoke(); busy = false; });
})();
