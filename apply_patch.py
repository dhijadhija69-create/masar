"""Applique les changements Masar (Jooble, Google Places, filtres fixes) sur jobs.py et extra.py.
Lance-le depuis le dossier masar_flask :  python apply_patch.py
Une copie de sauvegarde est créée (jobs.py.bak, extra.py.bak)."""
import os
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

JOBS = [
    # imports
    ('''import urllib.parse
import urllib.request
''', '''import urllib.error
import urllib.parse
import urllib.request
'''),
    ('''import ai
import osm
''', '''import ai
import osm
import places
'''),
    # Jooble : User-Agent + erreurs HTTP lisibles
    ('''    body = json.dumps({"keywords": keywords, "location": location}).encode()
    try:
        req = urllib.request.Request(f"https://jooble.org/api/{key}", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r).get("jobs", []), ""
    except Exception as e:
        return None, tr("Erreur Jooble : {err}", err=e)
''', '''    body = json.dumps({"keywords": keywords, "location": location, "page": 1}).encode()
    try:
        req = urllib.request.Request(f"https://jooble.org/api/{key}", data=body,
                                     headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (MasarApp/1.0)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r).get("jobs", []), ""
    except urllib.error.HTTPError as e:
        return None, tr("Erreur Jooble : {err}", err=f"HTTP {e.code} (clé invalide ou refusée ?)")
    except Exception as e:
        return None, tr("Erreur Jooble : {err}", err=e)
'''),
    # Jooble : message si 0 résultat
    ('''        if jobs is None:
            return back(err)
''', '''        if jobs is None:
            return back(err)
        if not jobs:
            return back("Jooble n'a trouvé aucune offre pour cette recherche. Essaie « analyste de données » ou « data analyst », ou laisse la ville vide.")
'''),
    # Import entreprises (une ville) : OpenStreetMap + Google Places si la clé existe
    ('''        try:
            items = osm.fetch(ville, GPS[ville], type_key)
        except Exception as e:
            return back(tr("OpenStreetMap n'a pas répondu ({err}). Vérifie ta connexion et réessaie dans une minute.", err=type(e).__name__))
        db = get_db()
        n = insert_entreprises(db, g.uid, items)
        db.commit()
        if not items:
            return back(tr("Aucune entreprise « {type} » trouvée à {ville} dans OpenStreetMap. Essaie un autre type ou une autre ville.", type=tr(type_key), ville=tr(ville)))
        return back(tr("{n} entreprise(s) ajoutée(s) à {ville} ({type}). Retrouve-les dans Entreprises, Carte et Analyse.", n=n, ville=tr(ville), type=tr(type_key)))
''', '''        db = get_db()
        n_osm = n_google = 0
        errs = []
        try:
            n_osm = insert_entreprises(db, g.uid, osm.fetch(ville, GPS[ville], type_key))
        except Exception as e:
            errs.append("OpenStreetMap : " + type(e).__name__)
        if os.environ.get("GOOGLE_PLACES_API_KEY", "").strip():
            try:
                n_google = insert_entreprises(db, g.uid, places.fetch(ville, GPS[ville], type_key), source="Google Places")
            except Exception as e:
                errs.append("Google Places : " + str(e)[:150])
        db.commit()
        msg = f"{n_osm + n_google} entreprise(s) ajoutée(s) à {ville} ({type_key}) : OpenStreetMap {n_osm}, Google Places {n_google}."
        if errs:
            msg += " Erreurs : " + " | ".join(errs)
        return back(msg)
'''),
]

EXTRA = [
    ('''import cvpdf
import jobs
''', '''import cvpdf
import jobs
import osm
'''),
    ('villes=sorted({r["ville"] for r in rows if r["ville"]})',
     'villes=sorted(set(ctx["VILLES"]) | {r["ville"] for r in rows if r["ville"]})'),
    ('secteurs=sorted({r["secteur"] for r in rows if r["secteur"]})',
     'secteurs=sorted(set(osm.TYPES) | {r["secteur"] for r in rows if r["secteur"]})'),
    ('specialites=sorted({r["specialite"] for r in rows if r["specialite"]})',
     'specialites=sorted({"Data & IA", "BI & Reporting", "Développement"} | {r["specialite"] for r in rows if r["specialite"]})'),
    ('villes=sorted({r["ville"] for r in allrows})',
     'villes=sorted(set(ctx["VILLES"]) | {r["ville"] for r in allrows})'),
    ('secteurs=sorted({r["secteur"] for r in allrows})',
     'secteurs=sorted(set(osm.TYPES) | {r["secteur"] for r in allrows})'),
]


def patch(name, changes):
    path = os.path.join(BASE, name)
    if not os.path.isfile(path):
        sys.exit(f"ERREUR : {name} introuvable dans {BASE}")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if "import places" in text or 'ctx["VILLES"]' in text:
        print(f"{name} : déjà modifié, rien à faire.")
        return
    for i, (old, new) in enumerate(changes, 1):
        if text.count(old) != 1:
            sys.exit(f"ERREUR dans {name}, changement n°{i} : texte original introuvable (fichier déjà modifié à la main ?). Rien n'a été écrit.")
        text = text.replace(old, new)
    shutil.copy(path, path + ".bak")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"{name} : OK ({len(changes)} changements, sauvegarde {name}.bak)")


if not os.path.isfile(os.path.join(BASE, "places.py")):
    sys.exit("ERREUR : places.py doit être dans le même dossier.")
patch("jobs.py", JOBS)
patch("extra.py", EXTRA)
print("Terminé. Ajoute GOOGLE_PLACES_API_KEY et JOOBLE_API_KEY dans .env puis lance : python app.py")
