#!/usr/bin/env python3
"""
Millésime — test de mesure.

Question : un modèle peut-il aider à dater les scans de photos papier ?

Le test compare plusieurs méthodes sur les scans dont la date est connue
(tags « <TAG_PREFIXE>/AAAA-MM », date issue du tampon au dos) :

  Visages (âge estimé + date de naissance → année de la photo)
    - insightface : genderage.onnx (référence du 1er test, léger)
    - mivolo      : MiVOLO v2, visage seul           (MIVOLO=1, image « mesure-pc »)
    - mivolo_corps: MiVOLO v2, visage + buste estimé (MIVOLO=1)
  Photo entière
    - vlm         : modèle de vision local via Ollama (VLM_URL), qui estime
                    directement l'année à partir de la scène et du tirage

Les mêmes méthodes tournent aussi sur des photos numériques datées des mêmes
personnes, pour voir si une correction apprise sur le numérique vaut pour les scans.

Le test est en LECTURE SEULE : rien n'est écrit dans Immich.
Il ne tourne qu'une fois : si resultats/rapport.md existe, il s'arrête aussitôt.
Pour le relancer : MILLESIME_TEST_FORCER=1, ou supprimer rapport.md.
"""

__version__ = "0.2.0"

import base64
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
# Configuration (variables d'environnement)
# --------------------------------------------------------------------------
IMMICH_URL = os.environ.get("IMMICH_URL", "http://immich_server:2283").rstrip("/")
API_KEY = os.environ.get("IMMICH_API_KEY", "")
TAG_PREFIXE = os.environ.get("TAG_PREFIXE", "Numérisation")
TAG_NON_DATEE = os.environ.get("TAG_NON_DATEE", "Non datée")
MAX_SCANS = int(os.environ.get("MAX_SCANS", "300"))
REFS_PAR_PERSONNE = int(os.environ.get("REFS_PAR_PERSONNE", "15"))
_threads = os.environ.get("THREADS", "2")
THREADS = (os.cpu_count() or 2) if _threads == "auto" else int(_threads)
FORCER = os.environ.get("MILLESIME_TEST_FORCER", "0") == "1"
WORK = Path(os.environ.get("DATA_DIR", "/data"))

INSIGHTFACE = os.environ.get("INSIGHTFACE", "1") == "1"
INSIGHTFACE_URL = os.environ.get(
    "MODELE_URL", "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip")

MIVOLO = os.environ.get("MIVOLO", "0") == "1"
MIVOLO_CORPS = os.environ.get("MIVOLO_CORPS", "1") == "1"
MIVOLO_ID = os.environ.get("MIVOLO_MODELE", "iitolstykh/mivolo_v2")

VLM_URL = os.environ.get("VLM_URL", "").rstrip("/")
VLM_MODELE = os.environ.get("VLM_MODELE", "qwen3-vl:8b")
MAX_PHOTOS_VLM = int(os.environ.get("MAX_PHOTOS_VLM", "150"))
VLM_TIMEOUT = int(os.environ.get("VLM_TIMEOUT", "600"))

OUT = WORK / "resultats"
MODELS = WORK / "models"
MODELE_INSIGHTFACE = MODELS / "genderage.onnx"
JOURNAL = OUT / "journal.txt"

SEUIL_UTILE = 3.0
SEUIL_ABANDON = 5.0
VISAGE_PETIT_PX = 40
TRANCHES = [(0, 12, "0-12 ans"), (13, 25, "13-25 ans"), (26, 50, "26-50 ans"), (51, 200, "51 ans et +")]
NOMS = {
    "insightface": "InsightFace (1er test)",
    "mivolo": "MiVOLO v2, visage seul",
    "mivolo_corps": "MiVOLO v2, visage + buste estimé",
    "vlm": "Vision locale (photo entière)",
}


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------
def log(msg: str) -> None:
    ligne = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(ligne, flush=True)
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(ligne + "\n")


session = requests.Session()
session.headers.update({"x-api-key": API_KEY, "Accept": "application/json"})


def api(methode: str, chemin: str, **kw):
    r = session.request(methode, f"{IMMICH_URL}/api{chemin}", timeout=60, **kw)
    r.raise_for_status()
    if not r.content:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def parse_date(valeur):
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


def est_nan(x) -> bool:
    return x != x


def stats_erreurs(ecarts):
    if not ecarts:
        return {"n": 0}
    absolus = [abs(e) for e in ecarts]
    return {
        "n": len(ecarts),
        "biais_median": round(mediane(ecarts), 1),
        "erreur_mediane": round(mediane(absolus), 1),
        "pct_2ans": round(100 * sum(a <= 2 for a in absolus) / len(absolus)),
        "pct_3ans": round(100 * sum(a <= 3 for a in absolus) / len(absolus)),
        "pct_5ans": round(100 * sum(a <= 5 for a in absolus) / len(absolus)),
    }


def boite_pixels(image: Image.Image, face: dict):
    """Boîte du visage en pixels de l'aperçu (Immich la donne dans imageWidth × imageHeight)."""
    sx = image.width / max(1, face.get("imageWidth") or image.width)
    sy = image.height / max(1, face.get("imageHeight") or image.height)
    return (face["boundingBoxX1"] * sx, face["boundingBoxY1"] * sy,
            face["boundingBoxX2"] * sx, face["boundingBoxY2"] * sy)


# --------------------------------------------------------------------------
# Estimateurs d'âge par visage
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
    return {"modele": modele, "avx": "avx" in flags, "avx2": "avx2" in flags,
            "coeurs": os.cpu_count() or 0}


def telecharger_insightface() -> None:
    if MODELE_INSIGHTFACE.exists():
        return
    MODELS.mkdir(parents=True, exist_ok=True)
    zip_path = MODELS / "buffalo_l.zip"
    log("Téléchargement du modèle InsightFace (archive ~280 Mo, une seule fois)…")
    with requests.get(INSIGHTFACE_URL, stream=True, timeout=120) as r:
        r.raise_for_status()
        with zip_path.open("wb") as f:
            for bloc in r.iter_content(chunk_size=1 << 20):
                f.write(bloc)
    with zipfile.ZipFile(zip_path) as z:
        membre = next(n for n in z.namelist() if n.endswith("genderage.onnx"))
        MODELE_INSIGHTFACE.write_bytes(z.read(membre))
    zip_path.unlink()


def test_onnxruntime() -> tuple[bool, str]:
    """Inférence factice dans un sous-processus : un plantage CPU (SIGILL) ne tue pas le test."""
    code = (
        "import onnxruntime as o, numpy as np;"
        f"s=o.InferenceSession(r'{MODELE_INSIGHTFACE}', providers=['CPUExecutionProvider']);"
        "i=s.get_inputs()[0];"
        "s.run(None,{i.name: np.zeros((1,3,96,96),dtype=np.float32)});"
        "print(o.__version__)"
    )
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if p.returncode == 0:
        return True, f"onnxruntime {p.stdout.strip()}"
    if p.returncode == -4:
        return False, "onnxruntime a planté (instruction CPU illégale)"
    return False, f"onnxruntime en échec (code {p.returncode}) : {p.stderr.strip()[-300:]}"


class InsightFace:
    """genderage.onnx d'InsightFace : carré 1,5 × la boîte, 96 px, pixels RGB bruts (normalisation dans le graphe)."""
    nom = "insightface"

    def __init__(self):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = THREADS
        opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(MODELE_INSIGHTFACE), opts, providers=["CPUExecutionProvider"])
        self.entree = self.session.get_inputs()[0].name

    def ages(self, image: Image.Image, face: dict) -> dict:
        x1, y1, x2, y2 = boite_pixels(image, face)
        cote = max(x2 - x1, y2 - y1) * 1.5
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        boite = tuple(int(round(v)) for v in (cx - cote / 2, cy - cote / 2, cx + cote / 2, cy + cote / 2))
        crop = image.crop(boite).resize((96, 96), Image.BILINEAR)
        blob = np.asarray(crop, dtype=np.float32).transpose(2, 0, 1)[None, ...]
        sortie = self.session.run(None, {self.entree: blob})[0][0]
        return {"insightface": float(sortie[2] * 100.0)}


class MiVolo:
    """
    MiVOLO v2 (Hugging Face iitolstykh/mivolo_v2, code chargé avec trust_remote_code).
    Les recadrages sont des tableaux BGR (comme OpenCV). Visage seul : body_input = [None].
    Visage + corps : buste estimé à partir du visage (Immich ne détecte pas les personnes).
    """
    nom = "mivolo"

    def __init__(self):
        import torch
        from transformers import AutoConfig, AutoImageProcessor, AutoModelForImageClassification

        torch.set_num_threads(THREADS)
        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.config = AutoConfig.from_pretrained(MIVOLO_ID, trust_remote_code=True)
        self.model = AutoModelForImageClassification.from_pretrained(
            MIVOLO_ID, trust_remote_code=True, torch_dtype=dtype).to(self.device).eval()
        self.proc = AutoImageProcessor.from_pretrained(MIVOLO_ID, trust_remote_code=True)
        self.dtype = dtype

    def _pixels(self, crops):
        pv = self.proc(images=crops)["pixel_values"]
        return pv.to(device=self.device, dtype=self.dtype) if pv is not None else None

    def _age(self, visage, corps) -> float:
        with self.torch.inference_mode():
            sortie = self.model(faces_input=self._pixels([visage]), body_input=self._pixels([corps]))
        return float(sortie.age_output[0].item())

    @staticmethod
    def buste(image: Image.Image, boite):
        """Buste approximatif : 3 largeurs de visage, du haut de la tête à 4 hauteurs de visage plus bas."""
        x1, y1, x2, y2 = boite
        w, h = x2 - x1, y2 - y1
        cx = (x1 + x2) / 2
        return (max(0, cx - 1.5 * w), max(0, y1 - 0.3 * h),
                min(image.width, cx + 1.5 * w), min(image.height, y2 + 3.0 * h))

    def ages(self, image: Image.Image, face: dict) -> dict:
        boite = boite_pixels(image, face)
        bgr = lambda b: np.ascontiguousarray(np.asarray(image.crop(tuple(int(round(v)) for v in b)))[:, :, ::-1])  # noqa: E731
        visage = bgr(boite)
        res = {"mivolo": self._age(visage, None)}
        if MIVOLO_CORPS:
            res["mivolo_corps"] = self._age(visage, bgr(self.buste(image, boite)))
        return res


# --------------------------------------------------------------------------
# Vision locale (Ollama) : année de la photo entière
# --------------------------------------------------------------------------
PROMPT_VLM = (
    "Cette image est un tirage papier de photo de famille, numérisé. "
    "Estime l'année de prise de vue à partir des indices visibles : vêtements, coiffures, "
    "lunettes, objets, voitures, décor, couleurs et aspect du tirage (virage, grain, bords, format). "
    "Si une date est imprimée sur la photo, utilise-la. "
    "Réponds uniquement en JSON : annee (entier), annee_min et annee_max (fourchette plausible), "
    "indices (une phrase courte en français)."
)
SCHEMA_VLM = {
    "type": "object",
    "properties": {
        "annee": {"type": "integer"},
        "annee_min": {"type": "integer"},
        "annee_max": {"type": "integer"},
        "indices": {"type": "string"},
    },
    "required": ["annee", "annee_min", "annee_max", "indices"],
}


def vlm_disponible() -> tuple[bool, str]:
    try:
        r = requests.get(f"{VLM_URL}/api/tags", timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        return False, f"Ollama injoignable à {VLM_URL} ({e.__class__.__name__})"
    noms = [m.get("name", "") for m in r.json().get("models", [])]
    voulu = VLM_MODELE if ":" in VLM_MODELE else VLM_MODELE + ":latest"
    if voulu not in noms:
        return False, f"modèle {VLM_MODELE} absent d'Ollama (lance « ollama pull {VLM_MODELE} »)"
    return True, f"Ollama OK, modèle {VLM_MODELE}"


def vlm_gpu() -> str:
    """Après un appel : part du modèle chargée en mémoire vidéo, d'après /api/ps."""
    try:
        for m in requests.get(f"{VLM_URL}/api/ps", timeout=10).json().get("models", []):
            if m.get("name", "").startswith(VLM_MODELE.split(":")[0]):
                taille, vram = m.get("size") or 0, m.get("size_vram") or 0
                if not taille:
                    break
                part = round(100 * vram / taille)
                return f"{part} % en mémoire vidéo ({vram / 2**30:.1f} Go sur {taille / 2**30:.1f} Go)"
    except (requests.RequestException, ValueError):
        pass
    return "inconnu"


def lire_json(texte: str) -> dict:
    texte = re.sub(r"<think>.*?</think>", "", texte or "", flags=re.S)
    m = re.search(r"\{.*\}", texte, flags=re.S)
    if not m:
        raise ValueError("pas de JSON dans la réponse")
    return json.loads(m.group(0))


def estimer_vlm(image: Image.Image) -> dict:
    img = image.copy()
    img.thumbnail((1024, 1024))
    buf = BytesIO()
    img.save(buf, "JPEG", quality=90)
    corps = {
        "model": VLM_MODELE,
        "messages": [{"role": "user", "content": PROMPT_VLM,
                      "images": [base64.b64encode(buf.getvalue()).decode()]}],
        "stream": False,
        "format": SCHEMA_VLM,
        "options": {"temperature": 0},
    }
    r = requests.post(f"{VLM_URL}/api/chat", json=corps, timeout=VLM_TIMEOUT)
    r.raise_for_status()
    d = lire_json(r.json().get("message", {}).get("content", ""))
    annee = int(d["annee"])
    if not 1880 <= annee <= date.today().year:
        raise ValueError(f"année hors bornes : {annee}")
    return {"annee": annee, "annee_min": int(d.get("annee_min", annee)),
            "annee_max": int(d.get("annee_max", annee)), "indices": str(d.get("indices", ""))[:200]}


# --------------------------------------------------------------------------
# Accès Immich
# --------------------------------------------------------------------------
def verifier_stockage() -> dict:
    try:
        cfg = api("GET", "/system-config")
    except requests.HTTPError as e:
        return {"lisible": False, "detail": f"lecture impossible ({e.response.status_code}) : clé sans droit admin ?"}
    st = (cfg or {}).get("storageTemplate", {})
    modele = st.get("template", "")
    return {"lisible": True, "actif": bool(st.get("enabled")), "modele": modele,
            "deplace_fichiers": bool(st.get("enabled")) and bool(re.search(r"\{\{\s*(y|M|d|w|W)", modele))}


def rechercher(filtres: dict, limite: int) -> list:
    resultats, page = [], 1
    while len(resultats) < limite:
        corps = {**filtres, "page": page, "size": min(250, limite), "withExif": True, "type": "IMAGE"}
        bloc = (api("POST", "/search/metadata", json=corps) or {}).get("assets", {})
        resultats += bloc.get("items", [])
        if not bloc.get("nextPage"):
            break
        page = int(bloc["nextPage"])
    return resultats[:limite]


def tags_numerisation():
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
            jour = int(m.group(3)) if m.group(3) else 15
            dates.append((t, date(int(m.group(1)), int(m.group(2)), jour)))
    return dates, non_datee


def apercu(asset_id: str) -> Image.Image:
    r = session.get(f"{IMMICH_URL}/api/assets/{asset_id}/thumbnail", params={"size": "preview"}, timeout=60)
    r.raise_for_status()
    return Image.open(BytesIO(r.content)).convert("RGB")


def visages(asset_id: str) -> list:
    return api("GET", "/faces", params={"id": asset_id}) or []


def echantillon(liste, n):
    if len(liste) <= n:
        return liste
    pas = len(liste) / n
    return [liste[int(i * pas)] for i in range(n)]


# --------------------------------------------------------------------------
# Mesure
# --------------------------------------------------------------------------
def mesurer_asset(estimateurs, asset_id, date_vraie, domaine, cpt, sans_naissance, personnes_vues,
                  temps, seulement_personne=None, image=None):
    """Âge de chaque visage nommé ayant une date de naissance, pour chaque estimateur."""
    lignes = []
    for f in visages(asset_id):
        personne = f.get("person")
        if not personne:
            cpt["visages_non_nommes"] += 1
            continue
        if seulement_personne and personne["id"] != seulement_personne:
            continue
        naissance = parse_date(personne.get("birthDate"))
        if not naissance:
            sans_naissance[personne["id"]] = personne.get("name") or "(sans nom)"
            cpt["visages_sans_naissance"] += 1
            continue
        age_vrai = age_exact(naissance, date_vraie)
        if age_vrai < 0:
            cpt["visages_avant_naissance"] += 1
            continue
        if image is None:
            image = apercu(asset_id)
        x1, y1, x2, y2 = boite_pixels(image, f)
        ligne = {
            "domaine": domaine, "asset_id": asset_id,
            "personne": personne.get("name") or "(sans nom)", "personne_id": personne["id"],
            "naissance": naissance.isoformat(), "date_vraie": date_vraie.isoformat(),
            "age_vrai": round(age_vrai, 1), "tranche": tranche(age_vrai),
            "visage_px": int(max(x2 - x1, y2 - y1)),
            "annee_naissance_dec": round(annee_decimale(naissance), 3),
            "annee_vraie_dec": round(annee_decimale(date_vraie), 3),
        }
        for est in estimateurs:
            debut = time.perf_counter()
            try:
                for nom, age in est.ages(image, f).items():
                    ligne[f"age_{nom}"] = round(age, 1)
                    ligne[f"ecart_{nom}"] = round(age - age_vrai, 1)
            except Exception as e:  # noqa: BLE001
                cpt[f"erreurs_{est.nom}"] += 1
                if cpt[f"erreurs_{est.nom}"] <= 3:
                    log(f"  {est.nom} : erreur sur {asset_id} ({e})")
            temps[est.nom] += time.perf_counter() - debut
            cpt[f"visages_{est.nom}"] += 1
        cpt["visages_mesures"] += 1
        personnes_vues[personne["id"]] = (personne.get("name") or "(sans nom)", naissance)
        lignes.append(ligne)
    return lignes, image


def annees_photos(lignes_scans, methode, correction):
    """Année par photo = médiane des années déduites de ses visages."""
    par_photo = defaultdict(list)
    for l in lignes_scans:
        if f"age_{methode}" in l:
            par_photo[l["asset_id"]].append(l)
    res = {}
    for asset_id, ls in par_photo.items():
        annees = [l["annee_naissance_dec"] + l[f"age_{methode}"] - correction for l in ls]
        res[asset_id] = (mediane(annees), ls[0]["annee_vraie_dec"])
    return res


def ecarts_de(res: dict, ids=None):
    return [est - vraie for a, (est, vraie) in res.items() if ids is None or a in ids]


# --------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------
def ecrire_csv(chemin: Path, lignes: list) -> None:
    if not lignes:
        return
    champs = []
    for l in lignes:
        for k in l:
            if k not in champs:
                champs.append(k)
    with chemin.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs, delimiter=";")
        w.writeheader()
        w.writerows(lignes)


def ligne_tableau(titre: str, s: dict) -> str:
    if not s.get("n"):
        return f"| {titre} | 0 | – | – | – | – | – |"
    return (f"| {titre} | {s['n']} | {s['biais_median']:+} | {s['erreur_mediane']} | "
            f"{s['pct_2ans']} % | {s['pct_3ans']} % | {s['pct_5ans']} % |")


ENTETE = ["| Méthode | n | biais | erreur médiane | ≤ 2 ans | ≤ 3 ans | ≤ 5 ans |",
          "|---|---|---|---|---|---|---|"]


def verdict(erreur: float, methode: str) -> str:
    if est_nan(erreur):
        return "❔ Pas assez de données pour conclure."
    if erreur < SEUIL_UTILE:
        return (f"✅ **{methode}** est utile : erreur médiane {erreur} an(s) < {SEUIL_UTILE}. "
                "Elle peut servir d'indice affiché sur l'écran de comparaison.")
    if erreur <= SEUIL_ABANDON:
        return (f"🟠 **{methode}** est un indice faible : erreur médiane {erreur} ans. "
                "À n'afficher qu'à titre indicatif, l'écran de comparaison fait le travail.")
    return (f"❌ Meilleure méthode : **{methode}**, erreur médiane {erreur} ans > {SEUIL_ABANDON}. "
            "V1 sans modèle (écran de comparaison seul).")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "rapport.md").exists() and not FORCER:
        print(f"Test déjà fait : {OUT / 'rapport.md'} existe. "
              "Pour le relancer : MILLESIME_TEST_FORCER=1 ou supprimer rapport.md.", flush=True)
        return 0
    JOURNAL.write_text("", encoding="utf-8")
    try:
        os.nice(10)
    except OSError:
        pass
    if not API_KEY:
        log("❌ IMMICH_API_KEY manquante.")
        return 1

    rapport = ["# Millésime — rapport du test de mesure", "",
               f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} (version {__version__})", ""]

    # 1. Matériel et modèles ------------------------------------------------
    cpu = info_cpu()
    log(f"CPU : {cpu['modele']} ({cpu['coeurs']} cœurs) — AVX : {'oui' if cpu['avx'] else 'non'}")
    estimateurs, lignes_mat = [], [
        f"- CPU : {cpu['modele']}, {cpu['coeurs']} cœurs (AVX : {'oui' if cpu['avx'] else 'non'}, "
        f"AVX2 : {'oui' if cpu['avx2'] else 'non'}), {THREADS} thread(s) utilisés"]
    if INSIGHTFACE:
        telecharger_insightface()
        ok, detail = test_onnxruntime()
        log(f"InsightFace : {detail}")
        lignes_mat.append(f"- InsightFace : {'✅' if ok else '❌'} {detail}")
        if ok:
            estimateurs.append(InsightFace())
    if MIVOLO:
        try:
            log(f"Chargement de MiVOLO ({MIVOLO_ID}, ~110 Mo au premier lancement)…")
            mv = MiVolo()
            estimateurs.append(mv)
            lignes_mat.append(f"- MiVOLO : ✅ {MIVOLO_ID} sur {mv.device}"
                              + (" (visage seul + visage et buste)" if MIVOLO_CORPS else " (visage seul)"))
        except Exception as e:  # noqa: BLE001
            log(f"MiVOLO indisponible : {e}")
            lignes_mat.append(f"- MiVOLO : ❌ {str(e)[:300]}")
    vlm_ok = False
    if VLM_URL:
        vlm_ok, detail = vlm_disponible()
        log(f"Vision locale : {detail}")
        lignes_mat.append(f"- Vision locale : {'✅' if vlm_ok else '❌'} {detail}")
    rapport += ["## 1. Matériel et modèles", "", *lignes_mat, ""]
    if not estimateurs and not vlm_ok:
        (OUT / "rapport.md").write_text("\n".join(rapport), encoding="utf-8")
        log("Arrêt : aucune méthode disponible. Voir rapport.md.")
        return 1

    # 2. Immich ---------------------------------------------------------------
    version = api("GET", "/server/version") or {}
    v = f"{version.get('major')}.{version.get('minor')}.{version.get('patch')}"
    log(f"Immich {v} joignable")
    stockage = verifier_stockage()
    rapport += ["## 2. Immich", "", f"- Version : {v}"]
    if stockage["lisible"]:
        rapport += [f"- Modèle de stockage : {'actif' if stockage['actif'] else 'inactif'} — `{stockage['modele'] or '—'}`",
                    f"- Changer une date déplace le fichier : **{'oui' if stockage['deplace_fichiers'] else 'non'}**"]
    else:
        rapport.append(f"- Modèle de stockage : {stockage['detail']}")
    rapport.append("")

    # 3. Scans datés ----------------------------------------------------------
    tags_dates, tag_non_datee = tags_numerisation()
    log(f"{len(tags_dates)} tags datés « {TAG_PREFIXE}/AAAA-MM »")
    cpt, temps = defaultdict(int), defaultdict(float)
    sans_naissance, personnes_vues = {}, {}
    ids_scans, scans = set(), []
    for tag, d in tags_dates:
        for a in rechercher({"tagIds": [tag["id"]]}, 5000):
            if a["id"] not in ids_scans:
                ids_scans.add(a["id"])
                scans.append((a["id"], d))
    if tag_non_datee:
        ids_scans.update(a["id"] for a in rechercher({"tagIds": [tag_non_datee["id"]]}, 20000))
    scans.sort(key=lambda x: x[1])
    scans = echantillon(scans, MAX_SCANS)
    ids_vlm = {a for a, _ in echantillon(scans, MAX_PHOTOS_VLM)} if vlm_ok else set()
    log(f"{len(scans)} scans datés à analyser" + (f", dont {len(ids_vlm)} par la vision locale" if vlm_ok else ""))

    lignes_scans, lignes_vlm = [], []
    for i, (asset_id, d) in enumerate(scans, 1):
        try:
            lignes, image = mesurer_asset(estimateurs, asset_id, d, "scan", cpt, sans_naissance,
                                          personnes_vues, temps)
            lignes_scans += lignes
            if asset_id in ids_vlm:
                if image is None:
                    image = apercu(asset_id)
                debut = time.perf_counter()
                try:
                    r = estimer_vlm(image)
                    vraie = annee_decimale(d)
                    lignes_vlm.append({"asset_id": asset_id, "date_vraie": d.isoformat(),
                                       "annee_vraie": round(vraie, 1), **r,
                                       "ecart": round(r["annee"] + 0.5 - vraie, 1)})
                except Exception as e:  # noqa: BLE001
                    cpt["erreurs_vlm"] += 1
                    if cpt["erreurs_vlm"] <= 3:
                        log(f"  vision locale : erreur sur {asset_id} ({e})")
                temps["vlm"] += time.perf_counter() - debut
                cpt["photos_vlm"] += 1
                if cpt["photos_vlm"] == 1:
                    cpt["vlm_gpu"] = vlm_gpu()
        except requests.HTTPError as e:
            log(f"  asset {asset_id} ignoré ({e.response.status_code})")
        if i % 25 == 0:
            log(f"  {i}/{len(scans)} scans traités, {cpt['visages_mesures']} visages, "
                f"{len(lignes_vlm)} photos datées par la vision locale")

    # 4. Photos numériques des mêmes personnes --------------------------------
    lignes_num = []
    if estimateurs:
        for pid, (nom, _) in list(personnes_vues.items()):
            try:
                candidats = [a for a in rechercher({"personIds": [pid]}, 400)
                             if a["id"] not in ids_scans
                             and parse_date(a.get("localDateTime") or (a.get("exifInfo") or {}).get("dateTimeOriginal"))]
            except requests.HTTPError as e:
                log(f"  photos de {nom} : recherche impossible ({e.response.status_code})")
                continue
            candidats.sort(key=lambda a: a.get("localDateTime") or "")
            for a in echantillon(candidats, REFS_PAR_PERSONNE):
                d = parse_date(a.get("localDateTime") or a["exifInfo"]["dateTimeOriginal"])
                try:
                    lignes, _ = mesurer_asset(estimateurs, a["id"], d, "numerique", cpt, sans_naissance,
                                              {}, temps, seulement_personne=pid)
                    lignes_num += lignes
                except requests.HTTPError:
                    continue
        log(f"Références numériques : {len(lignes_num)} visages")

    ecrire_csv(OUT / "visages.csv", lignes_scans + lignes_num)
    ecrire_csv(OUT / "vlm.csv", lignes_vlm)

    # 5. Analyse ----------------------------------------------------------------
    methodes = [m for est in estimateurs for m in (["mivolo", "mivolo_corps"] if est.nom == "mivolo" and MIVOLO_CORPS
                                                    else [est.nom])]
    candidats_verdict = []   # (erreur médiane, nom) des méthodes réalistes
    photos_par_methode = {}
    lignes_photos = defaultdict(dict)

    nb = max(1, cpt["visages_mesures"])
    rapport += [
        "## 3. Données", "",
        f"- Scans datés analysés : {len(scans)} — photos avec au moins un visage exploitable : "
        f"{len({l['asset_id'] for l in lignes_scans})}",
        f"- Visages mesurés : {cpt['visages_mesures']} (scans : {len(lignes_scans)}, numérique : {len(lignes_num)})",
        f"- Visages non nommés : {cpt['visages_non_nommes']}",
        f"- Visages de personnes sans date de naissance : {cpt['visages_sans_naissance']} "
        f"({len(sans_naissance)} personne(s))",
        f"- Visages « avant la naissance » (mal attribués ou date fausse) : {cpt['visages_avant_naissance']}",
    ]
    for est in estimateurs:
        rapport.append(f"- Temps moyen par visage, {est.nom} : {temps[est.nom] / max(1, cpt[f'visages_{est.nom}']):.2f} s"
                       + (f" ({cpt[f'erreurs_{est.nom}']} erreur(s))" if cpt[f"erreurs_{est.nom}"] else ""))
    if vlm_ok:
        rapport += [f"- Vision locale : {len(lignes_vlm)} photos datées sur {cpt['photos_vlm']} "
                    f"({cpt['erreurs_vlm']} échec(s)), {temps['vlm'] / max(1, cpt['photos_vlm']):.1f} s par photo",
                    f"- Vision locale, carte graphique : {cpt.get('vlm_gpu', 'inconnu')}"]
    rapport.append("")

    if methodes:
        rapport += ["## 4. Erreur par visage (âge estimé − âge vrai, en années)", "", *ENTETE]
        for m in methodes:
            e_scan = [l[f"ecart_{m}"] for l in lignes_scans if f"ecart_{m}" in l]
            e_num = [l[f"ecart_{m}"] for l in lignes_num if f"ecart_{m}" in l]
            rapport += [ligne_tableau(f"{NOMS[m]} — numérique", stats_erreurs(e_num)),
                        ligne_tableau(f"{NOMS[m]} — scans", stats_erreurs(e_scan))]
        rapport += ["", "### Par tranche d'âge (scans, sans correction)", "",
                    "| Tranche | " + " | ".join(NOMS[m] for m in methodes) + " |",
                    "|---|" + "---|" * len(methodes)]
        for _, _, t in TRANCHES:
            cellules = []
            for m in methodes:
                s = stats_erreurs([l[f"ecart_{m}"] for l in lignes_scans if l["tranche"] == t and f"ecart_{m}" in l])
                cellules.append(f"{s['erreur_mediane']} ans (biais {s['biais_median']:+}, n={s['n']})" if s["n"] else "–")
            rapport.append(f"| {t} | " + " | ".join(cellules) + " |")
        rapport.append("")

    rapport += ["## 5. Erreur sur l'année de la photo", "", *ENTETE]
    for m in methodes:
        e_num = [l[f"ecart_{m}"] for l in lignes_num if f"ecart_{m}" in l]
        e_scan = [l[f"ecart_{m}"] for l in lignes_scans if f"ecart_{m}" in l]
        b_num = mediane(e_num) if e_num else 0.0
        b_scan = mediane(e_scan) if e_scan else 0.0
        brut = annees_photos(lignes_scans, m, 0.0)
        photos_par_methode[m] = brut
        s_brut = stats_erreurs(ecarts_de(brut))
        s_num = stats_erreurs(ecarts_de(annees_photos(lignes_scans, m, b_num)))
        s_scan = stats_erreurs(ecarts_de(annees_photos(lignes_scans, m, b_scan)))
        rapport += [ligne_tableau(f"{NOMS[m]}, sans correction", s_brut),
                    ligne_tableau(f"{NOMS[m]}, biais du numérique ({b_num:+.1f})", s_num),
                    ligne_tableau(f"{NOMS[m]}, biais des scans ({b_scan:+.1f}) *", s_scan)]
        for libelle, s in ((f"{NOMS[m]}, sans correction", s_brut), (f"{NOMS[m]}, biais du numérique", s_num)):
            if s.get("n"):
                candidats_verdict.append((s["erreur_mediane"], libelle))
        for a, (est, vraie) in brut.items():
            lignes_photos[a].update({"asset_id": a, "annee_vraie": round(vraie, 1), f"annee_{m}": round(est, 1)})

    vlm_res = {}
    if lignes_vlm:
        vlm_res = {l["asset_id"]: (l["annee"] + 0.5, l["annee_vraie"]) for l in lignes_vlm}
        s_vlm = stats_erreurs(ecarts_de(vlm_res))
        rapport.append(ligne_tableau(NOMS["vlm"], s_vlm))
        if s_vlm.get("n"):
            candidats_verdict.append((s_vlm["erreur_mediane"], NOMS["vlm"]))
        dans = sum(l["annee_min"] <= int(l["annee_vraie"]) <= l["annee_max"] for l in lignes_vlm)
        larg = mediane([l["annee_max"] - l["annee_min"] for l in lignes_vlm])
        # Borne basse : pas avant la naissance la plus récente des personnes nommées présentes
        naiss_max = defaultdict(float)
        for l in lignes_scans:
            naiss_max[l["asset_id"]] = max(naiss_max[l["asset_id"]], l["annee_naissance_dec"])
        borne = {a: (max(est, naiss_max[a]) if a in naiss_max else est, vraie) for a, (est, vraie) in vlm_res.items()}
        rapport.append(ligne_tableau(f"{NOMS['vlm']} + borne des naissances", stats_erreurs(ecarts_de(borne))))
        for a, (est, vraie) in vlm_res.items():
            lignes_photos[a].update({"asset_id": a, "annee_vraie": round(vraie, 1), "annee_vlm": round(est, 1)})
        # Combinaisons sur les photos communes
        for m in methodes:
            communs = set(vlm_res) & set(photos_par_methode[m])
            if communs:
                mix = {a: ((vlm_res[a][0] + photos_par_methode[m][a][0]) / 2, vlm_res[a][1]) for a in communs}
                s_mix = stats_erreurs(ecarts_de(mix))
                rapport.append(ligne_tableau(f"Moyenne vision locale + {NOMS[m]}", s_mix))
                candidats_verdict.append((s_mix["erreur_mediane"], f"moyenne vision locale + {NOMS[m]}"))
        rapport += ["", f"Vision locale : l'année vraie tombe dans la fourchette annoncée pour {dans} photos sur "
                        f"{len(lignes_vlm)} (largeur médiane : {larg} ans)."]
    rapport += ["", "\\* optimiste : biais calculé sur les mêmes scans (potentiel d'une calibration sur scans datés).", ""]
    ecrire_csv(OUT / "photos.csv", list(lignes_photos.values()))

    # Comparaison sur les photos communes à toutes les méthodes
    ensembles = [set(r) for r in photos_par_methode.values()] + ([set(vlm_res)] if vlm_res else [])
    if len(ensembles) > 1:
        communs = set.intersection(*ensembles)
        if communs:
            rapport += [f"### Sur les {len(communs)} photos datées par toutes les méthodes", "", *ENTETE]
            for m, res in photos_par_methode.items():
                rapport.append(ligne_tableau(NOMS[m], stats_erreurs(ecarts_de(res, communs))))
            if vlm_res:
                rapport.append(ligne_tableau(NOMS["vlm"], stats_erreurs(ecarts_de(vlm_res, communs))))
            rapport.append("")

    # 6. Verdict ---------------------------------------------------------------
    meilleur = min(candidats_verdict) if candidats_verdict else (float("nan"), "aucune")
    rapport += ["## 6. Verdict", "", verdict(meilleur[0], meilleur[1]), "",
                "Méthodes classées (erreur médiane sur l'année de la photo) :", ""]
    rapport += [f"{i}. {nom} : {err} ans" for i, (err, nom) in enumerate(sorted(candidats_verdict), 1)]
    rapport.append("")

    if sans_naissance:
        nommees = sorted(n for n in sans_naissance.values() if n != "(sans nom)")
        rapport += ["## 7. Personnes sans date de naissance", "",
                    f"- {len(sans_naissance) - len(nommees)} groupe(s) de visages sans nom",
                    *[f"- {n}" for n in nommees], ""]

    (OUT / "rapport.md").write_text("\n".join(rapport), encoding="utf-8")
    log("Terminé. Résultats dans resultats/ (rapport.md, visages.csv, photos.csv, vlm.csv).")
    print("\n".join(rapport), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
