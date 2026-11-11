#!/usr/bin/env python3
"""
Millésime — calculateur à lancer sur le PC (image « calcul »).

1. Demande à Millésime (NAS) les visages à analyser.
2. Télécharge les aperçus PAR Millésime (la clé Immich reste sur le NAS).
3. Calcule l'âge avec MiVOLO v2 : visage seul et visage + buste estimé.
4. Renvoie les résultats par lots, et s'arrête quand la file est vide.

Variables : MILLESIME_URL (ex. http://192.168.1.10:8098), MILLESIME_JETON_CALCUL, THREADS.
"""
from __future__ import annotations

import os
import platform
import sys
import time
from io import BytesIO

import requests
from PIL import Image

URL = os.environ.get("MILLESIME_URL", "http://192.168.1.10:8098").rstrip("/")
JETON = os.environ.get("MILLESIME_JETON_CALCUL", "")
LOT = int(os.environ.get("LOT", "20"))
os.environ.setdefault("MIVOLO", "1")

import mesure  # noqa: E402  (réutilise le chargement et la préparation MiVOLO du test de mesure)

S = requests.Session()
S.headers["Authorization"] = f"Bearer {JETON}"


def appel(methode: str, chemin: str, **kw) -> requests.Response:
    for essai, attente in enumerate((2, 5, 15, 30, None), 1):
        try:
            r = S.request(methode, f"{URL}{chemin}", timeout=120, **kw)
            if r.status_code == 401:
                sys.exit("❌ Jeton refusé : vérifie MILLESIME_JETON_CALCUL dans .env (même valeur que dans la stack).")
            if r.status_code < 500 or attente is None:
                r.raise_for_status()
                return r
        except requests.ConnectionError:
            if attente is None:
                sys.exit(f"❌ Millésime injoignable à {URL} : vérifie MILLESIME_URL et que le NAS est allumé.")
        print(f"  Millésime ne répond pas bien, nouvel essai dans {attente} s ({essai}/4)", flush=True)
        time.sleep(attente)
    raise RuntimeError("inaccessible")


def main() -> int:
    if not JETON:
        sys.exit("❌ MILLESIME_JETON_CALCUL manquant dans .env.")
    restants = appel("GET", "/api/calcul/taches?n=1").json()["restants"]
    total = restants["calibrage"] + restants["a_dater"]
    print(f"Millésime ({URL}) : {total} visage(s) à analyser "
          f"({restants['calibrage']} pour le calibrage, {restants['a_dater']} pour dater).", flush=True)
    if not total:
        print("Rien à faire. Tu peux fermer ce terminal.", flush=True)
        return 0
    print("Chargement de MiVOLO…", flush=True)
    modele = mesure.MiVolo()
    print(f"MiVOLO prêt sur {modele.device}.", flush=True)
    fait, debut, apercus = 0, time.time(), {}
    while True:
        taches = appel("GET", f"/api/calcul/taches?n={LOT}").json()["taches"]
        if not taches:
            break
        resultats = []
        for t in taches:
            aid = t["asset_id"]
            if aid not in apercus:
                apercus.clear()  # un seul aperçu en mémoire
                apercus[aid] = Image.open(BytesIO(appel("GET", f"/api/calcul/apercu/{aid}").content)).convert("RGB")
            b = t["boite"]
            face = {"boundingBoxX1": b["x1"], "boundingBoxY1": b["y1"], "boundingBoxX2": b["x2"],
                    "boundingBoxY2": b["y2"], "imageWidth": b["imageWidth"], "imageHeight": b["imageHeight"]}
            try:
                ages = modele.ages(apercus[aid], face)
                resultats.append({"face_id": t["face_id"], "age_visage": round(ages["mivolo"], 2),
                                  "age_corps": round(ages["mivolo_corps"], 2) if "mivolo_corps" in ages else None})
            except Exception as e:  # noqa: BLE001
                print(f"  visage {t['face_id']} ignoré ({e})", flush=True)
                resultats.append({"face_id": t["face_id"], "age_visage": None})
        r = appel("POST", "/api/calcul/resultats", json={"resultats": resultats}).json()
        fait += r["enregistres"]
        reste = r["restants"]["calibrage"] + r["restants"]["a_dater"]
        vitesse = (time.time() - debut) / max(1, fait)
        print(f"  {fait}/{total} visages analysés — reste ~{reste * vitesse / 60:.0f} min", flush=True)
        if r["enregistres"] == 0:
            print("Aucun résultat accepté sur ce lot : arrêt pour éviter une boucle.", flush=True)
            break
    appel("POST", "/api/calcul/fin", json={"machine": platform.node()})
    print(f"Terminé : {fait} visages en {(time.time() - debut) / 60:.1f} min. "
          "Les propositions sont prêtes dans Millésime. Tu peux éteindre le PC.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
