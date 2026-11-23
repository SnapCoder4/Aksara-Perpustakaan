// Dropzone sampul buku: pilih/ambil foto -> editor crop 2:3 (Cropper.js) -> pratinjau -> unggah dengan progress.
// Foto asli tidak pernah diunggah; hanya hasil crop 600x900 (WebP/JPEG) yang masuk ke field "cover".
// Validasi di sini hanya kenyamanan; server memvalidasi ulang semuanya.
(function () {
  var OUT_W = 600, OUT_H = 900, QUALITY = 0.85, MAX_ORIGINAL = 25 * 1048576, MAX_ZOOM = 6;
  var dz = document.querySelector("[data-dropzone]");
  if (!dz) return;
  var form = dz.closest("form");
  var input = dz.querySelector('input[name="cover"]');
  var pick = dz.querySelector("[data-pick]"), cam = dz.querySelector("[data-cam]");
  var removeFlag = dz.querySelector('input[name="hapus_cover"]');
  var img = dz.querySelector(".dz-preview img");
  var err = dz.querySelector(".dz-err");
  var bar = dz.querySelector(".progress > i");
  var original = dz.getAttribute("data-original") || "";
  var blobUrl = null;

  var dlg = document.getElementById("crop-modal");
  var stage = document.getElementById("crop-img");
  var zoomInput = document.getElementById("crop-zoom");
  var cropErr = document.getElementById("crop-err");
  var cropper = null, srcUrl = null, minR = 1;

  function state(s) { dz.setAttribute("data-state", s); }
  function fail(msg) { dz.classList.add("err"); err.textContent = msg; }
  function clearErr() { dz.classList.remove("err"); err.textContent = ""; }
  function titleAlt() { var t = form.querySelector('[name="judul"]'); return "Sampul " + ((t && t.value) || "buku"); }

  // ---------- editor ----------
  function scaleNow() { var c = cropper.getCanvasData(); return c.width / c.naturalWidth; }
  function syncZoom() {
    var c = cropper.getCanvasData(), b = cropper.getCropBoxData();
    minR = Math.max(b.width / c.naturalWidth, b.height / c.naturalHeight);
    if (scaleNow() < minR - 1e-6) cropper.zoomTo(minR);
    zoomInput.value = Math.round(((scaleNow() / minR) - 1) / (MAX_ZOOM - 1) * 100);
  }
  function destroyCropper() {
    if (cropper) { cropper.destroy(); cropper = null; }
    if (srcUrl) { URL.revokeObjectURL(srcUrl); srcUrl = null; }
    stage.removeAttribute("src");
  }

  function openEditor(file) {
    clearErr();
    if (!file) return;
    if (!/^image\//.test(file.type)) return fail("File bukan gambar. Pilih foto JPG, PNG, atau WEBP.");
    if (file.size > MAX_ORIGINAL) return fail("Foto terlalu besar (" + (file.size / 1048576).toFixed(0) + " MB). Maksimal 25 MB.");
    cropErr.textContent = "";
    destroyCropper();
    srcUrl = URL.createObjectURL(file);
    stage.onload = function () {
      stage.onload = stage.onerror = null;
      cropper = new Cropper(stage, {
        aspectRatio: OUT_W / OUT_H, viewMode: 1, dragMode: "move", autoCropArea: 1,
        cropBoxMovable: false, cropBoxResizable: false, toggleDragModeOnDblclick: false,
        background: false, guides: true, center: false, highlight: false, checkOrientation: true,
        preview: dlg.querySelector(".crop-preview"),
        ready: syncZoom,
        zoom: function (e) {
          if (e.detail.ratio < minR - 1e-6 || e.detail.ratio > minR * MAX_ZOOM) { e.preventDefault(); return; }
          zoomInput.value = Math.round(((e.detail.ratio / minR) - 1) / (MAX_ZOOM - 1) * 100);
        }
      });
    };
    stage.onerror = function () {
      stage.onload = stage.onerror = null;
      dlg.close();
      fail("Foto tidak dapat dibaca. Coba file lain (JPG, PNG, atau WEBP).");
    };
    stage.src = srcUrl;
    dlg.showModal();
  }

  function exportCrop(done) {
    var canvas = cropper.getCroppedCanvas({ width: OUT_W, height: OUT_H, fillColor: "#fff", imageSmoothingQuality: "high" });
    if (!canvas) return done(null);
    canvas.toBlob(function (b) {
      if (b && b.type === "image/webp") return done(new File([b], "cover.webp", { type: "image/webp" }));
      canvas.toBlob(function (j) { done(j && new File([j], "cover.jpg", { type: "image/jpeg" })); }, "image/jpeg", QUALITY); // cadangan bila WebP tidak didukung
    }, "image/webp", QUALITY);
  }

  function apply(file) {
    var dt = new DataTransfer(); dt.items.add(file); input.files = dt.files;
    if (blobUrl) URL.revokeObjectURL(blobUrl);
    blobUrl = URL.createObjectURL(file);
    img.src = blobUrl; img.alt = titleAlt();
    removeFlag.value = "0";
    clearErr(); state("preview");
  }

  dlg.addEventListener("click", function (e) {
    if (!cropper) return;
    var rot = e.target.closest("[data-crop-rot]");
    if (rot) { cropper.rotate(parseInt(rot.getAttribute("data-crop-rot"), 10)); syncZoom(); return; }
    if (e.target.closest("[data-crop-reset]")) { cropper.reset(); syncZoom(); return; }
    if (e.target.closest("[data-crop-ok]")) {
      exportCrop(function (file) {
        if (!file) { cropErr.textContent = "Gagal memproses foto. Coba lagi atau pilih foto lain."; return; }
        apply(file); dlg.close();
      });
    }
  });
  dlg.querySelector("[data-crop-cancel]").addEventListener("click", function () { dlg.close(); }); // foto sebelumnya tetap dipakai
  zoomInput.addEventListener("input", function () {
    if (cropper) cropper.zoomTo(minR * (1 + (zoomInput.value / 100) * (MAX_ZOOM - 1)));
  });
  dlg.addEventListener("close", destroyCropper); // juga dipicu Esc

  // ---------- dropzone ----------
  function reset() {
    clearErr(); input.value = "";
    if (blobUrl) { URL.revokeObjectURL(blobUrl); blobUrl = null; }
    state("empty");
  }
  [pick, cam].forEach(function (el) {
    el.addEventListener("click", function (e) { e.stopPropagation(); });
    el.addEventListener("change", function () { var f = el.files[0]; el.value = ""; openEditor(f); });
  });

  dz.addEventListener("click", function (e) {
    if (e.target.closest("[data-dz-remove]")) {
      e.stopPropagation(); reset(); removeFlag.value = original ? "1" : "0"; return;
    }
    if (e.target.closest("[data-dz-cam]")) { e.stopPropagation(); cam.click(); return; }
    if (e.target.closest("[data-dz-pick],[data-dz-replace]") || dz.getAttribute("data-state") === "empty") pick.click();
  });
  dz.addEventListener("keydown", function (e) {
    if ((e.key === "Enter" || e.key === " ") && dz.getAttribute("data-state") === "empty" && e.target === dz) { e.preventDefault(); pick.click(); }
  });
  ["dragenter", "dragover"].forEach(function (n) { dz.addEventListener(n, function (e) { e.preventDefault(); dz.classList.add("drag"); }); });
  ["dragleave", "drop"].forEach(function (n) { dz.addEventListener(n, function (e) { e.preventDefault(); dz.classList.remove("drag"); }); });
  dz.addEventListener("drop", function (e) { if (e.dataTransfer.files[0]) openEditor(e.dataTransfer.files[0]); });

  // Kirim lewat XHR agar progress unggah bisa ditampilkan.
  form.addEventListener("submit", function (e) {
    if (!input.files.length || !window.XMLHttpRequest) return;
    e.preventDefault();
    var fd = new FormData(form), xhr = new XMLHttpRequest();
    state("uploading"); bar.style.width = "0";
    xhr.upload.onprogress = function (ev) { if (ev.lengthComputable) bar.style.width = Math.round(ev.loaded * 100 / ev.total) + "%"; };
    xhr.onload = function () {
      var html = xhr.responseText, url = xhr.responseURL || location.href;
      document.open(); document.write(html); document.close();
      if (url !== location.href) history.replaceState(null, "", url);
    };
    xhr.onerror = function () { state("preview"); fail("Koneksi terputus saat mengunggah. Coba lagi."); };
    xhr.open("POST", form.action || location.href);
    xhr.send(fd);
  });
})();
