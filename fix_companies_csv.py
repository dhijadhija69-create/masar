import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "data" / "entreprises.csv"

df = pd.read_csv(CSV_FILE, dtype=str, keep_default_na=False)

# -------------------------------------------------
# 1. Récupérer les anciennes colonnes
# -------------------------------------------------

if "secteur" not in df.columns:
    df["secteur"] = ""

if "sous_secteur" not in df.columns:
    df["sous_secteur"] = ""

if "ville" not in df.columns:
    df["ville"] = ""

if "region" not in df.columns:
    df["region"] = ""

# Ancien secteur -> nouveau secteur
ancien_secteur = df.get("secteur_recherche", "")

for i in df.index:

    # Secteur
    if not df.at[i, "secteur"]:
        ancien = str(ancien_secteur.iloc[i]).lower()

        if "intelligence artificielle" in ancien:
            df.at[i, "secteur"] = "Technologie"
            df.at[i, "sous_secteur"] = "Intelligence Artificielle"

        elif "data" in ancien:
            df.at[i, "secteur"] = "Technologie"
            df.at[i, "sous_secteur"] = "Data / Analytics"

        elif "informatique" in ancien:
            df.at[i, "secteur"] = "Technologie"
            df.at[i, "sous_secteur"] = "Informatique"

        elif "digital" in ancien:
            df.at[i, "secteur"] = "Digital"
            df.at[i, "sous_secteur"] = "Digital"

        else:
            df.at[i, "secteur"] = "Autre"

    # Ville
    if not df.at[i, "ville"]:
        if "ville_recherchee" in df.columns:
            df.at[i, "ville"] = df.at[i, "ville_recherchee"]

# -------------------------------------------------
# 2. Déduire la région
# -------------------------------------------------

regions = {
    "Casablanca": "Casablanca-Settat",
    "Rabat": "Rabat-Salé-Kénitra",
    "Marrakech": "Marrakech-Safi",
    "Tanger": "Tanger-Tétouan-Al Hoceïma",
    "Fès": "Fès-Meknès",
    "Agadir": "Souss-Massa",
    "Meknès": "Fès-Meknès",
    "Oujda": "Oriental",
    "Kenitra": "Rabat-Salé-Kénitra",
    "El Jadida": "Casablanca-Settat",
    "Beni Mellal": "Béni Mellal-Khénifra",
}

for i in df.index:
    ville = df.at[i, "ville"].strip()

    if not df.at[i, "region"]:
        df.at[i, "region"] = regions.get(ville, "")

# -------------------------------------------------
# 3. Nettoyer les colonnes
# -------------------------------------------------

colonnes_finales = [
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
    "date_collecte",
]

for colonne in colonnes_finales:
    if colonne not in df.columns:
        df[colonne] = ""

df = df[colonnes_finales]

# Supprimer les doublons Google
df = df.drop_duplicates(
    subset=["id_google"],
    keep="first"
)

# Sauvegarder
df.to_csv(
    CSV_FILE,
    index=False,
    encoding="utf-8-sig"
)

print("=" * 60)
print("✅ CSV NORMALISÉ")
print("=" * 60)
print("Entreprises :", len(df))
print("Colonnes :", ", ".join(df.columns))
print("Fichier :", CSV_FILE)