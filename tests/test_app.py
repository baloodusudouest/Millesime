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

MDP = "secret-commun-de-la-maison"
JC, JK, JH = "jeton-calcul", "jeton-maison", "jeton-ha"       # JK : MAISON_JETON (carnet et les autres applis maison)


def noms_de_test(monkeypatch):
    """Noms de tags et d'albums du faux Immich (1.5.1 : plus de valeur par défaut dans le code)."""
    monkeypatch.setenv("MILLESIME_TAG_PREFIXE", "Numérisation")
    monkeypatch.setenv("MILLESIME_ALBUM_NON_DATEES", "Non datées Numérisation")
    monkeypatch.setenv("MILLESIME_MODELE_ALBUM", "{annee} Numérisation")


MAISON = ("MAISON_PASSWORD", "MAISON_JETON", "MAISON_JETON_ANCIEN", "MAISON_LECTURE_SEULE", "MAISON_ANNEAU_URL")


@pytest.fixture(autouse=True)
def sans_variables_maison(monkeypatch):
    """2.11.0 : les variables communes de la maison ne viennent jamais de la machine qui lance les tests."""
    for v in MAISON:
        monkeypatch.delenv(v, raising=False)


@pytest.fixture
def env(tmp_path, monkeypatch):
    serveur, url, E = faux.demarrer()
    monkeypatch.setenv("MILLESIME_IMMICH_URL", url)
    monkeypatch.setenv("MILLESIME_IMMICH_CLE", faux.CLE)
    monkeypatch.setenv("MAISON_PASSWORD", MDP)
    monkeypatch.setenv("MILLESIME_JETON_CALCUL", JC)
    monkeypatch.setenv("MILLESIME_JETON_HA", JH)
    monkeypatch.setenv("MILLESIME_ETAT", str(tmp_path))
    noms_de_test(monkeypatch)
    from app import main
    from app.config import Config
    from app.service import Millesime
    main.ETAT.clear()
    main.ETAT["m"] = Millesime(Config.depuis_env())
    main.ETAT["synchro_auto"] = False
    # 2.12.0 : MAISON_JETON ouvre /api/etat et /externe/sauvegarde (lu à chaque demande). Posé après la Config pour que
    # Chambre noire et Transhumance restent « non reliées » dans les tests qui ne le disent pas.
    monkeypatch.setenv("MAISON_JETON", JK)
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
    assert "hugo" not in ids
    assert any(x["nom"] == "Personne F" for x in g["sans_naissance"])
    assert client.post("/api/nommer/inconnu1", json={"nom": "  Personne   BRAVO "}).json()["nom"] == "Personne BRAVO"
    assert E["personnes"]["inconnu1"]["name"] == "Personne BRAVO"
    client.post("/api/nommer/inconnu2/ignorer")
    assert client.get("/api/nommer").json()["groupes"] == []
    e = client.get("/api/etat", headers={"Authorization": f"Bearer {JK}"}).json()
    assert e["a_analyser"] > 0 and "allume le PC" in e["message"]
    assert {"Personne BRAVO", "Personne F"} <= {p["nom"] for p in e["sans_naissance"]}


def test_frise_et_images(env):
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    f = client.get("/api/personnes/hugo/frise").json()
    assert f["nom"] == "Personne E" and len(f["elements"]) >= 5
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
    assert sus and all(s["nom"] == "Personne CHARLIE" for s in sus)


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
    assert "Personne E" in noms and "" not in noms
    assert sug[0]["sur_scans"] >= sug[-1]["sur_scans"]          # présents sur les scans d'abord
    # un nom existant est refusé (accents et casse ignorés) : il faut fusionner
    r = client.post("/api/nommer/inconnu1", json={"nom": "personne charlie"})
    assert r.status_code == 400 and "existe déjà" in r.json()["detail"]
    ap = client.get("/api/nommer/inconnu1/apercu/mamie").json()
    assert ap["source"] and ap["cible"]["nom"] == "Personne CHARLIE" and ap["cible"]["exemples"]
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
    client.post("/api/nommer/inconnu2", json={"nom": "Personne ALPHA"})
    j = next(x for x in client.get("/api/journal").json() if x["action"] == "nommer")
    client.post(f"/api/journal/{j['id']}/annuler")
    assert E["personnes"]["inconnu2"]["name"] == ""
    b = client.get("/api/boite/nd0/nd0-f0").json()
    assert 0 < b["x"] < 1 and 0 < b["l"] < 1 and b["nom"] == "Personne E"


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
    client.post("/api/nommer/inconnu2", json={"nom": "Personne ALPHA"})
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
    # dans Immich : le visage non attribué de nd-sans est rattaché à Hugo, et le groupe inconnu2 est nommé
    f2 = next(f for f in E["assets"]["nd-sans"]["faces"] if f["id"] == "nd-sans-f2")
    f2["person"] = E["personnes"]["hugo"]
    E["personnes"]["inconnu2"]["name"] = "Personne ALPHA"
    s = client.get("/api/scans/nd-sans").json()
    assert s["statut"] == "a_trancher"
    r = client.post("/api/scans/nd-sans/actualiser").json()
    assert r["changes"] == 2 and r["a_calculer"] == 1
    s = client.get("/api/scans/nd-sans").json()
    noms = {v["face_id"]: v["person_nom"] for v in s["visages"]}
    assert noms["nd-sans-f2"] == "Personne E" and noms["nd-sans-f1"] == "Personne ALPHA"
    assert s["statut"] == "a_analyser"            # le visage de Hugo attend le calcul sur le PC


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
    # 2.12.0 : les noms ne sont plus exigés au démarrage : ce sont des réglages (Réglages), repris de la stack une fois
    for v in ("MILLESIME_TAG_PREFIXE", "MILLESIME_ALBUM_NON_DATEES", "MILLESIME_MODELE_ALBUM"):
        monkeypatch.delenv(v)
    Config.depuis_env()
    noms_de_test(monkeypatch)
    from app import main
    main.m().base.ecrire("tag_prefixe", "Autre nom")
    # 2.10.0 : l'ancien libellé reste suivi ; le nouveau, jamais trouvé, ne vide rien et n'arrête rien
    r = client.post("/api/synchroniser")
    assert r.status_code == 200
    assert client.get("/api/accueil").json()["compteurs"] == avant
    lib = {l["libelle"]: l for l in client.get("/api/sources").json()["libelles"]}
    assert lib["Autre nom"]["actuel"] and lib["Autre nom"]["vu_le"] is None and lib["Numérisation"]["vu_le"]
    # Seul libellé, jamais trouvé : arrêt sans rien effacer (protection 1.5.1)
    main.m().base.ecrire("libelles", [])
    r = client.post("/api/synchroniser")
    assert r.status_code == 400 and "introuvable" in r.json()["detail"]
    assert client.get("/api/accueil").json()["compteurs"] == avant
    main.m().base.ecrire("libelles", [])
    main.m().base.ecrire("tag_prefixe", "Numérisation")



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
    assert client.post("/api/nommer/inconnu1/fusionner", json={"cible": "hugo"}).status_code == 409
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
    assert client.get("/api/sources").json()["albums"] == {"non_datees": "Non datées Numérisation", "modele": "{annee} Numérisation", "depuis_chambre_noire": False}
    assert client.post("/api/reglages/albums", json={"non_datees": "Non datées Numérisation", "modele": "Sans année"}).status_code == 400
    assert client.post("/api/reglages/albums", json={"non_datees": "", "modele": "{annee} X"}).status_code == 400
    r = client.post("/api/reglages/albums", json={"non_datees": "Non datées Numérisation", "modele": "Scans de {annee}"}).json()
    assert r["albums"] == {"non_datees": "Non datées Numérisation", "modele": "Scans de {annee}", "depuis_chambre_noire": False}
    r = client.post(f"/api/scans/{cible}/valider", json={"annee": s["annee_proposee"], "marge": s["marge"]}).json()
    assert r["album"] == f"Scans de {s['annee_proposee']}" and cible not in E["albums"]["al-nd"]["assets"]
    # Sans réglage : valider un scan tagué est refusé net, avant toute écriture
    from app import main
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
    assert "n'est pas reliée" in r["demande"] and envois == []
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
    assert nd0["chemin"] == "/photos/Scans/Lot A/nd0.jpg" and nd0["noms"] == ["Personne DELTA", "Personne E"]
    assert {x["chemin"].split("/")[3] for x in liste if x["chemin"]} == {"Lot A", "Lot B"}
    r = client.post("/api/scans/nd0/visages/nd0-f0/detacher").json()
    assert r["ok"] and r["nom"] == "Personne E"
    face = next(f for f in E["assets"]["nd0"]["faces"] if f["id"] == "nd0-f0")
    nouvelle = (face["person"] or {}).get("id")
    assert nouvelle and nouvelle != "hugo" and not E["personnes"][nouvelle]["name"]
    s = client.get("/api/scans/nd0").json()
    assert next(v for v in s["visages"] if v["face_id"] == "nd0-f0")["person_nom"] in (None, "")
    assert client.post("/api/scans/nd0/visages/nd0-f0/detacher").status_code == 400      # il n'est plus rattaché à une personne nommée
    j = next(x for x in client.get("/api/journal").json() if x["action"] == "detacher")
    assert client.post(f"/api/journal/{j['id']}/annuler").json()["ok"]
    face = next(f for f in E["assets"]["nd0"]["faces"] if f["id"] == "nd0-f0")
    assert face["person"]["id"] == "hugo"
    assert next(v for v in client.get("/api/scans/nd0").json()["visages"] if v["face_id"] == "nd0-f0")["person_nom"] == "Personne E"


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
    E["personnes"]["hugo"]["name"] = "Personne ECHO"                                    # renommé dans Immich
    b = main.ETAT["m"].synchroniser()                                                    # la synchro de chaque heure
    assert not b["complete"] and b["relues"] < 10
    assert client.get("/api/scans/nd0").json()["visages"][0]["person_nom"] == "Personne ECHO"


def test_250_dates_dans_les_noms_et_albums():
    from app.service import date_d_un_nom, date_du_dossier, jour_du_dossier
    assert date_d_un_nom("Noël 1992 chez mamie") == "1992" and date_d_un_nom("juillet 1985") == "1985-07"
    assert date_d_un_nom("déc. 1992 neige") == "1992-12" and date_d_un_nom("Paule Bravo 1989-1992") == "1989/1992"
    assert date_d_un_nom("Numérisations 2010") is None and date_d_un_nom("1998 Numérisation Marc") is None   # lots de scans
    assert date_d_un_nom("1923 2023") is None and date_d_un_nom("Boite 156-184") is None and date_d_un_nom("85 86") is None
    assert date_du_dossier("/p/Vacances 1985/Plage/a.jpg") == "1985"
    assert jour_du_dossier("1989/1992") == "1990-07-01"
    # 2.7.3 : un jour précis dans le nom
    assert date_d_un_nom("1985-12-25 Noel") == "1985-12-25" and date_d_un_nom("04 1988-04-09 mariage") == "1988-04-09"
    assert date_d_un_nom("25.12.1985 Noël") == "1985-12-25" and date_d_un_nom("9 avril 1988") == "1988-04-09"
    assert date_d_un_nom("1er mai 1990") == "1990-05-01" and date_d_un_nom("1985-02-30 x") == "1985-02"    # jour impossible
    assert jour_du_dossier("1988-04-09") == "1988-04-09"
    assert date_du_dossier("/p/1988/04/1988-04-09 mariage/a.jpg") == "1988-04-09"


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


def test_280_home_assistant(env):
    """2.8.0 : /ha/etat avec son propre jeton, des nombres et l'état du PC, aucun nom ; les lecteurs sont notés."""
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    assert client.get("/ha/etat").status_code == 401
    assert client.get("/ha/etat", headers={"Authorization": f"Bearer {JK}"}).status_code == 401
    r = client.get("/ha/etat", headers={"Authorization": f"Bearer {JH}"})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    e = r.json()
    assert e["pc"] == "jamais_vu" and e["a_analyser"] > 0 and isinstance(e["sans_naissance"], int)
    assert set(e) >= {"a_dater", "a_trancher", "a_nommer", "validees", "total", "pc_pourcentage", "pc_reste_min"}
    texte = r.text
    for p in E["personnes"].values():
        if p.get("name"):
            assert p["name"] not in texte
    client.get("/api/etat", headers={"Authorization": f"Bearer {JK}"})
    lu = client.get("/api/accueil").json()["lu_par"]
    assert lu["ha"] and lu["carnet"] and lu["ha_ouvert"] is True


def test_290_noms_lus_dans_chambre_noire(env, monkeypatch):
    """2.9.0 : relié à Chambre noire, Millésime suit son libellé, son tag et son album des non datées ;
    s'il ne répond plus, les derniers noms lus restent en usage ; Chambre noire passe devant les Réglages."""
    import requests
    client, E = env
    connecter(client)
    from app import main
    m = main.m()
    lectures = []

    class Reponse:
        status_code = 200
        corps = {"regle": True, "libelle": "Numérisation", "album_non_datees": "Sans date (CN)",
                 "tag_non_datee": "Numérisation/Non datée"}
        def json(self):
            return self.corps
    vrai_get = requests.get

    def faux_get(url, **kw):
        if "/externe/noms" not in url:
            return vrai_get(url, **kw)
        lectures.append((url, kw["headers"]["Authorization"]))
        if Reponse.status_code == 0:
            raise requests.ConnectionError("hors ligne")
        return Reponse()
    monkeypatch.setattr(requests, "get", faux_get)
    # Non relié : rien n'est lu, noms de la stack
    client.post("/api/synchroniser")
    assert lectures == [] and m.album_non_datees == "Non datées Numérisation"
    assert client.get("/api/accueil").json()["chambre_noire"]["relie"] is False
    m.cfg.jeton_chambre_noire = "jeton-cn"
    r = client.post("/api/synchroniser")
    assert r.status_code == 200
    assert lectures == [("http://chambre-noire:8100/externe/noms", "Bearer jeton-cn")]
    assert m.album_non_datees == "Sans date (CN)" and m.tag_non_datee_complet == "Numérisation/Non datée"
    src = client.get("/api/sources").json()
    assert src["albums"]["depuis_chambre_noire"] and src["albums"]["non_datees"] == "Sans date (CN)"
    # Les Réglages ne changent plus que le modèle d'album
    client.post("/api/reglages/albums", json={"non_datees": "Autre", "modele": "{annee} Scans"})
    assert m.album_non_datees == "Sans date (CN)" and m.modele_album == "{annee} Scans"
    # Chambre noire hors ligne : derniers noms gardés, erreur montrée
    Reponse.status_code = 0
    client.post("/api/synchroniser")
    cn = client.get("/api/accueil").json()["chambre_noire"]
    assert cn["noms"]["album_non_datees"] == "Sans date (CN)" and "ne répond pas" in cn["erreur"]["detail"]
    # Nouveau libellé sans tag dans Immich : la synchro s'arrête sans rien vider
    Reponse.status_code = 200
    Reponse.corps = {**Reponse.corps, "libelle": "Autre lot", "tag_non_datee": "Autre lot/Non datée"}
    avant = len(client.get("/api/scans?statut=a_analyser").json())
    r = client.post("/api/synchroniser")
    assert r.status_code == 200                                   # 2.10.0 : l'ancien libellé reste suivi
    assert len(client.get("/api/scans?statut=a_analyser").json()) == avant
    lib = {l["libelle"]: l for l in client.get("/api/sources").json()["libelles"]}
    assert set(lib) == {"Numérisation", "Autre lot"} and lib["Autre lot"]["actuel"] and lib["Autre lot"]["origine"] == "chambre_noire"
    assert "Sans date (CN)" in m.albums_non_datees()       # album des non datées de l'ancien libellé, toujours reconnu
    # Jeton refusé
    Reponse.status_code = 401
    client.post("/api/synchroniser")
    assert "jeton refusé" in client.get("/api/accueil").json()["chambre_noire"]["erreur"]["detail"]


def test_290_prefixe_facultatif_si_chambre_noire(env):
    """2.12.0 : le libellé est un réglage ; vide, il est refusé tant que Chambre noire n'est pas reliée."""
    client, _ = env
    connecter(client)
    from app import main
    r = client.put("/api/reglages", json={"tag_prefixe": ""})
    assert r.status_code == 400 and "Chambre noire" in r.json()["detail"]
    main.m().cfg.jeton_chambre_noire = "j"
    r = client.put("/api/reglages", json={"tag_prefixe": ""})
    assert r.status_code == 200 and r.json()["reglages"]["tag_prefixe"] == ""
    main.m().cfg.jeton_chambre_noire = ""


def test_2100_libelles_suivis(env):
    """2.10.0 : anciens libellés gardés et relus ; ajout et retrait dans Réglages ; l'actuel ne se retire pas ;
    un tag déjà vu qui disparaît d'Immich arrête la synchro sans rien vider."""
    client, E = env
    connecter(client)
    from app import main
    m = main.m()
    client.post("/api/synchroniser")
    total = client.get("/api/accueil").json()["compteurs"]["total"]
    lib = client.get("/api/sources").json()["libelles"]
    assert [(l["libelle"], l["actuel"], l["origine"]) for l in lib] == [("Numérisation", True, "reglages")] and lib[0]["photos"] > 0
    assert client.post("/api/libelles", json={"libelle": "A/B"}).status_code == 400
    r = client.post("/api/libelles", json={"libelle": "Vieux lot"})
    assert r.status_code == 200 and [l["libelle"] for l in r.json()["libelles"]] == ["Numérisation", "Vieux lot"]
    assert client.post("/api/libelles", json={"libelle": "Vieux lot"}).status_code == 400
    assert "Non datées Vieux lot" in m.albums_non_datees()
    assert client.post("/api/synchroniser").status_code == 200          # jamais trouvé : rien n'arrête
    assert client.post("/api/libelles/retirer", json={"libelle": "Numérisation"}).status_code == 400   # l'actuel
    # Un libellé déjà vu dont le tag disparaît : arrêt, rien n'est vidé, conseil de le retirer
    liste = m.base.lire("libelles")
    for l in liste:
        if l["libelle"] == "Vieux lot":
            l["vu_le"] = "2026-11-01T10:00:00"
    m.base.ecrire("libelles", liste)
    r = client.post("/api/synchroniser")
    assert r.status_code == 400 and "Vieux lot/Non datée" in r.json()["detail"] and "retire" in r.json()["detail"]
    assert client.get("/api/accueil").json()["compteurs"]["total"] == total
    r = client.post("/api/libelles/retirer", json={"libelle": "Vieux lot"})
    assert [l["libelle"] for l in r.json()["libelles"]] == ["Numérisation"]
    assert client.post("/api/synchroniser").status_code == 200


# ---------------------------------------------------------------- 2.11.0 : variables communes de la maison

def _env_minimal(monkeypatch, tmp_path):
    for v in ("MILLESIME_PASSWORD", "MILLESIME_LECTURE_SEULE", "MILLESIME_JETON_TRANSHUMANCE",
              "MILLESIME_JETON_CHAMBRE_NOIRE", "MILLESIME_IMMICH_LIEN", "MILLESIME_JETON_CARNET"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("MILLESIME_IMMICH_CLE", "x")
    monkeypatch.setenv("MILLESIME_ETAT", str(tmp_path))
    noms_de_test(monkeypatch)


def test_2110_module_maison_non_retouche():
    from app import maison
    assert maison.CONTRAT == 3 and maison.CONTRAT_SAUVEGARDE == 1
    assert maison.empreinte_calculee() == maison.empreinte_ecrite()


def test_2120_mot_de_passe_commun_seul(monkeypatch, tmp_path):
    """2.12.0 : MAISON_PASSWORD seul ; l'ancien nom seul ne suffit plus : refus de démarrer."""
    from app.config import Config
    _env_minimal(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="MAISON_PASSWORD est absent ou trop court"):
        Config.depuis_env()
    monkeypatch.setenv("MILLESIME_PASSWORD", "ancien-mot-de-passe")
    with pytest.raises(RuntimeError, match="MAISON_PASSWORD est absent ou trop court"):
        Config.depuis_env()
    monkeypatch.setenv("MAISON_PASSWORD", "court")
    with pytest.raises(RuntimeError, match="trop court"):
        Config.depuis_env()
    monkeypatch.setenv("MAISON_PASSWORD", MDP)
    assert Config.depuis_env().mot_de_passe == MDP


def test_2110_lecture_seule_maison_et_forcage(monkeypatch, tmp_path):
    from app.config import Config
    _env_minimal(monkeypatch, tmp_path)
    monkeypatch.setenv("MAISON_PASSWORD", MDP)
    c = Config.depuis_env()
    assert not c.lecture_seule and c.lecture_seule_origine == ""
    monkeypatch.setenv("MAISON_LECTURE_SEULE", "oui")
    c = Config.depuis_env()
    assert c.lecture_seule and c.lecture_seule_origine == "maison"
    monkeypatch.setenv("MILLESIME_LECTURE_SEULE", "non")                # l'appli force l'écriture
    c = Config.depuis_env()
    assert not c.lecture_seule and c.lecture_seule_origine == ""
    monkeypatch.delenv("MAISON_LECTURE_SEULE")
    monkeypatch.setenv("MILLESIME_LECTURE_SEULE", "1")                  # valeurs acceptées d'avant : toujours valables
    c = Config.depuis_env()
    assert c.lecture_seule and c.lecture_seule_origine == "appli"


def test_2110_lecture_seule_maison_dite_a_l_ecran(env, monkeypatch):
    client, _ = env
    from app import main
    connecter(client)
    main.m().cfg.lecture_seule, main.m().cfg.lecture_seule_origine = True, "maison"
    s = client.get("/api/session").json()
    assert s["lecture_seule"] and s["lecture_seule_origine"] == "maison"
    r = client.post("/api/scans/nd-sans/valider", json={"annee": 1990})
    assert r.status_code == 409 and "MAISON_LECTURE_SEULE" in r.json()["detail"]


def test_2120_portes_a_jeton(env, monkeypatch):
    """/api/etat (carnet) : MAISON_JETON seul ; l'ancien jeton de carnet n'ouvre plus ; HA et le PC gardent les leurs."""
    client, _ = env
    monkeypatch.setenv("MILLESIME_JETON_CARNET", "ancien-jeton-carnet")
    commun = {"Authorization": f"Bearer {JK}"}
    assert client.get("/api/etat", headers=commun).status_code == 200
    assert client.get("/api/etat", headers={"X-Maison-Jeton": JK}).status_code == 200
    assert client.get("/api/etat", headers={"Authorization": "Bearer ancien-jeton-carnet"}).status_code == 401
    monkeypatch.setenv("MAISON_JETON_ANCIEN", "jeton-d-avant")              # changement de jeton commun
    assert client.get("/api/etat", headers={"Authorization": "Bearer jeton-d-avant"}).status_code == 200
    assert client.get("/api/etat", headers={"Authorization": "Bearer faux"}).status_code == 401
    assert client.get("/api/etat").status_code == 401
    # Home Assistant et le calculateur du PC ne s'ouvrent pas avec le jeton commun
    assert client.get("/ha/etat", headers=commun).status_code == 401
    assert client.get("/ha/etat", headers={"Authorization": f"Bearer {JH}"}).status_code == 200
    assert client.get("/api/calcul/taches", headers=commun).status_code == 401
    assert client.get("/externe/sauvegarde", headers={"Authorization": f"Bearer {JH}"}).status_code == 401
    assert client.get("/externe/sauvegarde", headers={"Authorization": f"Bearer {JC}"}).status_code == 401
    # MAISON_JETON vide : portes fermées, même avec un en-tête vide
    monkeypatch.delenv("MAISON_JETON")
    monkeypatch.delenv("MAISON_JETON_ANCIEN")
    assert client.get("/api/etat", headers={"Authorization": "Bearer "}).status_code == 401
    assert client.get("/api/etat", headers=commun).status_code == 401
    assert client.get("/externe/sauvegarde", headers=commun).status_code == 404


def test_2120_jetons_envoyes(monkeypatch, tmp_path):
    """Transhumance et Chambre noire : MAISON_JETON seul ; les anciens jetons par paire ne sont plus lus."""
    from app.config import Config
    _env_minimal(monkeypatch, tmp_path)
    monkeypatch.setenv("MAISON_PASSWORD", MDP)
    monkeypatch.setenv("MILLESIME_JETON_TRANSHUMANCE", "jeton-tr")
    monkeypatch.setenv("MILLESIME_JETON_CHAMBRE_NOIRE", "jeton-cn")
    c = Config.depuis_env()
    assert c.jeton_transhumance == "" and c.jeton_chambre_noire == ""
    monkeypatch.setenv("MAISON_JETON", "jeton-commun")
    c = Config.depuis_env()
    assert c.jeton_transhumance == "jeton-commun" and c.jeton_chambre_noire == "jeton-commun"


def test_2110_adresse_d_immich_par_l_annuaire(env, monkeypatch):
    client, _ = env
    from app import main, maison
    connecter(client)
    client.post("/api/synchroniser")
    services = [{"nom": "Immich", "locale": "http://nas.lan:2283/", "privee": "https://immich.exemple.ts.net"}]
    monkeypatch.setattr(main, "ANNUAIRE", maison.Annuaire(jeton="j", lire=lambda: services))
    s = client.get("/api/scans/nd-sans").json()
    assert s["lien_immich"] == "http://nas.lan:2283/photos/nd-sans"
    s = client.get("/api/scans/nd-sans", headers={"Host": "millesime.exemple.ts.net"}).json()
    assert s["lien_immich"] == "https://immich.exemple.ts.net/photos/nd-sans"
    assert all(g["lien_immich"].startswith("http://nas.lan:2283/people/") for g in client.get("/api/nommer").json()["groupes"])

    # Anneau injoignable : le chemin seul (le navigateur complète : même machine, port 2283) ;
    # 2.12.0 : MILLESIME_IMMICH_LIEN n'est plus lu
    def injoignable():
        raise OSError("pas d'Anneau")
    monkeypatch.setattr(main, "ANNUAIRE", maison.Annuaire(jeton="j", lire=injoignable))
    monkeypatch.setenv("MILLESIME_IMMICH_LIEN", "http://repli:2283")
    assert client.get("/api/scans/nd-sans").json()["lien_immich"] == "/photos/nd-sans"
    assert all(g["lien_immich"].startswith("/people/") for g in client.get("/api/nommer").json()["groupes"])


# ---------------------------------------------------------------- 2.12.0 : réglages dans l'appli, sauvegarde, restauration

def test_2120_reprise_au_premier_demarrage_puis_variable_ignoree(monkeypatch, tmp_path):
    """Les anciennes variables donnent la valeur de départ une seule fois (ligne au journal), puis ne sont plus lues."""
    from app.config import Config
    from app.service import Millesime
    _env_minimal(monkeypatch, tmp_path)
    monkeypatch.setenv("MAISON_PASSWORD", MDP)
    monkeypatch.setenv("MILLESIME_SYNCHRO_MINUTES", "30")
    m = Millesime(Config.depuis_env())
    assert m.reglages() == {"tag_prefixe": "Numérisation", "synchro_minutes": 30,
                            "album_non_datees": "Non datées Numérisation", "modele_album": "{annee} Numérisation",
                            "libelles": []}
    assert sorted(m.repris) == ["album_non_datees", "modele_album", "synchro_minutes", "tag_prefixe"]
    j = m.journal()
    assert {l["apres"]["cle"] for l in j if l["action"] == "reglage_repris"} == set(m.repris)
    assert next(l for l in j if l["apres"]["cle"] == "synchro_minutes")["avant"] == {"variable": "MILLESIME_SYNCHRO_MINUTES"}
    m.base.cx.close()
    # Second démarrage : la stack a changé, les réglages non
    monkeypatch.setenv("MILLESIME_TAG_PREFIXE", "Autre")
    monkeypatch.setenv("MILLESIME_SYNCHRO_MINUTES", "15")
    monkeypatch.delenv("MILLESIME_MODELE_ALBUM")
    m2 = Millesime(Config.depuis_env())
    assert m2.repris == [] and m2.reglages()["tag_prefixe"] == "Numérisation" and m2.synchro_minutes == 30
    assert m2.modele_album == "{annee} Numérisation"
    assert len([l for l in m2.journal() if l["action"] == "reglage_repris"]) == 4
    m2.base.cx.close()


def test_2120_reprise_d_une_valeur_fausse(monkeypatch, tmp_path):
    from app.config import Config
    from app.service import Millesime
    _env_minimal(monkeypatch, tmp_path)
    monkeypatch.setenv("MAISON_PASSWORD", MDP)
    monkeypatch.setenv("MILLESIME_SYNCHRO_MINUTES", "souvent")
    monkeypatch.setenv("MILLESIME_MODELE_ALBUM", "Sans année")
    m = Millesime(Config.depuis_env())
    assert m.synchro_minutes == 60 and m.modele_album == ""                 # valeur par défaut, rien de repris
    assert "synchro_minutes" not in m.repris and "modele_album" not in m.repris
    m.base.cx.close()


def test_2120_put_reglages_et_mauvais_types(env):
    client, _ = env
    assert client.get("/api/reglages").status_code == 401                   # session requise
    assert client.put("/api/reglages", json={"synchro_minutes": 10}).status_code == 401
    connecter(client)
    from app import main
    m = main.m()
    r = client.get("/api/reglages").json()
    assert r["reglages"]["tag_prefixe"] == "Numérisation" and r["reglages"]["synchro_minutes"] == 60
    m.reveil.clear()
    r = client.put("/api/reglages", json={"synchro_minutes": 15, "tag_prefixe": " Numérisation "})
    assert r.status_code == 200 and r.json()["reglages"]["synchro_minutes"] == 15
    assert m.synchro_minutes == 15 and m.reveil.is_set()                    # la boucle recalcule son attente sans redémarrer
    assert client.get("/api/accueil").json()["synchro_minutes"] == 15
    for corps, mot in (({"synchro_minutes": "beaucoup"}, "entier"), ({"synchro_minutes": True}, "entier"),
                       ({"synchro_minutes": 2}, "entre 5"), ({"tag_prefixe": 12}, "texte"),
                       ({"tag_prefixe": "A/B"}, "/"), ({"modele_album": "Sans année"}, "{annee}"),
                       ({"libelles": "x"}, "liste"), ({"inconnu": 1}, "inconnu"),
                       ({"synchro_minutes": 30, "album_non_datees": ["x"]}, "texte")):
        r = client.put("/api/reglages", json=corps)
        assert r.status_code == 400 and mot in r.json()["detail"], (corps, r.json())
    assert m.synchro_minutes == 15                                          # rien n'a changé (tout est vérifié avant)
    # Libellés suivis par les réglages : un ancien libellé ajouté, l'actuel remis de lui-même
    r = client.put("/api/reglages", json={"libelles": ["Vieux lot"]}).json()["reglages"]
    assert [l["libelle"] for l in r["libelles"]] == ["Vieux lot"]
    assert {l["libelle"] for l in client.get("/api/sources").json()["libelles"]} == {"Vieux lot", "Numérisation"}
    # Lecture seule : les réglages restent modifiables (rien n'est écrit dans Immich)
    m.cfg.lecture_seule = True
    assert client.put("/api/reglages", json={"album_non_datees": "Sans date"}).status_code == 200
    m.cfg.lecture_seule = False


def test_2120_externe_sauvegarde(env, monkeypatch):
    client, _ = env
    assert client.get("/externe/sauvegarde").status_code == 401
    assert client.get("/externe/sauvegarde", headers={"Authorization": "Bearer faux"}).status_code == 401
    r = client.get("/externe/sauvegarde", headers={"Authorization": f"Bearer {JK}"})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    s = r.json()
    from app import __version__
    from app.service import EXCLUS_SAUVEGARDE
    assert s["contrat"] == 1 and s["appli"] == "millesime" and s["version"] == __version__
    assert set(s["reglages"]) == {"tag_prefixe", "synchro_minutes", "album_non_datees", "modele_album", "libelles"}
    assert s["reglages"]["tag_prefixe"] == "Numérisation"
    texte = r.text
    for secret in (MDP, JK, JC, JH, "MAISON_", "MILLESIME_", "/state", "immich_server"):
        assert secret not in texte
    assert not set(EXCLUS_SAUVEGARDE) & set(s["reglages"])
    # sans session : la porte /externe/ ne passe pas par la connexion, et /health reste public
    assert client.get("/health").json()["ok"] is True


class FauxAnneau:
    """Faux Anneau pour lire_sauvegarde : deux sauvegardes."""
    def __init__(self):
        self.panne = None
        self.appels = []
        self.sauvegardes = {
            "2026-11-15": {"le": "2026-11-15T03:00:00+01:00", "version": "2.12.0",
                           "reglages": {"tag_prefixe": "Numérisation", "synchro_minutes": 120,
                                        "album_non_datees": "Non datées Numérisation", "modele_album": "Scans {annee}",
                                        "libelles": [{"libelle": "Vieux lot", "tag_non_datee": "Vieux lot/Non datée",
                                                      "album_non_datees": "Non datées Vieux lot"}],
                                        "jeton_secret": "ne-doit-pas-passer", "session_generation": 9}},
            "2026-11-14": {"le": "2026-11-14T03:00:00+01:00", "version": "2.12.0",
                           "reglages": {"tag_prefixe": "Numérisation", "synchro_minutes": 60,
                                        "album_non_datees": "Non datées Numérisation",
                                        "modele_album": "{annee} Numérisation", "libelles": []}}}

    def __call__(self, adresse, jeton):
        import urllib.error
        self.appels.append((adresse, jeton))
        if self.panne == "reseau":
            raise OSError("Anneau éteint")
        if self.panne == "rien":
            raise urllib.error.HTTPError(adresse, 404, "Not Found", {}, None)
        if "?le=" in adresse:
            le = adresse.split("?le=")[1]
            if le not in self.sauvegardes:
                raise urllib.error.HTTPError(adresse, 404, "Not Found", {}, None)
            return self.sauvegardes[le]
        return {"dates": sorted(self.sauvegardes, reverse=True)}


def test_2120_restaurer(env, monkeypatch):
    client, _ = env
    from app import main
    anneau = FauxAnneau()
    monkeypatch.setattr(main, "LIRE_SAUVEGARDE", anneau)
    assert client.get("/api/restaurer").status_code == 401                  # session requise
    connecter(client)
    client.post("/api/synchroniser")
    assert client.get("/api/restaurer").json() == {"dates": ["2026-11-15", "2026-11-14"]}
    assert anneau.appels[-1] == ("http://anneau:8094/externe/sauvegardes/millesime", JK)
    r = client.get("/api/restaurer?le=2026-11-15").json()
    assert r["version"] == "2.12.0"
    diff = {d["cle"]: (d["actuel"], d["sauve"]) for d in r["differences"]}
    assert set(diff) == {"synchro_minutes", "modele_album", "libelles"}     # ni secret ni clé exclue
    assert diff["synchro_minutes"] == (60, 120)
    assert client.get("/api/restaurer?le=2026-11-14").json()["differences"] == []   # le libellé actuel n'est pas sauvegardé
    # Application (permise en lecture seule : réglages internes seulement)
    main.m().cfg.lecture_seule = True
    r = client.post("/api/restaurer", json={"le": "2026-11-15"})
    main.m().cfg.lecture_seule = False
    assert r.status_code == 200 and sorted(r.json()["appliquees"]) == ["libelles", "modele_album", "synchro_minutes"]
    reg = client.get("/api/reglages").json()["reglages"]
    assert reg["synchro_minutes"] == 120 and reg["modele_album"] == "Scans {annee}"
    assert [l["libelle"] for l in reg["libelles"]] == ["Vieux lot"]
    assert {l["libelle"] for l in client.get("/api/sources").json()["libelles"]} == {"Numérisation", "Vieux lot"}
    assert "jeton_secret" not in reg and main.m().base.lire("session_generation", 0) != 9
    j = client.get("/api/journal").json()[0]
    assert j["action"] == "reglages_restaures" and j["apres"]["le"] == "2026-11-15" and j["avant"]["synchro_minutes"] == 60
    assert client.post(f"/api/journal/{j['id']}/annuler").status_code == 400  # un réglage ne s'annule pas par le journal
    assert client.get("/api/restaurer?le=2026-11-15").json()["differences"] == []
    assert "Rien à changer" in client.post("/api/restaurer", json={"le": "2026-11-15"}).json()["message"]
    assert client.post("/api/restaurer", json={}).status_code == 400
    # Rien à cette date, rien du tout, Anneau injoignable : messages clairs
    r = client.get("/api/restaurer?le=2020-01-01")
    assert r.status_code == 404 and "aucune sauvegarde" in r.json()["detail"]
    anneau.panne = "rien"
    r = client.get("/api/restaurer")
    assert r.status_code == 404 and "aucune sauvegarde" in r.json()["detail"]
    anneau.panne = "reseau"
    for r in (client.get("/api/restaurer"), client.get("/api/restaurer?le=2026-11-14"),
              client.post("/api/restaurer", json={"le": "2026-11-14"})):
        assert r.status_code == 503 and "injoignable" in r.json()["detail"]
    assert client.get("/api/reglages").json()["reglages"]["synchro_minutes"] == 120
    anneau.panne = None
    anneau.sauvegardes = {}
    r = client.get("/api/restaurer")
    assert r.status_code == 404 and "aucune sauvegarde" in r.json()["detail"]


def test_2122_age_infini_refuse(env):
    """2.12.2 (audit du 17/11/2026) : un âge Infinity reçu du PC ne bloque plus les synchronisations."""
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    m = __import__("app.main", fromlist=["m"]).m()
    face = m.base.un("SELECT face_id FROM visages WHERE age_visage IS NULL LIMIT 1")
    if face:
        m.recevoir_resultats([{"face_id": face["face_id"], "age_visage": float("inf")}])
        assert m.base.un("SELECT age_visage, calcule_le FROM visages WHERE face_id=?", face["face_id"])["calcule_le"] == "erreur"


def test_m29_fusion_refusee_notee_en_echec_et_annulation_incomplete_dite(env):
    """M29 (audit du 17/11/2026) : une fusion refusée par Immich n'est pas notée réussie ; une annulation qui ne
    rend pas tous les visages dit lesquels restent."""
    client, E = env
    connecter(client)
    client.post("/api/synchroniser")
    faces = sorted(f["id"] for x in E["assets"].values() for f in x["faces"] if (f["person"] or {}).get("id") == "inconnu1")
    assert len(faces) >= 2
    # Immich répond 200 mais refuse la fusion : erreur, rien n'a changé dans Millésime, le journal le dit
    E["fusion_refusee"] = True
    r = client.post("/api/nommer/inconnu1/fusionner", json={"cible": "mamie"})
    assert r.status_code == 400 and "refusé" in r.json()["detail"]
    assert "inconnu1" in [g["person_id"] for g in client.get("/api/nommer").json()["groupes"]]
    j = next(x for x in client.get("/api/journal").json() if x["action"] == "fusionner")
    assert j["apres"].get("erreur") and not j["annule_le"]
    assert client.post(f"/api/journal/{j['id']}/annuler").json()["ok"]        # rien à défaire : seulement noté
    assert all((f["person"] or {}).get("id") == "inconnu1" for x in E["assets"].values() for f in x["faces"] if f["id"] in faces)
    # Fusion réussie, puis annulation où Immich refuse un visage : l'annulation le dit
    E["fusion_refusee"] = False
    assert client.post("/api/nommer/inconnu1/fusionner", json={"cible": "mamie"}).json()["visages"] == len(faces)
    E["visages_refuses"] = {faces[0]}
    j = next(x for x in client.get("/api/journal").json() if x["action"] == "fusionner" and not x["annule_le"])
    r = client.post(f"/api/journal/{j['id']}/annuler").json()
    assert r["non_defaits"] == [faces[0]] and r["visages"] == len(faces) - 1 and "1 visage" in r["message"]
    assert next(f for x in E["assets"].values() for f in x["faces"] if f["id"] == faces[0])["person"]["id"] == "mamie"
    j = next(x for x in client.get("/api/journal").json() if x["id"] == j["id"])
    assert j["annule_le"] and j["apres"]["non_defaits"] == [faces[0]]


# ------------------------------------------------------------------ 2.13.0 : reçues des invités (dates signalées dans Sillage)

import faux_sillage  # noqa: E402


@pytest.fixture
def sillage(env):
    """Faux Sillage (contrat 1) relié à Millésime par le jeton commun ; scans synchronisés et calculés."""
    client, E = env
    from app import main
    serveur, url, S = faux_sillage.demarrer(JK)
    mm = main.m()
    mm.cfg.jeton_sillage, mm.cfg.sillage_url = JK, url
    connecter(client)
    client.post("/api/synchroniser")
    calculer(client, E)
    yield client, E, S, mm
    serveur.shutdown()


def _ligne(r, asset):
    return next(l for l in r["lignes"] + r["a_confirmer"] if l["asset_id"] == asset)


def test_2130_lecture_et_accepter_une_photo_d_appareil(sillage):
    """Lecture chez Sillage, une ligne par photo, compteur dans À traiter et dans /health ; « Accepter 2015 » passe
    par valider (date, tag ±3 car « environ », journal « avis d'invité », Annuler), puis traite chez Sillage."""
    client, E, S, mm = sillage
    from app import main
    S["avis"] += [faux_sillage.avis("s1", "num2014", 2013, date_affichee="2014-03-01", invites=["Prénom A", "Prénom B"]),
                  faux_sillage.avis("s2", "num2014", 2015, environ=True, mot="mariage d'une cousine", date_affichee="2014-03-01"),
                  faux_sillage.avis("s3", "nd0", 1992)]
    assert client.get("/api/recues").json()["lignes"] == []                     # rien tant qu'on n'a pas lu
    r = client.post("/api/recues/relire").json()
    assert S["requetes"][-1] == ("GET", "/externe/signalements", None)
    assert r["sillage"]["relie"] and r["sillage"]["lu"]["avis"] == 3 and r["sillage"]["erreur"] is None
    l = _ligne(r, "num2014")
    assert l["annees"] == [2013, 2015] and l["date_immich"] == "2014-03-01" and l["estimation"] is None
    assert [a["invites"] for a in l["avis"]] == [["Prénom A", "Prénom B"], ["Prénom A"]] and not l["deja_changee"]
    assert _ligne(r, "nd0")["estimation"]["annee"] is not None
    acc = client.get("/api/accueil").json()
    assert acc["compteurs"]["recues_invites"] == 2 and acc["sillage"]["relie"]
    main.ETAT.pop("sante", None)
    sante = client.get("/health").json()
    c = acc["compteurs"]
    assert sante["recues_invites"] == 2
    assert sante["a_traiter"] == c["a_dater"] + c["a_trancher"] + c["a_nommer"] + c["suspects"] + 2

    # une année qu'aucun invité n'a proposée se corrige, elle ne s'accepte pas
    assert client.post("/api/recues/num2014/accepter", json={"annee": 2010}).status_code == 400
    E["requetes"].clear()
    r = client.post("/api/recues/num2014/accepter", json={"annee": 2015}).json()
    assert r["issue"] == "acceptee" and r["confirme"] and r["tag"] == "Date estimée/2015 ±3"
    tag = next(t["id"] for t in E["tags"].values() if t["value"] == "Date estimée/2015 ±3")
    assert [(m_, c_) for m_, c_, _ in E["requetes"]] == [               # photo d'appareil : date et tag, aucun album
        ("PUT", "/api/assets/num2014"), ("PUT", "/api/tags"), ("PUT", f"/api/tags/{tag}/assets")]
    assert E["assets"]["num2014"]["exifInfo"]["dateTimeOriginal"] == "2015-07-01T12:00:00.000Z"
    assert S["requetes"][-1] == ("POST", "/externe/signalements/traite", {"asset": "num2014", "issue": "acceptee"})
    assert S["traites"] == {"s1": "acceptee", "s2": "acceptee"}                     # tous les avis de la photo
    j = client.get("/api/journal").json()[0]
    assert j["action"] == "valider" and j["asset_id"] == "num2014" and j["apres"]["source"] == "avis d'invité"
    r = client.get("/api/recues").json()
    assert [l["asset_id"] for l in r["lignes"]] == ["nd0"] and r["a_confirmer"] == []
    assert client.get("/api/accueil").json()["compteurs"]["recues_invites"] == 1
    # même Annuler qu'« À dater »
    assert client.post(f"/api/journal/{j['id']}/annuler").json()["ok"]
    assert E["assets"]["num2014"]["exifInfo"]["dateTimeOriginal"] == "2014-03-01T09:00:00.000Z"
    assert "num2014" not in E["tag_assets"][tag]


def test_2130_traite_en_echec_puis_repris_sans_reecrire(sillage):
    """Le POST traite échoue : l'écriture dans Immich est faite une fois, la ligne reste « à confirmer chez Sillage »,
    et la lecture suivante refait seulement le POST."""
    client, E, S, _ = sillage
    S["avis"].append(faux_sillage.avis("s1", "nd0", 1992))
    client.post("/api/recues/relire")
    S["panne_traite"] = True
    r = client.post("/api/recues/nd0/accepter", json={"annee": 1992}).json()
    assert r["confirme"] is False and "à confirmer chez Sillage" in r["message"]
    assert E["assets"]["nd0"]["exifInfo"]["dateTimeOriginal"] == "1992-07-01T12:00:00.000Z"
    r = client.get("/api/recues").json()
    assert r["lignes"] == [] and [l["asset_id"] for l in r["a_confirmer"]] == ["nd0"]
    assert r["a_confirmer"][0]["issue"] == "acceptee" and r["sillage"]["a_confirmer"] == 1
    assert client.get("/api/accueil").json()["compteurs"]["recues_invites"] == 0
    # Sillage revient : la relecture confirme, sans rien réécrire dans Immich
    S["panne_traite"] = False
    E["requetes"].clear()
    S["requetes"].clear()
    r = client.post("/api/recues/relire").json()
    assert S["requetes"] == [("POST", "/externe/signalements/traite", {"asset": "nd0", "issue": "acceptee"}),
                             ("GET", "/externe/signalements", None)]
    assert E["requetes"] == [] and r["a_confirmer"] == [] and r["lignes"] == [] and S["traites"] == {"s1": "acceptee"}
    assert len([j for j in client.get("/api/journal").json() if j["asset_id"] == "nd0"]) == 1


def test_2130_ecarter_et_corriger(sillage):
    """Écarter : seulement traite chez Sillage. Corriger : l'année tapée par Julien, marge 1."""
    client, E, S, _ = sillage
    S["avis"] += [faux_sillage.avis("s1", "nd0", 1970), faux_sillage.avis("s2", "nd2", 1950, environ=True)]
    client.post("/api/recues/relire")
    E["requetes"].clear()
    r = client.post("/api/recues/nd0/ecarter").json()
    assert r["issue"] == "ecartee" and r["confirme"] and E["requetes"] == []
    assert S["traites"] == {"s1": "ecartee"}
    assert client.post("/api/recues/nd0/ecarter").status_code == 400                # plus rien en attente
    r = client.post("/api/recues/nd2/corriger", json={"annee": 1996}).json()
    assert r["issue"] == "corrigee" and r["tag"] == "Date estimée/1996 ±1"
    assert S["traites"]["s2"] == "corrigee"
    assert client.post("/api/recues/nd2/inventer").status_code == 404


def test_2130_tout_accepter_seulement_si_un_avis_concorde(sillage):
    """« Tout accepter » : seulement les lignes à un seul avis, à ±2 ans de l'estimation de Millésime."""
    client, E, S, _ = sillage
    est_ = {a: client.get(f"/api/scans/{a}").json()["annee_proposee"] for a in ("nd0", "nd2", "nd4")}
    assert all(v is not None for v in est_.values())
    S["avis"] += [faux_sillage.avis("s1", "nd0", est_["nd0"] + 2),                              # concorde
                  faux_sillage.avis("s2", "nd2", est_["nd2"] - 9),                              # trop loin
                  faux_sillage.avis("s3", "nd4", est_["nd4"]), faux_sillage.avis("s4", "nd4", est_["nd4"]),   # deux avis
                  faux_sillage.avis("s5", "num2020", 2020)]                                     # pas d'estimation
    r = client.post("/api/recues/relire").json()
    assert {l["asset_id"]: l["tout_accepter"] for l in r["lignes"]} == {
        "nd0": True, "nd2": False, "nd4": False, "num2020": False}
    r = client.post("/api/recues/tout-accepter").json()
    assert r == {"faites": 1, "a_confirmer": 0, "erreurs": []}
    assert E["assets"]["nd0"]["exifInfo"]["dateTimeOriginal"] == f"{est_['nd0'] + 2}-07-01T12:00:00.000Z"
    assert set(S["traites"]) == {"s1"}
    assert {l["asset_id"] for l in client.get("/api/recues").json()["lignes"]} == {"nd2", "nd4", "num2020"}


def test_2130_date_deja_changee_et_mot_echappe(sillage):
    """La date d'Immich a changé depuis l'avis : c'est dit. Le mot libre reste du texte brut (120 caractères),
    affiché échappé : la page n'utilise jamais {@html}."""
    client, E, S, _ = sillage
    mot = "<img src=x onerror=alert(1)> baptême " + "x" * 200
    S["avis"] += [faux_sillage.avis("s1", "num2008", 2007, mot=mot, date_affichee="2005-07-01"),
                  faux_sillage.avis("s2", "num2020", 2019, date_affichee="2020-03-01"),
                  faux_sillage.avis("s3", "nd-remi", 1995, date_affichee=None)]       # « Aidez-moi à dater »
    r = client.post("/api/recues/relire").json()
    l = _ligne(r, "num2008")
    assert l["deja_changee"] and l["avis"][0]["deja_changee"]
    assert l["avis"][0]["mot"] == mot[:120] and l["avis"][0]["mot"].startswith("<img src=x")
    assert not _ligne(r, "num2020")["deja_changee"] and not _ligne(r, "nd-remi")["deja_changee"]
    page = (Path(__file__).resolve().parents[1] / "frontend/src/pages/Recues.svelte").read_text(encoding="utf-8")
    assert "{@html" not in page and "{a.mot}" in page


def test_2130_sillage_injoignable_ou_refuse(sillage):
    """Sillage arrêté, jeton refusé ou contrat inconnu : la dernière lecture reste, le message est dans la tuile.
    Un avis retiré par l'invité (changer d'avis) quitte la liste à la lecture suivante."""
    client, _, S, mm = sillage
    S["avis"] += [faux_sillage.avis("s1", "nd0", 1992), faux_sillage.avis("s2", "nd2", 1996)]
    client.post("/api/recues/relire")
    S["panne"] = True
    r = client.post("/api/recues/relire").json()
    assert len(r["lignes"]) == 2 and "503" in r["sillage"]["erreur"]["detail"]
    assert "503" in client.get("/api/accueil").json()["sillage"]["erreur"]["detail"]
    S["panne"] = False
    S["contrat"] = 2
    r = client.post("/api/recues/relire").json()
    assert len(r["lignes"]) == 2 and "contrat" in r["sillage"]["erreur"]["detail"]
    S["contrat"] = 1
    mm.cfg.jeton_sillage = "autre-jeton"
    assert "jeton refusé" in client.post("/api/recues/relire").json()["sillage"]["erreur"]["detail"]
    mm.cfg.jeton_sillage = JK
    S["avis"] = [a for a in S["avis"] if a["id"] != "s2"]                            # l'invité a changé d'avis
    r = client.post("/api/recues/relire").json()
    assert [l["asset_id"] for l in r["lignes"]] == ["nd0"] and r["sillage"]["erreur"] is None
    url = mm.cfg.sillage_url
    mm.cfg.sillage_url = "http://127.0.0.1:9"                                        # rien n'écoute
    r = client.post("/api/recues/relire").json()
    assert len(r["lignes"]) == 1 and "ne répond pas" in r["sillage"]["erreur"]["detail"]
    mm.cfg.sillage_url = url
    mm.cfg.jeton_sillage = ""                                                         # non relié : rien n'est lu
    S["requetes"].clear()
    assert client.post("/api/recues/relire").json()["sillage"]["relie"] is False and S["requetes"] == []


def test_2130_lecture_seule_gestes_refuses(sillage):
    """Lecture seule : accepter, corriger, écarter et tout accepter sont refusés ; rien chez Sillage ni dans Immich."""
    client, E, S, mm = sillage
    S["avis"].append(faux_sillage.avis("s1", "nd0", 1992))
    client.post("/api/recues/relire")
    mm.cfg.lecture_seule = mm.immich.lecture_seule = True
    E["requetes"].clear()
    S["requetes"].clear()
    for chemin, corps in (("/api/recues/nd0/accepter", {"annee": 1992}), ("/api/recues/nd0/corriger", {"annee": 1990}),
                          ("/api/recues/nd0/ecarter", {}), ("/api/recues/tout-accepter", {})):
        r = client.post(chemin, json=corps)
        assert r.status_code == 409 and "lecture seule" in r.json()["detail"]
    assert E["requetes"] == [] and S["requetes"] == [] and S["traites"] == {}
    assert len(client.post("/api/recues/relire").json()["lignes"]) == 1          # la lecture continue
