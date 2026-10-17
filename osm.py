"""Vraies entreprises depuis OpenStreetMap (Overpass API). Données ouvertes (ODbL), sans clé."""
import json
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "MasarApp/1.0 (projet etudiant)"}
OVERPASS = "https://overpass-api.de/api/interpreter"

TYPES = {  # type d'entreprise -> filtres OpenStreetMap
    "IT & Digital": ['["office"="it"]'],
    "Finance & Assurance": ['["office"~"insurance|financial"]', '["amenity"="bank"]'],
    "Industrie & Automobile": ['["industrial"]', '["man_made"="works"]'],
    "Agro-industrie": ['["industrial"~"food|agri"]'],
    "Offshoring & Télécoms": ['["office"~"telecommunication|call"]'],
    "Tourisme & Hôtellerie": ['["tourism"="hotel"]'],
    "Énergie & Environnement": ['["power"="plant"]', '["office"="energy_supplier"]'],
    "Santé": ['["amenity"~"hospital|clinic"]'],
    "Éducation & Formation": ['["amenity"~"university|college"]'],
    "Logistique & Transport": ['["office"~"logistics|courier"]'],
    "BTP & Immobilier": ['["office"~"construction|architect|estate_agent"]'],
    "Entreprises (général)": ['["office"="company"]'],
}


def bbox(ville, gps):
    lat, lng = gps
    d = 0.12
    return (lat - d, lng - d, lat + d, lng + d)  # sud, ouest, nord, est


def fetch(ville, gps, type_key, limit=80):
    s, w, n, e = bbox(ville, gps)
    parts = "".join(f"nwr{flt}({s:.4f},{w:.4f},{n:.4f},{e:.4f});" for flt in TYPES[type_key])
    query = f"[out:json][timeout:40];({parts});out center {limit};"
    req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": query}).encode(), headers=UA)
    with urllib.request.urlopen(req, timeout=70) as r:
        data = json.load(r)
    out = []
    for el in data.get("elements", []):
        t = el.get("tags", {})
        nom = t.get("name") or t.get("name:fr") or t.get("brand")
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if not nom or lat is None:
            continue
        adr = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street"), t.get("addr:suburb")) if x)
        out.append({
            "nom": nom, "ville": ville, "secteur": type_key,
            "email": t.get("email") or t.get("contact:email") or "",
            "tel": t.get("phone") or t.get("contact:phone") or t.get("contact:mobile") or "",
            "site": t.get("website") or t.get("contact:website") or "",
            "adresse": adr, "lat": lat, "lng": lng, "osm_id": f"{el['type']}/{el['id']}"})
    return out


def pause():
    time.sleep(2)  # courtoisie envers le serveur Overpass
