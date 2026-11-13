"""API FastAPI de Millésime et service de l'interface compilée."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from datetime import datetime
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import estimation as est
from .auth import COMMUN, COOKIE, DUREE, Sessions, jeton_valide
from .config import Config
from .immich import ErreurImmich, LectureSeule
from .service import ErreurMillesime, Millesime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
log = logging.getLogger("millesime")
ETAT: dict = {}
STATIC = Path(__file__).parent / "static"


def m() -> Millesime:
    return ETAT["m"]


def _boucle_synchro(stop: threading.Event):
    while not stop.is_set():
        try:
            m().synchroniser()
        except ErreurMillesime:
            pass
        except Exception as e:  # noqa: BLE001
            log.warning("Synchronisation en échec : %s", e)
        stop.wait(max(5, m().cfg.synchro_minutes) * 60)


@asynccontextmanager
async def cycle(app: FastAPI):
    if "m" not in ETAT:
        ETAT["m"] = Millesime(Config.depuis_env())
    ETAT["sessions"] = Sessions(m().cfg.mot_de_passe, m().base.lire("session_generation", 0))
    stop = threading.Event()
    if ETAT.get("synchro_auto", True):
        threading.Thread(target=_boucle_synchro, args=(stop,), daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="Millésime", version=__version__, lifespan=cycle)


@app.middleware("http")
async def garde(request: Request, appel):
    chemin = request.url.path
    if chemin.startswith("/api/calcul/"):
        if not jeton_valide(request.headers.get("authorization"), m().cfg.jeton_calcul):
            return JSONResponse({"detail": "Jeton de calcul manquant ou invalide."}, status_code=401)
    elif chemin == "/api/etat":
        if not jeton_valide(request.headers.get("authorization"), m().cfg.jeton_carnet):
            return JSONResponse({"detail": "Jeton carnet manquant ou invalide."}, status_code=401)
    elif chemin.startswith("/api/") and chemin not in ("/api/connexion", "/api/session", "/api/ha/etat"):
        if not ETAT["sessions"].connecte(request.cookies):
            return JSONResponse({"detail": "Connexion nécessaire."}, status_code=401)
    reponse = await appel(request)
    if chemin.startswith("/api/") and not chemin.startswith(("/api/apercu/", "/api/visage/", "/api/vignette/")):
        reponse.headers["Cache-Control"] = "no-store"
    return reponse


@app.exception_handler(ErreurMillesime)
async def _erreur(_: Request, exc: ErreurMillesime):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(LectureSeule)
async def _erreur_lecture_seule(_: Request, exc: LectureSeule):
    return JSONResponse({"detail": str(exc)}, status_code=409)


def ecriture() -> None:
    """À appeler en tête de toute route qui écrit dans Immich : refus net en lecture seule,
    avant toute trace dans le journal."""
    if m().cfg.lecture_seule:
        raise LectureSeule("Mode lecture seule (MILLESIME_LECTURE_SEULE) : rien n'est écrit dans Immich.")


@app.exception_handler(ErreurImmich)
async def _erreur_immich(_: Request, exc: ErreurImmich):
    return JSONResponse({"detail": str(exc)}, status_code=502)


@app.get("/health")
def sante():
    return {"ok": True, "version": __version__}


# -- connexion -------------------------------------------------------------------
@app.get("/api/session")
def session(request: Request):
    return {"connecte": ETAT["sessions"].connecte(request.cookies), "version": __version__,
            "lecture_seule": m().cfg.lecture_seule}


@app.post("/api/connexion")
async def connexion(corps: dict = Body(...)):
    s = ETAT["sessions"]
    await asyncio.sleep(s.attente())
    if not s.verifier_mot_de_passe(str(corps.get("mot_de_passe", ""))):
        raise HTTPException(401, "Mot de passe incorrect.")
    r = JSONResponse({"ok": True})
    r.set_cookie(COOKIE, s.creer(), max_age=DUREE, httponly=True, samesite="strict")
    return r


@app.post("/api/deconnexion")
def deconnexion():
    s = ETAT["sessions"]
    s.generation += 1
    m().base.ecrire("session_generation", s.generation)
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE)
    r.delete_cookie(COMMUN)      # « Se déconnecter » ferme aussi la connexion commune
    return r


# -- écrans ----------------------------------------------------------------------
@app.get("/api/accueil")
def accueil():
    return {**m().accueil(), "version": __version__}


@app.get("/api/pc")
def etat_pc():
    """État du calculateur (interrogé toutes les 10 à 30 s par l'interface)."""
    return m().etat_pc()


@app.post("/api/synchroniser")
def synchroniser():
    """Le bouton « Synchroniser » relit tout (2.4.0) ; la synchro de chaque heure est légère."""
    return m().synchroniser(complete=True)


@app.post("/api/datables/dater")
def dater_datables(corps: dict = Body(default={})):
    """2.5.0 : un lot de « Tout dater d'un coup » (l'écran rappelle jusqu'à ce qu'il n'en reste plus)."""
    ecriture()
    lot = str(corps.get("lot") or "")[:40] or datetime.now().strftime("nom-%Y%m%d-%H%M%S")
    groupe = str(corps["groupe"]) if corps.get("groupe") else None
    groupes = {str(k): (str(v) if v else None) for k, v in (corps.get("groupes") or {}).items()} or None
    return m().dater_par_nom(lot, min(max(int(corps.get("n") or 100), 1), 200), groupe, groupes)


@app.get("/api/datables/date")
def date_tapee(saisie: str):
    """2.7.0 : la date qui serait écrite pour une saisie (aperçu à côté du champ)."""
    from .service import date_saisie
    return {"date": date_saisie(saisie)}


@app.get("/api/datables/groupes")
def groupes_datables():
    """2.6.0 : les dossiers et albums qui datent des photos (colonne de gauche de « Datables par le nom »)."""
    return m().groupes_datables()


@app.get("/api/datables/photos")
def photos_datables(cle: str):
    return m().photos_groupe(cle)


@app.get("/api/vignette/{asset_id}")
def vignette(asset_id: str):
    return Response(m().vignette(asset_id), media_type="image/jpeg", headers=IMG)


@app.post("/api/lots/{lot}/annuler")
def annuler_lot(lot: str):
    ecriture()
    return m().annuler_lot(lot)


@app.get("/api/scans")
def scans(statut: str = "a_dater"):
    if statut not in ("a_dater", "a_trancher", "a_analyser", "validee", "plusieurs", "datables"):
        raise HTTPException(400, "Statut inconnu.")
    return m().liste(statut)


@app.get("/api/scans/{asset_id}")
def scan(asset_id: str):
    return m().scan(asset_id)


@app.post("/api/scans/{asset_id}/valider")
def valider(asset_id: str, corps: dict = Body(...)):
    ecriture()
    return m().valider(asset_id, corps.get("annee"), corps.get("marge", 1))


@app.post("/api/scans/{asset_id}/garder")
def garder_date(asset_id: str, corps: dict = Body(...)):
    """2.2.0 : la photo a déjà une date. « actuelle » : on la garde, rien n'est écrit. « nom » : celle du nom du fichier."""
    laquelle = str(corps.get("laquelle", ""))
    if laquelle in ("nom", "dossier"):
        ecriture()
    return m().garder_date(asset_id, laquelle)


@app.post("/api/scans/{asset_id}/actualiser")
def actualiser(asset_id: str):
    return m().actualiser_scan(asset_id)


@app.post("/api/scans/{asset_id}/visages/{face_id}/detacher")
def detacher(asset_id: str, face_id: str):
    """2.3.0 : le visage n'est pas la personne nommée : il est retiré de cette personne dans Immich."""
    ecriture()
    return m().detacher_visage(asset_id, face_id)


@app.post("/api/scans/{asset_id}/plusieurs")
def plusieurs(asset_id: str):
    return m().plusieurs_annees(asset_id)


# ---- 2.2.0 : ce que Millésime date (albums et dossiers choisis), et les noms d'albums des scans

@app.get("/api/sources")
def sources(choix: bool = False):
    return m().sources(avec_choix=choix)


@app.post("/api/sources")
def ajouter_sources(corps: dict = Body(...)):
    refs = corps.get("refs")
    return m().ajouter_sources(str(corps.get("sorte", "")), [str(r) for r in refs] if isinstance(refs, list) else [])


@app.post("/api/sources/retirer")
def retirer_source(corps: dict = Body(...)):
    return m().retirer_source(str(corps.get("cle", "")))


@app.post("/api/sources/demander")
def demander_passage(corps: dict = Body(...)):
    return {"message": m().demander_passage(str(corps.get("cle", ""))), **m().sources()}


@app.post("/api/reglages/albums")
def regler_albums(corps: dict = Body(...)):
    return m().regler_albums(str(corps.get("non_datees", "")), str(corps.get("modele", "")))


@app.get("/api/journal")
def journal():
    return m().journal()


@app.post("/api/journal/{jid}/annuler")
def annuler(jid: int):
    ecriture()
    return m().annuler(jid)


@app.get("/api/nommer")
def a_nommer():
    return {"groupes": m().groupes_a_nommer(), "sans_naissance": m().sans_naissance()}


@app.post("/api/nommer/{person_id}")
def nommer(person_id: str, corps: dict = Body(...)):
    ecriture()
    return m().nommer(person_id, str(corps.get("nom", "")))


@app.get("/api/nommer/suggestions")
def suggestions():
    return m().suggestions()


@app.get("/api/nommer/{source_id}/apercu/{cible_id}")
def apercu_fusion(source_id: str, cible_id: str):
    return m().apercu_fusion(source_id, cible_id)


@app.post("/api/nommer/{source_id}/fusionner")
def fusionner(source_id: str, corps: dict = Body(...)):
    ecriture()
    return m().fusionner(source_id, str(corps.get("cible", "")))


@app.post("/api/nommer/{person_id}/ignorer")
def ignorer(person_id: str):
    return m().ignorer_groupe(person_id)


@app.get("/api/suspects")
def suspects():
    return est.suspects(m().base, m().cfg.seuil_suspect)


@app.get("/api/personnes/{person_id}/frise")
def frise(person_id: str, forcer: bool = False):
    return m().frise(person_id, forcer)


@app.get("/api/calibrage")
def calibrage():
    return m().base.tous("SELECT * FROM calibrages ORDER BY version DESC LIMIT 10")


IMG = {"Cache-Control": "private, max-age=86400"}


@app.get("/api/apercu/{asset_id}")
def apercu(asset_id: str):
    return Response(m().apercu(asset_id), media_type="image/jpeg", headers=IMG)


@app.get("/api/boite/{asset_id}/{face_id}")
def boite(asset_id: str, face_id: str):
    return m().boite_visage(asset_id, face_id)


@app.get("/api/visage/{asset_id}/{face_id}")
def visage(asset_id: str, face_id: str):
    return Response(m().visage_jpeg(asset_id, face_id), media_type="image/jpeg", headers=IMG)


# -- calculateur (PC) ------------------------------------------------------------
@app.get("/api/calcul/taches")
def taches(n: int = 20, veille: bool = False, machine: str = ""):
    signal = m().signal_pc(veille, machine)
    return {"taches": m().taches(max(1, min(n, 100))), "restants": m().compter_taches(), **signal}


@app.post("/api/calcul/resultats")
def resultats(corps: dict = Body(...)):
    return m().recevoir_resultats(corps.get("resultats", []))


@app.get("/api/calcul/apercu/{asset_id}")
def apercu_calcul(asset_id: str):
    return Response(m().apercu(asset_id), media_type="image/jpeg")


@app.post("/api/calcul/fin")
def fin_calcul(corps: dict = Body(default={})):
    """Appelé par le calculateur quand la file est vide : relance une synchronisation complète."""
    t = m().compter_taches()
    m()._suivre_passe(t["calibrage"] + t["a_dater"], fini=not (t["calibrage"] + t["a_dater"]))
    m().base.ecrire("dernier_calcul", {**(m().base.lire("dernier_calcul") or {}), "fin": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                       "machine": str(corps.get("machine", ""))[:80]})
    return {"ok": True}


# -- autres applis ---------------------------------------------------------------
@app.get("/api/etat")
def etat():
    return m().etat()


@app.get("/api/ha/etat")
def ha_etat():
    return JSONResponse({"detail": "Intégration Home Assistant à venir."}, status_code=501)


# -- interface -------------------------------------------------------------------
if (STATIC / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")


@app.get("/{chemin:path}")
def interface(chemin: str):
    fichier = STATIC / chemin
    if chemin and fichier.is_file() and STATIC in fichier.resolve().parents:
        return FileResponse(fichier)
    index = STATIC / "index.html"
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"detail": "Interface non compilée."}, status_code=404)
