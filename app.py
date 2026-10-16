#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plateforme Web QR Image - Déployable sur Render
Convertit des images en codes QR accessibles partout dans le monde
"""

from flask import Flask, request, render_template, jsonify, send_file, url_for, redirect
import qrcode
import os
import uuid
import time
from PIL import Image
import io
import base64
from werkzeug.utils import secure_filename
import hashlib
import secrets
import json
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max
# Clé lue depuis l'environnement ; à défaut, valeur aléatoire générée au démarrage
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

# Configuration pour le stockage (en production, utilisez une base de données)
IMAGES_DIR = 'static/images'
QR_DIR = 'static/qr_codes'
DATA_FILE = 'image_data.json'

# Créer les dossiers nécessaires
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(QR_DIR, exist_ok=True)
os.makedirs('static', exist_ok=True)

# Extensions autorisées
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def allowed_file(filename):
    """Vérifie si l'extension du fichier est autorisée"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_image_data():
    """Charge les données des images depuis le fichier JSON"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        print(f"Erreur chargement des données: {DATA_FILE} non trouvé ou corrompu.")
        pass
    return {}

def save_image_data(data):
    """Sauvegarde les données des images dans le fichier JSON"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erreur sauvegarde: {e}")

def clean_old_images():
    """Nettoie les anciennes images (plus de 7 jours)"""
    try:
        data = load_image_data()
        current_time = datetime.now()
        to_remove = []
        
        for image_id, info in data.items():
            upload_time = datetime.fromisoformat(info.get('upload_time', '2024-01-01T00:00:00'))
            if current_time - upload_time > timedelta(days=7):
                to_remove.append(image_id)
                
                # Supprimer les fichiers
                try:
                    if os.path.exists(info.get('image_path', '')):
                        os.remove(info['image_path'])
                    if os.path.exists(info.get('qr_path', '')):
                        os.remove(info['qr_path'])
                except:
                    pass
        
        # Mettre à jour les données
        for image_id in to_remove:
            data.pop(image_id, None)
            
        if to_remove:
            save_image_data(data)
            print(f"Nettoyage: {len(to_remove)} images supprimées")
            
    except Exception as e:
        print(f"Erreur nettoyage: {e}")

def optimize_image(image_file, max_size_kb=500):
    """Optimise une image pour réduire sa taille"""
    try:
        print(f"Début optimisation, taille max: {max_size_kb}KB")
        
        # Reset file pointer et lire l'image
        image_file.seek(0)
        img = Image.open(image_file)
        print(f"Image originale: {img.size}, mode: {img.mode}")
        
        # Convertir en RGB si nécessaire
        if img.mode in ('RGBA', 'LA', 'P'):
            print(f"Conversion du mode {img.mode} vers RGB")
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1] if len(img.split()) > 3 else None)
            img = background
        
        # Redimensionner si l'image est trop grande
        max_dimension = 1920
        if img.width > max_dimension or img.height > max_dimension:
            print(f"Redimensionnement de {img.size}")
            ratio = min(max_dimension / img.width, max_dimension / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            print(f"Nouvelle taille: {img.size}")
        
        # Essayer différentes qualités JPEG
        for quality in [85, 75, 65, 55, 45, 35]:
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=quality, optimize=True)
            current_size_kb = len(output.getvalue()) / 1024
            print(f"Qualité {quality}: {current_size_kb:.1f}KB")
            
            if current_size_kb <= max_size_kb:
                output.seek(0)
                print(f"Optimisation réussie: {current_size_kb:.1f}KB")
                return output
        
        # Si toujours trop grande, réduire encore la taille
        for scale in [0.8, 0.6, 0.4]:
            new_size = (int(img.width * scale), int(img.height * scale))
            img_scaled = img.resize(new_size, Image.Resampling.LANCZOS)
            
            output = io.BytesIO()
            img_scaled.save(output, format='JPEG', quality=30, optimize=True)
            current_size_kb = len(output.getvalue()) / 1024
            print(f"Échelle {scale}: {current_size_kb:.1f}KB")
            
            if current_size_kb <= max_size_kb:
                output.seek(0)
                print(f"Optimisation réussie avec mise à l'échelle: {current_size_kb:.1f}KB")
                return output
        
        # Dernière tentative avec qualité minimale
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=20, optimize=True)
        output.seek(0)
        final_size_kb = len(output.getvalue()) / 1024
        print(f"Optimisation finale: {final_size_kb:.1f}KB")
        return output
        
    except Exception as e:
        print(f"Erreur optimisation: {e}")
        import traceback
        traceback.print_exc()
        # En cas d'erreur, retourner le fichier original
        image_file.seek(0)
        return image_file

def create_qr_code(url, size=10):
    """Crée un code QR pour l'URL donnée"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=size,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        qr_image = qr.make_image(fill_color="black", back_color="white")
        return qr_image
    except Exception as e:
        print(f"Erreur création QR: {e}")
        return None

def create_templates():
    """Crée les templates HTML"""
    os.makedirs('templates', exist_ok=True)
    
    # En-tête commun (polices, styles, favicon, thème appliqué avant le rendu)
    head_common = r'''  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#141b34">
  <link rel="icon" type="image/png" href="{{ url_for('static', filename='brand/favicon.png') }}">
  <link rel="apple-touch-icon" href="{{ url_for('static', filename='brand/apple-touch-icon.png') }}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}">
  <script>
    (function () {
      var t = null;
      try { t = localStorage.getItem('theme'); } catch (e) {}
      if (t !== 'dark' && t !== 'light') {
        t = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
      }
      document.documentElement.dataset.theme = t;
    })();
  </script>'''

    topbar = r'''  <header class="topbar">
    <div class="wrap">
      <a class="brand" href="{{ url_for('index') }}" aria-label="QR Image Platform, accueil">
        <span class="brand-mark" aria-hidden="true"></span>
        <span class="brand-name">QR Image <span>Platform</span></span>
      </a>
      <button class="theme-toggle" id="themeToggle" type="button" aria-label="Activer le thème sombre" aria-pressed="false">
        <svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
        <svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      </button>
    </div>
  </header>'''

    toast = r'''  <div class="toast" id="toast" role="status" aria-live="polite">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>
    <span></span>
  </div>'''

    # Template principal
    index_html = r'''<!DOCTYPE html>
<html lang="fr">
<head>
  <title>QR Image Platform · Partagez une image avec un QR code</title>
  <meta name="description" content="Déposez une image et obtenez instantanément un QR code qui l'ouvre sur n'importe quel téléphone.">
__HEAD__
</head>
<body>
  <a class="skip-link" href="#envoi">Aller à l'envoi d'image</a>
  <div class="hero">
__TOPBAR__
    <main class="wrap hero-grid" id="main">
      <div class="hero-copy">
        <span class="eyebrow">Partage d'images par QR code</span>
        <h1>Transformez une image en <em>QR code</em> partageable.</h1>
        <p class="lead">Déposez une photo, obtenez aussitôt un QR code qui l'ouvre sur n'importe quel téléphone. Sans compte, sans application à installer.</p>
        <ul class="facts" aria-label="Conditions d'utilisation">
          <li><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="9" cy="9" r="1.6"/><path d="m21 15-5-5L5 21"/></svg>PNG, JPG, GIF, BMP, WebP</li>
          <li><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>10 Mo maximum</li>
          <li><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>Conservée 7 jours</li>
        </ul>
      </div>

      <section class="upload-card" id="envoi" aria-labelledby="uploadTitle">
        <h2 class="sr-only" id="uploadTitle">Envoyer une image</h2>
        <div id="pickerArea">
          <input type="file" id="imageFile" class="sr-only" accept="image/png,image/jpeg,image/gif,image/bmp,image/webp" aria-describedby="dzHint">
          <label class="dropzone" id="uploadZone" for="imageFile">
            <span class="dz-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/></svg>
            </span>
            <span class="dz-title">Glissez-déposez votre image ici</span>
            <span class="dz-sub">ou <u>parcourez vos fichiers</u></span>
            <span class="dz-hint" id="dzHint">Formats PNG, JPG, GIF, BMP ou WebP · 10 Mo maximum</span>
          </label>

          <div class="preview" id="preview" hidden>
            <img id="previewImg" alt="">
            <div class="preview-body">
              <div class="preview-name" id="previewName"></div>
              <div class="preview-meta" id="previewMeta"></div>
              <div class="progress-track" id="progressTrack" role="progressbar" aria-label="Progression de l'envoi" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
                <div class="progress-bar" id="progressBar"></div>
              </div>
              <div class="status-text" id="statusText" aria-live="polite"></div>
            </div>
          </div>

          <div class="error" id="errorMsg" role="alert" hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.01"/></svg>
            <span id="errorText"></span>
          </div>
        </div>

        <div class="result" id="result" hidden>
          <div class="qr-frame">
            <img id="qrPreview" alt="QR code généré" width="170" height="170">
          </div>
          <div class="result-head">
            <span class="result-badge"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>Prêt à partager</span>
            <h2 id="resultTitle" tabindex="-1">Votre QR code est prêt</h2>
            <p class="note">Scannez-le ou partagez le lien : l'image s'ouvre sur n'importe quel appareil.</p>
          </div>
          <div class="link-field">
            <label class="sr-only" for="shareUrl">Lien de partage</label>
            <input id="shareUrl" type="text" readonly value="">
            <button class="btn btn-ghost btn-sm" id="copyLinkBtn" type="button">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/></svg>
              <span class="label">Copier le lien</span>
            </button>
          </div>
          <div class="actions">
            <a id="viewLink" class="btn btn-primary" href="#" target="_blank" rel="noopener">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>
              Voir l'image
            </a>
            <a id="downloadQrLink" class="btn btn-ghost" href="#" download>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>
              Télécharger le QR
            </a>
          </div>
          <div class="result-foot">
            <button class="btn btn-text" id="resetBtn" type="button">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
              Envoyer une autre image
            </button>
          </div>
        </div>
      </section>
    </main>
  </div>

  <section class="section" aria-labelledby="howTitle">
    <div class="wrap">
      <div class="section-head">
        <span class="kicker">Comment ça marche</span>
        <h2 id="howTitle">Trois étapes, quelques secondes.</h2>
        <p>Aucune inscription : l'image est optimisée, stockée sous un identifiant aléatoire et reliée à son propre QR code.</p>
      </div>
      <ol class="steps">
        <li class="step">
          <span class="step-num" aria-hidden="true">01</span>
          <span class="step-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/></svg></span>
          <h3>Déposez votre image</h3>
          <p>Glissez une photo dans la zone d'envoi ou choisissez-la depuis votre appareil.</p>
        </li>
        <li class="step">
          <span class="step-num" aria-hidden="true">02</span>
          <span class="step-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 20h4v-3"/></svg></span>
          <h3>Le QR code est généré</h3>
          <p>L'image est optimisée pour le web et un QR code unique pointe vers sa page de partage.</p>
        </li>
        <li class="step">
          <span class="step-num" aria-hidden="true">03</span>
          <span class="step-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="2" width="12" height="20" rx="2.5"/><path d="M11 18h2"/><path d="M9 7h2v2H9zM13 11h2v2h-2z"/></svg></span>
          <h3>Partagez ou imprimez</h3>
          <p>Téléchargez le QR, copiez le lien : il suffit de scanner pour voir l'image.</p>
        </li>
      </ol>
    </div>
  </section>

  <section class="section" aria-labelledby="whyTitle">
    <div class="wrap">
      <div class="section-head">
        <span class="kicker">Avantages</span>
        <h2 id="whyTitle">Pensé pour partager simplement.</h2>
      </div>
      <div class="features">
        <article class="feature">
          <span class="feature-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18z"/></svg></span>
          <h3>Accessible partout</h3>
          <p>Le lien s'ouvre dans n'importe quel navigateur, où que vous soyez.</p>
        </article>
        <article class="feature">
          <span class="feature-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="2" width="12" height="20" rx="2.5"/><path d="M11 18h2"/></svg></span>
          <h3>Mobile-friendly</h3>
          <p>Des pages conçues pour l'écran du téléphone qui scanne le code.</p>
        </article>
        <article class="feature">
          <span class="feature-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6z"/><path d="m9 12 2 2 4-4"/></svg></span>
          <h3>Sécurisé</h3>
          <p>Identifiants aléatoires impossibles à deviner, fichiers nettoyés après 7 jours.</p>
        </article>
        <article class="feature">
          <span class="feature-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg></span>
          <h3>Ultra-rapide</h3>
          <p>Images compressées automatiquement pour un affichage immédiat.</p>
        </article>
      </div>
    </div>
  </section>

  <footer class="footer">
    <div class="wrap">
      <span>QR Image Platform</span>
      <span>Images conservées 7 jours · 10 Mo maximum</span>
    </div>
  </footer>

__TOAST__
  <script src="{{ url_for('static', filename='js/app.js') }}"></script>
</body>
</html>
'''
    index_html = (index_html.replace('__HEAD__', head_common)
                            .replace('__TOPBAR__', topbar)
                            .replace('__TOAST__', toast))

    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(index_html)

    # Template de visualisation
    view_html = r'''<!DOCTYPE html>
<html lang="fr">
<head>
  <title>{{ image_info.original_name }} · QR Image Platform</title>
  <meta name="description" content="Image partagée via QR Image Platform.">
__HEAD__
</head>
<body>
  <a class="skip-link" href="#main">Aller au contenu</a>
  <div class="view-top">
__TOPBAR__
  </div>

  <main class="view-main" id="main">
    <div class="wrap">
      {% set t = image_info.upload_time or '' %}
      <article class="share-card" aria-labelledby="imgTitle">
        <figure class="stage" style="margin:0">
          <img id="sharedImg" src="{{ url_for('serve_image', image_id=image_id) }}" alt="Image partagée : {{ image_info.original_name }}">
        </figure>
        <div class="share-side">
          <div>
            <span class="kicker">Image partagée</span>
            <h1 id="imgTitle">{{ image_info.original_name }}</h1>
            <p class="sub">Partagée via QR Image Platform{% if t|length >= 10 %} le {{ t[8:10] }}/{{ t[5:7] }}/{{ t[0:4] }}{% endif %}.</p>
          </div>

          <dl class="meta">
            <div>
              <dt>Ajoutée le</dt>
              <dd>{% if t|length >= 16 %}{{ t[8:10] }}/{{ t[5:7] }}/{{ t[0:4] }} · {{ t[11:16] }}{% else %}{{ t[:10] }}{% endif %}</dd>
            </div>
            <div>
              <dt>Poids</dt>
              <dd>{% if image_info.file_size %}{{ '%.0f'|format(image_info.file_size / 1024) }} Ko{% else %}n/d{% endif %}</dd>
            </div>
            <div>
              <dt>Dimensions</dt>
              <dd id="dims">…</dd>
            </div>
            <div>
              <dt>Format</dt>
              <dd>JPEG optimisé</dd>
            </div>
          </dl>

          <div class="qr-block">
            <a class="qr-mini" href="{{ url_for('serve_qr', image_id=image_id) }}" target="_blank" rel="noopener" aria-label="Ouvrir le QR code en grand">
              <img src="{{ url_for('serve_qr', image_id=image_id) }}" alt="QR code de cette page">
            </a>
            <div>
              <strong>Scannez pour ouvrir sur mobile</strong>
              <p>Ce QR code renvoie vers cette page. Lien valable 7 jours après l'envoi.</p>
            </div>
          </div>

          <div class="share-actions">
            <a href="{{ url_for('serve_image', image_id=image_id) }}" class="btn btn-primary" download="{{ image_info.original_name }}">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>
              Télécharger l'image
            </a>
            <div class="row">
              <a href="{{ url_for('download_qr', image_id=image_id) }}" class="btn btn-ghost" aria-label="Télécharger le QR code">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M14 14h3v3h-3zM17 20h4v-3"/></svg>
                QR code
              </a>
              <button type="button" class="btn btn-ghost" data-copy-current>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/></svg>
                <span class="label">Copier le lien</span>
              </button>
            </div>
          </div>
        </div>
      </article>

      <aside class="cta-band">
        <div>
          <strong>Vous aussi, partagez une image en un scan.</strong>
          <p>Gratuit, sans compte, prêt en quelques secondes.</p>
        </div>
        <a class="btn btn-primary" href="{{ url_for('index') }}">Créer mon QR code</a>
      </aside>
    </div>
  </main>

  <footer class="footer">
    <div class="wrap">
      <span>Créé avec <a href="{{ url_for('index') }}">QR Image Platform</a></span>
      <span>Images conservées 7 jours</span>
    </div>
  </footer>

__TOAST__
  <script>
    (function () {
      var img = document.getElementById('sharedImg');
      var dims = document.getElementById('dims');
      function show() { if (img.naturalWidth) dims.textContent = img.naturalWidth + ' × ' + img.naturalHeight + ' px'; }
      if (img.complete) show(); else img.addEventListener('load', show);
      img.addEventListener('error', function () { dims.textContent = 'n/d'; });
    })();
  </script>
  <script src="{{ url_for('static', filename='js/app.js') }}"></script>
</body>
</html>
'''
    view_html = (view_html.replace('__HEAD__', head_common)
                          .replace('__TOPBAR__', topbar)
                          .replace('__TOAST__', toast))

    with open('templates/view_image.html', 'w', encoding='utf-8') as f:
        f.write(view_html)

# Créer les templates au démarrage de l'application
create_templates()

@app.route('/')
def index():
    """Page d'accueil avec formulaire d'upload"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_image():
    """Traite l'upload d'image et génère le QR code"""
    try:
        print("=== DEBUT UPLOAD ===")
        print(f"Files reçus: {list(request.files.keys())}")
        print(f"Form data: {list(request.form.keys())}")
        
        if 'image' not in request.files:
            print("ERREUR: Aucun fichier 'image' dans la requête")
            return jsonify({'error': 'Aucun fichier sélectionné'}), 400
        
        file = request.files['image']
        print(f"Fichier reçu: {file.filename}, taille: {file.content_length}")
        
        if file.filename == '':
            print("ERREUR: Nom de fichier vide")
            return jsonify({'error': 'Aucun fichier sélectionné'}), 400
        
        if not allowed_file(file.filename):
            print(f"ERREUR: Extension non autorisée pour {file.filename}")
            return jsonify({'error': 'Format de fichier non supporté. Utilisez: PNG, JPG, JPEG, GIF, BMP, WebP'}), 400
        
        # Nettoyer les anciennes images
        clean_old_images()
        
        # Générer un ID unique
        image_id = str(uuid.uuid4())
        print(f"ID généré: {image_id}")
        
        # Optimiser l'image
        print("Optimisation de l'image...")
        file.seek(0)  # Reset file pointer
        optimized_image = optimize_image(file, max_size_kb=500)
        
        # Sauvegarder l'image optimisée
        image_filename = f"{image_id}.jpg"
        image_path = os.path.join(IMAGES_DIR, image_filename)
        print(f"Sauvegarde vers: {image_path}")
        
        with open(image_path, 'wb') as f:
            optimized_image.seek(0)
            f.write(optimized_image.read())
        
        print(f"Image sauvegardée, taille: {os.path.getsize(image_path)} bytes")
        
        # Créer l'URL de visualisation
        view_url = url_for('view_image', image_id=image_id, _external=True)
        print(f"URL de visualisation: {view_url}")
        
        # Générer le QR code
        print("Génération du QR code...")
        qr_image = create_qr_code(view_url)
        if qr_image:
            qr_filename = f"qr_{image_id}.png"
            qr_path = os.path.join(QR_DIR, qr_filename)
            qr_image.save(qr_path)
            print(f"QR code sauvegardé: {qr_path}")
        else:
            print("ERREUR: Impossible de générer le QR code")
            return jsonify({'error': 'Erreur lors de la génération du QR code'}), 500
        
        # Sauvegarder les métadonnées
        data = load_image_data()
        data[image_id] = {
            'original_name': secure_filename(file.filename),
            'image_path': image_path,
            'qr_path': qr_path,
            'upload_time': datetime.now().isoformat(),
            'view_url': view_url,
            'file_size': os.path.getsize(image_path)
        }
        save_image_data(data)
        print("Métadonnées sauvegardées")
        
        response_data = {
            'success': True,
            'image_id': image_id,
            'view_url': view_url,
            'qr_url': url_for('serve_qr', image_id=image_id, _external=True),
            'download_qr_url': url_for('download_qr', image_id=image_id, _external=True)
        }
        print(f"=== UPLOAD REUSSI === {response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        print(f"ERREUR UPLOAD: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"Erreur lors du traitement: {str(e)}"}), 500

@app.route('/view/<image_id>')
def view_image(image_id):
    """Affiche l'image dans une page web"""
    data = load_image_data()
    if image_id not in data:
        return "Image non trouvée ou expirée", 404
    
    image_info = data[image_id]
    return render_template('view_image.html', 
                         image_id=image_id,
                         image_info=image_info)

@app.route('/image/<image_id>')
def serve_image(image_id):
    """Sert l'image directement"""
    data = load_image_data()
    if image_id not in data:
        return "Image non trouvée", 404
    
    image_path = data[image_id]['image_path']
    if not os.path.exists(image_path):
        return "Fichier non trouvé", 404
    
    return send_file(image_path)

@app.route('/qr/<image_id>')
def serve_qr(image_id):
    """Sert le QR code directement"""
    data = load_image_data()
    if image_id not in data:
        return "QR code non trouvé", 404
    
    qr_path = data[image_id]['qr_path']
    if not os.path.exists(qr_path):
        return "QR code non trouvé", 404
    
    return send_file(qr_path)

@app.route('/download-qr/<image_id>')
def download_qr(image_id):
    """Télécharge le QR code"""
    data = load_image_data()
    if image_id not in data:
        return "QR code non trouvé", 404
    
    qr_path = data[image_id]['qr_path']
    if not os.path.exists(qr_path):
        return "QR code non trouvé", 404
    
    return send_file(qr_path, as_attachment=True, 
                    download_name=f"qr_code_{image_id}.png")

@app.route('/favicon.ico')
def favicon():
    """Serve a simple favicon to avoid 404 errors"""
    return '', 204
    """Page de statistiques"""
    data = load_image_data()
    total_images = len(data)
    total_size = sum(info.get('file_size', 0) for info in data.values())
    
    return jsonify({
        'total_images': total_images,
        'total_size_mb': round(total_size / (1024 * 1024), 2),
        'platform_status': 'active'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
