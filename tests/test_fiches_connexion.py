"""Fiches « Connexion » communes (Millésime 2.15.0, contrat 3, socle 0.11.0) : forme de /api/maison/services, accès par session ou
ANNEAU_CLE seulement (jamais MAISON_JETON), « Vérifier » d'un service pas relié n'essaie rien, copies non retouchées
du module commun et de l'interface commune."""
from pathlib import Path

import pytest

from app import maison
from app.main import APPLI
from tests.test_app import JC, JH, JK, connecter, env, sans_variables_maison, sillage  # noqa: F401 (fixtures de test_app)


@pytest.fixture
def client(env):  # noqa: F811
    return env[0]

RACINE = Path(__file__).resolve().parent.parent
CLE = "cle-anneau-de-test-1234567890"
IDS = ["immich", "pc-calcul", "carnet", "home-assistant", "chambre-noire", "sillage"]
CHAMPS = {"id", "nom", "genre", "cible", "etat", "lit", "ecrit", "reglage", "detail", "verifie_le", "guide",
          "derniere_ecriture", "gestes"}


def test_forme_du_contrat_3(client):
    connecter(client)
    r = client.get("/api/maison/services")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    corps = r.json()
    assert corps["contrat"] == 3 and corps["appli"] == APPLI and corps["simule"] is False
    assert [s["id"] for s in corps["services"]] == IDS
    for s in corps["services"]:
        assert set(s) == CHAMPS and s["lit"] and s["ecrit"] and s["etat"] in maison.ETATS_SERVICE
        assert len(s["gestes"]) <= 1
        if s["etat"] == "pas_relie":
            assert s["reglage"]


def test_acces_session_ou_cle_anneau(client, monkeypatch):
    assert client.get("/api/maison/services").status_code == 401
    monkeypatch.setenv("MAISON_JETON", "jeton-commun-de-test-12345")
    entete = {"Authorization": "Bearer jeton-commun-de-test-12345"}
    assert client.get("/api/maison/services", headers=entete).status_code == 401
    monkeypatch.setenv("ANNEAU_CLE", CLE)
    assert client.get("/api/maison/services", headers={"Authorization": f"Bearer {CLE}"}).status_code == 200
    assert client.get("/api/maison/services", headers={"Authorization": "Bearer mauvaise"}).status_code == 401


def test_verifier_inconnu_et_pas_relie(client):
    connecter(client)
    assert client.post("/api/maison/services/inconnu/verifier").status_code == 404
    for s in client.get("/api/maison/services").json()["services"]:
        if s["etat"] == "pas_relie":
            apres = client.post(f"/api/maison/services/{s['id']}/verifier").json()
            assert apres["etat"] == "pas_relie" and apres["verifie_le"] is None


def test_copies_communes_non_retouchees():
    assert maison.CONTRAT == 3 and maison.VERSION_SOCLE == "0.11.1"
    assert maison.empreinte_calculee() == maison.empreinte_ecrite()
    for nom in maison.FICHIERS_INTERFACE:
        chemin = RACINE / "frontend" / "src" / "lib" / "services" / nom
        if not chemin.exists():          # tests lancés dans l'image : les sources de l'interface n'y sont pas
            continue
        ecrite, calculee = maison.empreinte_interface(chemin)
        assert ecrite and ecrite == calculee, nom


# ------------------------------------------------------------------ propres à Millésime (2.15.0)

def test_2150_fiches_de_millesime(env):  # noqa: F811
    """Textes repris de l'ancien écran, geste « Synchroniser » sur Immich, guide sur le calculateur du PC seulement."""
    client, _ = env
    connecter(client)
    s = {x["id"]: x for x in client.get("/api/maison/services").json()["services"]}
    assert s["immich"]["gestes"] == [{"id": "synchroniser", "nom": "Synchroniser maintenant"}]
    assert all(not x["gestes"] for i, x in s.items() if i != "immich")
    assert s["immich"]["lit"].startswith("Millésime lit dans Immich les scans, les visages et les dates de naissance.")
    assert "peut s'annuler" in s["immich"]["ecrit"]
    assert (s["carnet"]["genre"], s["carnet"]["cible"]) == ("maison", "carnet")
    assert (s["chambre-noire"]["genre"], s["chambre-noire"]["cible"]) == ("maison", "chambre-noire")
    assert s["chambre-noire"]["etat"] == "pas_relie" and s["chambre-noire"]["reglage"] == "MAISON_JETON"
    assert [i for i, x in s.items() if x["guide"]] == ["pc-calcul"]


def test_2150_guide_du_calculateur(env):  # noqa: F811
    """Mêmes blocs que la fiche « IA du PC » de Gazette ; tout ce que disait l'ancien écran ; jamais le jeton."""
    client, _ = env
    connecter(client)
    client.post("/api/synchroniser")
    g = {x["id"]: x for x in client.get("/api/maison/services").json()["services"]}["pc-calcul"]["guide"]
    assert all(g[k] for k in ("reglages", "allumer", "pannes", "une_fois", "terminal", "note"))
    reglages = {r["nom"]: r["valeur"] for r in g["reglages"]}
    assert reglages["État du PC"] == "Calculateur jamais lancé"
    assert "pour le calibrage" in reglages["Visages en attente"]
    assert "MiVOLO sur ton PC" in g["note"] and "Rien n'est écrit dans Immich pendant le calcul." in g["note"]
    une_fois = " ".join(u["texte"] + " " + u["commande"] for u in g["une_fois"])
    for attendu in ("Docker Desktop (installation pour l'utilisateur, WSL 2)", "C:\\millesime", "MILLESIME_URL=",
                    "MILLESIME_JETON_CALCUL=…   (la valeur de la stack homelab)", "pc/calcul.yml",
                    "docker compose -f calcul.yml up -d"):
        assert attendu in une_fois, attendu
    commandes = [c for p in g["pannes"] for c in p["commandes"]]
    assert "docker ps --filter name=millesime_calcul" in commandes
    assert any("logs --tail 30" in c for c in commandes)
    assert JC not in str(g)                                                        # le jeton n'est jamais montré
    # Le PC passe demander du travail : l'état suit, relu à chaque ouverture de la fiche
    client.get("/api/calcul/taches?n=1&veille=true&machine=GAMING", headers={"Authorization": f"Bearer {JC}"})
    g = {x["id"]: x for x in client.get("/api/maison/services").json()["services"]}["pc-calcul"]["guide"]
    etat = {r["nom"]: r["valeur"] for r in g["reglages"]}["État du PC"]
    assert etat.endswith("(GAMING)") and not etat.startswith(("Calculateur jamais", "PC non disponible"))


def test_2150_verifier_le_pc_ne_l_appelle_jamais(env, monkeypatch):  # noqa: F811
    """Vérifier relit le dernier contact noté par Millésime : aucune demande réseau, rien d'écrit."""
    import requests
    client, _ = env
    connecter(client)

    def interdit(*a, **kw):
        raise AssertionError("le PC ne doit jamais être appelé")
    monkeypatch.setattr(requests, "get", interdit)
    monkeypatch.setattr(requests, "request", interdit)
    f = client.post("/api/maison/services/pc-calcul/verifier").json()
    assert f["etat"] == "ne_repond_pas" and "jamais lancé" in f["detail"]
    from app import main
    main.SERVICES._dernier.clear()
    client.get("/api/calcul/taches?n=1&veille=true&machine=GAMING", headers={"Authorization": f"Bearer {JC}"})
    f = client.post("/api/maison/services/pc-calcul/verifier").json()
    assert f["etat"] == "repond" and "GAMING" in f["detail"] and "dernier contact" in f["detail"]
    main.SERVICES._dernier.clear()


def test_2150_verifier_immich_carnet_ha_et_lecture_seule(env):  # noqa: F811
    """Immich lit sa version ; carnet et Home Assistant : la date de leur dernier passage. Permis en lecture seule."""
    client, _ = env
    connecter(client)
    from app import main
    main.SERVICES._dernier.clear()
    mm = main.m()
    mm.cfg.lecture_seule = mm.immich.lecture_seule = True
    avant = client.get("/api/journal").json()
    try:
        f = client.post("/api/maison/services/immich/verifier").json()
        assert f["etat"] == "repond" and f["detail"].startswith("Immich ")
        assert client.post("/api/maison/services/carnet/verifier").json()["etat"] == "ne_repond_pas"
        client.get("/api/etat", headers={"Authorization": f"Bearer {JK}"})
        client.get("/ha/etat", headers={"Authorization": f"Bearer {JH}"})
        main.SERVICES._dernier.clear()
        assert client.post("/api/maison/services/carnet/verifier").json()["etat"] == "repond"
        assert client.post("/api/maison/services/home-assistant/verifier").json()["etat"] == "repond"
        assert client.get("/api/journal").json() == avant                          # rien d'écrit
    finally:
        mm.cfg.lecture_seule = mm.immich.lecture_seule = False
        main.SERVICES._dernier.clear()


def test_2150_synchroniser_sert_d_essai_a_immich(env):  # noqa: F811
    client, _ = env
    connecter(client)
    from app import main
    main.SERVICES._dernier.clear()
    assert client.post("/api/synchroniser").status_code == 200
    f = {x["id"]: x for x in client.get("/api/maison/services").json()["services"]}["immich"]
    assert f["etat"] == "repond" and f["detail"].startswith("Relu :")
    main.SERVICES._dernier.clear()


# ------------------------------------------------------------------ 2.16.0 : fiche Sillage

def test_2160_fiche_sillage(env):  # noqa: F811
    """Sixième fiche : ce que Millésime lit chez Sillage et ce qu'il y écrit ; non reliée sans jeton commun."""
    client, _ = env
    connecter(client)
    s = {x["id"]: x for x in client.get("/api/maison/services").json()["services"]}["sillage"]
    assert (s["genre"], s["cible"]) == ("maison", "sillage") and not s["gestes"] and not s["guide"]
    assert "Pas la bonne année ?" in s["lit"] and "Reçues des invités" in s["lit"]
    assert "photo est traitée" in s["ecrit"]
    assert s["etat"] == "pas_relie" and s["reglage"] == "MILLESIME_SILLAGE_URL et MAISON_JETON"


def test_2160_verifier_sillage_lit_sans_rien_garder(sillage):  # noqa: F811
    """Vérifier : un GET /externe/signalements, rien de gardé, aucun POST ; la lecture de 15 min sert aussi d'essai."""
    client, _E, S, mm = sillage
    from app import main
    main.SERVICES._dernier.clear()
    S["avis"].append({"id": "a1", "asset": "x1", "annee": 1987, "environ": False, "invites": ["Léa"]})
    avant = len(S["requetes"])
    f = client.post("/api/maison/services/sillage/verifier").json()
    assert f["etat"] == "repond" and "1 date proposée" in f["detail"]
    assert [r[0] for r in S["requetes"][avant:]] == ["GET"]
    assert not mm.base.tous("SELECT id FROM avis_invite")                     # rien n'est gardé par Vérifier
    S["panne"] = True
    main.SERVICES._dernier.clear()
    f = client.post("/api/maison/services/sillage/verifier").json()
    assert f["etat"] == "ne_repond_pas" and "503" in f["detail"]
    S["panne"] = False
    main.SERVICES._dernier.clear()
    main._lire_sillage_suivi()                                                 # la lecture régulière note l'essai
    f = {x["id"]: x for x in client.get("/api/maison/services").json()["services"]}["sillage"]
    assert f["etat"] == "repond" and "dernière lecture" in f["detail"]
    main.SERVICES._dernier.clear()
