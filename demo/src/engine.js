/*
 * QR Image Platform : moteur de la démo statique.
 *
 * Reproduit dans le navigateur ce que fait app.py côté serveur :
 *  - allowed_file()      : extensions PNG, JPG, JPEG, GIF, BMP, WebP ;
 *  - optimize_image()    : fond blanc, 1920 px maximum, JPEG de qualité 85 à 35
 *                          jusqu'à 500 Ko, puis réduction 0,8 / 0,6 / 0,4 en qualité 30,
 *                          puis qualité 20 en dernier recours ;
 *  - create_qr_code()    : correction d'erreur M, 10 px par module, marge de 4 modules ;
 *  - clean_old_images()  : suppression des images de plus de 7 jours.
 *
 * Aucune requête ne part vers un serveur : l'image et son QR code sont stockés
 * dans ce navigateur (IndexedDB, ou en mémoire si IndexedDB est indisponible).
 */
import qrcode from "qrcode-generator";

export const MAX_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "bmp", "webp"];
const MAX_SIZE_KB = 500;
const MAX_DIMENSION = 1920;
const RETENTION_MS = 7 * 24 * 3600 * 1000;

/* ---------------------------------------------------------------- utilitaires */

export function allowedFile(name) {
  const i = name.lastIndexOf(".");
  return i > 0 && ALLOWED_EXTENSIONS.includes(name.slice(i + 1).toLowerCase());
}

// Équivalent de werkzeug.utils.secure_filename
export function secureFilename(name) {
  let s = String(name || "").normalize("NFKD").replace(/[^\x00-\x7f]/g, "");
  s = s.replace(/[\/\\]/g, " ").trim().split(/\s+/).join("_");
  s = s.replace(/[^A-Za-z0-9_.-]/g, "").replace(/^[._]+|[._]+$/g, "");
  return s || "image";
}

// datetime.now().isoformat() : heure locale, sans fuseau
function isoLocal(d) {
  const p = (n, w = 2) => String(n).padStart(w, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}000`;
}

function uuid4() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

const toBlob = (canvas, type, quality) =>
  new Promise((ok, ko) => canvas.toBlob((b) => (b ? ok(b) : ko(new Error("Encodage impossible"))), type, quality));

function loadImage(blob) {
  return new Promise((ok, ko) => {
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); ok(img); };
    img.onerror = () => { URL.revokeObjectURL(url); ko(new Error("Image illisible")); };
    img.src = url;
  });
}

/* ------------------------------------------------------- optimisation (Pillow) */

function draw(img, w, h) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const ctx = c.getContext("2d");
  ctx.fillStyle = "#ffffff"; // conversion RGBA / P vers RGB sur fond blanc
  ctx.fillRect(0, 0, w, h);
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, 0, 0, w, h);
  return c;
}

export async function optimizeImage(file, maxSizeKb = MAX_SIZE_KB) {
  const img = await loadImage(file);
  let w = img.naturalWidth, h = img.naturalHeight;
  if (w > MAX_DIMENSION || h > MAX_DIMENSION) {
    const ratio = Math.min(MAX_DIMENSION / w, MAX_DIMENSION / h);
    w = Math.floor(w * ratio); h = Math.floor(h * ratio);
  }
  const canvas = draw(img, w, h);
  for (const q of [85, 75, 65, 55, 45, 35]) {
    const b = await toBlob(canvas, "image/jpeg", q / 100);
    if (b.size / 1024 <= maxSizeKb) return b;
  }
  for (const scale of [0.8, 0.6, 0.4]) {
    const c = draw(canvas, Math.floor(w * scale), Math.floor(h * scale));
    const b = await toBlob(c, "image/jpeg", 0.3);
    if (b.size / 1024 <= maxSizeKb) return b;
  }
  return toBlob(canvas, "image/jpeg", 0.2);
}

/* ------------------------------------------------------------ QR code (qrcode) */

export function createQrCode(url, size = 10, border = 4) {
  const qr = qrcode(0, "M"); // version minimale qui contient l'URL (fit=True)
  qr.addData(url);
  qr.make();
  const n = qr.getModuleCount();
  const px = (n + border * 2) * size;
  const c = document.createElement("canvas");
  c.width = px; c.height = px;
  const ctx = c.getContext("2d");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, px, px);
  ctx.fillStyle = "#000000";
  for (let r = 0; r < n; r++)
    for (let col = 0; col < n; col++)
      if (qr.isDark(r, col)) ctx.fillRect((col + border) * size, (r + border) * size, size, size);
  return toBlob(c, "image/png");
}

/* ------------------------------------------------- stockage (image_data.json) */

const memory = new Map();
let dbPromise = null;
function db() {
  if (!dbPromise) {
    dbPromise = new Promise((ok) => {
      try {
        const req = indexedDB.open("qr-image-platform-demo", 1);
        req.onupgradeneeded = () => req.result.createObjectStore("images", { keyPath: "id" });
        req.onsuccess = () => ok(req.result);
        req.onerror = () => ok(null);
        req.onblocked = () => ok(null);
      } catch (e) { ok(null); }
    });
  }
  return dbPromise;
}
function tx(store, mode, fn) {
  return db().then((d) => {
    if (!d) return null;
    return new Promise((ok) => {
      try {
        const t = d.transaction(store, mode);
        const r = fn(t.objectStore(store));
        t.oncomplete = () => ok(r && "result" in r ? r.result : true);
        t.onerror = () => ok(null);
      } catch (e) { ok(null); }
    });
  });
}

export async function saveRecord(rec) {
  memory.set(rec.id, rec);
  await tx("images", "readwrite", (s) => s.put(rec));
}

export async function getRecord(id) {
  if (memory.has(id)) return memory.get(id);
  const r = await tx("images", "readonly", (s) => s.get(id));
  return r || null;
}

export async function cleanOldImages() {
  const all = (await tx("images", "readonly", (s) => s.getAll())) || [...memory.values()];
  const now = Date.now();
  const old = all.filter((r) => now - new Date(r.upload_time).getTime() > RETENTION_MS);
  for (const r of old) {
    memory.delete(r.id);
    await tx("images", "readwrite", (s) => s.delete(r.id));
  }
  return old.length;
}

/* -------------------------------------------------------- route POST /upload */

export async function upload(file) {
  if (!file || !file.name) return { status: 400, body: { error: "Aucun fichier sélectionné" } };
  if (!allowedFile(file.name))
    return { status: 400, body: { error: "Format de fichier non supporté. Utilisez: PNG, JPG, JPEG, GIF, BMP, WebP" } };
  if (file.size > MAX_BYTES) return { status: 413, body: null };
  try {
    await cleanOldImages();
    const id = uuid4();
    const image = await optimizeImage(file);
    const viewUrl = `${location.origin}/view/${id}`;
    const qr = await createQrCode(viewUrl);
    await saveRecord({
      id,
      original_name: secureFilename(file.name),
      upload_time: isoLocal(new Date()),
      view_url: viewUrl,
      file_size: image.size,
      image,
      qr,
    });
    return {
      status: 200,
      body: {
        success: true,
        image_id: id,
        view_url: viewUrl,
        qr_url: URL.createObjectURL(qr),
        download_qr_url: URL.createObjectURL(qr),
      },
    };
  } catch (e) {
    return { status: 500, body: { error: `Erreur lors du traitement: ${e.message}` } };
  }
}

/* -------------------- interception de XMLHttpRequest pour POST /upload seulement */

export function installUploadMock() {
  const XP = XMLHttpRequest.prototype;
  const open = XP.open, send = XP.send;
  XP.open = function (method, url) {
    const u = new URL(url, location.href);
    if (u.origin === location.origin && u.pathname === "/upload" && String(method).toUpperCase() === "POST") {
      this.__demo = true;
      return;
    }
    this.__demo = false;
    return open.apply(this, arguments);
  };
  XP.send = function (body) {
    if (!this.__demo) return send.apply(this, arguments);
    const xhr = this;
    const file = body instanceof FormData ? body.get("image") : null;
    const total = file && file.size ? file.size : 1;
    const state = { status: 0, response: null, responseText: "" };
    ["status", "response", "responseText"].forEach((k) =>
      Object.defineProperty(xhr, k, { configurable: true, get: () => state[k] }));
    Object.defineProperty(xhr, "readyState", { configurable: true, get: () => (state.status ? 4 : 1) });
    const ev = (target, type, loaded) =>
      target.dispatchEvent(new ProgressEvent(type, { lengthComputable: loaded != null, loaded: loaded || 0, total }));

    // Simulation de l'envoi (aucun octet ne quitte le navigateur)
    const steps = [0.2, 0.45, 0.7, 0.9, 1];
    steps.forEach((f, i) => setTimeout(() => {
      ev(xhr.upload, "progress", Math.round(total * f));
      if (f === 1) {
        ev(xhr.upload, "load", total);
        upload(file).then((res) => {
          state.status = res.status;
          state.responseText = res.body == null ? "" : JSON.stringify(res.body);
          state.response = xhr.responseType === "json" ? res.body : state.responseText;
          if (res.body && res.body.image_id) {
            const a = document.getElementById("downloadQrLink");
            if (a) a.setAttribute("download", `qr_code_${res.body.image_id}.png`);
          }
          xhr.dispatchEvent(new Event("readystatechange"));
          ev(xhr, "load");
          ev(xhr, "loadend");
        });
      }
    }, 140 * (i + 1)));
  };
}

/* ------------------------------------------------ bandeau « Démo · données simulées » */

export function banner() {
  if (document.getElementById("__demo-badge")) return;
  const b = document.createElement("div");
  b.id = "__demo-badge";
  b.setAttribute("role", "note");
  b.title = "Démo statique : l'image est traitée et conservée dans ce navigateur, rien n'est envoyé à un serveur.";
  b.textContent = "Démo · données simulées";
  document.body.appendChild(b);
}
