import os
import csv
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv


# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CSV_FILE = DATA_DIR / "entreprises.csv"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

if not API_KEY:
    print("❌ GOOGLE_PLACES_API_KEY est absente du fichier .env")
    raise SystemExit(1)


# ============================================================
# 2. RECHERCHES
# ============================================================

recherches = [

    # IA / DATA
    ("intelligence artificielle", "Casablanca", "Technologie", "Intelligence Artificielle"),
    ("intelligence artificielle", "Rabat", "Technologie", "Intelligence Artificielle"),
    ("intelligence artificielle", "Marrakech", "Technologie", "Intelligence Artificielle"),

    ("data science", "Casablanca", "Technologie", "Data Science"),
    ("data science", "Rabat", "Technologie", "Data Science"),
    ("data science", "Marrakech", "Technologie", "Data Science"),

    ("data analytics", "Casablanca", "Technologie", "Data Analytics"),
    ("data analytics", "Rabat", "Technologie", "Data Analytics"),
    ("data analytics", "Marrakech", "Technologie", "Data Analytics"),

    ("business intelligence", "Casablanca", "Technologie", "Business Intelligence"),
    ("business intelligence", "Rabat", "Technologie", "Business Intelligence"),

    # INFORMATIQUE
    ("entreprise informatique", "Casablanca", "Technologie", "Informatique"),
    ("entreprise informatique", "Rabat", "Technologie", "Informatique"),
    ("entreprise informatique", "Marrakech", "Technologie", "Informatique"),
    ("entreprise informatique", "Tanger", "Technologie", "Informatique"),
    ("entreprise informatique", "Fès", "Technologie", "Informatique"),

    # DEVELOPPEMENT
    ("développement logiciel", "Casablanca", "Technologie", "Développement logiciel"),
    ("développement logiciel", "Rabat", "Technologie", "Développement logiciel"),
    ("développement logiciel", "Marrakech", "Technologie", "Développement logiciel"),

    # DIGITAL
    ("agence digitale", "Casablanca", "Digital", "Agence digitale"),
    ("agence digitale", "Rabat", "Digital", "Agence digitale"),
    ("agence digitale", "Marrakech", "Digital", "Agence digitale"),
    ("agence digitale", "Tanger", "Digital", "Agence digitale"),

    # CYBERSECURITE
    ("cybersécurité", "Casablanca", "Technologie", "Cybersécurité"),
    ("cybersécurité", "Rabat", "Technologie", "Cybersécurité"),

    # MARKETING
    ("agence marketing digital", "Casablanca", "Digital", "Marketing digital"),
    ("agence marketing digital", "Rabat", "Digital", "Marketing digital"),
    ("agence marketing digital", "Marrakech", "Digital", "Marketing digital"),
]


# ============================================================
# 3. GOOGLE PLACES
# ============================================================

URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.websiteUri,"
    "places.nationalPhoneNumber,"
    "places.location"
)


def rechercher_google(texte, ville):

    payload = {
        "textQuery": f"{texte} à {ville}, Maroc",
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
            "X-Goog-FieldMask": FIELD_MASK
        },
        method="POST"
    )

    try:

        with urllib.request.urlopen(request, timeout=30) as response:
            resultat = json.load(response)

        return resultat.get("places", [])

    except urllib.error.HTTPError as error:

        print(f"❌ Erreur Google HTTP {error.code}")
        return []

    except Exception as error:

        print("❌ Erreur :", error)
        return []


# ============================================================
# 4. CHARGER LES ENTREPRISES EXISTANTES
# ============================================================

entreprises = {}

if CSV_FILE.exists():

    with open(
        CSV_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as fichier:

        reader = csv.DictReader(fichier)

        for ligne in reader:

            identifiant = ligne.get("id_google", "").strip()

            if identifiant:
                entreprises[identifiant] = ligne


print()
print("=" * 60)
print("ENTREPRISES EXISTANTES :", len(entreprises))
print("=" * 60)


# ============================================================
# 5. COLLECTE
# ============================================================

for texte, ville, secteur, sous_secteur in recherches:

    print()
    print("Recherche :", texte)
    print("Ville     :", ville)

    places = rechercher_google(texte, ville)

    print("Résultats :", len(places))

    for place in places:

        google_id = place.get("id", "")

        if not google_id:
            continue

        nom = place.get("displayName", {}).get("text", "")

        adresse = place.get(
            "formattedAddress",
            ""
        )

        telephone = place.get(
            "nationalPhoneNumber",
            ""
        )

        site_web = place.get(
            "websiteUri",
            ""
        )

        location = place.get(
            "location",
            {}
        )

        latitude = location.get(
            "latitude",
            ""
        )

        longitude = location.get(
            "longitude",
            ""
        )

        # Nouvelle entreprise
        if google_id not in entreprises:

            entreprises[google_id] = {

                "id_google": google_id,

                "entreprise": nom,

                "secteur": secteur,

                "sous_secteur": sous_secteur,

                "ville": ville,

                "region": "",

                "adresse": adresse,

                "telephone": telephone,

                "email": "",

                "site_web": site_web,

                "latitude": latitude,

                "longitude": longitude,

                "type": "",

                "source": "Google Places",

                "date_collecte":
                    datetime.now().strftime("%Y-%m-%d")
            }

        else:

            # Compléter les informations manquantes
            ancienne = entreprises[google_id]

            if not ancienne.get("telephone"):
                ancienne["telephone"] = telephone

            if not ancienne.get("site_web"):
                ancienne["site_web"] = site_web

            if not ancienne.get("adresse"):
                ancienne["adresse"] = adresse


# ============================================================
# 6. EXPORT CSV
# ============================================================

colonnes = [
    "id_google",
    "entreprise",
    "secteur",
    "sous_secteur",
    "ville",
    "region",
    "adresse",
    "telephone",
    "email",
    "site_web",
    "latitude",
    "longitude",
    "type",
    "source",
    "date_collecte"
]

with open(
    CSV_FILE,
    "w",
    encoding="utf-8-sig",
    newline=""
) as fichier:

    writer = csv.DictWriter(
        fichier,
        fieldnames=colonnes
    )

    writer.writeheader()

    for entreprise in entreprises.values():

        ligne = {
            colonne: entreprise.get(colonne, "")
            for colonne in colonnes
        }

        writer.writerow(ligne)


# ============================================================
# 7. RESULTAT
# ============================================================

print()
print("=" * 60)
print("✅ COLLECTE TERMINÉE")
print("=" * 60)

print(
    "Nombre total d'entreprises :",
    len(entreprises)
)

print(
    "Fichier :",
    CSV_FILE
)