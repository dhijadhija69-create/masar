# Masar (Flask)

    pip install -r requirements.txt
    python app.py            # http://localhost:5000  (crée ton compte au premier lancement)

## Déploiement sur Render

1. Crée un dépôt GitHub privé et pousse le code. Ne pousse jamais `.env`, `masar.db`, `uploads/` ni `credentials*.json`.
2. Dans Render, crée un Blueprint depuis ce dépôt et applique `render.yaml`.
3. Ajoute `GEMINI_API_KEY`, `GOOGLE_CLIENT_ID` et `GOOGLE_CLIENT_SECRET` dans l'environnement du service Render.
4. Après la création du domaine Render, ajoute `https://<domaine-render>/gmail/callback` aux Authorized redirect URIs du client OAuth Google.
5. Active Gmail API dans le projet Google Cloud et ajoute `https://www.googleapis.com/auth/gmail.send` dans les OAuth Data Access scopes.

Le disque Render `masar-data` garde la base SQLite et les photos بين عمليات النشر؛ خدمة Render بخطة تدعم persistent disks مطلوبة. ملف `.env.example` غير مثال، والمفاتيح الحقيقية تبقى في إعدادات Render فقط.

## Clés (fichier `.env` ou `api.env` dans ce dossier)
    GEMINI_API_KEY=...       # chatbot, bio, CV, emails (sinon mode local limité)
    GOOGLE_PLACES_API_KEY=... # entreprises depuis Google Places (facturation Google Cloud requise)
    JOOBLE_API_KEY=...       # import d'offres (optionnel)
    MASAR_MODEL=gemini-3.8-flash

## Sécurité
Comptes avec mots de passe hachés, sessions HttpOnly, protection CSRF, limitation des tentatives de connexion,
données isolées par compte, en-têtes de sécurité. Debug désactivé par défaut (`MASAR_DEBUG=1` pour l'activer).
En ligne (HTTPS) : définis `MASAR_HTTPS=1` et utilise un serveur de production (gunicorn/waitress), pas `python app.py`.

## Données
Les entreprises et offres sont chargées depuis les CSV locaux. Les offres peuvent également être ajoutées manuellement ou via Jooble.
Pas de scraping de Rekrute/Indeed (conditions d'utilisation).

## Langues
Sélecteur FR / EN / ع dans la barre latérale (et sur les pages de connexion). Le choix est mémorisé par compte.
Les textes sont dans `translations.py` : ajoute une ligne pour traduire un nouveau texte. L'arabe passe l'interface en mode droite-à-gauche.
Le chatbot répond par défaut dans la langue choisie. Le CV (HTML et PDF) reste en français ou en anglais.
