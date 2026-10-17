import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv
import csv
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

if not API_KEY:
    print("ERREUR : GOOGLE_PLACES_API_KEY est absente.")
    raise SystemExit(1)

URL = "https://places.googleapis.com/v1/places:searchText"

recherches = [
    ("entreprises intelligence artificielle", "Casablanca"),
    ("entreprises data analytics informatique", "Rabat"),
    ("entreprises développement logiciel", "Marrakech"),
    ("entreprises services numériques", "Tanger"),
    ("entreprises informatique", "Fès"),
    ("entreprises digitales", "Agadir"),
]

entreprises = {}

for secteur, ville in recherches:
    print(f"\nRecherche : {secteur} | {ville}")

    payload = {
        "textQuery": f"{secteur} à {ville}, Maroc",
        "pageSize": 10,
        "languageCode": "fr",
        "regionCode": "MA"
    }

    request = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": (
                "places.id,"
                "places.displayName,"
                "places.formattedAddress,"
                "places.websiteUri,"
                "places.nationalPhoneNumber"
            )
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            resultat = json.load(response)

        places = resultat.get("places", [])
        print("Résultats :", len(places))

        for place in places:
            nom = place.get("displayName", {}).get("text", "").strip()

            if not nom:
                continue

            identifiant = place.get("id", nom.lower())

            entreprises[identifiant] = {
                "entreprise": nom,
                "secteur_recherche": secteur,
                "ville_recherchee": ville,
                "adresse": place.get("formattedAddress", ""),
                "telephone": place.get("nationalPhoneNumber", ""),
                "site_web": place.get("websiteUri", "")
            }

    except urllib.error.HTTPError as erreur:
        print("Erreur HTTP :", erreur.code)
        print(erreur.read().decode("utf-8", errors="replace"))

    except Exception as erreur:
        print("Erreur :", erreur)

print("\n" + "=" * 45)
print("TOTAL D'ENTREPRISES UNIQUES :", len(entreprises))

for entreprise in list(entreprises.values())[:10]:
    print(
        entreprise["entreprise"],
        "|",
        entreprise["ville_recherchee"],
        "|",
        entreprise["site_web"]
    )
    # Créer le dossier data s'il n'existe pas
DOSSIER_DATA = BASE_DIR / "data"
DOSSIER_DATA.mkdir(exist_ok=True)

# Chemin du fichier CSV
FICHIER_CSV = DOSSIER_DATA / "entreprises.csv"

# Colonnes du fichier

colonnes = [
    "id_google",
    "entreprise",
    "secteur_recherche",
    "ville_recherchee",
    "adresse",
    "telephone",
    "email",
    "site_web",
    "source",
    "date_collecte"
]



# Enregistrer les entreprises
with open(FICHIER_CSV, "w", newline="", encoding="utf-8-sig") as fichier:
    writer = csv.DictWriter(fichier, fieldnames=colonnes)
    writer.writeheader()

    for identifiant, entreprise in entreprises.items():
        ligne = {
            "id_google": identifiant,
            **entreprise,
            "source": "Google Places",
            "date_collecte": datetime.now().strftime("%Y-%m-%d")
        }
        writer.writerow(ligne)

print("\n✅ Export CSV terminé !")
print("Fichier créé :", FICHIER_CSV)
print("Nombre d'entreprises enregistrées :", len(entreprises))