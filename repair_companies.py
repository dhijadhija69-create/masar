import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "data" / "entreprises.csv"

df = pd.read_csv(
    CSV_FILE,
    dtype=str,
    keep_default_na=False
)

# ---------------------------------------------------------
# Les 60 premières entreprises viennent des 6 recherches
# originales : 10 résultats par recherche.
# ---------------------------------------------------------

groupes = [
    # 1
    ("Technologie", "Intelligence Artificielle", "Casablanca", "Casablanca-Settat"),

    # 2
    ("Technologie", "Data / Informatique", "Rabat", "Rabat-Salé-Kénitra"),

    # 3
    ("Technologie", "Développement logiciel", "Marrakech", "Marrakech-Safi"),

    # 4
    ("Digital", "Services numériques", "Tanger", "Tanger-Tétouan-Al Hoceïma"),

    # 5
    ("Technologie", "Informatique", "Fès", "Fès-Meknès"),

    # 6
    ("Digital", "Digital", "Agadir", "Souss-Massa"),
]

# Remplir les 60 premières lignes
for groupe_index, (secteur, sous_secteur, ville, region) in enumerate(groupes):

    debut = groupe_index * 10
    fin = debut + 10

    for i in range(debut, min(fin, len(df))):

        # Seulement si les informations sont vides
        if not df.at[i, "secteur"]:
            df.at[i, "secteur"] = secteur

        if not df.at[i, "sous_secteur"]:
            df.at[i, "sous_secteur"] = sous_secteur

        if not df.at[i, "ville"]:
            df.at[i, "ville"] = ville

        if not df.at[i, "region"]:
            df.at[i, "region"] = region


# ---------------------------------------------------------
# Pour les autres entreprises : nettoyer les champs
# ---------------------------------------------------------

for colonne in [
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
]:
    df[colonne] = df[colonne].fillna("").astype(str)


# ---------------------------------------------------------
# Supprimer les doublons Google
# ---------------------------------------------------------

df = df.drop_duplicates(
    subset=["id_google"],
    keep="first"
)


# ---------------------------------------------------------
# Export
# ---------------------------------------------------------

df.to_csv(
    CSV_FILE,
    index=False,
    encoding="utf-8-sig"
)

print("=" * 60)
print("✅ RÉPARATION TERMINÉE")
print("=" * 60)

print("Nombre d'entreprises :", len(df))
print()
print("Répartition par ville :")
print(df["ville"].value_counts().to_string())

print()
print("Répartition par secteur :")
print(df["secteur"].value_counts().to_string())

print()
print("Fichier :", CSV_FILE)