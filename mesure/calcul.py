#!/usr/bin/env python3
"""
Millésime — calculateur à lancer sur le PC (image « calcul »).

1. Demande à Millésime (NAS) les visages à analyser.
2. Télécharge les aperçus PAR Millésime (la clé Immich reste sur le NAS).
3. Calcule l'âge avec MiVOLO v2 : visage seul et visage + buste estimé.
4. Renvoie les résultats par lots.

Deux façons de tourner :
- VEILLE=1 (par défaut dans pc/calcul.yml) : reste allumé tant que Docker Desktop est ouvert,
  redemande du travail toutes les VEILLE_MINUTES (5), calcule dès qu'un visage attend.
  Quand la file est vide, Millésime en profite pour relire Immich (au plus toutes les 15 min).
  MiVOLO n'est chargé qu'au premier visage à calculer.
- VEILLE=0 : une seule passe, puis arrêt.

Variables : MILLESIME_URL (ex. http://192.168.1.10:8098), MILLESIME_JETON_CALCUL, THREADS,
VEILLE, VEILLE_MINUTES.
"""
from __future__ import annotations

import os
import platform
import sys
import time
from datetime import datetime
from io import BytesIO

import requests
from PIL import Image

URL = os.environ.get("MILLESIME_URL", "http://192.168.1.10:8098").rstrip("/")
JETON = os.environ.get("MILLESIME_JETON_CALCUL", "")
LOT = int(os.environ.get("LOT", "20"))
VEILLE = os.environ.get("VEILLE", "0") == "1"
VEILLE_MINUTES = float(os.environ.get("VEILLE_MINUTES", "5"))
VEILLE_CYCLES = int(os.environ.get("VEILLE_CYCLES", "0"))      # 0 = sans fin (les tests en mettent quelques-uns)
MACHINE = platform.node()
os.environ.setdefault("MIVOLO", "1")

import mesure  # noqa: E402  (réutilise le chargement et la préparation MiVOLO du test de mesure)

S = requests.Session()
S.headers["Authorization"] = f"Bearer {JETON}"
MODELE = {"mivolo": None}


class Injoignable(Exception):
    pass


def dire(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


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
                raise Injoignable(f"Millésime injoignable à {URL} : vérifie MILLESIME_URL et que le NAS est allumé.")
        dire(f"  Millésime ne répond pas bien, nouvel essai dans {attente} s ({essai}/4)")
        time.sleep(attente)
    raise Injoignable("Millésime ne répond pas.")


def modele():
    if MODELE["mivolo"] is None:
        dire("Chargement de MiVOLO…")
        MODELE["mivolo"] = mesure.MiVolo()
        dire(f"MiVOLO prêt sur {MODELE['mivolo'].device}.")
    return MODELE["mivolo"]


def passe() -> int:
    """Calcule tous les visages en attente ; renvoie le nombre de visages enregistrés."""
    r = appel("GET", f"/api/calcul/taches?n=1&veille={'true' if VEILLE else 'false'}&machine={MACHINE}").json()
    restants = r["restants"]
    total = restants["calibrage"] + restants["a_dater"]
    if not total:
        if not VEILLE:
            dire("Rien à faire. Tu peux fermer ce terminal.")
        elif r.get("synchro_lancee"):
            dire("Rien à calculer ; Millésime relit Immich pour repérer de nouveaux visages.")
        return 0
    dire(f"{total} visage(s) à analyser ({restants['calibrage']} pour le calibrage, {restants['a_dater']} pour dater).")
    mv = modele()
    fait, debut, apercus = 0, time.time(), {}
    while True:
        taches = appel("GET", f"/api/calcul/taches?n={LOT}&veille={'true' if VEILLE else 'false'}&machine={MACHINE}").json()["taches"]
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
                ages = mv.ages(apercus[aid], face)
                resultats.append({"face_id": t["face_id"], "age_visage": round(ages["mivolo"], 2),
                                  "age_corps": round(ages["mivolo_corps"], 2) if "mivolo_corps" in ages else None})
            except Exception as e:  # noqa: BLE001
                dire(f"  visage {t['face_id']} ignoré ({e})")
                resultats.append({"face_id": t["face_id"], "age_visage": None})
        r = appel("POST", "/api/calcul/resultats", json={"resultats": resultats}).json()
        fait += r["enregistres"]
        reste = r["restants"]["calibrage"] + r["restants"]["a_dater"]
        vitesse = (time.time() - debut) / max(1, fait)
        dire(f"  {fait}/{total} visages analysés — reste ~{reste * vitesse / 60:.0f} min")
        if r["enregistres"] == 0 and not any(x.get("age_visage") is None for x in resultats):
            dire("Aucun résultat accepté sur ce lot : arrêt de la passe pour éviter une boucle.")
            break
    appel("POST", "/api/calcul/fin", json={"machine": MACHINE})
    dire(f"Terminé : {fait} visages en {(time.time() - debut) / 60:.1f} min. Les propositions sont prêtes dans Millésime.")
    return fait


def main() -> int:
    if not JETON:
        sys.exit("❌ MILLESIME_JETON_CALCUL manquant dans .env.")
    if not VEILLE:
        try:
            passe()
        except Injoignable as e:
            sys.exit(f"❌ {e}")
        dire("Tu peux éteindre le PC.")
        return 0
    dire(f"Veille : Millésime ({URL}) est interrogé toutes les {VEILLE_MINUTES:g} min tant que Docker Desktop est ouvert.")
    cycle = 0
    while True:
        cycle += 1
        try:
            passe()
        except Injoignable as e:
            dire(f"{e} Nouvel essai dans {VEILLE_MINUTES:g} min.")
        if VEILLE_CYCLES and cycle >= VEILLE_CYCLES:
            return 0
        time.sleep(VEILLE_MINUTES * 60)


if __name__ == "__main__":
    sys.exit(main())
