"""Gmail : connexion OAuth au compte Gmail de l'utilisateur + envoi de candidatures (CV en pièce jointe).

Aucune dépendance externe (urllib). Scope minimal : gmail.send (Masar ne lit jamais ta boîte mail).
Identifiants OAuth : variables GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET dans .env,
ou fichier credentials.json (téléchargé depuis Google Cloud) à la racine du projet.
"""
import base64
import json
import os
import re
import secrets
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

from flask import g, jsonify, redirect, request, session, url_for

import cvpdf

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
SCOPES = "https://www.googleapis.com/auth/gmail.send openid email"
EMAIL_RX = re.compile(r"^[^@\s<>\",;]+@[^@\s<>\",;]+\.[^@\s<>\",;]+$")
BASE = os.path.dirname(os.path.abspath(__file__))


def client():
    """(client_id, client_secret) depuis .env, sinon credentials.json (ou credentials.json.json)."""
    cid = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    sec = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if cid and sec:
        return cid, sec
    for name in ("credentials.json", "credentials.json.json"):
        path = os.path.join(BASE, name)
        if os.path.isfile(path):
            try:
                d = json.load(open(path, encoding="utf-8"))
                d = d.get("web") or d.get("installed") or {}
                if d.get("client_id") and d.get("client_secret"):
                    return d["client_id"], d["client_secret"]
            except (OSError, ValueError):
                pass
    return "", ""


def configured():
    return all(client())


def _post(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            err = json.load(e)
        except Exception:
            err = {}
        raise RuntimeError(err.get("error_description") or err.get("error") or f"HTTP {e.code}")


def _email_from_id_token(tok):
    try:
        part = tok.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part)).get("email", "")
    except Exception:
        return ""


def build_message(sender, to, subject, body, pdf=None, filename="CV.pdf", letter_pdf=None):
    m = EmailMessage()  # lève ValueError si un en-tête contient un retour à la ligne (injection)
    m["To"], m["From"], m["Subject"] = to, sender, subject
    m.set_content(body)
    if pdf:
        m.add_attachment(pdf, maintype="application", subtype="pdf", filename=filename)
    if letter_pdf:
        m.add_attachment(
            letter_pdf, maintype="application", subtype="pdf",
            filename="Lettre_de_motivation.pdf",
        )
    return base64.urlsafe_b64encode(m.as_bytes()).decode()


def register(app, get_db, db_path, cv_bytes, profil):
    """cv_bytes() -> (pdf_bytes, filename). profil() -> dict du profil de l'utilisateur connecté."""
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS gmail(user_id INTEGER PRIMARY KEY, refresh_token TEXT NOT NULL, email TEXT)")

    def row():
        return get_db().execute("SELECT * FROM gmail WHERE user_id=?", (g.uid,)).fetchone()

    @app.get("/gmail/connect")
    def gmail_connect():
        cid, _ = client()
        if not cid:
            return redirect(url_for("importer", msg="Gmail : identifiants OAuth absents (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET ou credentials.json)."))
        nxt = request.args.get("next", "")
        session["gmail_next"] = nxt if nxt.startswith("/") and not nxt.startswith("//") else "/dashboard"
        session["gmail_state"] = secrets.token_urlsafe(24)
        q = urllib.parse.urlencode({
            "client_id": cid, "redirect_uri": url_for("gmail_callback", _external=True), "response_type": "code",
            "scope": SCOPES, "access_type": "offline", "prompt": "consent", "state": session["gmail_state"]})
        return redirect(f"{AUTH_URL}?{q}")

    @app.get("/gmail/callback")
    def gmail_callback():
        nxt = session.pop("gmail_next", "/dashboard")
        expected = session.pop("gmail_state", "")
        if request.args.get("error") or not expected or request.args.get("state") != expected:
            return redirect(nxt)
        cid, sec = client()
        try:
            tok = _post(TOKEN_URL, {"code": request.args.get("code", ""), "client_id": cid, "client_secret": sec,
                                    "redirect_uri": url_for("gmail_callback", _external=True),
                                    "grant_type": "authorization_code"})
        except RuntimeError:
            return redirect(nxt)
        if tok.get("refresh_token"):
            db = get_db()
            db.execute("INSERT INTO gmail(user_id,refresh_token,email) VALUES(?,?,?) "
                       "ON CONFLICT(user_id) DO UPDATE SET refresh_token=excluded.refresh_token, email=excluded.email",
                       (g.uid, tok["refresh_token"], _email_from_id_token(tok.get("id_token", ""))))
            db.commit()
        return redirect(nxt)

    @app.post("/gmail/disconnect")
    def gmail_disconnect():
        r = row()
        if r:
            try:  # révoque le jeton côté Google (best effort)
                _post("https://oauth2.googleapis.com/revoke", {"token": r["refresh_token"]})
            except Exception:
                pass
            get_db().execute("DELETE FROM gmail WHERE user_id=?", (g.uid,))
            get_db().commit()
        return redirect(request.form.get("next") if (request.form.get("next") or "").startswith("/") else "/dashboard")

    @app.post("/offres/<int:oid>/gmail")
    def gmail_send(oid):
        import jobs  # import tardif : jobs importe mailer
        r, db = row(), get_db()
        o = db.execute("SELECT * FROM offres WHERE id=? AND user_id=?", (oid, g.uid)).fetchone()
        if not r:
            return jsonify(ok=False, error="not_connected"), 400
        if not o or not EMAIL_RX.match((o["email"] or "").strip()):
            return jsonify(ok=False, error="no_recipient"), 400
        j = request.get_json(silent=True) or request.form
        subject, body = (j.get("subject") or "").strip()[:200], (j.get("body") or "").strip()[:8000]
        if not subject or not body:
            return jsonify(ok=False, error="empty"), 400
        cv_file = request.files.get("cv")
        if not cv_file or not cv_file.filename:
            return jsonify(ok=False, error="Choisis ton CV au format PDF."), 400
        if not cv_file.filename.lower().endswith(".pdf"):
            return jsonify(ok=False, error="Le CV doit être un fichier PDF."), 400
        cv_pdf = cv_file.read(14 * 1024 * 1024 + 1)
        if len(cv_pdf) > 14 * 1024 * 1024:
            return jsonify(ok=False, error="Le CV PDF ne doit pas dépasser 14 Mo."), 400
        if not cv_pdf.startswith(b"%PDF-"):
            return jsonify(ok=False, error="Le fichier choisi n'est pas un PDF valide."), 400
        cid, sec = client()
        try:
            access = _post(TOKEN_URL, {"client_id": cid, "client_secret": sec, "refresh_token": r["refresh_token"],
                                       "grant_type": "refresh_token"})["access_token"]
            letter_pdf = cvpdf.build_letter_pdf(profil(), dict(o), body)
            sender = f"{profil().get('nom') or g.user['nom']} <{r['email']}>" if r["email"] else None
            raw = build_message(
                sender or r["email"], o["email"].strip(), subject, body,
                cv_pdf, "CV.pdf", letter_pdf,
            )
            req = urllib.request.Request(SEND_URL, data=json.dumps({"raw": raw}).encode(), headers={
                "Authorization": f"Bearer {access}", "Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=30).read()
        except ValueError:
            return jsonify(ok=False, error="bad_header"), 400
        except urllib.error.HTTPError as e:
            try:
                details = json.loads(e.read().decode("utf-8", "replace")).get("error", {})
            except (ValueError, AttributeError):
                details = {}
            if isinstance(details, dict):
                message = details.get("message", "")
                reasons = ", ".join(
                    item.get("reason", "") for item in details.get("errors", [])
                    if isinstance(item, dict) and item.get("reason")
                )
                detail = "; ".join(part for part in (message, reasons) if part)
            else:
                detail = str(details)
            return jsonify(
                ok=False,
                error=f"Gmail API {e.code}: {detail or 'Vérifie les accès Gmail API du projet.'}"[:400],
            ), 502
        except (RuntimeError, urllib.error.URLError) as e:
            return jsonify(ok=False, error=type(e).__name__ + ": " + str(e)[:160]), 502
        jobs.ensure_candidature(db, dict(o), "Envoyée", "Email", f"Candidature envoyée via Gmail à {o['email']}")
        db.commit()
        return jsonify(ok=True)

    @app.errorhandler(413)
    def upload_too_large(error):
        if request.endpoint == "gmail_send":
            return jsonify(ok=False, error="Le CV est trop volumineux. Choisis un PDF de moins de 14 Mo."), 413
        return error


def connected_email(db, uid):
    """Adresse Gmail connectée ('' si aucune) ; None si la table n'existe pas encore."""
    try:
        r = db.execute("SELECT email FROM gmail WHERE user_id=?", (uid,)).fetchone()
    except sqlite3.OperationalError:
        return None
    return (r["email"] or "connecté") if r else ""
