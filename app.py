"""Masar : suivi des candidatures, analyse des entreprises, comptes sécurisés (Flask)."""
import csv
import io
import os
import sqlite3
from datetime import date, timedelta
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

from flask import Flask, Response, g, redirect, render_template, request, url_for

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.environ.get("MASAR_DATA_DIR", BASE))
os.makedirs(DATA_DIR, exist_ok=True)


def load_env_files():
    """Lit .env ou api.env (dans ce dossier ou ses parents), sans dépendance externe."""
    for name in (".env", "api.env"):
        d = BASE
        for _ in range(3):
            path = os.path.join(d, name)
            if os.path.isfile(path):
                for line in open(path, encoding="utf-8-sig"):
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            d = os.path.dirname(d)


load_env_files()
DB = os.path.join(DATA_DIR, "masar.db")
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

STATUTS = ["A postuler", "Envoyée", "Entretien", "Réponse positive", "Refusée"]
CANAUX = ["Email", "LinkedIn", "Site de l'entreprise", "Rekrute", "Emploi.ma", "Autre"]
RELANCE_JOURS = 7
VILLES = ["Casablanca", "Rabat", "Tanger", "Marrakech", "Fès", "Agadir", "Kénitra", "Salé", "Meknès",
          "Mohammedia", "Tétouan", "Oujda", "El Jadida", "Béni Mellal", "Nador", "Safi", "Laâyoune", "Dakhla"]


# --------------------------------------------------------------------------- DB
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def ensure_cols(db, table, cols):
    have = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
    for name, typ in cols.items():
        if name not in have:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")


def init_db():
    db = sqlite3.connect(DB)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
        nom TEXT NOT NULL, pw_hash TEXT NOT NULL, created TEXT);
    CREATE TABLE IF NOT EXISTS profils(user_id INTEGER PRIMARY KEY, nom TEXT DEFAULT '', titre TEXT DEFAULT '',
        ville TEXT DEFAULT '', email TEXT DEFAULT '', tel TEXT DEFAULT '', bio TEXT DEFAULT '',
        competences TEXT DEFAULT '', formation TEXT DEFAULT '', experience TEXT DEFAULT '',
        langues TEXT DEFAULT '', projets TEXT DEFAULT '', photo INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS candidatures(id INTEGER PRIMARY KEY AUTOINCREMENT, entreprise TEXT NOT NULL,
        poste TEXT NOT NULL, ville TEXT, canal TEXT, statut TEXT NOT NULL, date TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, cand_id INTEGER NOT NULL,
        date TEXT NOT NULL, texte TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS offres(id INTEGER PRIMARY KEY AUTOINCREMENT, titre TEXT, entreprise TEXT,
        ville TEXT, secteur TEXT, type TEXT, competences TEXT);
    CREATE TABLE IF NOT EXISTS csv_imports(user_id INTEGER NOT NULL, dataset TEXT NOT NULL,
        PRIMARY KEY(user_id, dataset));
    CREATE TABLE IF NOT EXISTS entreprises(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, nom TEXT,
        ville TEXT, secteur TEXT, email TEXT DEFAULT '', tel TEXT DEFAULT '', site TEXT DEFAULT '',
        adresse TEXT DEFAULT '', lat REAL, lng REAL, source TEXT DEFAULT '', osm_id TEXT);
    CREATE TABLE IF NOT EXISTS cvs(user_id INTEGER PRIMARY KEY, poste TEXT, lang TEXT, data TEXT);
    """)
    ensure_cols(db, "users", {"lang": "TEXT"})
    ensure_cols(db, "candidatures", {"user_id": "INTEGER", "email": "TEXT DEFAULT ''", "tel": "TEXT DEFAULT ''",
                                     "lat": "REAL", "lng": "REAL", "offre_id": "INTEGER"})
    ensure_cols(db, "offres", {"user_id": "INTEGER", "specialite": "TEXT DEFAULT ''", "email": "TEXT DEFAULT ''",
                               "tel": "TEXT DEFAULT ''", "adresse": "TEXT DEFAULT ''", "url": "TEXT DEFAULT ''",
                               "source": "TEXT DEFAULT ''", "description": "TEXT DEFAULT ''",
                               "lat": "REAL", "lng": "REAL"})
    db.commit()
    db.close()


# ------------------------------------------------------------ candidatures
@app.route("/")
def home():
    return redirect(url_for("dashboard"))


def own_cand(cid):
    return get_db().execute("SELECT * FROM candidatures WHERE id=? AND user_id=?", (cid, g.uid)).fetchone()


@app.route("/candidatures")
def candidatures():
    db = get_db()
    q = request.args.get("q", "").strip().lower()
    ville = request.args.get("ville", "")
    rows = [dict(r) for r in db.execute("SELECT * FROM candidatures WHERE user_id=? ORDER BY date DESC", (g.uid,))
            if (not q or q in (r["entreprise"] + " " + r["poste"]).lower()) and (not ville or r["ville"] == ville)]
    today = date.today()
    for r in rows:
        r["jours"] = (today - date.fromisoformat(r["date"])).days
        r["relancer"] = r["statut"] == "Envoyée" and r["jours"] >= RELANCE_JOURS
        r["events"] = db.execute("SELECT * FROM events WHERE cand_id=? ORDER BY id DESC", (r["id"],)).fetchall()
    colonnes = {s: [r for r in rows if r["statut"] == s] for s in STATUTS}
    envoyees = [r for r in rows if r["statut"] != "A postuler"]
    repondu = [r for r in rows if r["statut"] in ("Entretien", "Réponse positive", "Refusée")]
    stats = {"total": len(rows), "taux": round(100 * len(repondu) / len(envoyees)) if envoyees else 0,
             "entretiens": sum(r["statut"] in ("Entretien", "Réponse positive") for r in rows),
             "relances": [r for r in rows if r["relancer"]]}
    return render_template("candidatures.html", active="candidatures", colonnes=colonnes, stats=stats,
                           statuts=STATUTS, canaux=CANAUX, villes=VILLES, q=request.args.get("q", ""),
                           ville=ville, today=today.isoformat(), relance_jours=RELANCE_JOURS)


@app.post("/candidatures/add")
def add():
    f = request.form
    if f.get("entreprise", "").strip() and f.get("poste", "").strip():
        db = get_db()
        statut_ = f.get("statut") if f.get("statut") in STATUTS else "A postuler"
        d = f.get("date") or date.today().isoformat()
        cur = db.execute("INSERT INTO candidatures(entreprise,poste,ville,canal,statut,date,user_id) VALUES(?,?,?,?,?,?,?)",
                         (f["entreprise"].strip()[:120], f["poste"].strip()[:120], f.get("ville", "")[:60],
                          f.get("canal", "")[:60], statut_, d, g.uid))
        txt = f"Candidature ajoutée · statut « {statut_} »" + (f" · {f['notes'].strip()[:300]}" if f.get("notes", "").strip() else "")
        db.execute("INSERT INTO events(cand_id,date,texte) VALUES(?,?,?)", (cur.lastrowid, d, txt))
        db.commit()
    return redirect(url_for("candidatures"))


@app.post("/candidatures/<int:cid>/statut")
def statut(cid):
    new, row = request.form.get("statut"), own_cand(cid)
    if row and new in STATUTS and new != row["statut"]:
        db = get_db()
        db.execute("UPDATE candidatures SET statut=? WHERE id=?", (new, cid))
        db.execute("INSERT INTO events(cand_id,date,texte) VALUES(?,?,?)",
                   (cid, date.today().isoformat(), f"Statut : {row['statut']} → {new}"))
        db.commit()
    return redirect(url_for("candidatures"))


@app.post("/candidatures/<int:cid>/note")
def note(cid):
    t = request.form.get("texte", "").strip()[:500]
    if t and own_cand(cid):
        db = get_db()
        db.execute("INSERT INTO events(cand_id,date,texte) VALUES(?,?,?)", (cid, date.today().isoformat(), t))
        db.commit()
    return redirect(url_for("candidatures"))


@app.post("/candidatures/<int:cid>/relance")
def relance(cid):
    if own_cand(cid):
        db = get_db()
        db.execute("UPDATE candidatures SET date=? WHERE id=?", (date.today().isoformat(), cid))
        db.execute("INSERT INTO events(cand_id,date,texte) VALUES(?,?,?)", (cid, date.today().isoformat(), "Relance envoyée"))
        db.commit()
    return redirect(url_for("candidatures"))


@app.post("/candidatures/<int:cid>/delete")
def delete(cid):
    if own_cand(cid):
        db = get_db()
        db.execute("DELETE FROM events WHERE cand_id=?", (cid,))
        db.execute("DELETE FROM candidatures WHERE id=?", (cid,))
        db.commit()
    return redirect(url_for("candidatures"))


# ----------------------------------------------------------------- analyse
def analyse_data():
    rows = get_db().execute("SELECT ville, secteur, COUNT(*) n FROM entreprises WHERE user_id=? AND ville<>'' AND secteur<>'' "
                            "GROUP BY ville, secteur", (g.uid,)).fetchall()
    return [(r["ville"], r["secteur"], r["n"]) for r in rows]


def selection(all_rows):
    present_s = sorted({s for _, s, _ in all_rows})
    present_v = sorted({v for v, _, _ in all_rows})
    secteurs = [s for s in request.args.getlist("secteur") if s in present_s] or present_s
    villes = [v for v in request.args.getlist("ville") if v in present_v] or present_v
    return present_s, present_v, secteurs, villes


@app.route("/analyse")
def analyse_page():
    data = analyse_data()
    present_s, present_v, secteurs, villes = selection(data)
    rows = [r for r in data if r[1] in secteurs and r[0] in villes]
    par_ville, par_secteur, cell = {}, {}, {}
    for v, s, n in rows:
        par_ville[v] = par_ville.get(v, 0) + n
        par_secteur[s] = par_secteur.get(s, 0) + n
        cell[(v, s)] = n
    total = sum(par_ville.values())
    top_villes = sorted(par_ville.items(), key=lambda x: -x[1])
    top_secteurs = sorted(par_secteur.items(), key=lambda x: -x[1])
    return render_template(
        "analyse.html", active="analyse", empty=not data, present_s=present_s, present_v=present_v,
        sel_s=request.args.getlist("secteur"), sel_v=request.args.getlist("ville"), secteurs=secteurs, total=total,
        top_villes=top_villes, top_secteurs=top_secteurs, cell=cell, vmax=max(cell.values()) if cell else 1,
        top_villes_dict=par_ville, ordre_villes=[v for v, _ in top_villes],
        part_top3=round(100 * sum(n for _, n in top_villes[:3]) / total) if total else 0,
        query=request.query_string.decode())


@app.route("/analyse.csv")
def analyse_csv():
    data = analyse_data()
    _, _, secteurs, villes = selection(data)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ville", "secteur", "nb_entreprises"])
    w.writerows(sorted((r for r in data if r[1] in secteurs and r[0] in villes), key=lambda r: -r[2]))
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=analyse_entreprises.csv"})


init_db()

import auth  # noqa: E402
import extra  # noqa: E402
import i18n  # noqa: E402

i18n.init(app, get_db)  # avant auth : la langue sert aux messages d'erreur
auth.init(app, get_db, BASE)
extra.register(app, get_db, {"STATUTS": STATUTS, "RELANCE_JOURS": RELANCE_JOURS, "DB": DB, "BASE": BASE,
                             "VILLES": VILLES})

if __name__ == "__main__":
    # Le mode debug expose un débogueur : activé seulement si MASAR_DEBUG=1
    app.run(debug=os.environ.get("MASAR_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
