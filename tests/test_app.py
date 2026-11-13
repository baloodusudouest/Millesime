"""Tests de l'appli Millésime (serveur NAS) contre le faux Immich, avec un faux calculateur."""
import json
import random
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import faux_immich_app as faux  # noqa: E402

MDP = "secret-carnet"
JC, JK = "jeton-calcul", "jeton-carnet"


def noms_de_test(monkeypatch):
    """Noms de tags et d'albums du faux Immich (1.5.1 : plus de valeur par défaut dans le code)."""
    monkeypatch.setenv("MILLESIME_TAG_PREFIXE", "Numérisation")
    monkeypatch.setenv("MILLESIME_ALBUM_NON_DATEES", "Non datées Numérisation")
    monkeypatch.setenv("MILLESIME_MODELE_ALBUM", "{annee} Numérisation")


@pytest.fixture
def env(tmp_path, monkeypatch):
    serveur, url, E = faux.demarrer()
    monkeypatch.setenv("MILLESIME_IMMICH_URL", url)
    monkeypatch.setenv("MILLESIME_IMMICH_CLE", faux.CLE)
    monkeypatch.setenv("MILLESIME_PASSWORD", MDP)
    monkeypatch.setenv("MILLESIME_JETON_CALCUL", JC)
    monkeypatch.setenv("MILLESIME_JETON_CARNET", JK)
    monkeypatch.setenv("MILLESIME_ETAT", str(tmp_path))
    noms_de_test(monkeypatch)
    from app import main
    from app.config import Config
    from app.service import Millesime
    main.ETAT.clear()
    main.ETAT["m"] = Millesime(Config.depuis_env())
    main.ETAT["synchro_auto"] = False
    with TestClient(main.app) as client:
        yield client, E
    serveur.shutdown()


def connecter(client):
    r = client.post("/api/connexion", json={"mot_de_passe": MDP})
    assert r.status_code == 200


def calculer(client, E, biais=2.5, bruit=1.0, graine=1):
    """Faux calculateur : âge vrai + biais + bruit, comme MiVOLO sur les scans."""
    rnd = random.Random(graine)
    h = {"Authorization": f"Bearer {JC}"}
    total = 0
    while True:
        t = client.get("/api/calcul/taches?n=7", headers=h).json()["taches"]
        if not t:
            break
        for x in t:
            assert client.get(f"/api/calcul/apercu/{x['asset_id']}", headers=h).status_code == 200
        res = [{"face_id": x["face_id"], "age_visage": E["verite"][x["face_id"]] + biais + rnd.gauss(0, bruit),
                "age_corps": E["verite"][x["face_id"]] + biais + rnd.gauss(0, bruit)} for x in t]
        r = client.post("/api/calcul/resultats", headers=h, json={"resultats": res}).json()
        total += r["enregistres"]
    return total


def test_acces_protege(env):
    client, _ = env
    assert client.get("/api/accueil").status_code == 401
    assert client.get("/api/calcul/taches").status_code == 401
    assert client.get("/api/calcul/taches", headers={"Authorization": "Bearer faux"}).status_code == 401
    assert client.get("/api/etat").status_code == 401
    assert client.post("/api/connexion", json={"mot_de_passe": "non"}).status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/api/ha/etat").status_code == 501


def test_parcours_complet(env):
    client, E = env
    connecter(client)
    b = client.post("/api/synchroniser").json()
    assert b["scans"] == 32 + 8
    a = client.get("/api/accueil").json()["compteurs"]
    assert a["total"] == 8 and a["a_analyser"] >= 6

    # calcul sur le « PC » puis calibrage
    n = calculer(client, E)
    assert n > 0
    acc = client.get("/api/accueil").json()
    cal = acc["calibrage"]
    assert cal and cal["n_visages"] >= 60
    assert acc["taches"] == {"calibrage": 0, "a_dater": 0}

    # propositions : biais de +2,5 ans corrigé par le calibrage
    for aid, vraie in E["vraies"].items():
        s = client.get(f"/api/scans/{aid}").json()
        if s["annee_proposee"] is not None and s["details"]["visages"]:
            assert abs(s["annee_proposee"] - vraie) <= 2, (aid, s["annee_proposee"], vraie)
    s = client.get("/api/scans/nd-sans").json()
    assert s["statut"] == "a_trancher" and "aucun visage" in s["raison"]

    # validation : date, tag, albums dans Immich
    a_dater = client.get("/api/scans?statut=a_dater").json()
    assert a_dater
    cible = a_dater[0]["asset_id"]
    s = client.get(f"/api/scans/{cible}").json()
    r = client.post(f"/api/scans/{cible}/valider", json={"annee": s["annee_proposee"], "marge": s["marge"]}).json()
    asset = E["assets"][cible]
    assert asset["exifInfo"]["dateTimeOriginal"] == f"{s['annee_proposee']}-07-01T12:00:00.000Z"
    tag = next(t for t in E["tags"].values() if t["value"] == r["tag"])
    assert cible in E["tag_assets"][tag["id"]]
    assert cible not in E["albums"]["al-nd"]["assets"]
    album = next(al for al in E["albums"].values() if al["albumName"] == f"{s['annee_proposee']} Numérisation")
    assert cible in album["assets"]
    assert client.get(f"/api/scans/{cible}").json()["statut"] == "validee"

    # une resynchronisation garde la photo validée (tag Date estimée)
    client.post("/api/synchroniser")
    assert client.get(f"/api/scans/{cible}").json()["statut"] == "validee"

    # annulation : tout revient comme avant
    j = client.get("/api/journal").json()[0]
    assert client.post(f"/api/journal/{j['id']}/annuler").json()["ok"]
    assert asset["exifInfo"]["dateTimeOriginal"].startswith("1900-01-01")
    assert cible not in E["tag_assets"][tag["id"]]
    assert cible in E["albums"]["al-nd"]["assets"]
    assert cible not in album["assets"]
    assert client.get(f"/api/scans/{cible}").json()["statut"] in ("a_dater", "a_trancher")
    assert client.post(f"/api/journal/{j['id']}/annuler").status_code == 400


def test_bornes_et_controles(env):
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    assert client.post("/api/scans/nd0/valider", json={"annee": 2030, "marge": 1}).status_code == 400
    assert client.post("/api/scans/d1990-0/valider", json={"annee": 1990, "marge": 1}).status_code == 400
    # plusieurs années : aucune écriture dans Immich
    avant = len(E["ecritures"])
    assert client.post("/api/scans/nd-sans/plusieurs").status_code == 200
    assert len(E["ecritures"]) == avant
    assert client.get("/api/scans/nd-sans").json()["statut"] == "plusieurs"


def test_nommer_et_etat_carnet(env):
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    g = client.get("/api/nommer").json()
    ids = [x["person_id"] for x in g["groupes"]]
    assert ids[0] == "inconnu1"            # le plus fréquent sur les non datées
    assert "julien" not in ids
    assert any(x["nom"] == "Rémi J" for x in g["sans_naissance"])
    assert client.post("/api/nommer/inconnu1", json={"nom": "  Paul   GARNIER "}).json()["nom"] == "Paul GARNIER"
    assert E["personnes"]["inconnu1"]["name"] == "Paul GARNIER"
    client.post("/api/nommer/inconnu2/ignorer")
    assert client.get("/api/nommer").json()["groupes"] == []
    e = client.get("/api/etat", headers={"Authorization": f"Bearer {JK}"}).json()
    assert e["a_analyser"] > 0 and "allume le PC" in e["message"]
    assert {"Paul GARNIER", "Rémi J"} <= {p["nom"] for p in e["sans_naissance"]}


def test_frise_et_images(env):
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    f = client.get("/api/personnes/julien/frise").json()
    assert f["nom"] == "Julien B" and len(f["elements"]) >= 5
    assert not any(e["asset_id"].startswith("nd") for e in f["elements"])
    assert {"tampon", "numérique"} <= {e["source"] for e in f["elements"]}
    e0 = f["elements"][0]
    r = client.get(f"/api/visage/{e0['asset_id']}/{e0['face_id']}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get("/api/apercu/nd0").status_code == 200


def test_suspects(env):
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    # Jeanne estimée 15 ans trop jeune sur les scans datés : visages suspects
    h = {"Authorization": f"Bearer {JC}"}
    while True:
        t = client.get("/api/calcul/taches?n=50", headers=h).json()["taches"]
        if not t:
            break
        res = []
        for x in t:
            v = E["verite"][x["face_id"]] + 2.5
            if x["asset_id"].startswith("d") and x["face_id"].endswith("-f2"):
                v -= 15
            res.append({"face_id": x["face_id"], "age_visage": v, "age_corps": v})
        client.post("/api/calcul/resultats", headers=h, json={"resultats": res})
    sus = client.get("/api/suspects").json()
    assert sus and all(s["nom"] == "Jeanne DUVAL" for s in sus)


def test_calculateur_pc(env, monkeypatch):
    """Le vrai script calcul.py, avec un MiVOLO factice, contre un serveur Millésime réel (uvicorn)."""
    import socket
    import threading
    import time

    import uvicorn

    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    from app import main as appmain
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = uvicorn.Server(uvicorn.Config(appmain.app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(50):
        if srv.started:
            break
        time.sleep(0.1)
    monkeypatch.setenv("MILLESIME_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("MILLESIME_JETON_CALCUL", JC)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mesure"))
    import importlib

    import calcul
    importlib.reload(calcul)

    class FauxMiVolo:
        device = "cpu"
        appels = 0

        def ages(self, image, face):
            FauxMiVolo.appels += 1
            if FauxMiVolo.appels == 3:
                raise RuntimeError("visage illisible")
            return {"mivolo": 30.0, "mivolo_corps": 31.0}

    monkeypatch.setattr(calcul.mesure, "MiVolo", FauxMiVolo)
    try:
        assert calcul.main() == 0
        assert calcul.main() == 0                                 # relance : rien à faire
    finally:
        srv.should_exit = True
    acc = client.get("/api/accueil").json()
    assert acc["taches"] == {"calibrage": 0, "a_dater": 0}      # l'échec n'est pas redemandé en boucle
    assert acc["dernier_calcul"]["fin"]


def test_suggestions_fusion_et_annulation(env):
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    sug = client.get("/api/nommer/suggestions").json()
    noms = [s["nom"] for s in sug]
    assert "Julien B" in noms and "" not in noms
    assert sug[0]["sur_scans"] >= sug[-1]["sur_scans"]          # présents sur les scans d'abord
    # un nom existant est refusé (accents et casse ignorés) : il faut fusionner
    r = client.post("/api/nommer/inconnu1", json={"nom": "jeanne duval"})
    assert r.status_code == 400 and "existe déjà" in r.json()["detail"]
    ap = client.get("/api/nommer/inconnu1/apercu/mamie").json()
    assert ap["source"] and ap["cible"]["nom"] == "Jeanne DUVAL" and ap["cible"]["exemples"]
    faces_avant = sorted(f["id"] for x in E["assets"].values() for f in x["faces"]
                         if (f["person"] or {}).get("id") == "inconnu1")
    r = client.post("/api/nommer/inconnu1/fusionner", json={"cible": "mamie"}).json()
    assert r["visages"] == len(faces_avant) and "inconnu1" not in E["personnes"]
    assert all((f["person"] or {}).get("id") == "mamie" for x in E["assets"].values() for f in x["faces"]
               if f["id"] in faces_avant)
    assert "inconnu1" not in [g["person_id"] for g in client.get("/api/nommer").json()["groupes"]]
    # les visages fusionnés ont maintenant une date de naissance : ils partent au calcul
    t = client.get("/api/calcul/taches?n=100", headers={"Authorization": f"Bearer {JC}"}).json()["taches"]
    assert set(faces_avant) & {x["face_id"] for x in t}
    # annulation : une nouvelle personne récupère exactement ces visages
    j = next(x for x in client.get("/api/journal").json() if x["action"] == "fusionner")
    r = client.post(f"/api/journal/{j['id']}/annuler").json()
    nouvelle = r["person_id"]
    apres = sorted(f["id"] for x in E["assets"].values() for f in x["faces"]
                   if (f["person"] or {}).get("id") == nouvelle)
    assert apres == faces_avant
    assert nouvelle in [g["person_id"] for g in client.get("/api/nommer").json()["groupes"]]


def test_annuler_un_nommage_et_boite(env):
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    client.post("/api/nommer/inconnu2", json={"nom": "Lucie MARTIN"})
    j = next(x for x in client.get("/api/journal").json() if x["action"] == "nommer")
    client.post(f"/api/journal/{j['id']}/annuler")
    assert E["personnes"]["inconnu2"]["name"] == ""
    b = client.get("/api/boite/nd0/nd0-f0").json()
    assert 0 < b["x"] < 1 and 0 < b["l"] < 1 and b["nom"] == "Julien B"


def test_nommer_depuis_la_photo(env):
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    s = client.get("/api/scans/nd-sans").json()
    ids = {g["person_id"] for g in s["a_nommer"]}
    assert ids == {"inconnu1", "inconnu2"}
    g1 = next(g for g in s["a_nommer"] if g["person_id"] == "inconnu1")
    assert g1["visages"] >= 2 and g1["exemples"][0]["asset_id"] == "nd-sans"
    assert [x["etat"] for x in s["sans_personne"]] == ["non_attribue"] and s["lien_immich"].endswith("/photos/nd-sans")
    client.post("/api/nommer/inconnu2", json={"nom": "Lucie MARTIN"})
    s = client.get("/api/scans/nd-sans").json()
    assert {g["person_id"] for g in s["a_nommer"]} == {"inconnu1"}


def test_etat_des_visages(env):
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    # personne masquée dans Immich, et visage supprimé dans Immich depuis la synchro
    E["personnes"]["inconnu2"]["isHidden"] = True
    E["assets"]["nd-sans"]["faces"] = [f for f in E["assets"]["nd-sans"]["faces"] if f["id"] != "nd-sans-f0"]
    s = client.get("/api/scans/nd-sans").json()
    etats = {v["face_id"]: v["etat"] for v in s["visages"]}
    assert etats == {"nd-sans-f0": "supprime", "nd-sans-f1": "masque", "nd-sans-f2": "non_attribue"}
    assert next(g for g in s["a_nommer"] if g["person_id"] == "inconnu2")["masque"] is True
    assert "inconnu1" not in {g["person_id"] for g in s["a_nommer"]}     # son seul visage ici a disparu
    assert {x["etat"] for x in s["sans_personne"]} == {"supprime", "non_attribue"}
    s2 = client.get("/api/scans/nd0").json()
    assert {v["etat"] for v in s2["visages"]} == {"nomme"}


def test_relire_une_photo(env):
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    # dans Immich : le visage non attribué de nd-sans est rattaché à Julien, et le groupe inconnu2 est nommé
    f2 = next(f for f in E["assets"]["nd-sans"]["faces"] if f["id"] == "nd-sans-f2")
    f2["person"] = E["personnes"]["julien"]
    E["personnes"]["inconnu2"]["name"] = "Lucie MARTIN"
    s = client.get("/api/scans/nd-sans").json()
    assert s["statut"] == "a_trancher"
    r = client.post("/api/scans/nd-sans/actualiser").json()
    assert r["changes"] == 2 and r["a_calculer"] == 1
    s = client.get("/api/scans/nd-sans").json()
    noms = {v["face_id"]: v["person_nom"] for v in s["visages"]}
    assert noms["nd-sans-f2"] == "Julien B" and noms["nd-sans-f1"] == "Lucie MARTIN"
    assert s["statut"] == "a_analyser"            # le visage de Julien attend le calcul sur le PC


def test_lien_immich_pour_le_navigateur(monkeypatch):
    """Les liens « Ouvrir dans Immich » ne doivent jamais pointer vers l'adresse interne Docker."""
    from app.config import Config
    monkeypatch.setenv("MILLESIME_PASSWORD", "x")
    monkeypatch.setenv("MILLESIME_IMMICH_CLE", "x")
    monkeypatch.setenv("MILLESIME_ETAT", "/tmp/millesime-test-lien")
    noms_de_test(monkeypatch)
    monkeypatch.setenv("MILLESIME_IMMICH_URL", "http://immich_server:2283")
    monkeypatch.delenv("MILLESIME_IMMICH_LIEN", raising=False)
    cfg = Config.depuis_env()
    assert cfg.immich_lien == ""                       # chemin relatif → complété par le navigateur
    monkeypatch.setenv("MILLESIME_IMMICH_LIEN", "http://192.168.1.10:2283/")
    assert Config.depuis_env().immich_lien == "http://192.168.1.10:2283"


def test_veille_du_pc(env):
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    from app import main as appmain
    m = appmain.ETAT["m"]
    h = {"Authorization": f"Bearer {JC}"}
    # file pleine : pas de synchro, le PC est noté actif en veille, carnet ne demande plus d'allumer le PC
    r = client.get("/api/calcul/taches?n=1&veille=true&machine=gaming", headers=h).json()
    assert r["synchro_lancee"] is False
    pc = client.get("/api/pc").json()
    assert pc["etat"] == "en_cours" and pc["machine"] == "gaming" and pc["fait"] == 0 and pc["pourcentage"] == 0
    assert client.get("/api/accueil").json()["pc"]["etat"] == "en_cours"
    # un résultat reçu : la barre avance
    t1 = client.get("/api/calcul/taches?n=1&veille=true&machine=gaming", headers=h).json()["taches"][0]
    client.post("/api/calcul/resultats", headers=h, json={"resultats": [{"face_id": t1["face_id"], "age_visage": 30.0}]})
    pc = client.get("/api/pc").json()
    assert pc["fait"] == 1 and pc["total"] == pc["fait"] + pc["restants"] and pc["reste_min"] is not None
    e = client.get("/api/etat", headers={"Authorization": f"Bearer {JK}"}).json()
    assert e["pc_en_veille"] and "en cours d'analyse" in e["message"]
    calculer(client, E)
    client.post("/api/calcul/fin", headers=h, json={"machine": "gaming"})
    assert client.get("/api/pc").json()["etat"] == "disponible"
    # file vide, dernière synchro récente : rien
    assert client.get("/api/calcul/taches?n=1&veille=true", headers=h).json()["synchro_lancee"] is False
    # file vide, synchro vieille de plus de 15 min : relecture d'Immich lancée en arrière-plan
    b = m.base.lire("derniere_synchro"); b["le"] = "2020-01-01T00:00:00"; m.base.ecrire("derniere_synchro", b)
    assert client.get("/api/calcul/taches?n=1&veille=true", headers=h).json()["synchro_lancee"] is True
    import time
    for _ in range(50):
        if m.base.lire("derniere_synchro")["le"] > "2021":
            break
        time.sleep(0.1)
    assert m.base.lire("derniere_synchro")["le"] > "2021"
    # sans veille (passe manuelle) : jamais de synchro déclenchée
    b = m.base.lire("derniere_synchro"); b["le"] = "2020-01-01T00:00:00"; m.base.ecrire("derniere_synchro", b)
    assert client.get("/api/calcul/taches?n=1", headers=h).json()["synchro_lancee"] is False
    # PC silencieux depuis longtemps : de nouveau « allume le PC »
    vu = m.base.lire("pc_vu"); vu["le"] = "2020-01-01T00:00:00"; m.base.ecrire("pc_vu", vu)
    E["personnes"]["inconnu1"]["birthDate"] = "1970-01-01"
    client.post("/api/synchroniser")
    e = client.get("/api/etat", headers={"Authorization": f"Bearer {JK}"}).json()
    assert not e["pc_en_veille"] and "allume le PC" in e["message"]
    assert client.get("/api/pc").json()["etat"] == "indisponible"


def test_calculateur_en_veille(env, monkeypatch):
    """calcul.py en veille : deux cycles, MiVOLO chargé une seule fois, puis rien à faire au second cycle."""
    import socket
    import threading
    import time

    import uvicorn

    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    from app import main as appmain
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = uvicorn.Server(uvicorn.Config(appmain.app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(50):
        if srv.started:
            break
        time.sleep(0.1)
    for k, v in {"MILLESIME_URL": f"http://127.0.0.1:{port}", "MILLESIME_JETON_CALCUL": JC, "VEILLE": "1",
                 "VEILLE_CYCLES": "2", "VEILLE_MINUTES": "0.001"}.items():
        monkeypatch.setenv(k, v)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mesure"))
    import importlib

    import calcul
    importlib.reload(calcul)

    class FauxMiVolo:
        device = "cpu"
        charges = 0

        def __init__(self):
            FauxMiVolo.charges += 1

        def ages(self, image, face):
            return {"mivolo": 30.0, "mivolo_corps": 31.0}

    monkeypatch.setattr(calcul.mesure, "MiVolo", FauxMiVolo)
    try:
        assert calcul.main() == 0
    finally:
        srv.should_exit = True
    assert FauxMiVolo.charges == 1
    assert client.get("/api/accueil").json()["taches"] == {"calibrage": 0, "a_dater": 0}
    assert client.get("/api/accueil").json()["pc"]["etat"] == "disponible"


def test_151_noms_obligatoires_et_tag_introuvable(env, monkeypatch):
    """Sans les noms de tags et d'albums, Millésime ne démarre pas ; un préfixe faux arrête la
    synchronisation sans rien effacer."""
    from app.config import Config
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    avant = client.get("/api/accueil").json()["compteurs"]
    assert avant["total"] > 0
    monkeypatch.delenv("MILLESIME_TAG_PREFIXE")
    with pytest.raises(RuntimeError, match="MILLESIME_TAG_PREFIXE"):
        Config.depuis_env()
    noms_de_test(monkeypatch)
    for v in ("MILLESIME_ALBUM_NON_DATEES", "MILLESIME_MODELE_ALBUM"):       # 2.2.0 : réglables dans l'appli
        monkeypatch.delenv(v)
        Config.depuis_env()
        noms_de_test(monkeypatch)
    monkeypatch.setenv("MILLESIME_MODELE_ALBUM", "Numérisation")
    with pytest.raises(RuntimeError, match="annee"):
        Config.depuis_env()
    from app import main
    main.m().cfg.tag_prefixe = "Autre nom"
    r = client.post("/api/synchroniser")
    assert r.status_code == 400 and "introuvable" in r.json()["detail"]
    assert client.get("/api/accueil").json()["compteurs"] == avant
    main.m().cfg.tag_prefixe = "Numérisation"



def _pret_a_dater(client, E):
    connecter(client)
    client.post("/api/synchroniser")
    calculer(client, E)
    cible = client.get("/api/scans?statut=a_dater").json()[0]["asset_id"]
    return cible, client.get(f"/api/scans/{cible}").json()


def test_160_ce_que_valider_envoie_a_immich(env):
    """Fige les écritures d'une validation et de son annulation : une refonte de l'interface ou du
    service ne doit pas changer ce que Millésime écrit dans la photothèque."""
    client, E = env
    cible, s = _pret_a_dater(client, E)
    annee, marge = s["annee_proposee"], s["marge"]
    E["requetes"].clear()
    r = client.post(f"/api/scans/{cible}/valider", json={"annee": annee, "marge": marge}).json()
    tag = next(t["id"] for t in E["tags"].values() if t["value"] == r["tag"])
    album = next(a["id"] for a in E["albums"].values() if a["albumName"] == f"{annee} Numérisation")

    def forme(ecritures):
        return [(m, c.replace(cible, "<scan>").replace(tag, "<tag>").replace(album, "<album>"),
                 json.loads(json.dumps(corps).replace(cible, "<scan>").replace(tag, "<tag>").replace(album, "<album>")))
                for m, c, corps in ecritures]
    assert forme(E["requetes"]) == [
        ("PUT", "/api/assets/<scan>", {"dateTimeOriginal": f"{annee}-07-01T12:00:00.000Z"}),
        ("PUT", "/api/tags", {"tags": [f"Date estimée/{annee} ±{marge}"]}),
        ("PUT", "/api/tags/<tag>/assets", {"ids": ["<scan>"]}),
        ("DELETE", "/api/albums/al-nd/assets", {"ids": ["<scan>"]}),
        ("POST", "/api/albums", {"albumName": f"{annee} Numérisation", "assetIds": ["<scan>"]}),
    ]
    E["requetes"].clear()
    j = client.get("/api/journal").json()[0]
    assert client.post(f"/api/journal/{j['id']}/annuler").json()["ok"]
    assert [(m, c) for m, c, _ in forme(E["requetes"])] == [
        ("PUT", "/api/assets/<scan>"), ("DELETE", "/api/tags/<tag>/assets"),
        ("DELETE", "/api/albums/<album>/assets"), ("PUT", "/api/albums/al-nd/assets")]


def test_160_lecture_seule_rien_n_est_ecrit(env):
    """En lecture seule : la lecture et le calcul continuent, toute écriture dans Immich est refusée
    avant d'être journalisée, et le client Immich lui-même refuse d'écrire."""
    from app import main
    from app.immich import LectureSeule
    client, E = env
    cible, s = _pret_a_dater(client, E)
    mm = main.m()
    mm.cfg.lecture_seule = mm.immich.lecture_seule = True
    assert client.get("/api/session").json()["lecture_seule"] is True
    E["requetes"].clear()
    avant = len(client.get("/api/journal").json())
    r = client.post(f"/api/scans/{cible}/valider", json={"annee": s["annee_proposee"], "marge": s["marge"]})
    assert r.status_code == 409 and "lecture seule" in r.json()["detail"]
    assert client.post("/api/nommer/inconnu1", json={"nom": "Quelqu'un"}).status_code == 409
    assert client.post("/api/nommer/inconnu1/fusionner", json={"cible": "julien"}).status_code == 409
    assert E["requetes"] == [] and len(client.get("/api/journal").json()) == avant
    assert client.get(f"/api/scans/{cible}").json()["statut"] == "a_dater"
    assert client.post("/api/synchroniser").status_code == 200                # la lecture continue
    with pytest.raises(LectureSeule):
        mm.immich.changer_date(cible, "2000-07-01T12:00:00.000Z")             # dernier filet, au plus près du réseau
    assert E["requetes"] == []


# ------------------------------------------------------------------ 2.2.0 : albums et dossiers choisis

DOSSIER = "/bibliotheque/Avant/Numérisations 2010"


def _avec_sources(client, E):
    connecter(client)
    choix = client.get("/api/sources?choix=true").json()["choix"]
    assert {"id": "al-vieux", "nom": "Vieux scans", "nombre": 3} in choix["albums"] and DOSSIER in choix["dossiers"]
    client.post("/api/sources", json={"sorte": "album", "refs": ["al-vieux"]})
    r = client.post("/api/sources", json={"sorte": "dossier", "refs": [DOSSIER]}).json()
    assert [(s["sorte"], s["nom"]) for s in r["sources"]] == [("album", "Vieux scans"), ("dossier", "Numérisations 2010")]
    client.post("/api/synchroniser")
    calculer(client, E)
    return client.get("/api/sources").json()


def test_220_albums_et_dossiers_choisis(env):
    client, E = env
    r = _avec_sources(client, E)
    assert {s["cle"]: s["total"] for s in r["sources"]} == {"album:al-vieux": 3, f"dossier:{DOSSIER}": 2}
    assert r["tag"]["total"] == 8                                                # les scans tagués n'ont pas bougé
    choix = client.get("/api/sources?choix=true").json()["choix"]
    assert "al-vieux" not in {a["id"] for a in choix["albums"]} and DOSSIER not in choix["dossiers"]   # déjà pris
    listes = [x for st in ("a_dater", "a_trancher") for x in client.get(f"/api/scans?statut={st}").json()]
    assert {x["origine"] for x in listes} == {"tag", "album", "dossier"}
    # Valider une photo d'album : la date et le tag, aucun mouvement d'album
    E["requetes"].clear()
    r = client.post("/api/scans/alb0/valider", json={"annee": 1995, "marge": 2}).json()
    assert "album" not in r and r["demande"] == ""
    assert [(m, c) for m, c, _ in E["requetes"]] == [("PUT", "/api/assets/alb0"), ("PUT", "/api/tags"),
                                                     ("PUT", f"/api/tags/{r['tag_id']}/assets")]
    assert "alb0" in E["albums"]["al-vieux"]["assets"]
    j = client.get("/api/journal").json()[0]
    assert client.post(f"/api/journal/{j['id']}/annuler").json()["ok"]
    assert E["assets"]["alb0"]["exifInfo"]["dateTimeOriginal"].startswith("2003-11-02")
    # Refus
    assert client.post("/api/sources", json={"sorte": "album", "refs": ["inconnu"]}).status_code == 400
    assert client.post("/api/sources", json={"sorte": "autre", "refs": ["x"]}).status_code == 400
    assert client.post("/api/sources/retirer", json={"cle": "album:inconnu"}).status_code == 400
    # Retirer une source : ses photos pas encore datées quittent Millésime, rien n'est écrit dans Immich
    E["requetes"].clear()
    r = client.post("/api/sources/retirer", json={"cle": "album:al-vieux"}).json()
    assert [s["cle"] for s in r["sources"]] == [f"dossier:{DOSSIER}"] and E["requetes"] == []
    assert client.get("/api/scans/alb1").status_code == 400
    client.post("/api/synchroniser")
    assert client.get("/api/scans/alb1").status_code == 400 and client.get("/api/scans/dos0").status_code == 200


def test_220_date_deja_la_comparee_a_l_estimation(env):
    client, E = env
    _avec_sources(client, E)
    c = client.get("/api/scans/alb0").json()["comparaison"]                     # Immich dit 2003, la photo est de 1995
    assert c["date_connue"] == "2003-11-02" and c["date_nom"] is None and c["coherent"] is False and "Incohérence" in c["phrase"]
    c = client.get("/api/scans/alb1").json()["comparaison"]                     # le nom du fichier dit 1997
    assert c["date_nom"] == "1997-08-14" and c["coherent"] is False
    c = client.get("/api/scans/dos0").json()["comparaison"]                     # Immich dit 1991, l'estimation aussi
    assert c["date_connue"] == "1991-07-02" and c["coherent"] is True and "Cohérent" in c["phrase"]
    assert client.get("/api/scans/nd0").json()["comparaison"] is None            # un scan non daté (1900) n'a pas de date
    # Garder la date d'Immich : rien n'est écrit, la photo est comptée datée, et cela s'annule
    E["requetes"].clear()
    r = client.post("/api/scans/dos0/garder", json={"laquelle": "actuelle"}).json()
    assert E["requetes"] == [] and r["date_gardee"] == "1991-07-02"
    s = client.get("/api/scans/dos0").json()
    assert (s["statut"], s["annee_validee"]) == ("validee", 1991)
    assert client.post(f"/api/journal/{r['journal']}/annuler").json()["ok"] and E["requetes"] == []
    assert client.get("/api/scans/dos0").json()["statut"] != "validee"
    # Prendre la date du nom du fichier : une écriture, annulable
    r = client.post("/api/scans/alb1/garder", json={"laquelle": "nom"}).json()
    assert E["assets"]["alb1"]["exifInfo"]["dateTimeOriginal"] == "1997-08-14T12:00:00.000Z"
    assert client.post(f"/api/journal/{r['journal']}/annuler").json()["ok"]
    assert E["assets"]["alb1"]["exifInfo"]["dateTimeOriginal"].startswith("2003-11-02")
    assert client.post("/api/scans/alb0/garder", json={"laquelle": "nom"}).status_code == 400       # pas de date dans son nom
    assert client.post("/api/scans/nd0/garder", json={"laquelle": "actuelle"}).status_code == 400


def test_220_dates_dans_les_noms():
    from app.service import dates_connues
    for nom, attendu in (("IMG_20050412_101500.jpg", "2005-04-12"), ("2005-04-12 plage.jpg", "2005-04-12"), ("scan 1997.08.14.jpg", "1997-08-14"),
                         ("IMG_0001.jpg", None), ("DSC12345678.jpg", None), ("20991231.jpg", None), ("19051340.jpg", None)):
        assert dates_connues({"originalFileName": nom})[1] == attendu, nom
    assert dates_connues({"exifInfo": {"dateTimeOriginal": "1900-01-01T00:00:00.000Z"}})[0] is None
    assert dates_connues({"localDateTime": "2003-11-02T10:00:00.000Z"})[0] == "2003-11-02"
    assert dates_connues({"localDateTime": "2003-11-02T10:00:00.000Z"}, deja_estime=True)[0] is None


def test_220_noms_d_albums_regles_dans_l_appli(env):
    client, E = env
    cible, s = _pret_a_dater(client, E)
    assert client.get("/api/sources").json()["albums"] == {"non_datees": "Non datées Numérisation", "modele": "{annee} Numérisation", "depuis_la_stack": True}
    assert client.post("/api/reglages/albums", json={"non_datees": "Non datées Numérisation", "modele": "Sans année"}).status_code == 400
    assert client.post("/api/reglages/albums", json={"non_datees": "", "modele": "{annee} X"}).status_code == 400
    r = client.post("/api/reglages/albums", json={"non_datees": "Non datées Numérisation", "modele": "Scans de {annee}"}).json()
    assert r["albums"] == {"non_datees": "Non datées Numérisation", "modele": "Scans de {annee}", "depuis_la_stack": False}
    r = client.post(f"/api/scans/{cible}/valider", json={"annee": s["annee_proposee"], "marge": s["marge"]}).json()
    assert r["album"] == f"Scans de {s['annee_proposee']}" and cible not in E["albums"]["al-nd"]["assets"]
    # Sans variable dans la stack ni réglage : valider un scan tagué est refusé net, avant toute écriture
    from app import main
    main.m().cfg.album_non_datees = main.m().cfg.modele_album = ""
    main.m().base.executer("DELETE FROM reglages WHERE cle IN ('album_non_datees', 'modele_album')")
    autre = client.get("/api/scans?statut=a_dater").json()[0]["asset_id"]
    E["requetes"].clear()
    r = client.post(f"/api/scans/{autre}/valider", json={"annee": 1995, "marge": 2})
    assert r.status_code == 400 and "Réglages" in r.json()["detail"] and E["requetes"] == []


def test_220_demande_a_transhumance(env, monkeypatch):
    """Un dossier choisi dont toutes les photos sont datées : la demande de passage part vers Transhumance."""
    import requests
    client, E = env
    _avec_sources(client, E)
    from app import main
    envois = []

    class Reponse:
        status_code = 200
        def json(self):
            return {"ok": True}
    vrai_post = requests.post

    def faux_post(url, **kw):
        if "/externe/demandes" not in url:
            return vrai_post(url, **kw)
        envois.append((url, kw["headers"]["Authorization"], kw["json"]))
        return Reponse()
    monkeypatch.setattr(requests, "post", faux_post)
    cle = f"dossier:{DOSSIER}"
    # Sans jeton : rien ne part, et c'est dit
    r = client.post("/api/scans/dos0/garder", json={"laquelle": "actuelle"}).json()
    assert r["demande"] == "" and envois == []                                   # il reste une photo
    r = client.post("/api/scans/dos1/garder", json={"laquelle": "actuelle"}).json()
    assert "n'est pas réglé" in r["demande"] and envois == []
    assert client.post("/api/sources/demander", json={"cle": cle}).status_code == 400
    assert client.post("/api/sources/demander", json={"cle": "album:al-vieux"}).status_code == 400   # un album ne se demande pas
    main.m().cfg.jeton_transhumance = "jeton-tr"
    r = client.post("/api/sources/demander", json={"cle": cle}).json()
    assert r["message"] == "Demande de passage envoyée à Transhumance."
    assert envois == [("http://transhumance:8097/externe/demandes", "Bearer jeton-tr", {"dossier": DOSSIER, "de": "Millésime"})]
    assert next(s for s in r["sources"] if s["cle"] == cle)["demandee_le"]
    Reponse.status_code = 404
    Reponse.json = lambda self: {"detail": "Dossier inconnu de Transhumance."}
    r = client.post("/api/sources/demander", json={"cle": cle})
    assert r.status_code == 400 and "Dossier inconnu" in r.json()["detail"]


def test_filtres_dater_et_visage_detache(env):
    """2.3.0 : chemin et noms dans la liste (filtres de « Dater ») ; « ce n'est pas cette personne », annulable."""
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    liste = client.get("/api/scans?statut=a_analyser").json()
    nd0 = next(x for x in liste if x["asset_id"] == "nd0")
    assert nd0["chemin"] == "/photos/Scans/Lot A/nd0.jpg" and nd0["noms"] == ["Alex DUVAL", "Julien B"]
    assert {x["chemin"].split("/")[3] for x in liste if x["chemin"]} == {"Lot A", "Lot B"}
    r = client.post("/api/scans/nd0/visages/nd0-f0/detacher").json()
    assert r["ok"] and r["nom"] == "Julien B"
    face = next(f for f in E["assets"]["nd0"]["faces"] if f["id"] == "nd0-f0")
    nouvelle = (face["person"] or {}).get("id")
    assert nouvelle and nouvelle != "julien" and not E["personnes"][nouvelle]["name"]
    s = client.get("/api/scans/nd0").json()
    assert next(v for v in s["visages"] if v["face_id"] == "nd0-f0")["person_nom"] in (None, "")
    assert client.post("/api/scans/nd0/visages/nd0-f0/detacher").status_code == 400      # il n'est plus rattaché à une personne nommée
    j = next(x for x in client.get("/api/journal").json() if x["action"] == "detacher")
    assert client.post(f"/api/journal/{j['id']}/annuler").json()["ok"]
    face = next(f for f in E["assets"]["nd0"]["faces"] if f["id"] == "nd0-f0")
    assert face["person"]["id"] == "julien"
    assert next(v for v in client.get("/api/scans/nd0").json()["visages"] if v["face_id"] == "nd0-f0")["person_nom"] == "Julien B"


def test_240_date_lue_dans_le_dossier():
    from app.service import date_du_dossier, jour_du_dossier
    for chemin, attendu in (("/synologyphotos/Photos numérisées/Date/1983/01/scan.jpg", "1983-01"),
                            ("/photos/1983-07 Vacances/a.jpg", "1983-07"), ("/photos/Date/1983/a.jpg", "1983"),
                            ("/photos/Scans/Lot A/1983.jpg", None), ("/photos/2099/a.jpg", None), ("/photos/50 ans/a.jpg", None)):
        assert date_du_dossier(chemin) == attendu, chemin
    assert jour_du_dossier("1983-01") == "1983-01-15" and jour_du_dossier("1983") == "1983-07-01"


def test_240_sans_visage_le_dossier_propose_et_s_ecrit(env):
    """2.4.0 : une photo sans visage utile dont le dossier porte une date passe dans « à dater », et « prendre celle
    du dossier » l'écrit (annulable)."""
    client, E = env
    connecter(client)
    E["assets"]["nd-sans"]["originalPath"] = "/photos/Photos numérisées/Date/1983/01/nd-sans.jpg"
    client.post("/api/synchroniser")
    s = client.get("/api/scans/nd-sans").json()
    assert s["statut"] == "a_dater" and s["annee_proposee"] == 1983 and s["marge"] == 0
    assert s["comparaison"]["date_dossier"] == "1983-01" and "Aucun visage" in s["comparaison"]["phrase"]
    r = client.post("/api/scans/nd-sans/garder", json={"laquelle": "dossier"}).json()
    assert E["assets"]["nd-sans"]["exifInfo"]["dateTimeOriginal"] == "1983-01-15T12:00:00.000Z"
    assert client.get("/api/scans/nd-sans").json()["statut"] == "validee"
    assert client.post(f"/api/journal/{r['journal']}/annuler").json()["ok"]


def test_240_synchro_legere(env):
    """2.4.0 : la synchro de chaque heure ne relit que les photos changées (ou dont c'est le tour) ; les noms et
    dates de naissance viennent d'une seule lecture des personnes ; le bouton relit tout."""
    client, E = env
    connecter(client)
    from app import main
    b = client.post("/api/synchroniser").json()
    assert b["complete"] and b["relues"] > 10
    E["requetes"].clear()
    E["personnes"]["julien"]["name"] = "Julien BERT"                                    # renommé dans Immich
    b = main.ETAT["m"].synchroniser()                                                    # la synchro de chaque heure
    assert not b["complete"] and b["relues"] < 10
    assert client.get("/api/scans/nd0").json()["visages"][0]["person_nom"] == "Julien BERT"


def test_250_dates_dans_les_noms_et_albums():
    from app.service import date_d_un_nom, date_du_dossier, jour_du_dossier
    assert date_d_un_nom("Noël 1992 chez mamie") == "1992" and date_d_un_nom("juillet 1985") == "1985-07"
    assert date_d_un_nom("déc. 1992 neige") == "1992-12" and date_d_un_nom("Francine Philippe 1989-1992") == "1989/1992"
    assert date_d_un_nom("Numérisations 2010") is None and date_d_un_nom("1998 Numérisation Yves") is None   # lots de scans
    assert date_d_un_nom("1923 2023") is None and date_d_un_nom("Boite 156-184") is None and date_d_un_nom("85 86") is None
    assert date_du_dossier("/p/Vacances 1985/Plage/a.jpg") == "1985"
    assert jour_du_dossier("1989/1992") == "1990-07-01"


def test_250_tuile_datables_lot_et_annulation(env):
    """2.5.0 : un album ou un dossier daté rend la photo « datable » ; tout dater d'un coup par lots, et tout annuler."""
    client, E = env
    connecter(client)
    E["assets"]["nd-sans"]["originalPath"] = "/photos/Noël 1992 chez mamie/nd-sans.jpg"
    client.post("/api/synchroniser")
    acc = client.get("/api/accueil").json()["compteurs"]
    assert acc["datables"] >= 1
    liste = client.get("/api/scans?statut=datables").json()
    assert "nd-sans" in [x["asset_id"] for x in liste]
    s = client.get("/api/scans/nd-sans").json()
    assert s["annee_proposee"] == 1992 and s["comparaison"]["date_dossier_source"] == "le dossier"
    r = client.post("/api/datables/dater", json={"n": 200}).json()
    assert r["faites"] == len(liste) and r["restant"] == 0 and not r["erreurs"]
    assert E["assets"]["nd-sans"]["exifInfo"]["dateTimeOriginal"] == "1992-07-01T12:00:00.000Z"
    assert client.get("/api/scans/nd-sans").json()["statut"] == "validee"
    a = client.post(f"/api/lots/{r['lot']}/annuler").json()
    assert a["annulees"] == r["faites"] and not a["erreurs"]
    assert client.get("/api/scans/nd-sans").json()["statut"] != "validee"


def test_250_titre_d_album(env):
    client, E = env
    connecter(client)
    E["albums"]["al-noel"] = {"id": "al-noel", "albumName": "Noël juillet 1987 au chalet", "assets": {"nd-sans"}}
    client.post("/api/synchroniser")
    s = client.get("/api/scans/nd-sans").json()
    assert s["comparaison"]["date_dossier"] == "1987-07" and "Noël juillet 1987 au chalet" in s["comparaison"]["date_dossier_source"]
    assert s["annee_proposee"] == 1987 and "l'album" in s["raison"]


def test_260_dossiers_et_albums_datables(env):
    """2.6.0 : la colonne des dossiers/albums datables, leurs photos, et « dater toutes les photos du dossier »."""
    client, E = env
    connecter(client)
    E["assets"]["nd-sans"]["originalPath"] = "/photos/Noël 1992 chez mamie/sous/nd-sans.jpg"
    E["albums"]["al-noel"] = {"id": "al-noel", "albumName": "juillet 1987", "assets": {"nd2"}}
    E["assets"]["nd2"]["faces"] = []
    client.post("/api/synchroniser")
    g = client.get("/api/datables/groupes").json()
    noel = next(x for x in g if x["sorte"] == "dossier" and x["nom"].endswith("Noël 1992 chez mamie"))
    assert noel["date"] == "1992" and noel["n"] == 1
    assert any(x["sorte"] == "album" and x["nom"] == "juillet 1987" for x in g)
    photos = client.get("/api/datables/photos", params={"cle": noel["cle"]}).json()
    assert [p["asset_id"] for p in photos] == ["nd-sans"] and photos[0]["fichier"] == "nd-sans.jpg"
    r = client.post("/api/datables/dater", json={"groupe": noel["cle"], "n": 200}).json()
    assert r["faites"] == 1 and r["restant"] == 0
    assert client.get("/api/scans/nd-sans").json()["statut"] == "validee"
    assert client.get("/api/scans/nd2").json()["statut"] != "validee"                  # l'autre groupe n'a pas bougé
    assert client.get("/api/vignette/nd2").status_code == 200


def test_270_plusieurs_dossiers_dates_choisies(env):
    """2.7.0 : plusieurs dossiers/albums d'un coup, chacun à sa date (celle du nom, ou une date tapée)."""
    client, E = env
    connecter(client)
    E["assets"]["nd-sans"]["originalPath"] = "/photos/Noël 1992 chez mamie/nd-sans.jpg"
    E["albums"]["al-ete"] = {"id": "al-ete", "albumName": "Vacances juillet 1987", "assets": {"nd2"}}
    E["assets"]["nd2"]["faces"] = []
    client.post("/api/synchroniser")
    g = {x["nom"].rsplit("/", 1)[-1]: x["cle"] for x in client.get("/api/datables/groupes").json()}
    assert client.post("/api/datables/dater", json={"groupes": {g["Noël 1992 chez mamie"]: "31/02/1992"}}).status_code == 400
    r = client.post("/api/datables/dater", json={"groupes": {g["Noël 1992 chez mamie"]: "24/12/1992",
                                                           g["Vacances juillet 1987"]: None}, "n": 200}).json()
    assert r["faites"] == 2 and r["restant"] == 0
    assert E["assets"]["nd-sans"]["exifInfo"]["dateTimeOriginal"] == "1992-12-24T12:00:00.000Z"      # date tapée
    assert E["assets"]["nd2"]["exifInfo"]["dateTimeOriginal"] == "1987-07-15T12:00:00.000Z"          # date du nom
    assert client.post(f"/api/lots/{r['lot']}/annuler").json()["annulees"] == 2
