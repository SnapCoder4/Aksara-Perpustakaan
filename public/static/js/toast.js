// Toast: slide masuk, hilang otomatis setelah 4 detik.
window.Toast = (function () {
  function box() {
    var b = document.getElementById("toasts");
    if (!b) { b = document.createElement("div"); b.id = "toasts"; b.className = "toasts"; document.body.appendChild(b); }
    return b;
  }
  function show(message, kind) {
    var t = document.createElement("div");
    t.className = "toast " + (kind || "ok");
    t.setAttribute("role", kind === "err" ? "alert" : "status");
    var ic = document.createElement("span"); ic.className = "ic"; ic.textContent = kind === "err" ? "!" : kind === "warn" ? "!" : "✓";
    var tx = document.createElement("span"); tx.style.flex = "1"; tx.textContent = message;
    var x = document.createElement("button"); x.type = "button"; x.setAttribute("aria-label", "Tutup"); x.textContent = "×";
    t.append(ic, tx, x);
    box().appendChild(t);
    function close() { t.classList.add("out"); setTimeout(function () { t.remove(); }, 250); }
    x.addEventListener("click", close);
    setTimeout(close, 4000);
  }
  document.addEventListener("DOMContentLoaded", function () {
    var el = document.getElementById("flash-data");
    if (!el) return;
    try { JSON.parse(el.textContent).forEach(function (f) { show(f.m, f.k); }); } catch (e) {}
  });
  return { show: show };
})();
