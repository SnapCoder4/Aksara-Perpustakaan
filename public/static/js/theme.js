// Tema: gelap (awal) atau terang. Pilihan disimpan di localStorage.
(function () {
  var root = document.documentElement;
  function read() { try { return localStorage.getItem("aksara-theme"); } catch (e) { return null; } }
  function write(v) { try { localStorage.setItem("aksara-theme", v); } catch (e) {} }
  function apply(t) {
    root.setAttribute("data-theme", t);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
      b.textContent = t === "dark" ? "Mode terang" : "Mode gelap";
      b.setAttribute("aria-pressed", t === "dark" ? "true" : "false");
    });
  }
  apply(read() === "light" ? "light" : "dark");
  document.addEventListener("click", function (e) {
    if (!e.target.closest("[data-theme-toggle]")) return;
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    write(next);
    apply(next);
  });
})();
