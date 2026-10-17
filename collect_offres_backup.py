import csv
import re
import time
import html
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests


# ==================================================
# CONFIGURATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CSV_FILE = DATA_DIR / "offres.csv"

JAWB_URL = "https://jawb.ma/rss.xml"
WADIFA_URL = "https://www.wadifa-info.com/api/v1/concours?limit=100"

HEADERS = {
    "User-Agent": "Masar/1.0 (Morocco job opportunity aggregator)"
}

COLONNES = [
    "id_offre",
    "titre",
    "entreprise",
    "secteur",
    "ville",
    "type_contrat",
    "description",
    "date_publication",
    "lien",
    "source",
    "date_limite",
    "avis_officiel"
]

DATA_DIR.mkdir(exist_ok=True)


# ==================================================
# OUTILS
# ==================================================

def nettoyer(texte):
    """Nettoie le texte sans inventer d'informations."""
    if not texte:
        return ""

    texte = html.unescape(str(texte))
    texte = re.sub(r"<[^>]+>", " ", texte)
    texte = re.sub(r"\s+", " ", texte)

    return texte.strip()


def classer(titre, description=""):
    """Classe une annonce à partir de ses mots-clés."""

    texte = f"{titre} {description}".lower()

    if any(m in texte for m in [
        "stage", "stagiaire", "internship", "pfe"
    ]):
        type_contrat = "Stage"

    elif any(m in texte for m in [
        "cdi", "contrat à durée indéterminée"
    ]):
        type_contrat = "CDI"

    elif any(m in texte for m in [
        "cdd", "contrat à durée déterminée"
    ]):
        type_contrat = "CDD"

    elif any(m in texte for m in [
        "alternance", "alternant", "apprentissage"
    ]):
        type_contrat = "Alternance"

    else:
        type_contrat = "Non précisé"

    domaines = [
        ("Intelligence Artificielle", [
            "intelligence artificielle", "artificial intelligence",
            "machine learning", "deep learning"
        ]),
        ("Data", [
            "data analyst", "data scientist", "data science",
            "data engineer", "business intelligence", "big data"
        ]),
        ("Informatique", [
            "informatique", "développeur", "developer",
            "développement web", "python", "cybersécurité",
            "réseau informatique", "software"
        ]),
        ("Marketing", ["marketing", "communication"]),
        ("Finance et Comptabilité", [
            "comptable", "comptabilité", "finance"
        ]),
        ("Ressources Humaines", [
            "ressources humaines", "recrutement", "rh"
        ]),
        ("Management", ["management", "gestion de projet"]),
        ("Hôtellerie et Tourisme", [
            "hôtellerie", "hotel", "tourisme", "réceptionniste"
        ]),
    ]

    secteur = "Autre"

    for nom, mots in domaines:
        if any(mot in texte for mot in mots):
            secteur = nom
            break

    return secteur, type_contrat


def charger_csv():
    """Charge le fichier existant sans supprimer ses données."""

    if not CSV_FILE.exists():
        return []

    with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as f:
        lecteur = csv.DictReader(f)
        anciennes = []

        for ligne in lecteur:
            ancienne = {
                colonne: ligne.get(colonne, "") or ""
                for colonne in COLONNES
            }

            if ancienne.get("lien", "").strip():
                anciennes.append(ancienne)

        return anciennes


def sauvegarder_csv(lignes):
    """Sauvegarde toutes les annonces dans le CSV."""

    with open(CSV_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLONNES)
        writer.writeheader()
        writer.writerows(lignes)


def date_valide(valeur):
    """Vérifie les formats de date simples."""
    if not valeur:
        return ""

    valeur = str(valeur).strip()

    if re.match(r"^\d{4}-\d{2}-\d{2}$", valeur):
        return valeur

    return valeur


# ==================================================
# SOURCE 1 : JAWB.MA RSS
# ==================================================

def collecter_jawb():
    annonces = []

    print("\n[1/2] Collecte depuis Jawb.ma...")

    try:
        response = requests.get(
            JAWB_URL,
            headers=HEADERS,
            timeout=30
        )
        response.raise_for_status()

        root = ET.fromstring(response.content)
        items = root.findall(".//item")

        print("Annonces RSS reçues :", len(items))

        for item in items:
            titre = nettoyer(item.findtext("title", ""))
            lien = nettoyer(item.findtext("link", ""))
            description = nettoyer(item.findtext("description", ""))
            date_pub = nettoyer(item.findtext("pubDate", ""))

            if not titre or not lien:
                continue

            # On accepte seulement les liens HTTPS publics.
            parsed = urlparse(lien)

            if parsed.scheme != "https" or not parsed.netloc:
                continue

            secteur, type_contrat = classer(titre, description)

            annonces.append({
                "id_offre": "",
                "titre": titre,
                "entreprise": "",
                "secteur": secteur,
                "ville": "",
                "type_contrat": type_contrat,
                "description": description,
                "date_publication": date_pub,
                "lien": lien,
                "source": "Jawb.ma",
                "date_limite": "",
                "avis_officiel": ""
            })

        print("Annonces Jawb préparées :", len(annonces))

    except Exception as erreur:
        print("Erreur Jawb.ma :", erreur)

    return annonces


# ==================================================
# SOURCE 2 : WADIFA INFO API
# ==================================================

def collecter_wadifa():
    annonces = []

    print("\n[2/2] Collecte depuis Wadifa Info...")

    try:
        response = requests.get(
            WADIFA_URL,
            headers=HEADERS,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])

        print("Annonces API reçues :", len(items))

        for item in items:
            identifiant = str(item.get("id", "")).strip()
            titre = nettoyer(item.get("grade", ""))
            entreprise = nettoyer(item.get("employer", ""))
            lien = nettoyer(item.get("url", ""))
            avis_officiel = nettoyer(item.get("official_notice", ""))

            if not titre or not lien:
                continue

            parsed = urlparse(lien)

            if parsed.scheme != "https" or not parsed.netloc:
                continue

            publication = date_valide(item.get("published", ""))
            limite = date_valide(item.get("deadline", ""))
            postes = item.get("posts", "")

            description = (
                f"Nombre de postes : {postes}. "
                f"Date limite de candidature : {limite}."
            )

            annonces.append({
                "id_offre": f"WADIFA-{identifiant}",
                "titre": titre,
                "entreprise": entreprise,
                "secteur": "Fonction publique",
                "ville": "",
                "type_contrat": "Concours public",
                "description": description,
                "date_publication": publication,
                "lien": lien,
                "source": "Wadifa Info",
                "date_limite": limite,
                "avis_officiel": avis_officiel
            })

        print("Annonces Wadifa préparées :", len(annonces))

    except Exception as erreur:
        print("Erreur Wadifa Info :", erreur)

    return annonces


# ==================================================
# FUSION ET DEDOUBLONNAGE
# ==================================================

def main():
    anciennes = charger_csv()

    print("=" * 55)
    print("MASAR - COLLECTE DES OFFRES")
    print("=" * 55)
    print("Annonces déjà enregistrées :", len(anciennes))

    nouvelles = []
    nouvelles.extend(collecter_jawb())

    time.sleep(1)

    nouvelles.extend(collecter_wadifa())

    # Index des anciennes annonces par URL.
    par_lien = {}

    for annonce in anciennes:
        lien = annonce.get("lien", "").strip()
        if lien:
            par_lien[lien.rstrip("/")] = annonce

    ajoutees = 0
    mises_a_jour = 0

    for annonce in nouvelles:
        lien = annonce.get("lien", "").strip().rstrip("/")

        if not lien:
            continue

        if lien in par_lien:
            ancienne = par_lien[lien]

            # Complète seulement les champs vides.
            for cle, valeur in annonce.items():
                if valeur and not ancienne.get(cle):
                    ancienne[cle] = valeur

            mises_a_jour += 1

        else:
            if not annonce.get("id_offre"):
                annonce["id_offre"] = (
                    f"MASAR-{len(par_lien) + 1:06d}"
                )

            par_lien[lien] = annonce
            ajoutees += 1

    resultat = list(par_lien.values())

    # Ordre stable, du plus récent au plus ancien quand la date le permet.
    resultat.sort(
        key=lambda x: x.get("date_publication", ""),
        reverse=True
    )

    sauvegarder_csv(resultat)

    print("\n" + "=" * 55)
    print("COLLECTE TERMINÉE")
    print("=" * 55)
    print("Nouvelles annonces ajoutées :", ajoutees)
    print("Annonces existantes vérifiées :", mises_a_jour)
    print("Total dans offres.csv :", len(resultat))
    print("Fichier :", CSV_FILE)
    print("\nNote : les champs inconnus restent vides.")
    print("Source Wadifa Info : afficher le lien de l'annonce et")
    print("la mention « Source : Wadifa Info » dans Masar.")


if __name__ == "__main__":
    main()
