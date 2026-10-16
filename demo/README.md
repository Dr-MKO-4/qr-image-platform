# Démo statique de QR Image Platform

Version de démonstration sans serveur : la même interface que l'application Flask (`app.py`),
mais l'optimisation de l'image et la génération du QR code se font dans le navigateur.

- `src/engine.js` reprend les règles de `app.py` : extensions autorisées, 10 Mo maximum,
  optimisation JPEG (1920 px, qualité 85 à 20, 500 Ko visés), QR code en correction M
  (10 px par module, marge de 4), nettoyage des images de plus de 7 jours.
- La requête `POST /upload` de `static/js/app.js` est interceptée et servie localement :
  aucune image ne quitte le navigateur. Les images sont conservées dans IndexedDB,
  la page `/view/<id>` ne fonctionne donc que dans le navigateur qui a créé le QR code.
- QR code : bibliothèque `qrcode-generator` (MIT) empaquetée au build.

```bash
cd demo
npm ci
npm run build   # sortie : demo/dist (avec vercel.json pour la route /view/<id>)
```
