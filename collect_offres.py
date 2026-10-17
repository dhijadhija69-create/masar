import csv
import re
from pathlib import Path

# =====================================================
# CONFIGURATION
# =====================================================

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "data" / "offres.csv"

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


# =====================================================
# NORMALISATION
# =====================================================

def normaliser(texte):
    if not texte:
        return ""

    texte = str(texte).lower()

    # Normalisation simple des accents
    remplacements = {
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "à": "a",
        "â": "a",
        "ä": "a",
        "î": "i",
        "ï": "i",
        "ô": "o",
        "ö": "o",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "ç": "c",
    }

    for ancien, nouveau in remplacements.items():
        texte = texte.replace(ancien, nouveau)

    texte = re.sub(r"\s+", " ", texte)

    return texte.strip()


# =====================================================
# CLASSIFICATION DES SECTEURS
# =====================================================

REGLES_SECTEURS = [

    (
        "Intelligence Artificielle",
        [
            "intelligence artificielle",
            "artificial intelligence",
            "machine learning",
            "deep learning",
            "computer vision",
            "generative ai",
            "gen ai",
            "llm",
            "ai engineer",
            "ingenieur ia",
            "ingenieur en ia"
        ]
    ),

    (
        "Data & Analytics",
        [
            "data analyst",
            "data scientist",
            "data engineer",
            "data analytics",
            "data science",
            "business intelligence",
            "business analytics",
            "analyse de donnees",
            "analyste de donnees",
            "analyste donnees",
            "aide a la decision",
            "big data",
            "power bi",
            "tableau",
            "machine learning"
        ]
    ),

    (
        "Informatique & Développement",
        [
            "informatique",
            "developpeur",
            "developpeuse",
            "developer",
            "software engineer",
            "developpement logiciel",
            "developpement web",
            "developpeur web",
            "developpeur python",
            "python",
            "java",
            "javascript",
            "php",
            "programmation",
            "programmeur",
            "technicien informatique",
            "agent informatique"
        ]
    ),

    (
        "Systèmes, Réseaux & Cybersécurité",
        [
            "cybersecurite",
            "cybersecurity",
            "cyber",
            "administrateur systeme",
            "administrateur reseau",
            "technicien reseau",
            "reseau informatique",
            "systeme informatique",
            "devops",
            "cloud",
            "cloud engineer",
            "securite informatique"
        ]
    ),

    (
        "Ressources Humaines",
        [
            "ressources humaines",
            "recrutement",
            "recruteur",
            "recruteuse",
            "responsable recrutement",
            "charge rh",
            "assistant rh",
            "gestionnaire de paie",
            "administration du personnel"
        ]
    ),

    (
        "Marketing & Communication",
        [
            "marketing",
            "communication",
            "digital marketing",
            "marketing digital",
            "community manager",
            "seo",
            "social media",
            "communication digitale"
        ]
    ),

    (
        "Finance & Comptabilité",
        [
            "comptable",
            "comptabilite",
            "finance",
            "financier",
            "controleur de gestion",
            "audit financier",
            "auditeur"
        ]
    ),

    (
        "Santé & Médical",
        [
            "medical",
            "medecin",
            "infirmier",
            "infirmiere",
            "pharmaceutique",
            "pharmacie",
            "laboratoire medical",
            "sante"
        ]
    ),

    (
        "Commerce & Vente",
        [
            "commercial",
            "commerciale",
            "vendeur",
            "vendeuse",
            "vente",
            "conseiller commercial",
            "conseillere commerciale",
            "agent commercial"
        ]
    ),

    (
        "Tourisme & Hôtellerie",
        [
            "hotellerie",
            "hotel",
            "receptionniste",
            "tourisme",
            "agence de voyage",
            "voyage",
            "excursion"
        ]
    ),

    (
        "Transport & Logistique",
        [
            "logistique",
            "transport",
            "supply chain",
            "magasinier",
            "chauffeur",
            "livreur"
        ]
    ),

    (
        "Industrie & Production",
        [
            "industrie",
            "production industrielle",
            "maintenance industrielle",
            "technicien de maintenance",
            "controle qualite",
            "ingenieur industriel"
        ]
    ),

    (
        "Éducation & Formation",
        [
            "education",
            "formation",
            "formateur",
            "formatrice",
            "enseignant",
            "enseignante",
            "professeur",
            "professeure"
        ]
    ),

    (
        "Juridique & Administration",
        [
            "juridique",
            "juriste",
            "affaires juridiques",
            "droit",
            "administration",
            "administratif",
            "administrative",
            "secretariat"
        ]
    )
]


def classifier_secteur(offre):

    titre = offre.get("titre", "")
    entreprise = offre.get("entreprise", "")
    description = offre.get("description", "")

    texte = normaliser(
        f"{titre} {entreprise} {description}"
    )

    for secteur, mots_cles in REGLES_SECTEURS:

        for mot in mots_cles:

            if mot in texte:
                return secteur

    # Si aucune spécialité détectée
    if offre.get("source", "") == "Wadifa Info":
        return "Fonction publique"

    return "Autre"


# =====================================================
# EXTRACTION DE LA VILLE
# =====================================================

VILLES = {
    "Casablanca": ["casablanca"],
    "Rabat": ["rabat"],
    "Marrakech": ["marrakech"],
    "Tanger": ["tanger", "tangier"],
    "Agadir": ["agadir"],
    "Fès": ["fes", "fès"],
    "Meknès": ["meknes", "meknès"],
    "Oujda": ["oujda"],
    "Kénitra": ["kenitra", "kénitra"],
    "Tétouan": ["tetouan", "tétouan"],
    "Safi": ["safi"],
    "El Jadida": ["el jadida"],
    "Béni Mellal": ["beni mellal", "béni mellal"],
    "Nador": ["nador"],
    "Settat": ["settat"],
    "Khouribga": ["khouribga"],
    "Laâyoune": ["laayoune", "laâyoune"],
    "Dakhla": ["dakhla"],
    "Mohammedia": ["mohammedia"],
    "Benguerir": ["benguerir"],
    "Aït Melloul": ["ait melloul", "aït melloul"],
    "Salé": ["sale", "salé"],
    "Essaouira": ["essaouira"],
    "Ouarzazate": ["ouarzazate"],
    "Errachidia": ["errachidia"],
    "Taza": ["taza"],
    "Larache": ["larache"],
    "Ifrane": ["ifrane"],
    "Khémisset": ["khemisset", "khémisset"],
    "Berrechid": ["berrechid"]
}


def extraire_ville(offre):

    # Si la ville existe déjà, on la conserve
    ville_existante = offre.get("ville", "").strip()

    if ville_existante:
        return ville_existante

    texte = normaliser(
        f"{offre.get('titre', '')} "
        f"{offre.get('description', '')}"
    )

    for ville, variantes in VILLES.items():

        for variante in variantes:

            if re.search(
                r"(?<!\w)" + re.escape(variante) + r"(?!\w)",
                texte
            ):
                return ville

    return ""


# =====================================================
# TRAITEMENT DU CSV
# =====================================================

def main():

    if not CSV_FILE.exists():
        print("ERREUR : offres.csv introuvable.")
        return

    with open(
        CSV_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as fichier:

        offres = list(csv.DictReader(fichier))

    print("=" * 60)
    print("MASAR - RECLASSIFICATION DES OFFRES")
    print("=" * 60)

    print("Offres trouvées :", len(offres))

    modifications = 0

    for offre in offres:

        ancien_secteur = offre.get("secteur", "")
        ancienne_ville = offre.get("ville", "")

        nouveau_secteur = classifier_secteur(offre)
        nouvelle_ville = extraire_ville(offre)

        offre["secteur"] = nouveau_secteur
        offre["ville"] = nouvelle_ville

        if (
            ancien_secteur != nouveau_secteur
            or ancienne_ville != nouvelle_ville
        ):
            modifications += 1

    # Sauvegarde
    with open(
        CSV_FILE,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as fichier:

        writer = csv.DictWriter(
            fichier,
            fieldnames=COLONNES
        )

        writer.writeheader()
        writer.writerows(offres)

    print()
    print("Reclassification terminée.")
    print("Offres modifiées :", modifications)
    print("Fichier :", CSV_FILE)

    print()
    print("Exemples Data / IT :")
    print("-" * 60)

    compteur = 0

    for offre in offres:

        if offre["secteur"] in [
            "Data & Analytics",
            "Intelligence Artificielle",
            "Informatique & Développement",
            "Systèmes, Réseaux & Cybersécurité"
        ]:

            print(
                f"{offre['titre']} | "
                f"{offre['secteur']} | "
                f"{offre['ville']} | "
                f"{offre['entreprise']}"
            )

            compteur += 1

            if compteur >= 20:
                break


if __name__ == "__main__":
    main()