"""Tests de l'appli Millésime (serveur NAS) contre le faux Immich, avec un faux calculateur."""
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


@pytest.fixture
def env(tmp_path, monkeypatch):
    serveur, url, E = faux.demarrer()
    monkeypatch.setenv("MILLESIME_IMMICH_URL", url)
    monkeypatch.setenv("MILLESIME_IMMICH_CLE", faux.CLE)
    monkeypatch.setenv("MILLESIME_PASSWORD", MDP)
    monkeypatch.setenv("MILLESIME_JETON_CALCUL", JC)
    monkeypatch.setenv("MILLESIME_JETON_CARNET", JK)
    monkeypatch.setenv("MILLESIME_ETAT", str(tmp_path))
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
    assert client.get("/api/accueil").json()["pc"]["actif"] is True
    e = client.get("/api/etat", headers={"Authorization": f"Bearer {JK}"}).json()
    assert e["pc_en_veille"] and "en cours d'analyse" in e["message"]
    calculer(client, E)
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
    assert client.get("/api/accueil").json()["pc"]["veille"] is True
