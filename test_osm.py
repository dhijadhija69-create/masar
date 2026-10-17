import json
import urllib.parse
import urllib.request

query = """
[out:json][timeout:40];
area["name"="Marrakech"]["boundary"="administrative"]["admin_level"~"^[456]$"]->.a;
(
  nwr["office"](area.a);
  nwr["craft"](area.a);
  nwr["shop"="computer"](area.a);
  nwr["amenity"="coworking_space"](area.a);
);
out center tags;
"""

url = "https://overpass.kumi.systems/api/interpreter"

data = urllib.parse.urlencode({"data": query}).encode("utf-8")

req = urllib.request.Request(
    url,
    data=data,
    headers={"User-Agent": "MasarApp/1.0"},
    method="POST"
)

try:
    with urllib.request.urlopen(req, timeout=60) as response:
        result = json.load(response)

    elements = result.get("elements", [])

    print("Nombre de résultats :", len(elements))

    for element in elements[:15]:
        tags = element.get("tags", {})

        print("-" * 40)
        print("Nom :", tags.get("name", "Sans nom"))
        print("Type :", tags.get("office", tags.get("craft", tags.get("shop", ""))))
        print("Ville :", tags.get("addr:city", ""))
        print("Site :", tags.get("website", tags.get("contact:website", "")))
        print("Email :", tags.get("email", tags.get("contact:email", "")))
        print("Téléphone :", tags.get("phone", tags.get("contact:phone", "")))

except Exception as e:
    print("Erreur :", e)