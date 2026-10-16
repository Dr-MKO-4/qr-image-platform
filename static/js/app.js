/* QR Image Platform — interactions (thème, envoi, copie). Vanilla JS, sans dépendance. */
(function () {
  "use strict";

  var root = document.documentElement;

  /* ---------- Thème clair / sombre ---------- */
  var toggle = document.getElementById("themeToggle");
  function applyTheme(theme) {
    root.dataset.theme = theme;
    if (toggle) {
      toggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
      toggle.setAttribute("aria-label", theme === "dark" ? "Activer le thème clair" : "Activer le thème sombre");
    }
  }
  applyTheme(root.dataset.theme === "dark" ? "dark" : "light");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = root.dataset.theme === "dark" ? "light" : "dark";
      applyTheme(next);
      try { localStorage.setItem("theme", next); } catch (e) { /* stockage indisponible */ }
    });
  }

  /* ---------- Toast + copie ---------- */
  var toast = document.getElementById("toast");
  var toastTimer;
  function showToast(msg) {
    if (!toast) return;
    toast.querySelector("span").textContent = msg;
    toast.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("is-visible"); }, 2200);
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy") ? resolve() : reject(); } catch (e) { reject(e); }
      document.body.removeChild(ta);
    });
  }

  function bindCopy(btn, getText) {
    var label = btn.querySelector(".label");
    var original = label ? label.textContent : "";
    btn.addEventListener("click", function () {
      copyText(getText()).then(function () {
        btn.classList.add("is-done");
        if (label) label.textContent = "Lien copié";
        showToast("Lien copié dans le presse-papiers");
        setTimeout(function () {
          btn.classList.remove("is-done");
          if (label) label.textContent = original;
        }, 2000);
      }).catch(function () {
        showToast("Copie impossible : sélectionnez le lien manuellement");
      });
    });
  }

  document.querySelectorAll("[data-copy-current]").forEach(function (btn) {
    bindCopy(btn, function () { return window.location.href; });
  });

  /* ---------- Page d'accueil : envoi d'image ---------- */
  var fileInput = document.getElementById("imageFile");
  var dropzone = document.getElementById("uploadZone");
  if (!fileInput || !dropzone) return;

  var MAX_BYTES = 10 * 1024 * 1024;
  var errorBox = document.getElementById("errorMsg");
  var errorText = document.getElementById("errorText");
  var preview = document.getElementById("preview");
  var previewImg = document.getElementById("previewImg");
  var previewName = document.getElementById("previewName");
  var previewMeta = document.getElementById("previewMeta");
  var progressBar = document.getElementById("progressBar");
  var progressTrack = document.getElementById("progressTrack");
  var statusText = document.getElementById("statusText");
  var pickerArea = document.getElementById("pickerArea");
  var result = document.getElementById("result");
  var qrPreview = document.getElementById("qrPreview");
  var viewLink = document.getElementById("viewLink");
  var downloadLink = document.getElementById("downloadQrLink");
  var shareUrl = document.getElementById("shareUrl");
  var copyBtn = document.getElementById("copyLinkBtn");
  var resetBtn = document.getElementById("resetBtn");
  var objectUrl = null;
  var busy = false;

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " o";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " Ko";
    return (bytes / (1024 * 1024)).toFixed(1).replace(".", ",") + " Mo";
  }

  function showError(msg) {
    errorText.textContent = msg;
    errorBox.hidden = false;
  }
  function hideError() {
    errorBox.hidden = true;
    errorText.textContent = "";
  }

  function setProgress(pct, label) {
    progressBar.classList.remove("is-indeterminate");
    progressBar.style.width = pct + "%";
    progressTrack.setAttribute("aria-valuenow", String(Math.round(pct)));
    if (label) statusText.textContent = label;
  }
  function setIndeterminate(label) {
    progressBar.classList.add("is-indeterminate");
    progressTrack.removeAttribute("aria-valuenow");
    statusText.textContent = label;
  }

  function showPreview(file) {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(file);
    previewImg.src = objectUrl;
    previewImg.alt = "Aperçu de " + file.name;
    previewName.textContent = file.name;
    previewMeta.textContent = formatSize(file.size);
    setProgress(0, "Préparation de l'envoi…");
    progressTrack.hidden = false;
    preview.hidden = false;
  }

  function reset() {
    result.hidden = true;
    pickerArea.hidden = false;
    preview.hidden = true;
    hideError();
    fileInput.value = "";
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
    fileInput.focus();
  }

  function showResult(data, file) {
    qrPreview.src = data.qr_url;
    qrPreview.alt = "QR code menant à l'image " + file.name;
    viewLink.href = data.view_url;
    downloadLink.href = data.download_qr_url;
    shareUrl.value = data.view_url;
    pickerArea.hidden = true;
    result.hidden = false;
    // relance l'animation d'entrée à chaque nouveau résultat
    result.style.animation = "none";
    void result.offsetWidth;
    result.style.animation = "";
    document.getElementById("resultTitle").focus({ preventScroll: true });
  }

  function upload(file) {
    if (busy) return;
    hideError();
    if (!file) return;
    if (!file.type || file.type.indexOf("image/") !== 0) {
      showError("Fichier non supporté. Choisissez une image PNG, JPG, GIF, BMP ou WebP.");
      return;
    }
    if (file.size > MAX_BYTES) {
      showError("Le fichier est trop volumineux : la taille maximale est de 10 Mo.");
      return;
    }

    showPreview(file);
    busy = true;
    dropzone.setAttribute("aria-busy", "true");

    var form = new FormData();
    form.append("image", file);

    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/upload");
    xhr.responseType = "json";
    xhr.upload.addEventListener("progress", function (e) {
      if (!e.lengthComputable) return;
      var pct = (e.loaded / e.total) * 100;
      if (pct >= 100) setIndeterminate("Optimisation et génération du QR code…");
      else setProgress(pct, "Envoi… " + Math.round(pct) + " %");
    });
    xhr.upload.addEventListener("load", function () {
      setIndeterminate("Optimisation et génération du QR code…");
    });
    xhr.addEventListener("load", function () {
      busy = false;
      dropzone.removeAttribute("aria-busy");
      var data = xhr.response;
      if (data === null && typeof xhr.responseText === "string") {
        try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
      }
      if (xhr.status >= 200 && xhr.status < 300 && data && data.success) {
        setProgress(100, "Terminé");
        showResult(data, file);
      } else {
        progressTrack.hidden = true;
        var msg = (data && data.error) ? data.error : "Erreur serveur (" + xhr.status + ").";
        if (xhr.status === 413) msg = "Le fichier est trop volumineux : la taille maximale est de 10 Mo.";
        showError(msg);
        statusText.textContent = "Échec de l'envoi";
      }
    });
    xhr.addEventListener("error", function () {
      busy = false;
      dropzone.removeAttribute("aria-busy");
      progressTrack.hidden = true;
      statusText.textContent = "Échec de l'envoi";
      showError("Problème réseau ou serveur indisponible. Réessayez dans un instant.");
    });
    xhr.send(form);
  }

  fileInput.addEventListener("change", function () {
    if (fileInput.files && fileInput.files.length) upload(fileInput.files[0]);
  });

  var dragDepth = 0;
  dropzone.addEventListener("dragenter", function (e) {
    e.preventDefault();
    dragDepth++;
    dropzone.classList.add("is-dragover");
  });
  dropzone.addEventListener("dragover", function (e) {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
  });
  dropzone.addEventListener("dragleave", function () {
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) dropzone.classList.remove("is-dragover");
  });
  dropzone.addEventListener("drop", function (e) {
    e.preventDefault();
    dragDepth = 0;
    dropzone.classList.remove("is-dragover");
    if (e.dataTransfer && e.dataTransfer.files.length) upload(e.dataTransfer.files[0]);
  });
  // évite que le navigateur n'ouvre l'image si elle est lâchée hors de la zone
  ["dragover", "drop"].forEach(function (type) {
    window.addEventListener(type, function (e) { e.preventDefault(); });
  });

  if (copyBtn) bindCopy(copyBtn, function () { return shareUrl.value; });
  if (shareUrl) shareUrl.addEventListener("focus", function () { shareUrl.select(); });
  if (resetBtn) resetBtn.addEventListener("click", reset);
})();
