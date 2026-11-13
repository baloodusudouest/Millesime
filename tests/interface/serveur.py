"""Millésime de démonstration pour les tests d'écran : faux Immich, calcul déjà fait.

    python -m tests.interface.serveur <dossier d'état> <port>

Mot de passe : « essai ». Rien ne sort de la machine."""
from __future__ import annotations

import os
import random
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import faux_immich_app as faux  # noqa: E402

MDP, JETON = "essai", "jeton-calcul"


def calculer(base: str, E: dict) -> None:
    """Faux calculateur du PC : âge vrai + biais + bruit, comme dans les tests du back."""
    rnd = random.Random(1)
    h = {"Authorization": f"Bearer {JETON}"}
    with httpx.Client(base_url=base, timeout=30) as c:
        while True:
            taches = c.get("/api/calcul/taches?n=7", headers=h).json()["taches"]
            if not taches:
                break
            res = [{"face_id": x["face_id"], "age_visage": E["verite"][x["face_id"]] + 2.5 + rnd.gauss(0, 1),
                    "age_corps": E["verite"][x["face_id"]] + 2.5 + rnd.gauss(0, 1)} for x in taches]
            c.post("/api/calcul/resultats", headers=h, json={"resultats": res})


def main() -> None:
    dossier, port = Path(sys.argv[1]), int(sys.argv[2])
    _, url, E = faux.demarrer()
    os.environ.update({
        "MILLESIME_IMMICH_URL": url, "MILLESIME_IMMICH_CLE": faux.CLE, "MILLESIME_PASSWORD": MDP,
        "MILLESIME_JETON_CALCUL": JETON, "MILLESIME_JETON_CARNET": "jeton-carnet", "MILLESIME_ETAT": str(dossier),
        "MILLESIME_TAG_PREFIXE": "Numérisation", "MILLESIME_ALBUM_NON_DATEES": "Non datées Numérisation",
        "MILLESIME_MODELE_ALBUM": "{annee} Numérisation"})
    from app import main as appli
    appli.ETAT["synchro_auto"] = False
    serveur = uvicorn.Server(uvicorn.Config(appli.app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=serveur.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(base + "/health").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    # 2.2.0 : un dossier déjà choisi, pour que l'écran « Dater » ait des photos qui portent une date
    appli.m().ajouter_sources("dossier", ["/bibliotheque/Avant/Numérisations 2010"])
    # 2.6.0 : un dossier et un album dont le nom date des photos sans visage (« Datables par le nom »)
    E["assets"]["nd-sans"]["originalPath"] = "/photos/Noël 1992 chez mamie/nd-sans.jpg"
    E["albums"]["al-ete"] = {"id": "al-ete", "albumName": "Vacances juillet 1987", "assets": {"nd2"}}
    E["assets"]["nd2"]["faces"] = []
    appli.m().synchroniser()
    calculer(base, E)
    Path(dossier, "pret").write_text("ok")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
