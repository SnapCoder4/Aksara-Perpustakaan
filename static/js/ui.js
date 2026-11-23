// Interaksi umum: navbar, sidebar, dropdown, modal konfirmasi, reveal, counter, validasi form.
(function () {
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.documentElement.classList.remove("no-js");

  // Navbar menebal setelah scroll 40px + menu mobile
  var nav = document.querySelector(".navbar");
  if (nav) {
    var onScroll = function () { nav.classList.toggle("scrolled", window.scrollY > 40); };
    onScroll(); window.addEventListener("scroll", onScroll, { passive: true });
  }
  document.addEventListener("click", function (e) {
    var burger = e.target.closest("[data-nav-toggle]");
    if (burger && nav) { var o = nav.classList.toggle("open"); burger.setAttribute("aria-expanded", o); }

    // Dropdown
    var dd = e.target.closest("[data-dropdown]");
    document.querySelectorAll("[data-dropdown].open").forEach(function (d) { if (d !== dd) d.classList.remove("open"); });
    if (dd && e.target.closest("[data-dropdown-btn]")) {
      var open = dd.classList.toggle("open");
      dd.querySelector("[data-dropdown-btn]").setAttribute("aria-expanded", open);
    }

    // Sidebar: lipat (desktop) dan drawer (mobile)
    var shell = document.querySelector(".shell");
    if (shell) {
      if (e.target.closest("[data-side-collapse]")) {
        var c = shell.classList.toggle("collapsed");
        try { localStorage.setItem("aksara-side", c ? "1" : "0"); } catch (x) {}
      }
      if (e.target.closest("[data-side-open]")) shell.classList.add("open");
      if (e.target.closest("[data-side-close]")) shell.classList.remove("open");
    }

    // Tampilkan/sembunyikan kata sandi
    var pw = e.target.closest("[data-toggle-pw]");
    if (pw) {
      var inp = document.querySelector(pw.getAttribute("data-toggle-pw"));
      var show = inp.type === "password";
      inp.type = show ? "text" : "password";
      pw.setAttribute("aria-pressed", show);
      pw.setAttribute("aria-label", show ? "Sembunyikan kata sandi" : "Tampilkan kata sandi");
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") document.querySelectorAll("[data-dropdown].open").forEach(function (d) { d.classList.remove("open"); });
  });
  try { if (localStorage.getItem("aksara-side") === "1") { var s = document.querySelector(".shell"); if (s) s.classList.add("collapsed"); } } catch (e) {}

  // Muncul saat scroll + angka statistik naik saat terlihat
  function count(el) {
    var end = parseInt(el.getAttribute("data-count"), 10) || 0;
    if (reduce || end < 2) { el.textContent = end.toLocaleString("id-ID"); return; }
    var t0 = performance.now(), dur = 1100;
    (function step(t) {
      var p = Math.min(1, (t - t0) / dur), v = Math.round(end * (1 - Math.pow(1 - p, 3)));
      el.textContent = v.toLocaleString("id-ID");
      if (p < 1) requestAnimationFrame(step);
    })(t0);
  }
  var targets = document.querySelectorAll("[data-reveal], [data-count]");
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        en.target.classList.add("in");
        if (en.target.hasAttribute("data-count")) count(en.target);
        io.unobserve(en.target);
      });
    }, { threshold: .15 });
    targets.forEach(function (t) { io.observe(t); });
  } else {
    targets.forEach(function (t) { t.classList.add("in"); if (t.hasAttribute("data-count")) count(t); });
  }

  // Modal konfirmasi untuk form yang berbahaya (hapus, dll.)
  var dlg = document.getElementById("confirm-modal");
  var pending = null;
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (f.hasAttribute("data-confirm") && dlg && dlg.showModal && !f._ok) {
      e.preventDefault();
      pending = f;
      dlg.querySelector("[data-modal-text]").textContent = f.getAttribute("data-confirm");
      dlg.showModal();
      return;
    }
    // Validasi sisi klien sederhana + status loading
    if (f.hasAttribute("data-validate")) {
      var bad = false;
      f.querySelectorAll("[required]").forEach(function (i) {
        var box = i.closest(".fld, .field");
        var err = box && box.parentElement.querySelector("[data-err]") || (box && box.querySelector("[data-err]"));
        var empty = !i.value.trim();
        if (box) box.classList.toggle("bad", empty);
        if (box && box.classList.contains("field")) box.classList.toggle("has-error", empty);
        if (err) err.hidden = !empty;
        if (empty) bad = true;
      });
      if (bad) {
        e.preventDefault();
        var g = f.closest(".glass");
        if (g) { g.classList.remove("shake"); void g.offsetWidth; g.classList.add("shake"); }
        for (var k = 0; k < f.elements.length; k++) { if (f.elements[k].required && !f.elements[k].value.trim()) { f.elements[k].focus(); break; } }
        return;
      }
    }
    var btn = f.querySelector("[data-loading-btn]");
    if (btn) { btn.setAttribute("aria-busy", "true"); }
  });
  if (dlg) {
    dlg.addEventListener("click", function (e) {
      if (e.target.closest("[data-modal-cancel]") || e.target === dlg) { dlg.close(); pending = null; }
      if (e.target.closest("[data-modal-ok]") && pending) { var f = pending; pending = null; dlg.close(); f._ok = true; f.requestSubmit ? f.requestSubmit() : f.submit(); }
    });
  }
})();
