"""
Tests du test de mesure, contre le faux Immich (tests/faux_immich.py).

Le modèle genderage.onnx est téléchargé une fois dans ~/.cache/millesime
(ou pris dans MILLESIME_MODELE_LOCAL s'il est fourni), puis copié dans le
dossier de données de chaque test.
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

RACINE = Path(__file__).resolve().parents[1]
SCRIPT = RACINE / "mesure" / "mesure.py"
CACHE = Path(os.environ.get("MILLESIME_CACHE", Path.home() / ".cache" / "millesime"))
MODELE_URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"


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
           "DATA_DIR": str(data), "MAX_SCANS": "50", **env_sup}
    return subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True,
                          text=True, timeout=600)


def test_mesure_complete(tmp_path, modele):
    serveur, url, etat = faux_immich.demarrer()
    try:
        p = lancer(url, tmp_path, modele)
    finally:
        serveur.shutdown()
    assert p.returncode == 0, p.stdout + p.stderr
    rapport = (tmp_path / "resultats" / "rapport.md").read_text(encoding="utf-8")
    assert "Inférence : ✅" in rapport
    assert "Scans datés analysés : 20" in rapport
    assert "Visages non nommés : 6" in rapport
    assert "Sans Date (`p3`)" in rapport
    assert "## 6. Verdict" in rapport
    # Test d'écriture : fait, tenu après ré-extraction, date d'origine remise
    assert "Écriture de la date : ✅" in rapport
    assert "Date d'origine restaurée : ✅" in rapport
    assert etat["jobs"] and etat["jobs"][0]["name"] == "refresh-metadata"
    nd = etat["assets"]["nd-2"]["exifInfo"]["dateTimeOriginal"]
    assert nd.startswith("1900-01-01"), "la photo test n'a pas retrouvé sa date"
    # Seule la photo test a été touchée
    touchees = [a for a in etat["assets"].values()
                if a["id"] != "nd-2" and a["exifInfo"]["dateTimeOriginal"].startswith("1985")]
    assert not touchees
    for nom in ("visages.csv", "photos.csv", "journal.txt", "sauvegarde_date_test.json"):
        assert (tmp_path / "resultats" / nom).exists(), nom


def test_ne_se_relance_pas(tmp_path, modele):
    serveur, url, etat = faux_immich.demarrer()
    try:
        assert lancer(url, tmp_path, modele).returncode == 0
        nb_jobs = len(etat["jobs"])
        p = lancer(url, tmp_path, modele)
        assert p.returncode == 0
        assert "Test déjà fait" in p.stdout
        assert len(etat["jobs"]) == nb_jobs, "la deuxième passe ne doit rien écrire"
        p = lancer(url, tmp_path, modele, MILLESIME_TEST_FORCER="1")
        assert "Test déjà fait" not in p.stdout
    finally:
        serveur.shutdown()


def test_stockage_par_date_bloque_l_ecriture(tmp_path, modele):
    serveur, url, etat = faux_immich.demarrer(stockage_actif=True)
    try:
        p = lancer(url, tmp_path, modele)
    finally:
        serveur.shutdown()
    assert p.returncode == 0, p.stdout + p.stderr
    rapport = (tmp_path / "resultats" / "rapport.md").read_text(encoding="utf-8")
    assert "déplace le fichier : **OUI" in rapport
    assert "range par date" in rapport
    assert not etat["jobs"]
    assert all(not a["exifInfo"]["dateTimeOriginal"].startswith("1985") for a in etat["assets"].values())


def test_cle_refusee(tmp_path, modele):
    serveur, url, _ = faux_immich.demarrer()
    try:
        p = lancer(url, tmp_path, modele, IMMICH_API_KEY="mauvaise")
    finally:
        serveur.shutdown()
    assert p.returncode != 0
