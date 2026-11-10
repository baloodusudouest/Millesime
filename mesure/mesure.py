#!/usr/bin/env python3
"""
Millésime — test de mesure (avant tout développement de l'appli).

But : mesurer si un modèle d'âge local (genderage.onnx d'InsightFace) est assez
précis sur TES scans pour aider à dater des photos, et vérifier les points
bloquants côté Immich.

Ce que fait le script :
  1. Vérifie le CPU (AVX ou non) et que onnxruntime tourne dessus.
  2. Lit le modèle de stockage Immich (déplacement de fichiers ?).
  3. Prend les scans tagués « <TAG_PREFIXE>/AAAA-MM » (date du tampon = vérité),
     estime l'âge de chaque visage nommé ayant une date de naissance.
  4. Fait de même sur des photos numériques datées (EXIF) des mêmes personnes,
     pour voir si une correction apprise sur le numérique vaut pour les scans.
  5. Calcule l'erreur par visage et par photo, écrit des CSV et un rapport.
  6. (Option) Teste l'écriture de la date sur UNE photo « Non datée », vérifie
     qu'elle tient après une ré-extraction des métadonnées, puis la restaure.

Seule écriture dans Immich : l'étape 6, sur une seule photo, restaurée à la fin.
Tout le reste est en lecture seule.

Le test ne tourne qu'une fois : si resultats/rapport.md existe déjà, le conteneur
s'arrête aussitôt (une mise à jour de la stack ne le relance donc pas).
Pour le relancer : MILLESIME_TEST_FORCER=1, ou supprimer rapport.md.
"""

__version__ = "0.1.0"

import csv
import json
import os
import re
import statistics
import subprocess
import sys
import time
import zipfile
from collections import defaultdict
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import requests
from PIL import Image

# --------------------------------------------------------------------------
# Configuration (variables d'environnement du compose)
# --------------------------------------------------------------------------
IMMICH_URL = os.environ.get("IMMICH_URL", "http://immich_server:2283").rstrip("/")
API_KEY = os.environ.get("IMMICH_API_KEY", "")
TAG_PREFIXE = os.environ.get("TAG_PREFIXE", "Numérisation")
TAG_NON_DATEE = os.environ.get("TAG_NON_DATEE", "Non datée")
MAX_SCANS = int(os.environ.get("MAX_SCANS", "300"))
REFS_PAR_PERSONNE = int(os.environ.get("REFS_PAR_PERSONNE", "15"))
TEST_ECRITURE = os.environ.get("TEST_ECRITURE", "1") == "1"
THREADS = int(os.environ.get("THREADS", "2"))
FORCER = os.environ.get("MILLESIME_TEST_FORCER", "0") == "1"
WORK = Path(os.environ.get("DATA_DIR", "/data"))
MODELE_URL = os.environ.get(
    "MODELE_URL",
    "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
)

OUT = WORK / "resultats"
MODELS = WORK / "models"
MODELE = MODELS / "genderage.onnx"
JOURNAL = OUT / "journal.txt"

# Seuils de décision (erreur médiane absolue par photo, en années)
SEUIL_UTILE = 3.0
SEUIL_ABANDON = 5.0
VISAGE_PETIT_PX = 40

TRANCHES = [(0, 12, "0-12 ans"), (13, 25, "13-25 ans"), (26, 50, "26-50 ans"), (51, 200, "51 ans et +")]


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------
def log(msg: str) -> None:
    """Affiche dans les logs Portainer et garde une trace dans journal.txt."""
    ligne = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(ligne, flush=True)
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(ligne + "\n")


session = requests.Session()
session.headers.update({"x-api-key": API_KEY, "Accept": "application/json"})


def api(methode: str, chemin: str, **kw):
    """Appel à l'API Immich ; renvoie le JSON (ou None si réponse vide)."""
    r = session.request(methode, f"{IMMICH_URL}/api{chemin}", timeout=60, **kw)
    r.raise_for_status()
    if not r.content:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def parse_date(valeur):
    """Transforme une date ISO Immich (avec ou sans heure) en objet date."""
    if not valeur:
        return None
    try:
        return datetime.fromisoformat(str(valeur).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(valeur)[:10])
        except ValueError:
            return None


def annee_decimale(d: date) -> float:
    return d.year + (d.timetuple().tm_yday - 1) / 365.25


def age_exact(naissance: date, le: date) -> float:
    return (le - naissance).days / 365.25


def tranche(age: float) -> str:
    for mini, maxi, nom in TRANCHES:
        if mini <= age < maxi + 1:
            return nom
    return TRANCHES[-1][2]


def mediane(valeurs):
    return statistics.median(valeurs) if valeurs else float("nan")


def stats_erreurs(ecarts):
    """Résumé d'une liste d'écarts signés (estimé − vrai), en années."""
    if not ecarts:
        return {"n": 0}
    absolus = [abs(e) for e in ecarts]
    return {
        "n": len(ecarts),
        "biais_median": round(mediane(ecarts), 1),
        "erreur_mediane": round(mediane(absolus), 1),
        "erreur_moyenne": round(statistics.mean(absolus), 1),
        "pct_2ans": round(100 * sum(a <= 2 for a in absolus) / len(absolus)),
        "pct_3ans": round(100 * sum(a <= 3 for a in absolus) / len(absolus)),
        "pct_5ans": round(100 * sum(a <= 5 for a in absolus) / len(absolus)),
    }


# --------------------------------------------------------------------------
# Étape 0 : CPU et modèle
# --------------------------------------------------------------------------
def info_cpu() -> dict:
    modele, flags = "inconnu", []
    try:
        for ligne in Path("/proc/cpuinfo").read_text().splitlines():
            if ligne.startswith("model name") and modele == "inconnu":
                modele = ligne.split(":", 1)[1].strip()
            if ligne.startswith("flags") and not flags:
                flags = ligne.split(":", 1)[1].split()
    except OSError:
        pass
    return {"modele": modele, "avx": "avx" in flags, "avx2": "avx2" in flags}


def telecharger_modele() -> None:
    """Télécharge buffalo_l.zip une seule fois et n'en garde que genderage.onnx."""
    if MODELE.exists():
        log(f"Modèle déjà présent : {MODELE}")
        return
    MODELS.mkdir(parents=True, exist_ok=True)
    zip_path = MODELS / "buffalo_l.zip"
    log("Téléchargement du modèle (archive ~280 Mo, une seule fois)…")
    with requests.get(MODELE_URL, stream=True, timeout=120) as r:
        r.raise_for_status()
        with zip_path.open("wb") as f:
            for bloc in r.iter_content(chunk_size=1 << 20):
                f.write(bloc)
    with zipfile.ZipFile(zip_path) as z:
        membre = next(n for n in z.namelist() if n.endswith("genderage.onnx"))
        MODELE.write_bytes(z.read(membre))
    zip_path.unlink()
    log(f"Modèle extrait : {MODELE} ({MODELE.stat().st_size // 1024} Ko)")


def test_onnxruntime() -> tuple[bool, str]:
    """
    Lance une inférence factice dans un sous-processus : si le CPU ne supporte
    pas une instruction (sans AVX), le sous-processus meurt (SIGILL) sans tuer
    le script, qui peut alors l'écrire dans le rapport.
    """
    code = (
        "import onnxruntime as o, numpy as np;"
        f"s=o.InferenceSession(r'{MODELE}', providers=['CPUExecutionProvider']);"
        "i=s.get_inputs()[0];"
        "s.run(None,{i.name: np.zeros((1,3,96,96),dtype=np.float32)});"
        "print(o.__version__)"
    )
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if p.returncode == 0:
        return True, f"onnxruntime {p.stdout.strip()} OK"
    if p.returncode == -4:
        return False, "onnxruntime a planté (instruction CPU illégale, probablement AVX manquant)"
    return False, f"onnxruntime en échec (code {p.returncode}) : {p.stderr.strip()[-400:]}"


class ModeleAge:
    """Modèle genderage d'InsightFace : visage 96×96 → âge estimé."""

    def __init__(self, chemin: Path):
        import onnxruntime as ort

        # genderage.onnx (buffalo_l) normalise lui-même l'image : ses deux premiers
        # nœuds sont _minusscalar0 (Sub) et _mulscalar0 (Mul). On lui donne donc
        # les pixels bruts 0-255, en RGB, comme InsightFace (swapRB=True).
        self.moyenne, self.ecart = 0.0, 1.0

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = THREADS
        opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(chemin), opts, providers=["CPUExecutionProvider"])
        entree = self.session.get_inputs()[0]
        self.nom_entree = entree.name
        self.taille = int(entree.shape[2]) if isinstance(entree.shape[2], int) else 96

    def age(self, visage_rgb: Image.Image) -> float:
        tableau = np.asarray(visage_rgb.convert("RGB"), dtype=np.float32)
        tableau = (tableau - self.moyenne) / self.ecart
        blob = tableau.transpose(2, 0, 1)[None, ...]
        sortie = self.session.run(None, {self.nom_entree: blob})[0][0]
        return float(sortie[2] * 100.0)


def recadrer(image: Image.Image, face: dict, taille: int):
    """Recadre l'aperçu sur la boîte du visage (marge ×1,5, carré) et redimensionne."""
    sx = image.width / max(1, face.get("imageWidth") or image.width)
    sy = image.height / max(1, face.get("imageHeight") or image.height)
    x1, y1 = face["boundingBoxX1"] * sx, face["boundingBoxY1"] * sy
    x2, y2 = face["boundingBoxX2"] * sx, face["boundingBoxY2"] * sy
    cote_visage = max(x2 - x1, y2 - y1)
    cote = cote_visage * 1.5
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    boite = tuple(int(round(v)) for v in (cx - cote / 2, cy - cote / 2, cx + cote / 2, cy + cote / 2))
    # PIL complète en noir ce qui dépasse de l'image
    return image.crop(boite).resize((taille, taille), Image.BILINEAR), cote_visage


# --------------------------------------------------------------------------
# Accès Immich
# --------------------------------------------------------------------------
def verifier_stockage() -> dict:
    """Lit le modèle de stockage (nécessite une clé admin)."""
    try:
        cfg = api("GET", "/system-config")
    except requests.HTTPError as e:
        return {"lisible": False, "detail": f"lecture impossible ({e.response.status_code}) : clé sans droit admin ?"}
    st = (cfg or {}).get("storageTemplate", {})
    modele = st.get("template", "")
    date_dans_modele = bool(re.search(r"\{\{\s*(y|M|d|w|W)", modele))
    return {
        "lisible": True,
        "actif": bool(st.get("enabled")),
        "modele": modele,
        "deplace_fichiers": bool(st.get("enabled")) and date_dans_modele,
    }


def rechercher(filtres: dict, limite: int) -> list:
    """Recherche paginée /search/metadata."""
    resultats, page = [], 1
    while len(resultats) < limite:
        corps = {**filtres, "page": page, "size": min(250, limite), "withExif": True, "type": "IMAGE"}
        rep = api("POST", "/search/metadata", json=corps)
        bloc = (rep or {}).get("assets", {})
        resultats += bloc.get("items", [])
        suivante = bloc.get("nextPage")
        if not suivante:
            break
        page = int(suivante)
    return resultats[:limite]


def tags_numerisation():
    """Sépare les tags datés (…/AAAA-MM) du tag « Non datée »."""
    dates, non_datee = [], None
    for t in api("GET", "/tags") or []:
        valeur = t.get("value") or t.get("name") or ""
        if not valeur.startswith(TAG_PREFIXE + "/"):
            continue
        suffixe = valeur[len(TAG_PREFIXE) + 1:]
        if suffixe == TAG_NON_DATEE:
            non_datee = t
            continue
        m = re.fullmatch(r"(\d{4})-(\d{2})(?:-(\d{2}))?", suffixe)
        if m:
            jour = int(m.group(3)) if m.group(3) else 15  # milieu du mois si jour inconnu
            dates.append((t, date(int(m.group(1)), int(m.group(2)), jour)))
    return dates, non_datee


cache_apercus: dict = {}


def apercu(asset_id: str) -> Image.Image:
    if asset_id not in cache_apercus:
        r = session.get(f"{IMMICH_URL}/api/assets/{asset_id}/thumbnail",
                        params={"size": "preview"}, timeout=60)
        r.raise_for_status()
        cache_apercus.clear()  # un seul aperçu en mémoire à la fois
        cache_apercus[asset_id] = Image.open(BytesIO(r.content)).convert("RGB")
    return cache_apercus[asset_id]


def visages(asset_id: str) -> list:
    return api("GET", "/faces", params={"id": asset_id}) or []


# --------------------------------------------------------------------------
# Mesures
# --------------------------------------------------------------------------
def mesurer_asset(modele, asset_id, date_vraie, domaine, compteurs, sans_naissance,
                  personnes_vues, seulement_personne=None):
    """Estime l'âge de chaque visage nommé d'un asset ; renvoie les lignes CSV."""
    lignes = []
    for f in visages(asset_id):
        personne = f.get("person")
        if not personne:
            compteurs["visages_non_nommes"] += 1
            continue
        if seulement_personne and personne["id"] != seulement_personne:
            continue
        naissance = parse_date(personne.get("birthDate"))
        if not naissance:
            sans_naissance[personne["id"]] = personne.get("name") or "(sans nom)"
            compteurs["visages_sans_naissance"] += 1
            continue
        age_vrai = age_exact(naissance, date_vraie)
        if age_vrai < 0:
            compteurs["visages_avant_naissance"] += 1  # visage mal attribué ou date fausse
            continue
        debut = time.perf_counter()
        crop, cote_px = recadrer(apercu(asset_id), f, modele.taille)
        age_est = modele.age(crop)
        compteurs["temps_inference"] += time.perf_counter() - debut
        compteurs["visages_mesures"] += 1
        personnes_vues[personne["id"]] = (personne.get("name") or "(sans nom)", naissance)
        lignes.append({
            "domaine": domaine,
            "asset_id": asset_id,
            "personne": personne.get("name") or "(sans nom)",
            "personne_id": personne["id"],
            "naissance": naissance.isoformat(),
            "date_vraie": date_vraie.isoformat(),
            "age_vrai": round(age_vrai, 1),
            "age_estime": round(age_est, 1),
            "ecart": round(age_est - age_vrai, 1),
            "tranche": tranche(age_vrai),
            "visage_px": int(cote_px),
            "annee_naissance_dec": round(annee_decimale(naissance), 3),
            "annee_vraie_dec": round(annee_decimale(date_vraie), 3),
        })
    return lignes


def estimation_photos(lignes_scans, correction):
    """Fusionne les visages d'une photo (médiane) et compare à l'année vraie."""
    par_photo = defaultdict(list)
    for l in lignes_scans:
        par_photo[l["asset_id"]].append(l)
    ecarts, detail = [], []
    for asset_id, ls in par_photo.items():
        annees = [l["annee_naissance_dec"] + l["age_estime"] - correction(l) for l in ls]
        est = mediane(annees)
        vraie = ls[0]["annee_vraie_dec"]
        ecarts.append(est - vraie)
        detail.append({"asset_id": asset_id, "nb_visages": len(ls),
                       "annee_vraie": round(vraie, 1), "annee_estimee": round(est, 1),
                       "ecart": round(est - vraie, 1)})
    return ecarts, detail


# --------------------------------------------------------------------------
# Test d'écriture (une seule photo, restaurée)
# --------------------------------------------------------------------------
def test_ecriture(non_datee_tag, stockage) -> dict:
    if not TEST_ECRITURE:
        return {"fait": False, "detail": "désactivé (TEST_ECRITURE=0)"}
    if not stockage.get("lisible"):
        return {"fait": False, "detail": "modèle de stockage illisible : test sauté par prudence"}
    if stockage.get("deplace_fichiers"):
        return {"fait": False, "detail": "le modèle de stockage range par date : écrire déplacerait le fichier, test sauté"}
    if not non_datee_tag:
        return {"fait": False, "detail": f"aucun tag « {TAG_PREFIXE}/{TAG_NON_DATEE} » trouvé"}

    # Choix : un scan Non daté, avec une date d'origine, sans visage nommé si possible
    candidats = rechercher({"tagIds": [non_datee_tag["id"]]}, 30)
    choisi = None
    for a in candidats:
        if not (a.get("exifInfo") or {}).get("dateTimeOriginal"):
            continue
        if not any(f.get("person") for f in visages(a["id"])):
            choisi = a
            break
        choisi = choisi or a
    if not choisi:
        return {"fait": False, "detail": "aucun scan Non daté avec une date d'origine exploitable"}

    asset_id = choisi["id"]
    origine = api("GET", f"/assets/{asset_id}")["exifInfo"]["dateTimeOriginal"]
    (OUT / "sauvegarde_date_test.json").write_text(
        json.dumps({"asset_id": asset_id, "dateTimeOriginal": origine}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    log(f"Test d'écriture sur {asset_id} (date d'origine sauvegardée : {origine})")

    valeur_test = "1985-07-01T12:00:00.000Z"
    res = {"fait": True, "asset_id": asset_id, "date_origine": origine}
    try:
        api("PUT", f"/assets/{asset_id}", json={"dateTimeOriginal": valeur_test})
        time.sleep(3)
        lue = api("GET", f"/assets/{asset_id}")["exifInfo"].get("dateTimeOriginal")
        res["ecriture_ok"] = str(lue).startswith("1985-07-01")
        res["date_lue_apres_ecriture"] = lue

        # Ré-extraction des métadonnées : la date tient-elle ?
        try:
            api("POST", "/assets/jobs", json={"assetIds": [asset_id], "name": "refresh-metadata"})
            res["reextraction_lancee"] = True
        except requests.HTTPError as e:
            res["reextraction_lancee"] = False
            res["reextraction_erreur"] = str(e.response.status_code)
        lue = None
        for _ in range(12):  # jusqu'à 60 s
            time.sleep(5)
            lue = api("GET", f"/assets/{asset_id}")["exifInfo"].get("dateTimeOriginal")
        res["date_lue_apres_reextraction"] = lue
        res["tient_apres_reextraction"] = str(lue).startswith("1985-07-01")
    finally:
        try:
            api("PUT", f"/assets/{asset_id}", json={"dateTimeOriginal": origine})
            time.sleep(3)
            lue = api("GET", f"/assets/{asset_id}")["exifInfo"].get("dateTimeOriginal")
            res["restauree"] = parse_date(lue) == parse_date(origine)
            res["date_lue_apres_restauration"] = lue
        except Exception as e:  # noqa: BLE001
            res["restauree"] = False
            res["erreur_restauration"] = str(e)
            log(f"⚠️ Restauration à faire à la main : voir sauvegarde_date_test.json ({e})")
    return res


# --------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------
def ecrire_csv(chemin: Path, lignes: list) -> None:
    if not lignes:
        return
    with chemin.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(lignes)


def tableau_stats(titre: str, s: dict) -> str:
    if not s.get("n"):
        return f"| {titre} | 0 | – | – | – | – | – |"
    return (f"| {titre} | {s['n']} | {s['biais_median']:+} | {s['erreur_mediane']} | "
            f"{s['pct_2ans']} % | {s['pct_3ans']} % | {s['pct_5ans']} % |")


def verdict(erreur: float) -> str:
    if erreur != erreur:  # NaN
        return "❔ Pas assez de données pour conclure."
    if erreur < SEUIL_UTILE:
        return f"✅ Modèle utile : erreur médiane {erreur} an(s) < {SEUIL_UTILE}. Il peut servir d'indice affiché."
    if erreur <= SEUIL_ABANDON:
        return f"🟠 Indice faible : erreur médiane {erreur} ans. À n'afficher qu'à titre indicatif, l'écran de comparaison fait le travail."
    return f"❌ Modèle inutile : erreur médiane {erreur} ans > {SEUIL_ABANDON}. V1 sans modèle (écran de comparaison seul)."


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "rapport.md").exists() and not FORCER:
        print(f"Test déjà fait : {OUT / 'rapport.md'} existe. "
              "Pour le relancer : MILLESIME_TEST_FORCER=1 ou supprimer rapport.md.", flush=True)
        return 0
    JOURNAL.write_text("", encoding="utf-8")
    try:
        os.nice(10)  # priorité basse pour ne pas gêner Plex et la VM HA
    except OSError:
        pass
    if not API_KEY:
        log("❌ IMMICH_API_KEY manquante.")
        return 1

    rapport = ["# Millésime — rapport du test de mesure", "",
               f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} (version {__version__})", ""]

    # 0. CPU + onnxruntime
    cpu = info_cpu()
    log(f"CPU : {cpu['modele']} — AVX : {'oui' if cpu['avx'] else 'non'}")
    telecharger_modele()
    ok, detail = test_onnxruntime()
    log(detail)
    rapport += ["## 1. Matériel", "",
                f"- CPU : {cpu['modele']} (AVX : {'oui' if cpu['avx'] else 'non'}, AVX2 : {'oui' if cpu['avx2'] else 'non'})",
                f"- Inférence : {'✅' if ok else '❌'} {detail}", ""]
    if not ok:
        (OUT / "rapport.md").write_text("\n".join(rapport), encoding="utf-8")
        log("Arrêt : le modèle ne tourne pas sur ce CPU. Voir rapport.md.")
        return 1
    modele = ModeleAge(MODELE)

    # 1. Immich + stockage
    version = api("GET", "/server/version") or {}
    log(f"Immich {version.get('major')}.{version.get('minor')}.{version.get('patch')} joignable")
    stockage = verifier_stockage()
    log(f"Modèle de stockage : {stockage}")
    rapport += ["## 2. Immich", "",
                f"- Version : {version.get('major')}.{version.get('minor')}.{version.get('patch')}"]
    if stockage["lisible"]:
        rapport += [f"- Modèle de stockage : {'actif' if stockage['actif'] else 'inactif'} — `{stockage['modele'] or '—'}`",
                    f"- Changer une date déplace le fichier : **{'OUI ⚠️ (bloquant)' if stockage['deplace_fichiers'] else 'non'}**"]
    else:
        rapport += [f"- Modèle de stockage : {stockage['detail']}"]
    rapport.append("")

    # 2. Scans datés par tampon
    tags_dates, tag_non_datee = tags_numerisation()
    log(f"{len(tags_dates)} tags datés « {TAG_PREFIXE}/AAAA-MM » trouvés")
    compteurs = defaultdict(float)
    sans_naissance, personnes_vues = {}, {}
    ids_scans, scans = set(), []
    for tag, d in tags_dates:
        for a in rechercher({"tagIds": [tag["id"]]}, 5000):
            if a["id"] not in ids_scans:
                ids_scans.add(a["id"])
                scans.append((a["id"], d))
    if tag_non_datee:
        for a in rechercher({"tagIds": [tag_non_datee["id"]]}, 20000):
            ids_scans.add(a["id"])
    # Échantillon réparti sur toutes les périodes
    scans.sort(key=lambda x: x[1])
    if len(scans) > MAX_SCANS:
        pas = len(scans) / MAX_SCANS
        scans = [scans[int(i * pas)] for i in range(MAX_SCANS)]
    log(f"{len(scans)} scans datés à analyser")

    lignes_scans = []
    for i, (asset_id, d) in enumerate(scans, 1):
        try:
            lignes_scans += mesurer_asset(modele, asset_id, d, "scan", compteurs, sans_naissance, personnes_vues)
        except requests.HTTPError as e:
            log(f"  asset {asset_id} ignoré ({e.response.status_code})")
        if i % 25 == 0:
            log(f"  {i}/{len(scans)} scans traités, {int(compteurs['visages_mesures'])} visages mesurés")

    # 3. Photos numériques des mêmes personnes
    lignes_num = []
    for pid, (nom, naissance) in list(personnes_vues.items()):
        try:
            candidats = [a for a in rechercher({"personIds": [pid]}, 400)
                         if a["id"] not in ids_scans
                         and parse_date((a.get("exifInfo") or {}).get("dateTimeOriginal") or a.get("localDateTime"))]
        except requests.HTTPError as e:
            log(f"  recherche des photos de {nom} impossible ({e.response.status_code})")
            continue
        candidats.sort(key=lambda a: a.get("localDateTime") or "")
        if len(candidats) > REFS_PAR_PERSONNE:
            pas = len(candidats) / REFS_PAR_PERSONNE
            candidats = [candidats[int(i * pas)] for i in range(REFS_PAR_PERSONNE)]
        for a in candidats:
            d = parse_date(a.get("localDateTime") or a["exifInfo"]["dateTimeOriginal"])
            try:
                lignes_num += mesurer_asset(modele, a["id"], d, "numerique", compteurs,
                                            sans_naissance, {}, seulement_personne=pid)
            except requests.HTTPError:
                continue
        log(f"  références numériques : {nom} traité")

    ecrire_csv(OUT / "visages.csv", lignes_scans + lignes_num)

    # 4. Analyse
    ecarts_scan = [l["ecart"] for l in lignes_scans]
    ecarts_num = [l["ecart"] for l in lignes_num]
    biais_num = mediane(ecarts_num) if ecarts_num else 0.0
    biais_scan = mediane(ecarts_scan) if ecarts_scan else 0.0
    biais_tranche_num = {t: mediane([l["ecart"] for l in lignes_num if l["tranche"] == t])
                         for _, _, t in TRANCHES}

    s_scan_brut = stats_erreurs(ecarts_scan)
    s_scan_corr_num = stats_erreurs([e - biais_num for e in ecarts_scan])
    s_scan_corr_scan = stats_erreurs([e - biais_scan for e in ecarts_scan])
    s_num = stats_erreurs(ecarts_num)

    ph_brut, detail_photos = estimation_photos(lignes_scans, lambda l: 0.0)
    ph_corr_num, _ = estimation_photos(lignes_scans, lambda l: biais_num)
    ph_corr_scan, _ = estimation_photos(lignes_scans, lambda l: biais_scan)
    ph_corr_tranche, _ = estimation_photos(
        lignes_scans,
        lambda l: biais_tranche_num.get(l["tranche"]) if biais_tranche_num.get(l["tranche"]) == biais_tranche_num.get(l["tranche"]) else biais_num)
    ecrire_csv(OUT / "photos.csv", detail_photos)

    sp = {"brut": stats_erreurs(ph_brut), "num": stats_erreurs(ph_corr_num),
          "tranche": stats_erreurs(ph_corr_tranche), "scan": stats_erreurs(ph_corr_scan)}
    meilleure_realiste = min(
        (sp["brut"].get("erreur_mediane", float("inf")), "sans correction"),
        (sp["num"].get("erreur_mediane", float("inf")), "biais global du numérique"),
        (sp["tranche"].get("erreur_mediane", float("inf")), "biais par tranche du numérique"),
    )

    nb_mesures = max(1, compteurs["visages_mesures"])
    rapport += [
        "## 3. Données", "",
        f"- Scans datés analysés : {len(scans)} — photos avec au moins un visage exploitable : {len(detail_photos)}",
        f"- Visages mesurés : {int(compteurs['visages_mesures'])} (scans : {len(lignes_scans)}, numérique : {len(lignes_num)})",
        f"- Visages non nommés : {int(compteurs['visages_non_nommes'])}",
        f"- Visages de personnes sans date de naissance : {int(compteurs['visages_sans_naissance'])} ({len(sans_naissance)} personne(s))",
        f"- Visages « avant la naissance » (mal attribués ou date fausse) : {int(compteurs['visages_avant_naissance'])}",
        f"- Temps moyen par visage : {compteurs['temps_inference'] / nb_mesures:.2f} s", "",
        "## 4. Erreur par visage (âge estimé − âge vrai, en années)", "",
        "| Jeu | n | biais | erreur médiane | ≤ 2 ans | ≤ 3 ans | ≤ 5 ans |",
        "|---|---|---|---|---|---|---|",
        tableau_stats("Numérique (références)", s_num),
        tableau_stats("Scans, sans correction", s_scan_brut),
        tableau_stats(f"Scans, biais du numérique ({biais_num:+.1f})", s_scan_corr_num),
        tableau_stats(f"Scans, biais des scans ({biais_scan:+.1f}) *", s_scan_corr_scan),
        "", "\\* optimiste : biais calculé sur les mêmes scans, montre le potentiel d'une calibration sur scans datés.", "",
        "### Par tranche d'âge (scans, sans correction)", "",
        "| Tranche | n | biais | erreur médiane | ≤ 2 ans | ≤ 3 ans | ≤ 5 ans |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, _, t in TRANCHES:
        rapport.append(tableau_stats(t, stats_erreurs([l["ecart"] for l in lignes_scans if l["tranche"] == t])))
    petits = [l["ecart"] for l in lignes_scans if l["visage_px"] < VISAGE_PETIT_PX]
    grands = [l["ecart"] for l in lignes_scans if l["visage_px"] >= VISAGE_PETIT_PX]
    rapport += ["", "### Selon la taille du visage dans l'aperçu (scans)", "",
                "| Taille | n | biais | erreur médiane | ≤ 2 ans | ≤ 3 ans | ≤ 5 ans |",
                "|---|---|---|---|---|---|---|",
                tableau_stats(f"< {VISAGE_PETIT_PX} px", stats_erreurs(petits)),
                tableau_stats(f"≥ {VISAGE_PETIT_PX} px", stats_erreurs(grands)), "",
                "## 5. Erreur sur l'année de la photo (visages fusionnés)", "",
                "| Méthode | n | biais | erreur médiane | ≤ 2 ans | ≤ 3 ans | ≤ 5 ans |",
                "|---|---|---|---|---|---|---|",
                tableau_stats("Sans correction", sp["brut"]),
                tableau_stats("Biais global du numérique", sp["num"]),
                tableau_stats("Biais par tranche du numérique", sp["tranche"]),
                tableau_stats("Biais des scans *", sp["scan"]), "",
                "## 6. Verdict", "",
                f"Meilleure méthode réaliste : **{meilleure_realiste[1]}**.", "",
                verdict(meilleure_realiste[0]), ""]

    # 5. Test d'écriture
    log("Test d'écriture…")
    try:
        ecr = test_ecriture(tag_non_datee, stockage)
    except Exception as e:  # noqa: BLE001
        ecr = {"fait": False, "detail": f"erreur : {e}"}
    log(f"Test d'écriture : {ecr}")
    rapport += ["## 7. Écriture de la date dans Immich", ""]
    if not ecr.get("fait"):
        rapport.append(f"- Non réalisé : {ecr.get('detail')}")
    else:
        rapport += [
            f"- Photo test : `{ecr['asset_id']}`",
            f"- Écriture de la date : {'✅' if ecr.get('ecriture_ok') else '❌'} (lue : {ecr.get('date_lue_apres_ecriture')})",
            f"- Ré-extraction lancée : {'oui' if ecr.get('reextraction_lancee') else 'non ' + str(ecr.get('reextraction_erreur', ''))}",
            f"- La date tient après ré-extraction : {'✅' if ecr.get('tient_apres_reextraction') else '❌'} (lue : {ecr.get('date_lue_apres_reextraction')})",
            f"- Date d'origine restaurée : {'✅' if ecr.get('restauree') else '❌ à faire à la main (sauvegarde_date_test.json)'}",
        ]
    rapport.append("")

    if sans_naissance:
        rapport += ["## 8. Personnes sans date de naissance", ""]
        rapport += [f"- {nom} (`{pid}`)" for pid, nom in sorted(sans_naissance.items(), key=lambda x: x[1])]
        rapport.append("")

    (OUT / "rapport.md").write_text("\n".join(rapport), encoding="utf-8")
    log("Terminé. Résultats dans le dossier resultats/ (rapport.md, visages.csv, photos.csv).")
    print("\n".join(rapport), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
