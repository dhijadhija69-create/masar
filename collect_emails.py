import re
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin, urlparse

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "data" / "entreprises.csv"

# نجيب غير 10 شركات فالتجربة الأولى
TEST_LIMIT = 1000

EMAIL_REGEX = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)

PAGES = [
    "",
    "/contact",
    "/contactez-nous",
    "/contact-us",
    "/recrutement",
    "/careers",
    "/jobs",
    "/emploi",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/142 Safari/537.36"
    )
}


def nettoyer_url(url):
    if not url:
        return ""

    url = url.strip()

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url.rstrip("/")


def trouver_emails(html):
    emails = set()

    # Emails visibles dans le HTML
    for email in EMAIL_REGEX.findall(html):
        email = email.lower().strip()

        # Exclure quelques faux résultats fréquents
        if not email.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            emails.add(email)

    return sorted(emails)


def chercher_email(site):
    site = nettoyer_url(site)

    if not site:
        return None, None

    # Vérifier que le domaine est valide
    try:
        domaine = urlparse(site).netloc
    except Exception:
        return None, None

    if not domaine:
        return None, None

    for page in PAGES:

        url = urljoin(site + "/", page.lstrip("/"))

        try:

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=10,
                allow_redirects=True
            )

            if response.status_code != 200:
                continue

            emails = trouver_emails(response.text)

            if emails:

                # Priorité aux emails professionnels
                priorites = [
                    "recrutement",
                    "recruitment",
                    "career",
                    "careers",
                    "emploi",
                    "rh",
                    "hr",
                    "jobs",
                    "contact",
                    "info",
                ]

                emails = sorted(
                    emails,
                    key=lambda e: next(
                        (
                            i
                            for i, mot in enumerate(priorites)
                            if mot in e
                        ),
                        999
                    )
                )

                return emails[0], url

        except requests.RequestException:
            continue

        except Exception:
            continue

    return None, None


# ---------------------------------------------------------
# Charger le CSV
# ---------------------------------------------------------

df = pd.read_csv(
    CSV_FILE,
    dtype=str,
    keep_default_na=False
)

if "email" not in df.columns:
    df["email"] = ""

if "source_email" not in df.columns:
    df["source_email"] = ""


# ---------------------------------------------------------
# Test sur 10 entreprises
# ---------------------------------------------------------

indices = df.index[df["site_web"].str.strip() != ""][:TEST_LIMIT]

print("=" * 60)
print("TEST COLLECTE EMAIL")
print("=" * 60)

print("Entreprises testées :", len(indices))

trouves = 0

for i in indices:

    entreprise = df.at[i, "entreprise"]
    site = df.at[i, "site_web"]

    print()
    print("Entreprise :", entreprise)
    print("Site       :", site)

    email, source = chercher_email(site)

    if email:

        df.at[i, "email"] = email
        df.at[i, "source_email"] = source

        print("✅ Email :", email)
        print("Source   :", source)

        trouves += 1

    else:

        print("❌ Aucun email trouvé")

    time.sleep(1)


# ---------------------------------------------------------
# Sauvegarder
# ---------------------------------------------------------

df.to_csv(
    CSV_FILE,
    index=False,
    encoding="utf-8-sig"
)

print()
print("=" * 60)
print("TEST TERMINÉ")
print("=" * 60)

print("Emails trouvés :", trouves)
print("Entreprises testées :", len(indices))
print("Fichier :", CSV_FILE)