"""Entreprises depuis Google Places API (New) : Text Search. Clé dans .env : GOOGLE_PLACES_API_KEY."""
import json
import os
import urllib.error
import urllib.request

URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ("places.id,places.displayName,places.formattedAddress,places.location,"
          "places.nationalPhoneNumber,places.internationalPhoneNumber,places.websiteUri")

# type d'entreprise (mêmes clés que osm.TYPES) -> texte de recherche
QUERIES = {
    "IT & Digital": "société informatique",
    "Finance & Assurance": "banque assurance",
    "Industrie & Automobile": "usine industrie",
    "Agro-industrie": "industrie agroalimentaire",
    "Offshoring & Télécoms": "centre d'appels télécom",
    "Tourisme & Hôtellerie": "hôtel",
    "Énergie & Environnement": "entreprise énergie",
    "Santé": "clinique",
    "Éducation & Formation": "centre de formation",
    "Logistique & Transport": "société logistique transport",
    "BTP & Immobilier": "entreprise BTP agence immobilière",
    "Entreprises (général)": "entreprise",
}


def fetch(ville, gps, type_key, limit=20):
    key = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    if not key:
        raise RuntimeError("clé GOOGLE_PLACES_API_KEY absente de .env")
    lat, lng = gps
    body = {"textQuery": f"{QUERIES.get(type_key, 'entreprise')} {ville} Maroc",
            "languageCode": "fr", "regionCode": "MA", "pageSize": min(limit, 20),
            "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 15000.0}}}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        raise RuntimeError(f"HTTP {e.code} {msg[:180]}")
    out = []
    for p in data.get("places", []):
        loc = p.get("location") or {}
        nom = (p.get("displayName") or {}).get("text")
        if not nom or loc.get("latitude") is None:
            continue
        out.append({
            "nom": nom, "ville": ville, "secteur": type_key, "email": "",
            "tel": p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber") or "",
            "site": p.get("websiteUri") or "", "adresse": p.get("formattedAddress") or "",
            "lat": loc["latitude"], "lng": loc["longitude"], "osm_id": f"google/{p['id']}"})
    return out
