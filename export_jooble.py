import os
import json
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv

# Charger les variables d'environnement
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("JOOBLE_API_KEY")

if not API_KEY:
    print("ERREUR : JOOBLE_API_KEY est vide.")
    raise SystemExit(1)


def rechercher_offres(mots_cles, ville):
    """Recherche les offres sur Jooble."""

    url = f"https://jooble.org/api/{API_KEY}"

    payload = {
        "keywords": mots_cles,
        "location": f"{ville}, Morocco"
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.load(response)

        return result.get("jobs", [])

    except urllib.error.HTTPError as error:
        print(f"Erreur HTTP {error.code}")
        return []

    except Exception as error:
        print("Erreur :", error)
        return []


# Recherches de test au Maroc
recherches = [
    ("Stage Data Analyst", "Casablanca"),
    ("Stage Data Analyst", "Marrakech"),
    ("Stage informatique", "Rabat"),
    ("Stage Python", "Casablanca"),
    ("Data Scientist", "Morocco"),
]

for mots_cles, ville in recherches:

    print("\n" + "=" * 50)
    print(f"Recherche : {mots_cles} | {ville}")

    offres = rechercher_offres(mots_cles, ville)

    print("Nombre d'offres :", len(offres))

    for offre in offres[:3]:
        print("Titre :", offre.get("title", ""))
        print("Entreprise :", offre.get("company", ""))
        print("Localisation :", offre.get("location", ""))
        print("Lien :", offre.get("link", ""))