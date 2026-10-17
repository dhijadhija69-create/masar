"""Pages Masar : tableau de bord, profil + photo, CV (IA + PDF), chatbot, offres, matching, entreprises."""
import io
import json
import os
from datetime import date

from flask import abort, g, jsonify, redirect, render_template, request, send_file, url_for
from PIL import Image, ImageOps

import ai
import cvpdf
import jobs
import mailer
import osm
from i18n import current_lang, tr

PROFIL_FIELDS = ["nom", "titre", "ville", "email", "tel", "bio", "competences",
                 "formation", "experience", "langues", "projets"]
LABELS = {
    "fr": {"resume": "Profil", "skills": "Compétences", "projects": "Projets", "exp": "Expérience",
           "edu": "Formation", "lang": "Langues"},
    "en": {"resume": "Summary", "skills": "Skills", "projects": "Projects", "exp": "Experience",
           "edu": "Education", "lang": "Languages"},
}


def register(app, get_db, ctx):
    statuts, relance_jours = ctx["STATUTS"], ctx["RELANCE_JOURS"]
    villes_config = ctx["VILLES"]
    uploads = os.path.join(os.environ.get("MASAR_DATA_DIR", ctx["BASE"]), "uploads")
    os.makedirs(uploads, exist_ok=True)

    # ------------------------------------------------------------- helpers
    def profil():
        db = get_db()
        row = db.execute("SELECT * FROM profils WHERE user_id=?", (g.uid,)).fetchone()
        if not row:
            db.execute("INSERT INTO profils(user_id, nom, email) VALUES(?,?,?)", (g.uid, g.user["nom"], g.user["email"]))
            db.commit()
            row = db.execute("SELECT * FROM profils WHERE user_id=?", (g.uid,)).fetchone()
        return dict(row)

    def photo_file():
        path = os.path.join(uploads, f"photo_{g.uid}.jpg")
        return path if os.path.isfile(path) else None

    @app.context_processor
    def inject_account_photo():
        return {"account_photo_url": url_for("photo") if g.get("uid") and photo_file() else ""}

    def completeness(p):
        filled = sum(1 for f in PROFIL_FIELDS if (p.get(f) or "").strip()) + (1 if photo_file() else 0)
        return round(100 * filled / (len(PROFIL_FIELDS) + 1))

    def offres_scored(p, q="", ville="", secteur="", specialite=""):
        skills = ai.skills_of(p)
        mine = {ai.norm(s) for s in skills}
        normalized_query = ai.norm(q) if q else ""
        equivalences = {
            "IT & Digital": {
                "IT & Digital", "Informatique & Développement", "Technologie",
            },
        }
        matching_sectors = {
            ai.norm(item) for item in equivalences.get(secteur, {secteur})
        } if secteur else set()
        out = []
        for o in get_db().execute("SELECT * FROM offres WHERE user_id=?", (g.uid,)).fetchall():
            o = dict(o)
            hay = ai.norm(" ".join([o["titre"] or "", o["entreprise"] or "", o["competences"] or ""]))
            if ((normalized_query and normalized_query not in hay) or (ville and o["ville"] != ville)
                    or (matching_sectors and ai.norm(o["secteur"]) not in matching_sectors)
                    or (specialite and o.get("specialite") != specialite)):
                continue
            req = [x.strip() for x in (o["competences"] or "").split(",") if x.strip()]
            ok = [x for x in req if ai.norm(x) in mine]
            o["req"], o["ok"], o["manque"] = req, ok, [x for x in req if x not in ok]
            if req:
                o["score"] = round(100 * len(ok) / len(req))
            else:  # offre importée sans liste de compétences : on cherche tes compétences dans le texte
                txt = ai.norm((o.get("titre") or "") + " " + (o.get("description") or ""))
                hits = [sk for sk in skills if ai.norm(sk) in txt]
                o["ok"], o["score"] = hits, min(100, 30 * len(hits))
            out.append(o)
        return sorted(out, key=lambda o: -o["score"])

    def cand_stats():
        c, relances = {s: 0 for s in statuts}, []
        for r in get_db().execute("SELECT * FROM candidatures WHERE user_id=?", (g.uid,)).fetchall():
            c[r["statut"]] = c.get(r["statut"], 0) + 1
            if r["statut"] == "Envoyée" and (date.today() - date.fromisoformat(r["date"])).days >= relance_jours:
                relances.append(f"{r['entreprise']} · {r['poste']}")
        return c, relances

    def chat_ctx():
        p = profil()
        c, relances = cand_stats()
        offs = offres_scored(p)
        villes = {r["ville"]: r["n"] for r in get_db().execute(
            "SELECT ville, COUNT(*) n FROM entreprises WHERE user_id=? GROUP BY ville", (g.uid,))}
        mine = {ai.norm(s) for s in ai.skills_of(p)}
        demand = {}
        for o in offs:
            for s in o["req"]:
                if ai.norm(s) not in mine:
                    demand[s] = demand.get(s, 0) + 1
        return {"profil": {k: p[k] for k in PROFIL_FIELDS}, "stats": c, "relances": relances,
                "top_offres": [{k: o[k] for k in ("titre", "entreprise", "ville", "score")} for o in offs[:5]],
                "top_villes": sorted(villes.items(), key=lambda x: -x[1])[:5],
                "manquantes": [s for s, _ in sorted(demand.items(), key=lambda x: -x[1])]}

    # --------------------------------------------------------------- pages
    @app.route("/dashboard")
    def dashboard():
        p = profil()
        c, relances = cand_stats()
        n_ent = get_db().execute("SELECT COUNT(*) FROM entreprises WHERE user_id=?", (g.uid,)).fetchone()[0]
        best = offres_scored(p)[:5]
        return render_template("dashboard.html", active="dashboard", p=p, pct=completeness(p), c=c,
                               total=sum(c.values()), relances=relances, best=best, n_ent=n_ent,
                               gmail=mailer.connected_email(get_db(), g.uid), gmail_ok=mailer.configured(),
                               prenom=(p["nom"] or g.user["nom"]).split(" ")[0])

    @app.route("/profil", methods=["GET", "POST"])
    def profil_page():
        err = ""
        if request.method == "POST":
            vals = [request.form.get(f, "").strip()[:3000] for f in PROFIL_FIELDS]
            db = get_db()
            db.execute("UPDATE profils SET " + ",".join(f"{f}=?" for f in PROFIL_FIELDS) + " WHERE user_id=?", vals + [g.uid])
            path = os.path.join(uploads, f"photo_{g.uid}.jpg")
            f = request.files.get("photo")
            if request.form.get("remove_photo") and os.path.isfile(path):
                os.remove(path)
            elif f and f.filename:
                try:
                    im = Image.open(f.stream)
                    if im.format not in ("JPEG", "PNG", "WEBP"):
                        raise ValueError
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    ImageOps.fit(im, (480, 480)).save(path, "JPEG", quality=88)  # ré-encodage : supprime les métadonnées
                except Exception:
                    err = tr("Photo invalide : utilise un fichier JPG, PNG ou WebP (4 Mo maximum).")
            db.execute("UPDATE profils SET photo=? WHERE user_id=?", (1 if os.path.isfile(path) else 0, g.uid))
            db.commit()
            if not err:
                return redirect(url_for("profil_page", saved=1))
        p = profil()
        return render_template("profil.html", active="profil", p=p, pct=completeness(p), saved=request.args.get("saved"),
                               llm=ai.llm_enabled(), err=err, has_photo=bool(photo_file()))

    @app.route("/photo")
    def photo():
        path = photo_file()
        if not path:
            abort(404)
        return send_file(path, mimetype="image/jpeg", max_age=0)

    @app.post("/api/bio")
    def api_bio():
        data = request.get_json(silent=True) or {}
        p = {f: str(data.get(f, ""))[:1500] for f in PROFIL_FIELDS}
        return jsonify(bio=ai.gen_bio(p), mode="llm" if ai.llm_enabled() else "local")

    def saved_cv():
        row = get_db().execute("SELECT * FROM cvs WHERE user_id=?", (g.uid,)).fetchone()
        return (json.loads(row["data"]), row["poste"], row["lang"]) if row else (None, "", "fr")

    def make_cv(p, poste, lang):
        cv = ai.gen_cv(p, poste, lang)
        db = get_db()
        db.execute("INSERT INTO cvs(user_id,poste,lang,data) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
                   "poste=excluded.poste, lang=excluded.lang, data=excluded.data", (g.uid, poste, lang, json.dumps(cv, ensure_ascii=False)))
        db.commit()
        return cv

    @app.route("/cv")
    def cv_page():
        p = profil()
        if request.args.get("gen"):
            poste = request.args.get("poste", "").strip()[:120]
            lang = "en" if request.args.get("lang") == "en" else "fr"
            cv = make_cv(p, poste, lang)
        else:
            cv, poste, lang = saved_cv()
            if not cv:
                lang = "en" if current_lang() == "en" else "fr"
        return render_template("cv.html", active="cv", p=p, cv=cv, poste=poste, lang=lang, llm=ai.llm_enabled(),
                               labels=LABELS[lang], has_photo=bool(photo_file()))

    @app.route("/cv.pdf")
    def cv_pdf():
        p = profil()
        cv, poste, lang = saved_cv()
        if not cv:
            cv, poste, lang = make_cv(p, "", "fr"), "", "fr"
        pdf = cvpdf.build_pdf(p, cv, poste, LABELS[lang], photo_file())
        name = "".join(c for c in (p["nom"] or "CV") if c.isalnum() or c in " -_").strip().replace(" ", "_") or "CV"
        return send_file(io.BytesIO(pdf), mimetype="application/pdf", as_attachment=True, download_name=f"CV_{name}.pdf")

    @app.route("/chat")
    def chat_page():
        p = profil()
        return render_template("chat.html", active="chat", prenom=(p["nom"] or g.user["nom"]).split(" ")[0],
                               initial=request.args.get("q", "").strip()[:1000])

    @app.get("/api/ia-status")
    def ia_status():
        return jsonify(ai.llm_status())

    @app.post("/api/chat")
    def api_chat():
        data = request.get_json(silent=True) or {}
        msg = str(data.get("message", "")).strip()[:4000]
        if not msg:
            return jsonify(reply=tr("Écris-moi un message pour commencer."), mode="local")
        reply, mode, err = ai.chat_reply(msg, data.get("history") or [], chat_ctx())
        return jsonify(reply=reply, mode=mode, error=err)

    @app.route("/offres")
    def offres_page():
        p = profil()
        jobs.sync_local_csv_data(get_db(), g.uid)
        q, ville, secteur, specialite = (request.args.get(k, "") for k in ("q", "ville", "secteur", "specialite"))
        db = get_db()
        rows = db.execute("SELECT ville, secteur, specialite FROM offres WHERE user_id=?", (g.uid,)).fetchall()
        return render_template(
            "offres.html", active="offres", offres=offres_scored(p, q, ville, secteur, specialite), q=q, ville=ville,
            secteur=secteur, specialite=specialite, added=request.args.get("added"),
            msg=request.args.get("msg", ""),
            villes=sorted(set(villes_config) | {r["ville"] for r in rows if r["ville"]}, key=str.casefold),
            secteurs=sorted(set(osm.TYPES) | {r["secteur"] for r in rows if r["secteur"]}),
            specialites=sorted({item[-1] for item in jobs.DEMO_OFFRES} |
                               {r["specialite"] for r in rows if r["specialite"]}), total=len(rows))

    @app.route("/recherche")
    def recherche():
        return redirect(url_for("offres_page", **request.args))

    @app.post("/offres/<int:oid>/postuler")
    def postuler(oid):
        db = get_db()
        o = db.execute("SELECT * FROM offres WHERE id=? AND user_id=?", (oid, g.uid)).fetchone()
        if o:
            jobs.ensure_candidature(db, dict(o), "A postuler", "Site de l'entreprise", "Ajoutée depuis la page Offres")
            db.commit()
        return redirect(url_for("offres_page", added=o["titre"] if o else ""))

    @app.route("/matching")
    def matching():
        p = profil()
        offs = offres_scored(p)
        demand = {}
        for o in offs:
            for s in o["manque"]:
                demand[s] = demand.get(s, 0) + 1
        return render_template("matching.html", active="matching", offres=offs, mine=ai.skills_of(p),
                               a_apprendre=sorted(demand.items(), key=lambda x: -x[1])[:6])

    @app.route("/entreprises")
    def entreprises():
        q, ville, secteur = (request.args.get(k, "").strip() for k in ("q", "ville", "secteur"))
        db = get_db()
        jobs.sync_local_csv_data(db, g.uid)
        allrows = db.execute("SELECT * FROM entreprises WHERE user_id=? ORDER BY (email<>'') + (tel<>'') DESC, nom", (g.uid,)).fetchall()
        rows = [dict(r) for r in allrows if (not q or ai.norm(q) in ai.norm(r["nom"])) and (not ville or r["ville"] == ville)
                and (not secteur or r["secteur"] == secteur)]
        return render_template("entreprises.html", active="entreprises", liste=rows[:200], n=len(rows), q=q, ville=ville,
                               secteur=secteur, villes=sorted({r["ville"] for r in allrows}),
                               secteurs=sorted({r["secteur"] for r in allrows}), total=len(allrows))

    @app.post("/entreprises/<int:eid>/spontanee")
    def spontanee(eid):
        db = get_db()
        e = db.execute("SELECT * FROM entreprises WHERE id=? AND user_id=?", (eid, g.uid)).fetchone()
        if not e:
            abort(404)
        o = db.execute("SELECT id FROM offres WHERE user_id=? AND entreprise=? AND source='Spontanée'", (g.uid, e["nom"])).fetchone()
        if not o:
            cur = db.execute(
                "INSERT INTO offres(user_id,titre,entreprise,ville,secteur,type,competences,specialite,email,tel,adresse,url,source,description,lat,lng) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (g.uid, "Candidature spontanée", e["nom"], e["ville"], e["secteur"], "Spontanée", "", "", e["email"], e["tel"],
                 e["adresse"], e["site"], "Spontanée", f"Candidature spontanée chez {e['nom']} ({e['secteur']}).", e["lat"], e["lng"]))
            db.commit()
            oid = cur.lastrowid
        else:
            oid = o["id"]
        return redirect(url_for("offre_page", oid=oid))

    def cv_bytes():
        p = profil()
        cv, poste, lang = saved_cv()
        if not cv:
            cv, poste, lang = make_cv(p, "", "fr"), "", "fr"
        name = "".join(c for c in (p["nom"] or "CV") if c.isalnum() or c in " -_").strip().replace(" ", "_") or "CV"
        return cvpdf.build_pdf(p, cv, poste, LABELS[lang], photo_file()), f"CV_{name}.pdf"

    mailer.register(app, get_db, ctx["DB"], cv_bytes, profil)
    jobs.register(app, get_db, {"profil": profil, "DB": ctx["DB"], "statuts": statuts})
