#!/usr/bin/env python3
"""
Millésime — compte le stock à dater (lecture seule).

Pour les scans « <TAG_PREFIXE>/<TAG_NON_DATEE> » :
  - nombre de scans ;
  - nombre de visages, nommés ou non ;
  - scans avec au moins un visage nommé ayant une date de naissance ;
  - personnes nommées sans date de naissance, groupes sans nom les plus fréquents.
Variables : IMMICH_URL, IMMICH_API_KEY (comme le test de mesure).
"""
import os
from collections import Counter

import requests

URL = os.environ.get("IMMICH_URL", "http://immich_server:2283").rstrip("/")
S = requests.Session()
S.headers["x-api-key"] = os.environ["IMMICH_API_KEY"]
PREFIXE = os.environ.get("TAG_PREFIXE", "Numérisation")
NON_DATEE = os.environ.get("TAG_NON_DATEE", "Non datée")


def api(m, chemin, **kw):
    r = S.request(m, f"{URL}/api{chemin}", timeout=60, **kw)
    r.raise_for_status()
    return r.json()


tag = next((t for t in api("GET", "/tags") if (t.get("value") or "") == f"{PREFIXE}/{NON_DATEE}"), None)
if not tag:
    raise SystemExit(f"Tag « {PREFIXE}/{NON_DATEE} » introuvable")

assets, page = [], 1
while page:
    bloc = api("POST", "/search/metadata", json={"tagIds": [tag["id"]], "page": page, "size": 250, "type": "IMAGE"})["assets"]
    assets += bloc["items"]
    page = int(bloc["nextPage"]) if bloc.get("nextPage") else None

nb_visages = nb_nommes = nb_exploitables_visages = 0
scans_exploitables = scans_avec_visage = 0
sans_naissance, groupes_sans_nom = Counter(), Counter()
for i, a in enumerate(assets, 1):
    faces = api("GET", "/faces", params={"id": a["id"]})
    nb_visages += len(faces)
    ok = False
    if faces:
        scans_avec_visage += 1
    for f in faces:
        p = f.get("person")
        if not p:
            continue
        if not p.get("name"):
            groupes_sans_nom[p["id"]] += 1
            continue
        nb_nommes += 1
        if p.get("birthDate"):
            nb_exploitables_visages += 1
            ok = True
        else:
            sans_naissance[p["name"]] += 1
    scans_exploitables += ok
    if i % 200 == 0:
        print(f"  {i}/{len(assets)} scans lus", flush=True)

n = max(1, len(assets))
print("\n=== Stock « Non datée » ===")
print(f"Scans : {len(assets)}")
print(f"Scans avec au moins un visage détecté : {scans_avec_visage} ({100 * scans_avec_visage // n} %)")
print(f"Scans datables aujourd'hui (≥ 1 visage nommé avec naissance) : {scans_exploitables} ({100 * scans_exploitables // n} %)")
print(f"Visages : {nb_visages} — nommés : {nb_nommes} — nommés avec naissance : {nb_exploitables_visages}")
print(f"Temps de calcul MiVOLO estimé sur le PC (1,5 s/visage nommé avec naissance, x2 avec buste) : "
      f"{nb_exploitables_visages * 3 / 60:.0f} min")
print(f"\nPersonnes nommées sans date de naissance ({len(sans_naissance)}) :")
for nom, c in sans_naissance.most_common(15):
    print(f"  {c:4d} visages  {nom}")
print(f"\nGroupes de visages sans nom : {len(groupes_sans_nom)} — les 10 plus fréquents :")
for pid, c in groupes_sans_nom.most_common(10):
    print(f"  {c:4d} visages  {URL}/people/{pid}")
