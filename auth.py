"""Comptes utilisateurs, sessions, protection CSRF, limitation des tentatives, en-têtes de sécurité."""
import hmac
import os
import re
import secrets
import time
from datetime import timedelta

from flask import g, redirect, render_template, request, session, url_for
from i18n import tr
from werkzeug.security import check_password_hash, generate_password_hash

PUBLIC = {"login", "signup", "static", "set_lang", None}
FAILS = {}  # "ip|email" -> [nombre, premier_échec]
MAX_FAILS, LOCK_SECONDS = 5, 300
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DUMMY_HASH = generate_password_hash("dummy-password-for-timing")


def secret_key(base):
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    folder = os.path.join(base, "instance")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    return open(path).read().strip()


def locked(key):
    rec = FAILS.get(key)
    if not rec:
        return False
    if time.time() - rec[1] > LOCK_SECONDS:
        FAILS.pop(key, None)
        return False
    return rec[0] >= MAX_FAILS


def fail(key):
    rec = FAILS.setdefault(key, [0, time.time()])
    rec[0] += 1


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def init(app, get_db, base):
    app.config.update(
        SECRET_KEY=secret_key(base),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("MASAR_HTTPS") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
    )
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def gate():
        g.uid, g.user = None, None
        if request.endpoint == "gmail_send":
            request.max_content_length = 15 * 1024 * 1024
        if request.method == "POST":
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
            expected = session.get("csrf")
            if not expected or not sent or not hmac.compare_digest(sent, expected):
                return (tr("Session expirée ou requête invalide. Recharge la page et réessaie."), 400)
        uid = session.get("uid")
        if uid:
            row = get_db().execute("SELECT id, nom, email, lang FROM users WHERE id=?", (uid,)).fetchone()
            if row:
                g.uid, g.user = row["id"], dict(row)
        if request.endpoint in PUBLIC:
            return None
        if not g.uid:
            return redirect(url_for("login"))
        return None

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: https://tile.openstreetmap.de; "
            "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; frame-ancestors 'none'; form-action 'self'")
        if resp.mimetype == "text/html":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.context_processor
    def inject_user():
        return {"user": g.get("user")}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.uid:
            return redirect(url_for("dashboard"))
        error, email = "", ""
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            pw = request.form.get("password", "")
            key = f"{request.remote_addr}|{email}"
            if locked(key):
                error = tr("Trop de tentatives. Réessaie dans 5 minutes.")
            else:
                row = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
                ok = check_password_hash(row["pw_hash"] if row else DUMMY_HASH, pw)
                if row and ok:
                    FAILS.pop(key, None)
                    chosen = session.get("lang")
                    session.clear()
                    session["lang"] = row["lang"] or chosen or "fr"
                    session["uid"] = row["id"]
                    session.permanent = True
                    return redirect(url_for("dashboard"))
                fail(key)
                error = tr("Email ou mot de passe incorrect.")
        return render_template("login.html", error=error, email=email)

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if g.uid:
            return redirect(url_for("dashboard"))
        error, form = "", {}
        if request.method == "POST":
            form = {k: request.form.get(k, "").strip() for k in ("nom", "email")}
            form["email"] = form["email"].lower()
            pw, pw2 = request.form.get("password", ""), request.form.get("password2", "")
            db = get_db()
            if not form["nom"] or len(form["nom"]) > 80:
                error = tr("Entre ton nom complet.")
            elif not EMAIL_RE.match(form["email"]) or len(form["email"]) > 120:
                error = tr("Entre un email valide.")
            elif len(pw) < 8 or pw.isdigit() or pw.lower() == form["email"]:
                error = tr("Mot de passe trop faible : 8 caractères minimum, pas uniquement des chiffres.")
            elif pw != pw2:
                error = tr("Les deux mots de passe sont différents.")
            elif db.execute("SELECT 1 FROM users WHERE email=?", (form["email"],)).fetchone():
                error = tr("Un compte existe déjà avec cet email.")
            else:
                cur = db.execute("INSERT INTO users(email, nom, pw_hash, created, lang) VALUES(?,?,?,date('now'),?)",
                                 (form["email"], form["nom"], generate_password_hash(pw), session.get("lang") or "fr"))
                db.execute("INSERT INTO profils(user_id, nom, email) VALUES(?,?,?)",
                           (cur.lastrowid, form["nom"], form["email"]))
                db.commit()
                chosen = session.get("lang")
                session.clear()
                session["lang"] = chosen or "fr"
                session["uid"] = cur.lastrowid
                session.permanent = True
                return redirect(url_for("profil_page"))
        return render_template("signup.html", error=error, form=form)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))
