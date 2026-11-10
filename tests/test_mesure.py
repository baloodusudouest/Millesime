"""
Tests du test de mesure, contre un faux Immich et un faux Ollama.

- InsightFace : modèle téléchargé une fois dans ~/.cache/millesime
  (ou pris dans MILLESIME_MODELE_LOCAL).
- MiVOLO : testé seulement si MILLESIME_TEST_MIVOLO=1 (téléchargement depuis
  Hugging Face, fait par la CI « mesure-pc »).
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent))
import faux_immich  # noqa: E402
import faux_ollama  # noqa: E402

RACINE = Path(__file__).resolve().parents[1]
SCRIPT = RACINE / "mesure" / "mesure.py"
CACHE = Path(os.environ.get("MILLESIME_CACHE", Path.home() / ".cache" / "millesime"))
MODELE_URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
AVEC_MIVOLO = os.environ.get("MILLESIME_TEST_MIVOLO") == "1"


@pytest.fixture(scope="session")
def modele() -> Path:
    local = os.environ.get("MILLESIME_MODELE_LOCAL")
    if local and Path(local).exists():
        return Path(local)
    cible = CACHE / "genderage.onnx"
    if not cible.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        archive = CACHE / "buffalo_l.zip"
        with requests.get(MODELE_URL, stream=True, timeout=300) as r:
            r.raise_for_status()
            with archive.open("wb") as f:
                for bloc in r.iter_content(chunk_size=1 << 20):
                    f.write(bloc)
        with zipfile.ZipFile(archive) as z:
            cible.write_bytes(z.read(next(n for n in z.namelist() if n.endswith("genderage.onnx"))))
        archive.unlink()
    return cible


def lancer(url: str, data: Path, modele: Path, **env_sup) -> subprocess.CompletedProcess:
    (data / "models").mkdir(parents=True, exist_ok=True)
    if not (data / "models" / "genderage.onnx").exists():
        shutil.copy(modele, data / "models" / "genderage.onnx")
    env = {**os.environ, "IMMICH_URL": url, "IMMICH_API_KEY": faux_immich.CLE,
           "DATA_DIR": str(data), "MAX_SCANS": "50", "MIVOLO": "0", **env_sup}
    return subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True,
                          text=True, timeout=1200)


def lire_rapport(data: Path) -> str:
    return (data / "resultats" / "rapport.md").read_text(encoding="utf-8")


def test_insightface_seul(tmp_path, modele):
    serveur, url, etat = faux_immich.demarrer(stockage_actif=True)
    try:
        p = lancer(url, tmp_path, modele)
    finally:
        serveur.shutdown()
    assert p.returncode == 0, p.stdout + p.stderr
    rapport = lire_rapport(tmp_path)
    assert "InsightFace : ✅" in rapport
    assert "Scans datés analysés : 20" in rapport
    assert "Visages non nommés : 6" in rapport
    assert "1 groupe(s) de visages sans nom" not in rapport  # « Sans Date » a un nom
    assert "- Sans Date" in rapport
    assert "déplace le fichier : **oui**" in rapport
    assert "InsightFace (1er test), sans correction" in rapport
    assert "## 6. Verdict" in rapport
    # Lecture seule : aucune date modifiée, aucune tâche lancée
    assert not etat["jobs"]
    assert all(not a["exifInfo"]["dateTimeOriginal"].startswith("1985") for a in etat["assets"].values())
    for nom in ("visages.csv", "photos.csv", "journal.txt"):
        assert (tmp_path / "resultats" / nom).exists(), nom


def test_vision_locale(tmp_path, modele):
    serveur, url, _ = faux_immich.demarrer()
    ollama, url_ollama, etat_ollama = faux_ollama.demarrer(annee=2006)
    try:
        p = lancer(url, tmp_path, modele, VLM_URL=url_ollama, MAX_PHOTOS_VLM="10")
    finally:
        serveur.shutdown()
        ollama.shutdown()
    assert p.returncode == 0, p.stdout + p.stderr
    rapport = lire_rapport(tmp_path)
    assert "Vision locale : ✅ Ollama OK" in rapport
    assert etat_ollama["appels"] == 10
    assert "10 photos datées sur 10" in rapport
    assert "75 % en mémoire vidéo" in rapport
    assert "Vision locale (photo entière) + borne des naissances" in rapport
    assert "Moyenne vision locale + InsightFace" in rapport
    assert "photos datées par toutes les méthodes" in rapport
    assert (tmp_path / "resultats" / "vlm.csv").exists()


def test_vision_locale_seule_et_reponse_avec_reflexion(tmp_path, modele):
    """Sans InsightFace, avec une réponse précédée d'un bloc <think> : le JSON est quand même lu."""
    serveur, url, _ = faux_immich.demarrer()
    brut = '<think>je regarde les vêtements</think>\n{"annee": 2004, "annee_min": 2000, "annee_max": 2008, "indices": "x"}'
    ollama, url_ollama, _ = faux_ollama.demarrer(reponse_brute=brut)
    try:
        p = lancer(url, tmp_path, modele, VLM_URL=url_ollama, MAX_PHOTOS_VLM="5", INSIGHTFACE="0")
    finally:
        serveur.shutdown()
        ollama.shutdown()
    assert p.returncode == 0, p.stdout + p.stderr
    rapport = lire_rapport(tmp_path)
    assert "5 photos datées sur 5 (0 échec(s))" in rapport
    assert "InsightFace" not in rapport.split("## 2.")[0]


def test_vision_locale_reponse_vide(tmp_path, modele):
    """Réflexion qui remplit le contexte : réponse vide comptée comme échec, le test continue."""
    serveur, url, _ = faux_immich.demarrer()
    ollama, url_ollama, _ = faux_ollama.demarrer(reponse_brute="")
    try:
        p = lancer(url, tmp_path, modele, VLM_URL=url_ollama, MAX_PHOTOS_VLM="4")
    finally:
        serveur.shutdown()
        ollama.shutdown()
    assert p.returncode == 0, p.stdout + p.stderr
    assert "0 photos datées sur 4 (4 échec(s))" in lire_rapport(tmp_path)
    assert "réponse vide (réflexion de 50 caractères" in p.stdout


def test_modele_vlm_absent(tmp_path, modele):
    serveur, url, _ = faux_immich.demarrer()
    ollama, url_ollama, etat_ollama = faux_ollama.demarrer(modele="llava:7b")
    try:
        p = lancer(url, tmp_path, modele, VLM_URL=url_ollama)
    finally:
        serveur.shutdown()
        ollama.shutdown()
    assert p.returncode == 0, p.stdout + p.stderr
    assert "ollama pull qwen3-vl:8b-instruct" in lire_rapport(tmp_path)
    assert etat_ollama["appels"] == 0


def test_ne_se_relance_pas(tmp_path, modele):
    serveur, url, _ = faux_immich.demarrer()
    try:
        assert lancer(url, tmp_path, modele).returncode == 0
        p = lancer(url, tmp_path, modele)
        assert p.returncode == 0 and "Test déjà fait" in p.stdout
        p = lancer(url, tmp_path, modele, MILLESIME_TEST_FORCER="1")
        assert "Test déjà fait" not in p.stdout
    finally:
        serveur.shutdown()


def test_coupure_immich_reessayee(tmp_path, modele):
    """Immich répond 503 aux deux premiers appels : le test réessaie et va au bout."""
    serveur, url, etat = faux_immich.demarrer(pannes=2)
    try:
        p = lancer(url, tmp_path, modele, MAX_SCANS="10")
    finally:
        serveur.shutdown()
    assert p.returncode == 0, p.stdout + p.stderr
    assert "nouvel essai dans 2 s (1/4)" in p.stdout
    assert "Scans datés analysés : 10" in lire_rapport(tmp_path)


def test_cle_refusee(tmp_path, modele):
    serveur, url, _ = faux_immich.demarrer()
    try:
        p = lancer(url, tmp_path, modele, IMMICH_API_KEY="mauvaise")
    finally:
        serveur.shutdown()
    assert p.returncode != 0


@pytest.mark.skipif(not AVEC_MIVOLO, reason="MiVOLO testé seulement dans la CI mesure-pc (MILLESIME_TEST_MIVOLO=1)")
def test_mivolo(tmp_path, modele):
    serveur, url, _ = faux_immich.demarrer()
    try:
        p = lancer(url, tmp_path, modele, MIVOLO="1", MAX_SCANS="20", REFS_PAR_PERSONNE="3")
    finally:
        serveur.shutdown()
    assert p.returncode == 0, p.stdout + p.stderr
    rapport = lire_rapport(tmp_path)
    assert "MiVOLO : ✅" in rapport, rapport
    assert "MiVOLO v2, visage seul — scans" in rapport
    assert "MiVOLO v2, visage + buste estimé — scans" in rapport
    assert "erreur(s)" not in rapport.split("## 4.")[0], rapport
