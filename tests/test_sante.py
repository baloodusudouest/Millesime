"""2.14.0 : santé des tâches de fond et copie de la base dans /health (socle 0.9.0)."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import faux_sillage  # noqa: E402

from test_app import JK, MDP, env, sans_variables_maison  # noqa: E402,F401 (fixtures)


def _sante(client, **kw):
    """/health, en laissant à la boucle de copie le temps de lire son état de départ (tâche lancée au démarrage)."""
    for _ in range(50):
        j = client.get("/health", **kw).json()
        if j["copie_base"] and j["copie_base"]["bases"] == ["millesime.db"]:
            return j
        time.sleep(0.02)
    return j


def test_health_porte_la_sante_des_taches_et_la_copie(env):  # noqa: F811
    client, _ = env
    j = _sante(client)
    assert j["ok"] is True and "a_traiter" in j                                  # rien d'existant ne change
    assert j["version_socle"] == "0.9.1"
    taches = {t["nom"]: t for t in j["taches"]}
    assert {"synchro-immich", "lecture-sillage", "synchro-complete", "copie-des-bases"} <= set(taches)
    assert taches["synchro-immich"]["type"] == "reguliere" and taches["synchro-immich"]["periode_s"] >= 300
    assert taches["lecture-sillage"]["type"] == "reguliere" and taches["lecture-sillage"]["periode_s"] == 900
    assert taches["synchro-complete"]["type"] == "demande"
    assert taches["copie-des-bases"]["periode_s"] == 86400
    assert j["copie_base"]["bases"] == ["millesime.db"] and j["copie_base"]["le"] is None   # pas encore de nuit
    assert all("message" not in t for t in j["taches"])                          # sans jeton : pas de message
    assert all("message" in t for t in client.get("/health", headers={"Authorization": f"Bearer {JK}"}).json()["taches"])
    assert all("message" not in t for t in client.get("/health", headers={"Authorization": "Bearer faux"}).json()["taches"])
    assert client.post("/api/connexion", json={"mot_de_passe": MDP}).status_code == 200
    assert all("message" in t for t in client.get("/health").json()["taches"])  # session valide


def test_sillage_muet_met_la_lecture_en_retard(env, monkeypatch):  # noqa: F811
    """La boucle de 15 min chez Sillage : Sillage en panne → tour raté (lire_sillage garde l'erreur pour lui,
    comme avant) → « en_retard » ; Sillage revenu → « ok »."""
    client, _ = env
    from app import main, maison
    taches = maison.Taches()
    monkeypatch.setattr(maison, "TACHES", taches)
    taches.declarer(main.TACHE_SILLAGE, periode_s=main.SILLAGE_MINUTES * 60)
    serveur, url, S = faux_sillage.demarrer(JK)
    try:
        mm = main.m()
        mm.cfg.jeton_sillage, mm.cfg.sillage_url = JK, url
        S["panne"] = True

        def un_tour():
            stop = threading.Event()
            fil = threading.Thread(target=main._boucle_sillage, args=(stop,), daemon=True)
            avant = len(S["requetes"])
            fil.start()
            for _ in range(250):
                if len(S["requetes"]) > avant and taches.etat()[0]["dernier_essai"] and not taches._taches[main.TACHE_SILLAGE]["en_cours"]:
                    break
                time.sleep(0.02)
            stop.set()
            fil.join(5)

        un_tour()
        etat = taches.etat(avec_messages=True)[0]
        assert etat["etat"] == "en_retard" and etat["derniere_erreur"] and etat["derniere_reussite"] is None
        assert "503" in etat["message"]
        assert "503" in mm.etat_sillage()["erreur"]["detail"]             # toujours noté comme avant
        S["panne"] = False
        un_tour()
        assert taches.etat()[0]["etat"] == "ok"
    finally:
        serveur.shutdown()
