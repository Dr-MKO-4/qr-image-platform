import "./demo.css";
import { getRecord, cleanOldImages, banner } from "./engine.js";
import "../../static/js/app.js";

banner();

const $ = (id) => document.getElementById(id);
const id = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");

function notFound() {
  const card = document.querySelector(".share-card");
  card.className = "share-card notfound";
  card.removeAttribute("aria-labelledby");
  card.innerHTML =
    '<h1>Image non trouvée ou expirée</h1>' +
    "<p>Le lien ne correspond à aucune image, ou celle-ci a dépassé sa durée de conservation de 7 jours.</p>" +
    '<p class="sub">Dans cette démo, les images restent dans le navigateur qui les a créées : ' +
    "un autre appareil (par exemple le téléphone qui scanne le QR code) ne peut pas les ouvrir.</p>" +
    '<a class="btn btn-primary" href="/">Créer mon QR code</a>';
  document.title = "Image non trouvée · QR Image Platform";
}

(async () => {
  await cleanOldImages();
  const rec = id ? await getRecord(id) : null;
  if (!rec) return notFound();
  const t = rec.upload_time || "";
  const img = $("sharedImg");
  const imgUrl = URL.createObjectURL(rec.image);
  const qrUrl = URL.createObjectURL(rec.qr);
  document.title = `${rec.original_name} · QR Image Platform`;
  img.alt = `Image partagée : ${rec.original_name}`;
  img.addEventListener("load", () => { $("dims").textContent = `${img.naturalWidth} × ${img.naturalHeight} px`; });
  img.addEventListener("error", () => { $("dims").textContent = "n/d"; });
  img.src = imgUrl;
  $("imgTitle").textContent = rec.original_name;
  if (t.length >= 10) $("imgSub").textContent = `Partagée via QR Image Platform le ${t.slice(8, 10)}/${t.slice(5, 7)}/${t.slice(0, 4)}.`;
  $("addedAt").textContent = t.length >= 16 ? `${t.slice(8, 10)}/${t.slice(5, 7)}/${t.slice(0, 4)} · ${t.slice(11, 16)}` : t.slice(0, 10);
  $("weight").textContent = rec.file_size ? `${Math.round(rec.file_size / 1024)} Ko` : "n/d";
  $("qrImg").src = qrUrl;
  $("qrBig").href = qrUrl;
  $("dlImage").href = imgUrl;
  $("dlImage").setAttribute("download", rec.original_name);
  $("dlQr").href = qrUrl;
  $("dlQr").setAttribute("download", `qr_code_${rec.id}.png`);
})();
