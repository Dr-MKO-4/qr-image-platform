import "./demo.css";
import { installUploadMock, banner } from "./engine.js";
import "../../static/js/app.js";

installUploadMock();
banner();

/* Image d'exemple dessinée localement (paysage fictif), pour essayer sans fichier. */
function sampleImage() {
  const w = 1600, h = 1000;
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const x = c.getContext("2d");
  const sky = x.createLinearGradient(0, 0, 0, h * 0.62);
  sky.addColorStop(0, "#1b2a55"); sky.addColorStop(0.55, "#e0795b"); sky.addColorStop(1, "#f6c27a");
  x.fillStyle = sky; x.fillRect(0, 0, w, h);
  x.fillStyle = "#fff1c9"; x.beginPath(); x.arc(w * 0.68, h * 0.5, 90, 0, Math.PI * 2); x.fill();
  const hill = (y, amp, color, phase) => {
    x.fillStyle = color; x.beginPath(); x.moveTo(0, h);
    for (let i = 0; i <= w; i += 20) x.lineTo(i, y + Math.sin(i / 210 + phase) * amp + Math.sin(i / 77) * amp * 0.25);
    x.lineTo(w, h); x.closePath(); x.fill();
  };
  hill(h * 0.6, 38, "#5d3b5e", 0.4);
  hill(h * 0.7, 30, "#2f2848", 1.9);
  hill(h * 0.82, 22, "#17172b", 3.1);
  x.fillStyle = "rgba(255,255,255,.85)";
  for (let i = 0; i < 40; i++) x.fillRect((i * 397) % w, (i * 151) % (h * 0.3), 2, 2);
  return new Promise((ok) => c.toBlob((b) => ok(new File([b], "Coucher de soleil.png", { type: "image/png" })), "image/png"));
}

const btn = document.getElementById("sampleBtn");
const input = document.getElementById("imageFile");
if (btn && input) {
  btn.addEventListener("click", async () => {
    const file = await sampleImage();
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
