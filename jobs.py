"""Offres : détail, candidature par email, carte, imports (OpenStreetMap, Jooble, CSV, manuel), démo."""
import csv
import io
import json
import os
import random
import re
import sqlite3
import threading
import urllib.parse
import urllib.request
from datetime import date

from flask import Response, g, jsonify, redirect, render_template, request, url_for

import ai
import mailer
import osm
import places
from i18n import current_lang, tr

GPS = {"Casablanca": (33.5731, -7.5898), "Rabat": (34.0209, -6.8416), "Tanger": (35.7595, -5.8340),
       "Marrakech": (31.6295, -7.9811), "Fès": (34.0331, -5.0003), "Agadir": (30.4278, -9.5981),
       "Kénitra": (34.2610, -6.5802), "Salé": (34.0531, -6.7985), "Meknès": (33.8935, -5.5473),
       "Mohammedia": (33.6866, -7.3830), "Tétouan": (35.5785, -5.3684), "Oujda": (34.6814, -1.9086),
       "El Jadida": (33.2316, -8.5007), "Béni Mellal": (32.3373, -6.3498), "Nador": (35.1681, -2.9335),
       "Safi": (32.2994, -9.2372), "Laâyoune": (27.1253, -13.1625), "Dakhla": (23.6848, -15.9580)}

SITES = [("Rekrute", "rekrute.com"), ("Indeed Maroc", "ma.indeed.com"), ("Emploi.ma", "emploi.ma"),
         ("LinkedIn", "linkedin.com/jobs"), ("Anapec", "anapec.ma")]
PROGRESS = {}  # uid -> état de l'import « toutes les villes »


def gps_of(ville, seed=0):
    base = GPS.get(ville or "")
    if not base:
        return None, None
    return round(base[0] + ((seed * 37) % 100 - 50) / 4000, 5), round(base[1] + ((seed * 53) % 100 - 50) / 4000, 5)


def sync_local_csv_data(db, uid):
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    def rows(filename):
        path = os.path.join(data_dir, filename)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8-sig", newline="") as source:
            return [
                {str(key or "").strip().lower(): (value or "").strip()
                 for key, value in row.items() if key}
                for row in csv.DictReader(source)
            ]

    def value(row, *keys):
        return next((row[key] for key in keys if row.get(key)), "")

    def coordinate(raw, low, high):
        try:
            number = float(raw)
            return number if low <= number <= high else None
        except (TypeError, ValueError):
            return None

    def already_imported(dataset):
        return db.execute(
            "SELECT 1 FROM csv_imports WHERE user_id=? AND dataset=?",
            (uid, dataset),
        ).fetchone()

    if not already_imported("entreprises"):
        source_rows = rows("entreprises.csv")
        if source_rows is not None:
            existing = {
                (ai.norm(row["nom"]), ai.norm(row["ville"]))
                for row in db.execute(
                    "SELECT nom, ville FROM entreprises WHERE user_id=?", (uid,)
                )
            }
            for row in source_rows:
                name = value(row, "nom", "entreprise")
                city = value(row, "ville")
                if not name or not city:
                    continue
                key = (ai.norm(name), ai.norm(city))
                if key in existing:
                    continue
                lat = coordinate(value(row, "lat", "latitude"), -90, 90)
                lng = coordinate(value(row, "lng", "longitude"), -180, 180)
                if lat is None or lng is None:
                    lat, lng = GPS.get(city, (None, None))
                source_name = value(row, "source")
                db.execute(
                    "INSERT INTO entreprises(user_id,nom,ville,secteur,email,tel,site,adresse,"
                    "lat,lng,source,osm_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (uid, name[:200], city[:100], value(row, "secteur"),
                     value(row, "email"), value(row, "tel", "telephone"),
                     value(row, "site", "site_web"), value(row, "adresse"), lat, lng,
                     f"CSV local: {source_name}" if source_name else "CSV local",
                     value(row, "osm_id", "id_google")),
                )
                existing.add(key)
            db.execute(
                "INSERT OR IGNORE INTO csv_imports(user_id,dataset) VALUES(?,?)",
                (uid, "entreprises"),
            )

    company_contacts = {}
    for company in db.execute(
            "SELECT nom,email,tel,adresse FROM entreprises WHERE user_id=?", (uid,)):
        key = ai.norm(company["nom"])
        if key and company["email"]:
            company_contacts.setdefault(key, dict(company))

    if not already_imported("offres"):
        source_rows = rows("offres.csv")
        if source_rows is not None:
            existing_urls = {
                row[0] for row in db.execute(
                    "SELECT url FROM offres WHERE user_id=? AND COALESCE(url,'')<>''", (uid,)
                )
            }
            existing_titles = {
                (ai.norm(row[0]), ai.norm(row[1]), ai.norm(row[2]))
                for row in db.execute(
                    "SELECT titre, entreprise, ville FROM offres WHERE user_id=?", (uid,)
                )
            }
            for row in source_rows:
                title = value(row, "titre")
                company = value(row, "entreprise")
                city = value(row, "ville")
                if not title or not company:
                    continue
                url = value(row, "url", "lien")
                key = (ai.norm(title), ai.norm(company), ai.norm(city))
                if (url and url in existing_urls) or (not url and key in existing_titles):
                    continue
                company_contact = company_contacts.get(ai.norm(company), {})
                lat = coordinate(value(row, "lat", "latitude"), -90, 90)
                lng = coordinate(value(row, "lng", "longitude"), -180, 180)
                if lat is None or lng is None:
                    lat, lng = GPS.get(city, (None, None))
                source_name = value(row, "source")
                db.execute(
                    "INSERT INTO offres(user_id,titre,entreprise,ville,secteur,type,competences,"
                    "specialite,email,tel,adresse,url,source,description,lat,lng) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (uid, title[:150], company[:150], city[:100], value(row, "secteur"),
                     value(row, "type", "type_contrat"), value(row, "competences"),
                     value(row, "specialite"), value(row, "email") or company_contact.get("email", ""),
                     value(row, "tel", "telephone") or company_contact.get("tel", ""),
                     value(row, "adresse") or company_contact.get("adresse", ""), url,
                     f"CSV local: {source_name}" if source_name else "CSV local",
                     value(row, "description")[:3000], lat, lng),
                )
                if url:
                    existing_urls.add(url)
                existing_titles.add(key)
            db.execute(
                "INSERT OR IGNORE INTO csv_imports(user_id,dataset) VALUES(?,?)",
                (uid, "offres"),
            )

    for offer in db.execute(
            "SELECT id,entreprise FROM offres WHERE user_id=? AND COALESCE(email,'')=''",
            (uid,)).fetchall():
        contact = company_contacts.get(ai.norm(offer["entreprise"]))
        if contact:
            db.execute(
                "UPDATE offres SET email=?, tel=CASE WHEN COALESCE(tel,'')='' THEN ? "
                "ELSE tel END WHERE id=?",
                (contact["email"], contact["tel"], offer["id"]),
            )
    db.commit()


def geocode(address):
    """OpenStreetMap Nominatim (1 requête/seconde max, User-Agent obligatoire)."""
    try:
        url = "https://nominatim.openstreetmap.org/search?format=json&limit=1&q=" + urllib.parse.quote(address)
        req = urllib.request.Request(url, headers=osm.UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
        return (float(d[0]["lat"]), float(d[0]["lon"])) if d else (None, None)
    except Exception:
        return None, None


def jooble_search(keywords, location):
    key = os.environ.get("JOOBLE_API_KEY", "").strip()
    if not key:
        return None, tr("Ajoute ta clé gratuite dans JOOBLE_API_KEY (jooble.org/api/about).")
    body = json.dumps({"keywords": keywords, "location": location}).encode()
    try:
        req = urllib.request.Request(f"https://jooble.org/api/{key}", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r).get("jobs", []), ""
    except Exception as e:
        return None, tr("Erreur Jooble : {err}", err=e)


def jooble_moroccan_city(location):
    parts = [ai.norm(part.strip()) for part in re.split(r"[,;/|]", location) if part.strip()]
    city = next((city for city in GPS if ai.norm(city) in parts), None)
    if city and (len(parts) == 1 or "morocco" in parts or "maroc" in parts):
        return city
    return None


def ensure_candidature(db, o, statut, canal, note):
    """Crée (ou met à jour) la candidature liée à une offre, avec contact et position."""
    today = date.today().isoformat()
    row = db.execute("SELECT id, statut FROM candidatures WHERE user_id=? AND entreprise=? AND poste=?",
                     (g.uid, o["entreprise"], o["titre"])).fetchone()
    if row:
        if row["statut"] == "A postuler" and statut != "A postuler":
            db.execute("UPDATE candidatures SET statut=?, canal=?, date=? WHERE id=?", (statut, canal, today, row["id"]))
            db.execute("INSERT INTO events(cand_id,date,texte) VALUES(?,?,?)", (row["id"], today, note))
        return row["id"]
    cur = db.execute(
        "INSERT INTO candidatures(user_id,entreprise,poste,ville,canal,statut,date,email,tel,lat,lng,offre_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (g.uid, o["entreprise"], o["titre"], o["ville"], canal, statut, today, o["email"], o["tel"], o["lat"], o["lng"], o["id"]))
    db.execute("INSERT INTO events(cand_id,date,texte) VALUES(?,?,?)", (cur.lastrowid, today, note))
    return cur.lastrowid


def insert_entreprises(db, uid, items, source="OpenStreetMap"):
    n = 0
    for d in items:
        if d.get("osm_id") and db.execute("SELECT 1 FROM entreprises WHERE user_id=? AND osm_id=?", (uid, d["osm_id"])).fetchone():
            continue
        db.execute("INSERT INTO entreprises(user_id,nom,ville,secteur,email,tel,site,adresse,lat,lng,source,osm_id) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (uid, d["nom"], d["ville"], d["secteur"], d.get("email", ""), d.get("tel", ""), d.get("site", ""),
                    d.get("adresse", ""), d["lat"], d["lng"], source, d.get("osm_id", "")))
        n += 1
    return n


def osm_all_cities(db_path, uid, type_key):
    st = PROGRESS[uid] = {"running": True, "done": 0, "total": len(GPS), "added": 0, "errors": 0}
    for ville, gps in GPS.items():
        try:
            items = osm.fetch(ville, gps, type_key)
            db = sqlite3.connect(db_path)
            st["added"] += insert_entreprises(db, uid, items)
            db.commit()
            db.close()
        except Exception:
            st["errors"] += 1
        st["done"] += 1
        osm.pause()
    st["running"] = False


DEMO_OFFRES = [
    ("Stage Data Analyst", "Société Démo A", "Rabat", "IT & Digital", "Stage", "python,pandas,sql,power bi", "Data & IA"),
    ("Stage Python / IA", "Société Démo B", "Marrakech", "IT & Digital", "Stage", "python,machine learning,scikit-learn", "Data & IA"),
    ("Data Engineer Junior", "Société Démo C", "Casablanca", "Finance & Assurance", "CDI", "python,sql,airflow,etl", "Data & IA"),
    ("Stage BI", "Société Démo D", "Tanger", "Industrie & Automobile", "Stage", "sql,power bi,excel", "BI & Reporting"),
    ("Développeur Flask", "Société Démo E", "Casablanca", "IT & Digital", "CDI", "python,flask,sql,git", "Développement"),
    ("Ingénieur NLP junior", "Société Démo F", "Rabat", "IT & Digital", "CDI", "python,nlp,llm,transformers", "Data & IA"),
]


def load_demo(db, uid):
    for i, (t, ent, v, sec, typ, comp, spec) in enumerate(DEMO_OFFRES, 1):
        lat, lng = gps_of(v, i)
        db.execute("INSERT INTO offres(user_id,titre,entreprise,ville,secteur,type,competences,specialite,email,tel,adresse,source,description,lat,lng) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (uid, t, ent, v, sec, typ, comp, spec, f"rh@demo-{i}.example", f"05 00 00 00 {i:02d}", f"Centre-ville, {v} (fictif)",
                    "Démo", f"Offre de démonstration : {t}.", lat, lng))
    rnd = random.Random(7)
    for v in ("Casablanca", "Rabat", "Tanger", "Marrakech", "Fès", "Agadir", "Kénitra", "Oujda"):
        for sec in ("IT & Digital", "Finance & Assurance", "Industrie & Automobile", "Agro-industrie", "Tourisme & Hôtellerie", "Santé"):
            for k in range(rnd.randint(3, 12)):
                lat, lng = gps_of(v, rnd.randint(1, 5000))
                db.execute("INSERT INTO entreprises(user_id,nom,ville,secteur,lat,lng,source) VALUES(?,?,?,?,?,?,?)",
                           (uid, f"Société Démo {v[:3]}-{sec[:3]}-{k + 1}", v, sec, lat, lng, "Démo"))


def clear_demo(db, uid):
    ids = [r[0] for r in db.execute("SELECT id FROM offres WHERE user_id=? AND source='Démo'", (uid,))]
    for oid in ids:
        for c in db.execute("SELECT id FROM candidatures WHERE user_id=? AND offre_id=?", (uid, oid)).fetchall():
            db.execute("DELETE FROM events WHERE cand_id=?", (c[0],))
            db.execute("DELETE FROM candidatures WHERE id=?", (c[0],))
    db.execute("DELETE FROM offres WHERE user_id=? AND source='Démo'", (uid,))
    db.execute("DELETE FROM entreprises WHERE user_id=? AND source='Démo'", (uid,))


def register(app, get_db, h):
    profil, DB = h["profil"], h["DB"]

    def offre(oid):
        r = get_db().execute("SELECT * FROM offres WHERE id=? AND user_id=?", (oid, g.uid)).fetchone()
        return dict(r) if r else None

    @app.route("/offres/<int:oid>")
    def offre_page(oid):
        sync_local_csv_data(get_db(), g.uid)
        o = offre(oid)
        if not o:
            return redirect(url_for("offres_page"))
        p = profil()
        mine = {ai.norm(s) for s in ai.skills_of(p)}
        req = [x.strip() for x in (o["competences"] or "").split(",") if x.strip()]
        cand = get_db().execute("SELECT * FROM candidatures WHERE user_id=? AND offre_id=?", (g.uid, oid)).fetchone()
        return render_template("offre.html", active="offres", o=o, req=req, mine=mine, cand=cand,
                               subject=f"Candidature – {o['titre']} – {p.get('nom', '')}", p=p, llm=ai.llm_enabled(),
                               sent=request.args.get("sent"), gmail=mailer.connected_email(get_db(), g.uid),
                               gmail_ok=mailer.configured(), email_saved=request.args.get("email_saved"),
                               email_error=request.args.get("email_error"))

    @app.post("/offres/<int:oid>/email")
    def save_offer_email(oid):
        address = request.form.get("email", "").strip()
        if not offre(oid):
            return redirect(url_for("offres_page"))
        if len(address) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address):
            return redirect(url_for("offre_page", oid=oid, email_error=1))
        db = get_db()
        db.execute("UPDATE offres SET email=? WHERE id=? AND user_id=?", (address, oid, g.uid))
        db.commit()
        return redirect(url_for("offre_page", oid=oid, email_saved=1))

    @app.post("/api/lettre/<int:oid>")
    def api_lettre(oid):
        o, p = offre(oid), profil()
        if not o:
            return jsonify(texte="")
        out, err = ai.ask_llm(
            f"Tu rédiges une lettre de motivation courte (150 à 200 mots), polie et personnalisée, en {'English' if ai.mail_lang() == 'en' else 'français'}. "
            "N'invente aucun fait absent du profil. Pas d'objet, commence par la salutation, termine par la signature. "
            "Le CV sera joint séparément au même email.",
            [{"role": "user", "content": json.dumps({"profil": p, "offre": {k: o[k] for k in ("titre", "entreprise", "ville", "description", "competences")}}, ensure_ascii=False)}], 500)
        if not out:
            sk = ", ".join(ai.skills_of(p)[:4]) or "Data"
            tel = f"\n{p['tel']}" if p.get("tel") else ""
            if ai.mail_lang() == "en":
                titre = p.get("titre") or "a student in artificial intelligence"
                what = f"the position « {o['titre']} »" if o["source"] != "Spontanée" else "a possible opportunity"
                out = (f"Hello,\n\nI am currently {titre[0].lower() + titre[1:]} and I am writing about {what} at {o['entreprise']}. "
                       f"I work with {sk} and have already built concrete projects with these tools. I would be glad to learn within your team.\n\n"
                       f"My CV is attached. I remain available to talk at your convenience.\n\nKind regards,\n{p.get('nom', '')}{tel}")
            else:
                titre = p.get("titre") or "étudiante en intelligence artificielle"
                what = f"du poste « {o['titre']} »" if o["source"] != "Spontanée" else "d'une éventuelle opportunité"
                out = (f"Bonjour,\n\nActuellement {titre[0].lower() + titre[1:]}, je vous écris au sujet {what} chez {o['entreprise']}. "
                       f"Je travaille avec {sk} et j'ai déjà mené des projets concrets avec ces outils. Je serais ravie d'apprendre au sein de votre équipe.\n\n"
                       f"Vous trouverez mon CV en pièce jointe. Je reste disponible pour un échange à votre convenance.\n\nCordialement,\n{p.get('nom', '')}{tel}")
        return jsonify(texte=out, mode="llm" if not err else "local", error="" if err in ("", "no_key") else err)

    @app.post("/offres/<int:oid>/envoye")
    def envoye(oid):
        o = offre(oid)
        if o:
            db = get_db()
            ensure_candidature(db, o, "Envoyée", "Email", f"Candidature envoyée par email à {o['email']}")
            db.commit()
        return redirect(url_for("offre_page", oid=oid, sent=1))

    @app.route("/carte")
    def carte():
        db = get_db()
        q = lambda sql: [dict(r) for r in db.execute(sql, (g.uid,))]
        pts = {"offres": q("SELECT id,titre,entreprise,ville,adresse,tel,email,lat,lng FROM offres WHERE user_id=? AND lat IS NOT NULL"),
               "entreprises": q("SELECT id,nom,secteur,ville,adresse,tel,email,site,lat,lng FROM entreprises WHERE user_id=? AND lat IS NOT NULL LIMIT 3000"),
               "suivi": q("SELECT id,poste,entreprise,ville,statut,tel,email,lat,lng,offre_id FROM candidatures WHERE user_id=? AND lat IS NOT NULL")}
        return render_template("carte.html", active="carte", pts=pts)

    # ------------------------------------------------------------ import
    @app.route("/importer")
    def importer():
        return redirect(url_for("offres_page", msg=request.args.get("msg", "")))

    def insert_offre(db, d):
        if d.get("url") and db.execute("SELECT 1 FROM offres WHERE user_id=? AND url=?", (g.uid, d["url"])).fetchone():
            return False
        lat, lng = d.get("lat"), d.get("lng")
        if lat is None and d.get("adresse"):
            lat, lng = geocode(f"{d['adresse']}, {d.get('ville', '')}, Maroc")
        if lat is None:
            lat, lng = gps_of(d.get("ville"), random.randint(1, 5000))
        db.execute("INSERT INTO offres(user_id,titre,entreprise,ville,secteur,type,competences,specialite,email,tel,adresse,url,source,description,lat,lng) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (g.uid, d.get("titre", "")[:150], d.get("entreprise", "")[:150], d.get("ville", ""), d.get("secteur", ""), d.get("type", ""),
                    d.get("competences", ""), d.get("specialite", ""), d.get("email", ""), d.get("tel", ""), d.get("adresse", ""),
                    d.get("url", ""), d.get("source", "Manuel"), d.get("description", "")[:3000], lat, lng))
        return True

    def back(msg):
        return redirect(url_for("importer", msg=msg))

    def csv_response(filename, columns, rows):
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(columns)
        writer.writerows(rows)
        return Response(
            "\ufeff" + output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/export/entreprises.csv")
    def export_entreprises_csv():
        columns = ("nom", "ville", "secteur", "email", "tel", "site", "adresse", "lat", "lng")
        rows = get_db().execute(
            "SELECT nom,ville,secteur,email,tel,site,adresse,lat,lng FROM entreprises "
            "WHERE user_id=? ORDER BY ville,nom", (g.uid,)).fetchall()
        return csv_response("entreprises.csv", columns, rows)

    @app.get("/export/offres.csv")
    def export_offres_csv():
        columns = ("titre", "entreprise", "ville", "email", "tel", "adresse", "specialite",
                   "competences", "url", "lat", "lng", "secteur", "type", "description", "source")
        rows = get_db().execute(
            "SELECT titre,entreprise,ville,email,tel,adresse,specialite,competences,url,lat,lng,"
            "secteur,type,description,source FROM offres WHERE user_id=? ORDER BY id", (g.uid,)).fetchall()
        return csv_response("offres.csv", columns, rows)

    @app.post("/importer/entreprises-csv")
    def importer_entreprises_csv():
        file = request.files.get("fichier")
        if not file or not file.filename.lower().endswith(".csv"):
            return back(tr("Choisis un fichier CSV d'entreprises."))
        try:
            reader = csv.DictReader(io.StringIO(file.read().decode("utf-8-sig")))
        except UnicodeDecodeError:
            return back(tr("Le fichier CSV doit être encodé en UTF-8."))
        headers = {str(name or "").strip().lower() for name in (reader.fieldnames or [])}
        if not {"nom", "ville"}.issubset(headers):
            return back(tr("Le CSV entreprises doit contenir les colonnes nom et ville."))

        db, added = get_db(), 0
        for row in reader:
            data = {str(key or "").strip().lower(): (value or "").strip()
                    for key, value in row.items() if key}
            name, city = data.get("nom", ""), data.get("ville", "")
            if not name or not city:
                continue
            city = next((known for known in GPS if ai.norm(known) == ai.norm(city)), city)
            if db.execute("SELECT 1 FROM entreprises WHERE user_id=? AND lower(nom)=lower(?) "
                          "AND lower(ville)=lower(?)", (g.uid, name, city)).fetchone():
                continue
            try:
                lat, lng = float(data.get("lat", "")), float(data.get("lng", ""))
                if not -90 <= lat <= 90 or not -180 <= lng <= 180:
                    raise ValueError
            except ValueError:
                lat, lng = GPS.get(city, (None, None))
            db.execute(
                "INSERT INTO entreprises(user_id,nom,ville,secteur,email,tel,site,adresse,lat,lng,source,osm_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (g.uid, name[:200], city[:100], data.get("secteur", "")[:120],
                 data.get("email", "")[:200], data.get("tel", "")[:80],
                 data.get("site", "")[:500], data.get("adresse", "")[:500],
                 lat, lng, "CSV", ""))
            added += 1
        db.commit()
        return back(tr("{n} entreprise(s) importée(s) depuis le CSV.", n=added))

    @app.post("/importer/places")
    def importer_places():
        type_key, ville = request.form.get("type", ""), request.form.get("ville", "")
        if type_key not in osm.TYPES or ville not in GPS:
            return back(tr("Choix invalide."))
        try:
            items = places.fetch(ville, GPS[ville], type_key)
        except Exception as e:
            return back(tr("Google Places n'a pas répondu ({err}). Vérifie la clé, l'API Places et la facturation.",
                           err=type(e).__name__))
        if not items:
            return back(tr("Aucune entreprise trouvée dans Google Places à {ville}. Essaie un autre type ou une autre ville.",
                           ville=ville))
        db = get_db()
        count = insert_entreprises(db, g.uid, items, source="Google Places")
        db.commit()
        return back(tr("{n} entreprise(s) ajoutée(s) depuis Google Places à {ville}.",
                       n=count, ville=ville))

    @app.post("/importer/vider-places")
    def vider_places():
        db = get_db()
        db.execute("DELETE FROM entreprises WHERE user_id=? AND source='Google Places'", (g.uid,))
        db.commit()
        return back(tr("Entreprises importées de Google Places supprimées."))

    @app.post("/importer/osm")
    def importer_osm():
        type_key, ville = request.form.get("type", ""), request.form.get("ville", "")
        if type_key not in osm.TYPES or (ville != "all" and ville not in GPS):
            return back(tr("Choix invalide."))
        if ville == "all":
            if PROGRESS.get(g.uid, {}).get("running"):
                return back(tr("Un import est déjà en cours."))
            threading.Thread(target=osm_all_cities, args=(DB, g.uid, type_key), daemon=True).start()
            return back(tr("Import lancé pour toutes les villes. La page se met à jour toute seule (environ 1 à 2 minutes)."))
        try:
            items = osm.fetch(ville, GPS[ville], type_key)
        except Exception as e:
            return back(tr("OpenStreetMap n'a pas répondu ({err}). Vérifie ta connexion et réessaie dans une minute.", err=type(e).__name__))
        db = get_db()
        n = insert_entreprises(db, g.uid, items)
        db.commit()
        if not items:
            return back(tr("Aucune entreprise « {type} » trouvée à {ville} dans OpenStreetMap. Essaie un autre type ou une autre ville.", type=tr(type_key), ville=tr(ville)))
        return back(tr("{n} entreprise(s) ajoutée(s) à {ville} ({type}). Retrouve-les dans Entreprises, Carte et Analyse.", n=n, ville=tr(ville), type=tr(type_key)))

    @app.post("/importer/manuel")
    def importer_manuel():
        f = request.form
        if f.get("titre", "").strip() and f.get("entreprise", "").strip():
            db = get_db()
            insert_offre(db, {k: f.get(k, "").strip() for k in
                              ("titre", "entreprise", "ville", "secteur", "type", "competences", "specialite", "email", "tel", "adresse", "url", "description")})
            db.commit()
        return back(tr("Offre ajoutée. Retrouve-la dans Offres et sur la Carte."))

    @app.post("/importer/csv")
    def importer_csv():
        file, n = request.files.get("fichier"), 0
        if file:
            db = get_db()
            for r in csv.DictReader(io.StringIO(file.read().decode("utf-8-sig"))):
                d = {k: (v or "").strip() for k, v in r.items() if k}
                for k in ("lat", "lng"):
                    try:
                        d[k] = float(d[k]) if d.get(k) else None
                    except ValueError:
                        d[k] = None
                d["source"] = d.get("source") or "CSV"
                n += insert_offre(db, d)
            db.commit()
        return back(tr("{n} offre(s) importée(s).", n=n))

    @app.post("/importer/jooble")
    def importer_jooble():
        kw, loc = request.form.get("keywords", "").strip(), request.form.get("location", "").strip()
        query_location = loc or "Morocco"
        if loc and "morocco" not in ai.norm(loc) and "maroc" not in ai.norm(loc):
            query_location = f"{loc}, Morocco"
        found_jobs, err = jooble_search(kw, query_location)
        if found_jobs is None:
            return back(err)
        db, n, eligible = get_db(), 0, 0
        for j in found_jobs[:40]:
            ville = jooble_moroccan_city(j.get("location") or "")
            if not ville:
                continue
            eligible += 1
            n += insert_offre(db, {"titre": j.get("title", ""), "entreprise": j.get("company") or "Entreprise non précisée",
                                   "ville": ville, "type": j.get("type", ""), "url": j.get("link", ""), "source": "Jooble",
                                   "specialite": kw, "description": re.sub(r"<[^>]+>", "", j.get("snippet", ""))})
        db.commit()
        if found_jobs and not eligible:
            return back(tr("Jooble n'a renvoyé aucune offre dans une ville marocaine reconnue. Vérifie les mots-clés et la ville."))
        return back(tr("{n} offre(s) importée(s) depuis Jooble.", n=n))

    @app.post("/importer/demo")
    def importer_demo():
        db = get_db()
        if request.form.get("action") == "clear":
            clear_demo(db, g.uid)
            msg = tr("Données de démonstration supprimées.")
        else:
            if not db.execute("SELECT 1 FROM offres WHERE user_id=? AND source='Démo'", (g.uid,)).fetchone():
                load_demo(db, g.uid)
            msg = tr("Données de démonstration chargées (fictives, à supprimer quand tu as tes vraies données).")
        db.commit()
        return back(msg)

    @app.post("/importer/vider-osm")
    def vider_osm():
        db = get_db()
        db.execute("DELETE FROM entreprises WHERE user_id=? AND source='OpenStreetMap'", (g.uid,))
        db.commit()
        return back(tr("Entreprises importées d'OpenStreetMap supprimées."))
