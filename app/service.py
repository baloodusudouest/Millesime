"""Cœur de Millésime : synchronisation avec Immich, file de calcul, écriture, Nommer, frise, état."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import threading
from collections import OrderedDict
from datetime import datetime

from PIL import Image

from . import estimation as est
from .base import Base
from .config import Config
from .immich import ErreurImmich, Immich

log = logging.getLogger("millesime")


def maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


_DATE_DANS_NOM = re.compile(r"(?<!\d)((?:19|20)\d{2})[-_. ]?(0[1-9]|1[0-2])[-_. ]?(0[1-9]|[12]\d|3[01])(?!\d)")


# 2.4.0-2.5.0 : une date lue dans un nom de dossier, de sous-dossier ou d'album (jamais le nom du fichier) :
#   …/1983/01/…, …/1983-07 Vacances/…, « Noël 1992 chez mamie », « juillet 1985 », « 1989-1992 ».
_MOIS_NOMS = {"janv": 1, "janvier": 1, "fev": 2, "fevr": 2, "fevrier": 2, "mars": 3, "avr": 4, "avril": 4, "mai": 5,
              "juin": 6, "juil": 7, "juillet": 7, "aout": 8, "sept": 9, "septembre": 9, "oct": 10, "octobre": 10,
              "nov": 11, "novembre": 11, "dec": 12, "decembre": 12}
_MOIS_ANNEE = re.compile(r"\b(" + "|".join(sorted(_MOIS_NOMS, key=len, reverse=True)) + r")\.?\s+(1[89]\d{2}|20\d{2})\b")
_ANNEE_MOIS = re.compile(r"^(1[89]\d{2}|20\d{2})[-_. ](0[1-9]|1[0-2])(?:\b|$)")
_ANNEE = re.compile(r"(?<!\d)(1[89]\d{2}|20\d{2})(?!\d)")
_MOIS = re.compile(r"^(0[1-9]|1[0-2])(?:\b|$)")
ECART_MAX = 20                                       # « 1923-2023 » ne dit rien d'une photo
# un nom de lot dit quand la photo a été numérisée, importée ou sauvegardée, pas quand elle a été prise
_LOT = re.compile(r"\b(numeris\w*|scans?|scanne\w*|import\w*|sauvegardes?|backups?|exports?|telecharg\w*)\b")


def _sans_accents(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def date_d_un_nom(nom: str, suivant: str = "") -> str | None:
    """« AAAA-MM », « AAAA » ou « AAAA/AAAA » (une fourchette) lue dans un nom ; `suivant` : le sous-dossier
    qui suit, pour « …/1983/01/… ». None si le nom ne dit pas de date."""
    n = _sans_accents(nom.strip())
    if _LOT.search(n):
        return None                                  # « Numérisations 2010 » : l'année du scan, pas de la photo
    maintenant_ = datetime.now().year
    m = _MOIS_ANNEE.search(n)
    if m and int(m.group(2)) <= maintenant_:
        return f"{m.group(2)}-{_MOIS_NOMS[m.group(1)]:02d}"
    m = _ANNEE_MOIS.match(n)
    if m and int(m.group(1)) <= maintenant_:
        return f"{m.group(1)}-{m.group(2)}"
    annees = sorted({int(a) for a in _ANNEE.findall(n) if 1850 <= int(a) <= maintenant_})
    if not annees or annees[-1] - annees[0] > ECART_MAX:
        return None
    if len(annees) == 1:
        mois = _MOIS.match(suivant.strip()) if re.fullmatch(r"\d{4}", n) and suivant else None
        return f"{annees[0]}-{mois.group(1)}" if mois else str(annees[0])
    return f"{annees[0]}/{annees[-1]}"


def date_du_dossier(chemin: str | None) -> str | None:
    """La date du dossier le plus profond du chemin qui en porte une (le nom du fichier ne compte pas)."""
    morceaux = (chemin or "").replace("\\", "/").split("/")[:-1]
    trouvee = None
    for i, m in enumerate(morceaux):
        d = date_d_un_nom(m, morceaux[i + 1] if i + 1 < len(morceaux) else "")
        if d:
            trouvee = d
    return trouvee


def dossier_date(chemin: str | None) -> tuple[str, str] | None:
    """2.6.0 : (le dossier qui porte la date, la date) : « …/Noël 1992 » → (« …/Noël 1992 », « 1992 ») ; pour
    « …/1983/01/… », le dossier est « …/1983/01 ». None si aucun dossier du chemin ne porte de date."""
    morceaux = (chemin or "").replace("\\", "/").split("/")[:-1]
    trouve = None
    for i, m in enumerate(morceaux):
        suivant = morceaux[i + 1] if i + 1 < len(morceaux) else ""
        d = date_d_un_nom(m, suivant)
        if d:
            seul = date_d_un_nom(m) or ""
            fin = i + 2 if len(d) == 7 and len(seul) != 7 else i + 1     # le mois vient du sous-dossier « 01 »
            trouve = ("/".join(morceaux[:fin]), d)
    return trouve


def bornes(d: str) -> tuple[int, int]:
    """Les années couvertes par une date de nom : (1985, 1985) ou (1989, 1992)."""
    if "/" in d:
        a, b = d.split("/")
        return int(a), int(b)
    return int(d[:4]), int(d[:4])


def jour_du_dossier(d: str) -> str:
    """La date écrite : le 15 du mois, le 1er juillet pour une année seule, le 1er juillet de l'année du milieu
    pour une fourchette."""
    if len(d) == 7 and "/" not in d:
        return f"{d}-15"
    a, b = bornes(d)
    return f"{(a + b) // 2}-07-01"


def dates_connues(a: dict, deja_estime: bool = False) -> tuple[str | None, str | None]:
    """La date que la photo porte déjà, hors de toute estimation : celle d'Immich (EXIF) quand ce n'est pas
    le 1900 des scans non datés, et celle écrite dans le nom du fichier (AAAAMMJJ, AAAA-MM-JJ)."""
    brut = ((a.get("exifInfo") or {}).get("dateTimeOriginal") or a.get("localDateTime") or "")[:10]
    connue = brut if re.fullmatch(r"\d{4}-\d{2}-\d{2}", brut) and int(brut[:4]) > 1901 and not deja_estime else None
    m = _DATE_DANS_NOM.search(a.get("originalFileName") or "")
    du_nom = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m and int(m.group(1)) <= datetime.now().year else None
    return connue, du_nom


class ErreurMillesime(Exception):
    pass


class Cache(OrderedDict):
    def __init__(self, taille: int):
        super().__init__()
        self.taille = taille
        self.verrou = threading.Lock()

    def obtenir(self, cle, fabrique):
        with self.verrou:
            if cle in self:
                self.move_to_end(cle)
                return self[cle]
        val = fabrique()
        with self.verrou:
            self[cle] = val
            while len(self) > self.taille:
                self.popitem(last=False)
        return val


class Millesime:
    def __init__(self, cfg: Config, immich: Immich | None = None):
        self.cfg = cfg
        self.base = Base(cfg.etat_dir / "millesime.db")
        self.immich = immich or Immich(cfg.immich_url, cfg.immich_cle, cfg.lecture_seule)
        self.verrou_synchro = threading.Lock()
        self.apercus = Cache(24)
        self.vignettes = Cache(600)                  # 2.6.0 : grilles de « Datables par le nom »
        self.visages_immich = Cache(256)
        self.suggestions_cache = None

    # ------------------------------------------------------------------ synchro
    def synchroniser(self, complete: bool = False) -> dict:
        """Relit les scans « Non datée » et datés, leurs visages et les personnes, puis recalcule."""
        if not self.verrou_synchro.acquire(blocking=False):
            raise ErreurMillesime("Synchronisation déjà en cours.")
        try:
            debut = datetime.now()
            pref = self.cfg.tag_prefixe + "/"
            tags = self.immich.tags()
            non_datee = next((t for t in tags if (t.get("value") or "") == pref + self.cfg.tag_non_datee), None)
            if not non_datee:
                # 1.5.1 : un nom mal saisi dans la stack ne doit pas vider la liste des scans en silence
                raise ErreurMillesime(f"Le tag « {pref}{self.cfg.tag_non_datee} » est introuvable dans Immich : vérifie "
                                      "MILLESIME_TAG_PREFIXE et MILLESIME_TAG_NON_DATEE dans la stack. Rien n'a été modifié.")
            dates = []
            for t in tags:
                v = t.get("value") or ""
                m = re.fullmatch(re.escape(pref) + r"(\d{4})-(\d{2})(?:-(\d{2}))?", v)
                if m:
                    dates.append((t, f"{m.group(1)}-{m.group(2)}-{m.group(3) or '15'}"))
            estimees = set()
            for t in tags:
                if (t.get("value") or "").startswith(self.cfg.tag_estimee + "/"):
                    estimees.update(a["id"] for a in self.immich.rechercher({"tagIds": [t["id"]]}))

            vus = set()
            maj: dict[str, str] = {}                     # 2.4.0 : dernière modification de chaque photo dans Immich
            if non_datee:
                for a in self.immich.rechercher({"tagIds": [non_datee["id"]]}):
                    vus.add(a["id"])
                    maj[a["id"]] = a.get("updatedAt") or ""
                    envoi = est.parse_date(a.get("createdAt") or a.get("fileCreatedAt"))
                    self._enregistrer_scan(a["id"], "non_datee", None, envoi.isoformat() if envoi else None,
                                           envoi.year if envoi else None, a["id"] in estimees, chemin=a.get("originalPath"))
            for t, d in dates:
                for a in self.immich.rechercher({"tagIds": [t["id"]]}):
                    if a["id"] not in vus:
                        vus.add(a["id"])
                        maj[a["id"]] = a.get("updatedAt") or ""
                        self._enregistrer_scan(a["id"], "datee", d, None, None, False, chemin=a.get("originalPath"))
            # 2.2.0 : les albums et les dossiers choisis dans l'appli. Toutes leurs images sont à dater,
            # sauf celles déjà vues par un tag (le tag passe devant) ; une image déjà estimée est comptée faite.
            for src in self.base.tous("SELECT * FROM sources ORDER BY ajoutee_le"):
                try:
                    photos = self.immich.photos_album(src["ref"]) if src["sorte"] == "album" else self.immich.photos_dossier(src["ref"])
                except ErreurImmich as e:
                    # Un album supprimé ou un dossier parti (migration) : on garde ce qu'on connaît, on le dit
                    log.warning("Source illisible (%s) : %s", src["sorte"], e)
                    vus.update(r["asset_id"] for r in self.base.tous("SELECT asset_id FROM scans WHERE source=?", src["cle"]))
                    continue
                for a in photos:
                    if a["id"] in vus:
                        continue
                    vus.add(a["id"])
                    maj[a["id"]] = a.get("updatedAt") or ""
                    envoi = est.parse_date(a.get("createdAt") or a.get("fileCreatedAt"))
                    self._enregistrer_scan(a["id"], "non_datee", None, envoi.isoformat() if envoi else None,
                                           envoi.year if envoi else None, a["id"] in estimees, source=src["cle"],
                                           chemin=a.get("originalPath"))
                    connue, du_nom = dates_connues(a, a["id"] in estimees)
                    self.base.executer("UPDATE scans SET date_connue=?, date_nom=? WHERE asset_id=?", connue, du_nom, a["id"])
            # scans disparus d'Immich (ou retagués) : retirés
            for r in self.base.tous("SELECT asset_id FROM scans"):
                if r["asset_id"] not in vus:
                    self.base.executer("DELETE FROM visages WHERE asset_id=?", r["asset_id"])
                    self.base.executer("DELETE FROM scans WHERE asset_id=?", r["asset_id"])
            # 2.4.0 : la date écrite dans le chemin des dossiers ; 2.5.0 : à défaut, dans le titre d'un album
            par_album = self._dates_des_albums()
            for r in self.base.tous("SELECT asset_id, chemin, date_dossier, date_nom_source FROM scans"):
                d, src = date_du_dossier(r["chemin"]), "dossier"
                if not d and r["asset_id"] in par_album:
                    d, src = par_album[r["asset_id"]]
                src = src if d else None
                if (d, src) != (r["date_dossier"], r["date_nom_source"]):
                    self.base.executer("UPDATE scans SET date_dossier=?, date_nom_source=? WHERE asset_id=?", d, src, r["asset_id"])
            # 2.4.0 : synchro légère. Les visages ne sont relus que pour une photo changée dans Immich, jamais lue,
            # ou dont c'est le tour (chaque photo une fois par jour, réparties sur les 24 heures) ; `complete` : toutes.
            # Les noms, dates de naissance et masquages viennent d'une seule lecture des personnes.
            n_visages, relues, heure, lu_le = 0, 0, datetime.now().hour, maintenant()
            for r in self.base.tous("SELECT asset_id, maj_immich, visages_lus_le FROM scans WHERE statut <> 'validee' OR type='datee'"):
                m_ = maj.get(r["asset_id"], "")
                tour = int(hashlib.md5(r["asset_id"].encode()).hexdigest(), 16) % 24 == heure
                if complete or not r["visages_lus_le"] or m_ != (r["maj_immich"] or "") or tour:
                    n_visages += self._synchro_visages(r["asset_id"])
                    relues += 1
                    self.base.executer("UPDATE scans SET maj_immich=?, visages_lus_le=? WHERE asset_id=?", m_, lu_le, r["asset_id"])
            self._rafraichir_personnes()
            cal = est.calibrer(self.base)
            est.recalculer_propositions(self.base, self.cfg.seuil_doute)
            bilan = {"le": maintenant(), "duree_s": round((datetime.now() - debut).total_seconds(), 1),
                     "scans": len(vus), "visages": n_visages, "relues": relues, "complete": complete,
                     "calibrage": cal["version"] if cal else None}
            self.base.ecrire("derniere_synchro", bilan)
            log.info("Synchronisation : %s", bilan)
            return bilan
        finally:
            self.verrou_synchro.release()

    def _enregistrer_scan(self, asset_id, type_, date_tampon, lot, annee_envoi, deja_estime, source=None, chemin=None):
        existant = self.base.un("SELECT * FROM scans WHERE asset_id=?", asset_id)
        if chemin:                                       # 2.3.0 : pour filtrer « Dater » par dossier
            self.base.executer("UPDATE scans SET chemin=? WHERE asset_id=?", chemin, asset_id) if existant else None
        if existant:
            self.base.executer("UPDATE scans SET type=?, date_tampon=?, lot=COALESCE(?, lot), "
                               "annee_envoi=COALESCE(?, annee_envoi), source=? WHERE asset_id=?",
                               type_, date_tampon, lot, annee_envoi, source, asset_id)
            if deja_estime and existant["statut"] != "validee":
                self.base.executer("UPDATE scans SET statut='validee' WHERE asset_id=?", asset_id)
        else:
            self.base.executer("INSERT INTO scans(asset_id, type, date_tampon, lot, annee_envoi, statut, source, chemin) "
                               "VALUES(?,?,?,?,?,?,?,?)", asset_id, type_, date_tampon, lot, annee_envoi,
                               "validee" if deja_estime else ("a_analyser" if type_ == "non_datee" else "datee"), source,
                               chemin)

    def _dates_des_albums(self) -> dict[str, tuple[str, str]]:
        """2.5.0 : les photos des albums dont le titre porte une date (« Vacances 1985 », « juillet 1992 »).
        Une photo dans plusieurs albums datés prend la date la plus précise."""
        res: dict[str, tuple[str, str]] = {}
        try:
            albums = self.immich.albums()
        except ErreurImmich as e:
            log.warning("Albums illisibles : %s", e)
            return res
        precision = lambda d: (len(d) == 7 and "/" not in d, -(bornes(d)[1] - bornes(d)[0]))
        for al in albums:
            d = date_d_un_nom(al.get("albumName") or "")
            if not d:
                continue
            try:
                photos = self.immich.photos_album(al["id"])
            except ErreurImmich:
                continue
            for a in photos:
                avant = res.get(a["id"])
                if not avant or precision(d) > precision(avant[0]):
                    res[a["id"]] = (d, f"album:{al.get('albumName', '').strip()}")
        return res

    def _rafraichir_personnes(self) -> int:
        """2.4.0 : noms, dates de naissance et masquage des personnes des visages connus, en une lecture."""
        try:
            gens = {p["id"]: p for p in self.immich.personnes(masquees=True)}
        except ErreurImmich as e:
            log.warning("Personnes illisibles : %s", e)
            return 0
        changes = 0
        for v in self.base.tous("SELECT DISTINCT person_id, person_nom, naissance, person_masque FROM visages WHERE person_id IS NOT NULL"):
            p = gens.get(v["person_id"])
            if not p:
                continue                              # fusionnée ou supprimée : la relecture de ses photos le dira
            nom, naissance, masque = p.get("name") or None, p.get("birthDate") or None, 1 if p.get("isHidden") else 0
            if (nom, naissance, masque) != (v["person_nom"], v["naissance"], v["person_masque"]):
                self.base.executer("UPDATE visages SET person_nom=?, naissance=?, person_masque=? WHERE person_id=?",
                                   nom, naissance, masque, v["person_id"])
                changes += 1
        if changes:
            self.suggestions_cache = None
        return changes

    def _synchro_visages(self, asset_id: str) -> int:
        faces = self.immich.visages(asset_id)
        ids = set()
        for f in faces:
            p = f.get("person") or {}
            ids.add(f["id"])
            self.base.executer("""
                INSERT INTO visages(face_id, asset_id, person_id, person_nom, naissance, x1, y1, x2, y2, img_w, img_h,
                                    person_masque)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(face_id) DO UPDATE SET person_id=excluded.person_id, person_nom=excluded.person_nom,
                    naissance=excluded.naissance, x1=excluded.x1, y1=excluded.y1, x2=excluded.x2, y2=excluded.y2,
                    img_w=excluded.img_w, img_h=excluded.img_h, person_masque=excluded.person_masque""",
                f["id"], asset_id, p.get("id"), p.get("name") or None, (p.get("birthDate") or None),
                f["boundingBoxX1"], f["boundingBoxY1"], f["boundingBoxX2"], f["boundingBoxY2"],
                f.get("imageWidth"), f.get("imageHeight"), 1 if p.get("isHidden") else 0)
        for r in self.base.tous("SELECT face_id FROM visages WHERE asset_id=?", asset_id):
            if r["face_id"] not in ids:
                self.base.executer("DELETE FROM visages WHERE face_id=?", r["face_id"])
        return len(ids)

    # ------------------------------------------------------------------ calcul (PC)
    def taches(self, n: int = 20) -> list[dict]:
        """Visages à calculer : personne avec date de naissance, âge encore inconnu. Scans datés d'abord (calibrage)."""
        lignes = self.base.tous("""
            SELECT v.face_id, v.asset_id, v.x1, v.y1, v.x2, v.y2, v.img_w, v.img_h FROM visages v
            JOIN scans s ON s.asset_id = v.asset_id
            WHERE v.naissance IS NOT NULL AND v.age_visage IS NULL AND s.statut <> 'validee'
              AND (v.calcule_le IS NULL OR v.calcule_le <> 'erreur')
            ORDER BY CASE s.type WHEN 'datee' THEN 0 ELSE 1 END, v.asset_id LIMIT ?""", n)
        return [{"face_id": l["face_id"], "asset_id": l["asset_id"],
                 "boite": {"x1": l["x1"], "y1": l["y1"], "x2": l["x2"], "y2": l["y2"],
                           "imageWidth": l["img_w"], "imageHeight": l["img_h"]}} for l in lignes]

    VEILLE_SYNCHRO_MINUTES = 15      # relecture d'Immich déclenchée par le PC en veille, au plus souvent
    PC_ACTIF_MINUTES = 12            # le PC est « en veille » s'il a demandé du travail récemment

    def signal_pc(self, veille: bool, machine: str = "") -> dict:
        """Le calculateur vient demander du travail : on le note et, en veille avec une file vide,
        on relance une synchronisation Immich (en arrière-plan) si la dernière date de plus de 15 min."""
        self.base.ecrire("pc_vu", {"le": maintenant(), "veille": bool(veille), "machine": machine[:80]})
        lancee = False
        t = self.compter_taches()
        self._suivre_passe(t["calibrage"] + t["a_dater"])
        if veille and not (t["calibrage"] + t["a_dater"]):
            derniere = (self.base.lire("derniere_synchro") or {}).get("le")
            age = (datetime.now() - datetime.fromisoformat(derniere)).total_seconds() / 60 if derniere else 1e9
            if age >= self.VEILLE_SYNCHRO_MINUTES and not self.verrou_synchro.locked():
                def _synchro():
                    try:
                        self.synchroniser()
                    except Exception as e:  # noqa: BLE001
                        log.warning("Synchronisation demandée par le PC en échec : %s", e)
                threading.Thread(target=_synchro, daemon=True).start()
                lancee = True
        return {"synchro_lancee": lancee}

    def _suivre_passe(self, restants: int, fini: bool = False) -> None:
        """Mémorise l'avancement du calcul en cours (pour la barre de progression)."""
        passe = self.base.lire("pc_passe")
        en_cours = passe and not passe.get("fini")
        if fini or not restants:
            if en_cours:
                self.base.ecrire("pc_passe", {**passe, "restants": 0, "fini": maintenant()})
            return
        if en_cours and (datetime.now() - datetime.fromisoformat(passe.get("maj", passe["debut"]))).total_seconds() > 900:
            en_cours = False   # passe interrompue (PC éteint en route) : on repart de zéro pour l'estimation
        if not en_cours:
            passe = {"debut": maintenant(), "total": restants}
        passe["total"] = max(passe["total"], restants)   # de nouveaux visages peuvent arriver en route
        passe.update(restants=restants, maj=maintenant())
        self.base.ecrire("pc_passe", passe)

    def etat_pc(self) -> dict:
        """État du calculateur pour l'interface :
        indisponible (pas de contact depuis 12 min), disponible (rien à calculer),
        en_attente (des visages attendent, le PC les prendra à son prochain passage, ≤ 5 min),
        en_cours (calcul en route, avec avancement et temps restant estimé)."""
        pc = self.pc_actif()
        t = self.compter_taches()
        restants = t["calibrage"] + t["a_dater"]
        if not pc:
            return {"etat": "jamais_vu", "restants": restants}
        base = {"machine": pc.get("machine") or "", "le": pc["le"], "il_y_a_min": pc["il_y_a_min"], "restants": restants}
        if not pc["actif"]:
            return {**base, "etat": "indisponible"}
        if not restants:
            return {**base, "etat": "disponible"}
        passe = self.base.lire("pc_passe")
        if not passe or passe.get("fini"):
            return {**base, "etat": "en_attente"}
        total = max(passe["total"], restants)
        fait = total - restants
        ecoule = (datetime.now() - datetime.fromisoformat(passe["debut"])).total_seconds()
        reste_min = round(ecoule / fait * restants / 60) if fait else None
        return {**base, "etat": "en_cours", "total": total, "fait": fait,
                "pourcentage": round(100 * fait / total) if total else 0, "reste_min": reste_min,
                "debut": passe["debut"]}

    def pc_actif(self) -> dict | None:
        vu = self.base.lire("pc_vu")
        if not vu:
            return None
        minutes = (datetime.now() - datetime.fromisoformat(vu["le"])).total_seconds() / 60
        return {**vu, "il_y_a_min": round(minutes), "actif": minutes <= self.PC_ACTIF_MINUTES}

    def compter_taches(self) -> dict:
        r = self.base.un("""
            SELECT SUM(CASE WHEN s.type='datee' THEN 1 ELSE 0 END) AS datees,
                   SUM(CASE WHEN s.type='non_datee' THEN 1 ELSE 0 END) AS non_datees
            FROM visages v JOIN scans s ON s.asset_id = v.asset_id
            WHERE v.naissance IS NOT NULL AND v.age_visage IS NULL AND s.statut <> 'validee'
              AND (v.calcule_le IS NULL OR v.calcule_le <> 'erreur')""") or {}
        return {"calibrage": r.get("datees") or 0, "a_dater": r.get("non_datees") or 0}

    def recevoir_resultats(self, resultats: list[dict]) -> dict:
        n = 0
        with self.base.transaction() as cx:
            for r in resultats:
                if r.get("age_visage") is None:
                    # échec du calcul sur ce visage : marqué pour ne pas le redemander en boucle
                    cx.execute("UPDATE visages SET calcule_le='erreur' WHERE face_id=?", (r.get("face_id"),))
                    continue
                n += cx.execute(
                    "UPDATE visages SET age_visage=?, age_corps=?, calcule_le=? WHERE face_id=?",
                    (float(r["age_visage"]), None if r.get("age_corps") is None else float(r["age_corps"]),
                     maintenant(), r["face_id"])).rowcount
        self.base.ecrire("dernier_calcul", {"le": maintenant(), "recus": n, **self.compter_taches()})
        if n:
            est.calibrer(self.base)
            est.recalculer_propositions(self.base, self.cfg.seuil_doute)
        t = self.compter_taches()
        self._suivre_passe(t["calibrage"] + t["a_dater"])
        vu = self.base.lire("pc_vu")
        if vu:
            self.base.ecrire("pc_vu", {**vu, "le": maintenant()})
        return {"enregistres": n, "restants": t}

    # ------------------------------------------------------------------ images
    def vignette(self, asset_id: str) -> bytes:
        return self.vignettes.obtenir(asset_id, lambda: self.immich.vignette(asset_id))

    def apercu(self, asset_id: str) -> bytes:
        return self.apercus.obtenir(asset_id, lambda: self.immich.apercu(asset_id))

    def visage_jpeg(self, asset_id: str, face_id: str, taille: int = 192) -> bytes:
        """Vignette carrée d'un visage (1,4 × la boîte), recadrée dans l'aperçu Immich."""
        v = self.base.un("SELECT * FROM visages WHERE face_id=?", face_id)
        if not v:
            faces = self.visages_immich.obtenir(asset_id, lambda: self.immich.visages(asset_id))
            f = next((x for x in faces if x["id"] == face_id), None)
            if not f:
                raise ErreurMillesime("Visage introuvable.")
            v = {"x1": f["boundingBoxX1"], "y1": f["boundingBoxY1"], "x2": f["boundingBoxX2"],
                 "y2": f["boundingBoxY2"], "img_w": f.get("imageWidth"), "img_h": f.get("imageHeight")}
        img = Image.open(io.BytesIO(self.apercu(asset_id))).convert("RGB")
        sx = img.width / max(1, v["img_w"] or img.width)
        sy = img.height / max(1, v["img_h"] or img.height)
        x1, y1, x2, y2 = v["x1"] * sx, v["y1"] * sy, v["x2"] * sx, v["y2"] * sy
        cote = max(x2 - x1, y2 - y1) * 1.4
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        crop = img.crop(tuple(int(round(c)) for c in (cx - cote / 2, cy - cote / 2, cx + cote / 2, cy + cote / 2)))
        crop = crop.resize((taille, taille), Image.LANCZOS)
        buf = io.BytesIO()
        crop.save(buf, "JPEG", quality=85)
        return buf.getvalue()

    def boite_visage(self, asset_id: str, face_id: str) -> dict:
        """Boîte d'un visage en fractions de l'image (0-1), pour l'encadrer sur la photo en grand."""
        v = self.base.un("SELECT x1, y1, x2, y2, img_w, img_h, person_nom FROM visages WHERE face_id=?", face_id)
        if not v:
            faces = self.visages_immich.obtenir(asset_id, lambda: self.immich.visages(asset_id))
            f = next((x for x in faces if x["id"] == face_id), None)
            if not f:
                raise ErreurMillesime("Visage introuvable.")
            v = {"x1": f["boundingBoxX1"], "y1": f["boundingBoxY1"], "x2": f["boundingBoxX2"], "y2": f["boundingBoxY2"],
                 "img_w": f.get("imageWidth"), "img_h": f.get("imageHeight"),
                 "person_nom": (f.get("person") or {}).get("name")}
        w, h = v["img_w"] or 1, v["img_h"] or 1
        return {"x": v["x1"] / w, "y": v["y1"] / h, "l": (v["x2"] - v["x1"]) / w, "h": (v["y2"] - v["y1"]) / h,
                "nom": v.get("person_nom") or ""}

    # ------------------------------------------------------------------ écrans
    def accueil(self) -> dict:
        c = {r["statut"]: r["n"] for r in self.base.tous(
            "SELECT statut, COUNT(*) AS n FROM scans WHERE type='non_datee' GROUP BY statut")}
        cal = self.base.un("SELECT version, cree_le, n_visages, cv_mediane, cv_3ans FROM calibrages "
                           "ORDER BY version DESC LIMIT 1")
        return {"compteurs": {"a_analyser": c.get("a_analyser", 0), "a_dater": c.get("a_dater", 0),
                              "a_trancher": c.get("a_trancher", 0), "validees": c.get("validee", 0),
                              "plusieurs": c.get("plusieurs", 0), "total": sum(c.values()),
                              "a_nommer": len(self.groupes_a_nommer()),
                              "sans_naissance": len(self.sans_naissance()),
                              "suspects": len(est.suspects(self.base, self.cfg.seuil_suspect)),
                              "datables": len(self.datables())},
                "taches": self.compter_taches(), "calibrage": cal,
                "derniere_synchro": self.base.lire("derniere_synchro"),
                "pc": self.etat_pc(),
                "dernier_calcul": self.base.lire("dernier_calcul")}

    def datables(self) -> list[dict]:
        """2.5.0 : les photos qu'un nom de dossier, de sous-dossier ou d'album date : sans visage pour dater, ou dont
        les visages disent la même chose que le nom. Celles où les visages le contredisent n'y sont pas."""
        res = []
        for r in self.base.tous("SELECT * FROM scans WHERE type='non_datee' AND statut IN ('a_dater', 'a_trancher') "
                                "AND date_dossier IS NOT NULL ORDER BY asset_id"):
            c = self._comparer(r)
            if (r.get("raison") or "").startswith("date lue dans") or (c and c["coherent"]):
                res.append(r)
        return res

    def _groupe_de(self, r: dict) -> tuple[str, str, str, str]:
        """(clé, sorte, nom, date) du dossier ou de l'album qui date la photo."""
        src = r.get("date_nom_source") or "dossier"
        if src.startswith("album:"):
            return src, "album", src[6:], r["date_dossier"]
        dd = dossier_date(r.get("chemin")) or ((r.get("chemin") or "").rsplit("/", 1)[0], r["date_dossier"])
        return f"dossier:{dd[0]}", "dossier", dd[0], r["date_dossier"]

    def groupes_datables(self) -> list[dict]:
        """2.6.0 : les dossiers et les albums qui datent des photos, avec leur date et le nombre de photos."""
        g: dict[str, dict] = {}
        for r in self.datables():
            cle, sorte, nom, d = self._groupe_de(r)
            x = g.setdefault(cle, {"cle": cle, "sorte": sorte, "nom": nom, "date": d, "n": 0, "sans_visage": 0})
            x["n"] += 1
            x["sans_visage"] += 1 if (r.get("raison") or "").startswith("date lue dans") else 0
        return sorted(g.values(), key=lambda x: (x["date"], x["nom"].lower()))

    def photos_groupe(self, cle: str) -> list[dict]:
        return [{"asset_id": r["asset_id"], "fichier": (r.get("chemin") or "").rsplit("/", 1)[-1],
                 "annee_proposee": r["annee_proposee"], "marge": r["marge"], "raison": r["raison"]}
                for r in self.datables() if self._groupe_de(r)[0] == cle]

    def dater_par_nom(self, lot: str, n: int = 100, groupe: str | None = None) -> dict:
        """2.5.0 : « Tout dater d'un coup » par lots de `n` : chaque photo prend la date de son nom (écrite dans Immich,
        notée au journal avec le numéro du lot, pour tout annuler d'un geste)."""
        faites, erreurs = 0, []
        choix = [r for r in self.datables() if not groupe or self._groupe_de(r)[0] == groupe]
        for r in choix[:n]:
            try:
                self.garder_date(r["asset_id"], "dossier", lot=lot)
                faites += 1
            except ErreurMillesime as e:
                erreurs.append(str(e))
                if len(erreurs) >= 3:
                    break
        reste = [r for r in self.datables() if not groupe or self._groupe_de(r)[0] == groupe]
        return {"lot": lot, "faites": faites, "restant": len(reste), "erreurs": erreurs[:3]}

    def annuler_lot(self, lot: str) -> dict:
        """Annule toutes les écritures d'un lot, de la plus récente à la plus ancienne."""
        ids = [j["id"] for j in self.base.tous("SELECT id, apres FROM journal WHERE annule_le IS NULL ORDER BY id DESC")
               if json.loads(j["apres"] or "{}").get("lot") == lot]
        faites, erreurs = 0, []
        for jid in ids:
            try:
                self.annuler(jid)
                faites += 1
            except (ErreurMillesime, ErreurImmich) as e:
                erreurs.append(str(e))
        return {"annulees": faites, "erreurs": erreurs[:3]}

    def liste(self, statut: str) -> list[dict]:
        ordre = "marge ASC, asset_id" if statut == "a_dater" else "asset_id"
        # 2.3.0 : chemin (dossier + fichier) et noms des personnes sur la photo, pour filtrer la liste
        noms: dict[str, list[str]] = {}
        for v in self.base.tous("SELECT asset_id, person_nom FROM visages WHERE person_nom IS NOT NULL AND person_nom <> ''"):
            noms.setdefault(v["asset_id"], []).append(v["person_nom"])
        if statut == "datables":
            lignes = [{k: r[k] for k in ("asset_id", "annee_proposee", "marge", "raison", "source", "chemin")} for r in self.datables()]
        else:
            lignes = self.base.tous(f"SELECT asset_id, annee_proposee, marge, raison, source, chemin FROM scans "
                                    f"WHERE type='non_datee' AND statut=? ORDER BY {ordre}", statut)
        return [{**r, "origine": (r.pop("source") or "tag:").split(":", 1)[0], "noms": sorted(set(noms.get(r["asset_id"], [])))}
                for r in lignes]

    def scan(self, asset_id: str) -> dict:
        s = self.base.un("SELECT * FROM scans WHERE asset_id=?", asset_id)
        if not s:
            raise ErreurMillesime("Scan inconnu.")
        s["details"] = json.loads(s["details"] or "{}")
        s["visages"] = self.base.tous("SELECT face_id, person_id, person_nom, naissance, x1, y1, x2, y2, img_w, img_h, "
                                      "age_visage, age_corps, person_masque FROM visages WHERE asset_id=?", asset_id)
        # État de chaque visage, vérifié en direct auprès d'Immich (sans modifier la base : la synchro s'en charge)
        try:
            live = {f["id"]: f for f in self.immich.visages(asset_id)}
        except ErreurImmich:
            live = None
        for v in s["visages"]:
            f = live.get(v["face_id"]) if live is not None else None
            p = (f or {}).get("person") or {}
            if live is not None and f is None:
                v["etat"] = "supprime"        # n'existe plus dans Immich depuis la dernière synchro
            elif not (p.get("id") if f else v["person_id"]):
                v["etat"] = "non_attribue"    # détecté par Immich, rattaché à aucune personne
            elif (p.get("isHidden") if f else v["person_masque"]):
                v["etat"] = "masque"          # personne masquée dans Immich
            elif not (p.get("name") if f else v["person_nom"]):
                v["etat"] = "groupe_sans_nom"
            else:
                v["etat"] = "nomme"
        s["origine"] = (s.get("source") or "tag:").split(":", 1)[0]
        s["comparaison"] = self._comparer(s)
        etats = {v["face_id"]: v["etat"] for v in s["visages"]}
        s["lien_immich"] = f"{self.cfg.immich_lien}/photos/{asset_id}"
        # groupes sans nom présents sur la photo, avec leur nombre total de visages (pour les nommer sur place)
        s["a_nommer"] = self.base.tous(f"""
            SELECT v.person_id, MIN(v.face_id) AS face_id, ? AS asset_id,
                   (SELECT COUNT(*) FROM visages w WHERE w.person_id = v.person_id) AS visages
            FROM visages v WHERE v.asset_id=? AND v.person_id IS NOT NULL
              AND (v.person_nom IS NULL OR v.person_nom = '')
            GROUP BY v.person_id""", asset_id, asset_id)
        for g in s["a_nommer"]:
            g["exemples"] = [{"face_id": g["face_id"], "asset_id": asset_id}]
            g["lien_immich"] = f"{self.cfg.immich_lien}/people/{g['person_id']}"
        # un groupe dont tous les visages de la photo ont disparu d'Immich n'est plus à nommer ici
        s["a_nommer"] = [g for g in s["a_nommer"] if any(
            etats.get(v["face_id"]) in ("groupe_sans_nom", "masque") for v in s["visages"] if v["person_id"] == g["person_id"])]
        for g in s["a_nommer"]:
            g["masque"] = any(etats.get(v["face_id"]) == "masque" for v in s["visages"] if v["person_id"] == g["person_id"])
        s["sans_personne"] = [{"face_id": v["face_id"], "etat": v["etat"]} for v in s["visages"]
                              if v["etat"] in ("non_attribue", "supprime")]
        return s

    @staticmethod
    def _comparer(s: dict) -> dict | None:
        """2.2.0 : la photo porte déjà une date (Immich, nom du fichier). On la met en regard de l'estimation,
        on dit s'il y a une incohérence, et c'est l'utilisateur qui choisit."""
        connue, du_nom, dossier = s.get("date_connue"), s.get("date_nom"), s.get("date_dossier")
        if not connue and not du_nom and not dossier:
            return None
        estimee, marge = s.get("annee_proposee"), s.get("marge") or 0
        if (s.get("raison") or "").startswith("date lue dans"):
            estimee = None                           # la proposition vient du nom lui-même : rien à comparer
        # chaque date connue couvre une ou plusieurs années (une fourchette « 1989/1992 » lue dans un nom)
        plages = [(int(d[:4]), int(d[:4])) for d in (connue, du_nom) if d] + ([bornes(dossier)] if dossier else [])
        distance = lambda a, p: 0 if p[0] <= a <= p[1] else min(abs(a - p[0]), abs(a - p[1]))
        ecart = max(distance(estimee, p) for p in plages) if estimee is not None else None
        entre_elles = len(plages) > 1 and max(p[0] for p in plages) > min(p[1] for p in plages)
        if estimee is None:
            coherent, phrase = (None if not entre_elles else False,
                                "Les dates connues ne disent pas la même année." if entre_elles
                                else "Aucun visage pour vérifier cette date." if dossier and not connue and not du_nom
                                else "Pas encore d'estimation à comparer.")
        elif ecart > marge + 1 or entre_elles:
            coherent = False
            phrase = (f"Incohérence : {ecart} an{'s' if ecart > 1 else ''} d'écart avec l'estimation ({estimee} ±{marge})."
                      if ecart > marge + 1 else "Les dates connues ne disent pas la même année.")
        else:
            coherent, phrase = True, f"Cohérent avec l'estimation ({estimee} ±{marge})."
        source = s.get("date_nom_source") or ("dossier" if dossier else None)
        return {"date_connue": connue, "date_nom": du_nom if du_nom != connue else None, "date_dossier": dossier,
                "date_dossier_source": ("l'album « " + source[6:] + " »") if source and source.startswith("album:") else "le dossier",
                "annee_estimee": estimee,
                "marge": marge if estimee is not None else None, "coherent": coherent, "phrase": phrase}

    def garder_date(self, asset_id: str, laquelle: str, lot: str | None = None) -> dict:
        """La photo garde sa date d'Immich (rien n'est écrit), ou prend celle de son nom de fichier (une écriture,
        annulable). Dans les deux cas elle est comptée comme datée."""
        s = self.base.un("SELECT * FROM scans WHERE asset_id=? AND type='non_datee'", asset_id)
        if not s:
            raise ErreurMillesime("Scan inconnu.")
        choisie = {"actuelle": s.get("date_connue"), "nom": s.get("date_nom"),
                   "dossier": jour_du_dossier(s["date_dossier"]) if s.get("date_dossier") else None}.get(laquelle)
        if not choisie:
            raise ErreurMillesime("Cette photo n'a pas cette date.")
        avant = {"statut": s["statut"]}
        apres = {"origine": laquelle, "date_gardee": choisie, **({"lot": lot} if lot else {})}
        ecrit = laquelle in ("nom", "dossier")
        if ecrit:
            a = self.immich.asset(asset_id)
            avant["date"] = (a.get("exifInfo") or {}).get("dateTimeOriginal") or a.get("localDateTime")
            apres["date"] = f"{choisie}T12:00:00.000Z"
        jid = self.base.executer("INSERT INTO journal(asset_id, action, avant, apres, le) VALUES(?,?,?,?,?)",
                                 asset_id, "valider" if ecrit else "garder", json.dumps(avant), json.dumps(apres), maintenant())
        if ecrit:
            try:
                self.immich.changer_date(asset_id, apres["date"])
            except ErreurImmich as e:
                apres["erreur"] = str(e)
                self.base.executer("UPDATE journal SET apres=? WHERE id=?", json.dumps(apres), jid)
                raise ErreurMillesime(f"Écriture interrompue ({e}). Voir le journal pour annuler.") from e
        self.base.executer("UPDATE scans SET statut='validee', annee_validee=?, vu_le=? WHERE asset_id=?",
                           int(choisie[:4]), maintenant(), asset_id)
        if s.get("source"):
            apres["demande"] = self._demande_si_fini(s["source"])
        return {"journal": jid, **apres}

    def actualiser_scan(self, asset_id: str) -> dict:
        """Relit tout de suite dans Immich les visages et les noms d'une photo, puis recalcule sa proposition."""
        s = self.base.un("SELECT * FROM scans WHERE asset_id=?", asset_id)
        if not s:
            raise ErreurMillesime("Scan inconnu.")
        avant = {v["face_id"]: (v["person_id"], v["person_nom"]) for v in
                 self.base.tous("SELECT face_id, person_id, person_nom FROM visages WHERE asset_id=?", asset_id)}
        self.visages_immich.pop(asset_id, None)
        self._synchro_visages(asset_id)
        apres = {v["face_id"]: (v["person_id"], v["person_nom"]) for v in
                 self.base.tous("SELECT face_id, person_id, person_nom FROM visages WHERE asset_id=?", asset_id)}
        personnes = {p for p, _ in list(avant.values()) + list(apres.values()) if p}
        for pid in personnes:
            self.base.executer("DELETE FROM frises WHERE person_id=?", pid)
        if s["type"] == "non_datee" and s["statut"] not in ("validee", "plusieurs"):
            version, p = est.calibrage_courant(self.base)
            r = est.proposer(self.base, s, version, p, self.cfg.seuil_doute)
            self.base.executer("UPDATE scans SET statut=?, annee_proposee=?, marge=?, raison=?, details=? WHERE asset_id=?",
                               r["statut"], r["annee_proposee"], r["marge"], r["raison"], json.dumps(r["details"]), asset_id)
        self.suggestions_cache = None
        nouveaux = [f for f in apres if f not in avant]
        changes = [f for f in apres if f in avant and avant[f] != apres[f]]
        return {"nouveaux": len(nouveaux), "changes": len(changes), "retires": len([f for f in avant if f not in apres]),
                "a_calculer": self.base.valeur("SELECT COUNT(*) FROM visages WHERE asset_id=? AND naissance IS NOT NULL "
                                               "AND age_visage IS NULL", asset_id)}

    # ------------------------------------------------------------------ écriture
    def _album_par_nom(self, nom: str) -> dict | None:
        return next((a for a in self.immich.albums() if a.get("albumName") == nom), None)

    def valider(self, asset_id: str, annee: int, marge: int) -> dict:
        s = self.base.un("SELECT * FROM scans WHERE asset_id=? AND type='non_datee'", asset_id)
        if not s:
            raise ErreurMillesime("Scan inconnu.")
        annee, marge = int(annee), max(0, int(marge))
        if not 1880 <= annee <= datetime.now().year:
            raise ErreurMillesime("Année hors bornes.")
        if s["annee_envoi"] and annee > s["annee_envoi"]:
            raise ErreurMillesime(f"Année postérieure à l'envoi du scan ({s['annee_envoi']}).")
        a = self.immich.asset(asset_id)
        tags_estimes = [t for t in (a.get("tags") or [])
                        if (t.get("value") or "").startswith(self.cfg.tag_estimee + "/")]
        albums_avant = [{"id": al["id"], "nom": al.get("albumName")} for al in self.immich.albums(asset_id)]
        avant = {"date": (a.get("exifInfo") or {}).get("dateTimeOriginal") or a.get("localDateTime"),
                 "tags_estimes": [{"id": t["id"], "valeur": t.get("value")} for t in tags_estimes],
                 "albums": albums_avant, "statut": s["statut"]}
        apres = {"date": f"{annee}-07-01T12:00:00.000Z", "tag": f"{self.cfg.tag_estimee}/{annee} ±{marge}"}
        if not s.get("source"):
            if not self.modele_album or not self.album_non_datees:
                raise ErreurMillesime("Les deux noms d'albums des scans ne sont pas réglés : renseigne-les dans Réglages. Rien n'a été modifié.")
            apres["album"] = self.modele_album.format(annee=annee)
        jid = self.base.executer("INSERT INTO journal(asset_id, action, avant, apres, le) VALUES(?,?,?,?,?)",
                                 asset_id, "valider", json.dumps(avant), json.dumps(apres), maintenant())
        try:
            for t in tags_estimes:
                self.immich.detaguer(t["id"], [asset_id])
            self.immich.changer_date(asset_id, apres["date"])
            tag = self.immich.tag_existant_ou_cree(apres["tag"])
            self.immich.taguer(tag["id"], [asset_id])
            apres["tag_id"] = tag["id"]
            if not s.get("source"):
                # Un scan tagué quitte l'album des non datées pour celui de son année.
                # Une photo d'un album ou d'un dossier choisi reste où elle est (2.2.0) : date et tag seulement.
                nd = next((al for al in albums_avant if al["nom"] == self.album_non_datees), None)
                if nd:
                    self.immich.retirer_album(nd["id"], [asset_id])
                album = self._album_par_nom(apres["album"])
                if album:
                    self.immich.ajouter_album(album["id"], [asset_id])
                else:
                    album = self.immich.creer_album(apres["album"], [asset_id])
                apres["album_id"] = album["id"]
        except ErreurImmich as e:
            apres["erreur"] = str(e)
            self.base.executer("UPDATE journal SET apres=? WHERE id=?", json.dumps(apres), jid)
            raise ErreurMillesime(f"Écriture interrompue ({e}). Voir le journal pour annuler.") from e
        self.base.executer("UPDATE journal SET apres=? WHERE id=?", json.dumps(apres), jid)
        self.base.executer("UPDATE scans SET statut='validee', annee_validee=?, vu_le=? WHERE asset_id=?",
                           annee, maintenant(), asset_id)
        if s.get("source"):
            apres["demande"] = self._demande_si_fini(s["source"])
        return {"journal": jid, **apres}

    def plusieurs_annees(self, asset_id: str) -> dict:
        s = self.base.un("SELECT statut FROM scans WHERE asset_id=? AND type='non_datee'", asset_id)
        if not s:
            raise ErreurMillesime("Scan inconnu.")
        jid = self.base.executer("INSERT INTO journal(asset_id, action, avant, apres, le) VALUES(?,?,?,?,?)",
                                 asset_id, "plusieurs", json.dumps({"statut": s["statut"]}),
                                 json.dumps({"statut": "plusieurs"}), maintenant())
        self.base.executer("UPDATE scans SET statut='plusieurs', vu_le=? WHERE asset_id=?", maintenant(), asset_id)
        return {"journal": jid}

    # ------------------------------------------------------------------ réglages et sources (2.2.0)
    @property
    def album_non_datees(self) -> str:
        return self.base.lire("album_non_datees") or self.cfg.album_non_datees

    @property
    def modele_album(self) -> str:
        return self.base.lire("modele_album") or self.cfg.modele_album

    def regler_albums(self, album_non_datees: str, modele_album: str) -> dict:
        album_non_datees, modele_album = (album_non_datees or "").strip(), (modele_album or "").strip()
        if not album_non_datees:
            raise ErreurMillesime("Le nom de l'album des scans non datés est vide.")
        if "{annee}" not in modele_album:
            raise ErreurMillesime("Le modèle d'album doit contenir {annee}, par exemple « {annee} Numérisation ».")
        self.base.ecrire("album_non_datees", album_non_datees)
        self.base.ecrire("modele_album", modele_album)
        return self.sources()

    def _source(self, cle: str) -> dict:
        src = self.base.un("SELECT * FROM sources WHERE cle=?", cle)
        if not src:
            raise ErreurMillesime("Source inconnue.")
        return src

    def sources(self, avec_choix: bool = False) -> dict:
        """Ce que Millésime date : les scans tagués, et les albums et dossiers choisis ici."""
        comptes = {r["source"]: r for r in self.base.tous(
            "SELECT source, COUNT(*) AS total, SUM(statut='validee') AS faites FROM scans "
            "WHERE type='non_datee' GROUP BY source")}
        tag = comptes.get(None, {"total": 0, "faites": 0})
        liste = [{**s, "total": (comptes.get(s["cle"]) or {}).get("total", 0), "faites": (comptes.get(s["cle"]) or {}).get("faites") or 0}
                 for s in self.base.tous("SELECT * FROM sources ORDER BY sorte, nom")]
        sortie = {"tag": {"nom": f"{self.cfg.tag_prefixe}/{self.cfg.tag_non_datee}", "total": tag["total"], "faites": tag["faites"] or 0},
                  "sources": liste,
                  "albums": {"non_datees": self.album_non_datees, "modele": self.modele_album,
                             "depuis_la_stack": not self.base.lire("album_non_datees") and bool(self.cfg.album_non_datees)},
                  "transhumance": bool(self.cfg.jeton_transhumance)}
        if avec_choix:
            pris = {s["cle"] for s in liste}
            sortie["choix"] = {
                "albums": sorted(({"id": a["id"], "nom": a.get("albumName") or "", "nombre": a.get("assetCount", 0)}
                                  for a in self.immich.albums() if "album:" + a["id"] not in pris),
                                 key=lambda a: a["nom"].casefold()),
                "dossiers": [d for d in self.immich.dossiers() if "dossier:" + d not in pris]}
        return sortie

    def ajouter_sources(self, sorte: str, refs: list[str]) -> dict:
        """Ajoute des albums ou des dossiers à dater. Lecture seule d'Immich : rien n'y est écrit."""
        if sorte not in ("album", "dossier") or not refs:
            raise ErreurMillesime("Choix invalide.")
        if sorte == "album":
            connus = {a["id"]: a.get("albumName") or "" for a in self.immich.albums()}
        else:
            connus = {d: d.rstrip("/").rsplit("/", 1)[-1] for d in self.immich.dossiers()}
        for ref in refs:
            if ref not in connus:
                raise ErreurMillesime("Album ou dossier inconnu d'Immich : recharge la liste.")
            self.base.executer("INSERT OR IGNORE INTO sources(cle, sorte, ref, nom, ajoutee_le) VALUES(?,?,?,?,?)",
                               f"{sorte}:{ref}", sorte, ref, connus[ref], maintenant())
        return self.sources()

    def retirer_source(self, cle: str) -> dict:
        """Retire une source. Ses photos pas encore datées quittent Millésime ; celles déjà datées gardent
        leur date dans Immich et leur ligne au journal."""
        self._source(cle)
        for r in self.base.tous("SELECT asset_id FROM scans WHERE source=? AND statut<>'validee'", cle):
            self.base.executer("DELETE FROM visages WHERE asset_id=?", r["asset_id"])
            self.base.executer("DELETE FROM scans WHERE asset_id=?", r["asset_id"])
        self.base.executer("UPDATE scans SET source=NULL WHERE source=?", cle)
        self.base.executer("DELETE FROM sources WHERE cle=?", cle)
        return self.sources()

    def _demande_si_fini(self, cle: str) -> str:
        """Un dossier choisi dont toutes les photos sont datées : la demande de passage part vers Transhumance.
        Rend ce qui s'est passé, en clair ; ne lève jamais (la validation est déjà écrite)."""
        src = self.base.un("SELECT * FROM sources WHERE cle=?", cle)
        if not src or src["sorte"] != "dossier" or src["demandee_le"]:
            return ""
        reste = self.base.valeur("SELECT COUNT(*) FROM scans WHERE source=? AND statut<>'validee'", cle)
        if reste:
            return ""
        try:
            return self.demander_passage(cle)
        except ErreurMillesime as e:
            return str(e)

    def demander_passage(self, cle: str) -> str:
        """Demande à Transhumance de faire passer ce dossier. Transhumance le note et le montre ;
        il ne lance rien de lui-même."""
        import requests
        src = self._source(cle)
        if src["sorte"] != "dossier":
            raise ErreurMillesime("Seul un dossier se demande à Transhumance : un album est déjà dans Immich.")
        if not self.cfg.jeton_transhumance:
            raise ErreurMillesime("Transhumance n'est pas réglé (MILLESIME_JETON_TRANSHUMANCE) : la demande n'est pas partie.")
        try:
            r = requests.post(self.cfg.transhumance_url + "/externe/demandes", timeout=15,
                              headers={"Authorization": f"Bearer {self.cfg.jeton_transhumance}"},
                              json={"dossier": src["ref"], "de": "Millésime"})
        except requests.RequestException as e:
            raise ErreurMillesime(f"Transhumance ne répond pas ({e.__class__.__name__}) : la demande n'est pas partie.") from e
        if r.status_code >= 400:
            detail = ""
            try:
                detail = r.json().get("detail", "")
            except ValueError:
                pass
            raise ErreurMillesime(f"Transhumance a refusé la demande ({r.status_code}). {detail}".strip())
        self.base.executer("UPDATE sources SET demandee_le=? WHERE cle=?", maintenant(), cle)
        return "Demande de passage envoyée à Transhumance."

    def journal(self, n: int = 100) -> list[dict]:
        lignes = self.base.tous("SELECT * FROM journal ORDER BY id DESC LIMIT ?", n)
        for l in lignes:
            l["avant"], l["apres"] = json.loads(l["avant"] or "{}"), json.loads(l["apres"] or "{}")
        return lignes

    def annuler(self, journal_id: int) -> dict:
        j = self.base.un("SELECT * FROM journal WHERE id=?", journal_id)
        if not j or j["annule_le"]:
            raise ErreurMillesime("Entrée inconnue ou déjà annulée.")
        dernier = self.base.valeur("SELECT MAX(id) FROM journal WHERE asset_id=? AND annule_le IS NULL", j["asset_id"])
        if dernier != j["id"]:
            raise ErreurMillesime("Annule d'abord la modification la plus récente de cette photo.")
        avant, apres = json.loads(j["avant"]), json.loads(j["apres"])
        aid = j["asset_id"]
        if j["action"] == "nommer":
            self.immich.nommer_personne(aid, avant.get("nom") or "")
            self.base.executer("UPDATE visages SET person_nom=? WHERE person_id=?", avant.get("nom") or None, aid)
            self.base.executer("UPDATE journal SET annule_le=? WHERE id=?", maintenant(), journal_id)
            self.suggestions_cache = None
            return {"ok": True}
        if j["action"] == "fusionner":
            return self._annuler_fusion(j, avant, apres)
        if j["action"] == "detacher":
            return self._annuler_detacher(j, avant)
        if j["action"] == "valider":
            if avant.get("date"):
                self.immich.changer_date(aid, avant["date"])
            if apres.get("tag_id"):
                self.immich.detaguer(apres["tag_id"], [aid])
            for t in avant.get("tags_estimes", []):
                self.immich.taguer(t["id"], [aid])
            if apres.get("album_id") and apres["album_id"] not in {a["id"] for a in avant.get("albums", [])}:
                self.immich.retirer_album(apres["album_id"], [aid])
            for al in avant.get("albums", []):
                if al["nom"] == self.album_non_datees:
                    self.immich.ajouter_album(al["id"], [aid])
        self.base.executer("UPDATE journal SET annule_le=? WHERE id=?", maintenant(), journal_id)
        self.base.executer("UPDATE scans SET statut='a_analyser', annee_validee=NULL WHERE asset_id=?", aid)
        est.recalculer_propositions(self.base, self.cfg.seuil_doute)
        return {"ok": True}

    # ------------------------------------------------------------------ Nommer
    def groupes_a_nommer(self) -> list[dict]:
        lignes = self.base.tous("""
            SELECT v.person_id, COUNT(*) AS visages,
                   SUM(CASE WHEN s.type='non_datee' THEN 1 ELSE 0 END) AS sur_non_datees,
                   MIN(v.face_id) AS face_id, MIN(v.asset_id) AS asset_id
            FROM visages v JOIN scans s ON s.asset_id = v.asset_id
            WHERE v.person_id IS NOT NULL AND (v.person_nom IS NULL OR v.person_nom = '')
              AND v.person_id NOT IN (SELECT person_id FROM groupes_ignores)
            GROUP BY v.person_id ORDER BY sur_non_datees DESC, visages DESC""")
        for g in lignes:
            g["exemples"] = self.base.tous("SELECT face_id, asset_id FROM visages WHERE person_id=? LIMIT 6",
                                           g["person_id"])
            g["lien_immich"] = f"{self.cfg.immich_lien}/people/{g['person_id']}"
        return lignes

    @staticmethod
    def _cle_nom(nom: str) -> str:
        import unicodedata
        n = unicodedata.normalize("NFKD", " ".join((nom or "").split()).casefold())
        return "".join(c for c in n if not unicodedata.combining(c))

    def suggestions(self) -> list[dict]:
        """Personnes nommées d'Immich : celles présentes sur des scans d'abord (par nombre de scans), puis les autres."""
        import time as _t
        if self.suggestions_cache and _t.monotonic() - self.suggestions_cache[0] < 300:
            return self.suggestions_cache[1]
        sur_scans = {r["person_id"]: r["n"] for r in self.base.tous(
            "SELECT person_id, COUNT(DISTINCT asset_id) AS n FROM visages WHERE person_id IS NOT NULL GROUP BY person_id")}
        res = [{"person_id": p["id"], "nom": p["name"], "naissance": p.get("birthDate"),
                "sur_scans": sur_scans.get(p["id"], 0)}
               for p in self.immich.personnes() if (p.get("name") or "").strip()]
        res.sort(key=lambda p: (-p["sur_scans"], self._cle_nom(p["nom"])))
        self.suggestions_cache = (_t.monotonic(), res)
        return res

    def personne_existante(self, nom: str, sauf: str | None = None) -> dict | None:
        cle = self._cle_nom(nom)
        return next((p for p in self.suggestions() if self._cle_nom(p["nom"]) == cle and p["person_id"] != sauf), None)

    def nommer(self, person_id: str, nom: str) -> dict:
        nom = " ".join((nom or "").split())
        if len(nom) < 2:
            raise ErreurMillesime("Nom trop court.")
        existe = self.personne_existante(nom, sauf=person_id)
        if existe:
            raise ErreurMillesime(f"« {existe['nom']} » existe déjà dans Immich : choisis-le pour fusionner, "
                                  "sinon Immich aurait deux personnes du même nom.")
        self.suggestions_cache = None
        self.immich.nommer_personne(person_id, nom)
        self.base.executer("UPDATE visages SET person_nom=? WHERE person_id=?", nom, person_id)
        self.base.executer("INSERT INTO journal(asset_id, action, avant, apres, le) VALUES(?,?,?,?,?)",
                           person_id, "nommer", json.dumps({"nom": ""}), json.dumps({"nom": nom}), maintenant())
        return {"ok": True, "nom": nom}

    def _visages_de_personne(self, person_id: str) -> list[str]:
        """Tous les visages d'une personne dans Immich (pas seulement ceux des scans)."""
        ids = []
        for a in self.immich.rechercher({"personIds": [person_id]}, 5000):
            ids += [f["id"] for f in self.immich.visages(a["id"]) if (f.get("person") or {}).get("id") == person_id]
        return ids

    def apercu_fusion(self, source_id: str, cible_id: str) -> dict:
        cible = next((p for p in self.suggestions() if p["person_id"] == cible_id), None)
        if not cible:
            raise ErreurMillesime("Personne cible introuvable dans Immich.")
        src = self.base.tous("SELECT face_id, asset_id FROM visages WHERE person_id=? LIMIT 6", source_id)
        exemples = self.base.tous("SELECT face_id, asset_id FROM visages WHERE person_id=? LIMIT 6", cible_id)
        if len(exemples) < 6:
            vus = {e["asset_id"] for e in exemples}
            for a in self.immich.rechercher({"personIds": [cible_id]}, 30):
                if len(exemples) >= 6:
                    break
                if a["id"] in vus:
                    continue
                f = next((x for x in self.immich.visages(a["id"]) if (x.get("person") or {}).get("id") == cible_id), None)
                if f:
                    exemples.append({"face_id": f["id"], "asset_id": a["id"]})
        return {"source": src, "cible": {**cible, "exemples": exemples}}

    def fusionner(self, source_id: str, cible_id: str) -> dict:
        """Fusionne le groupe sans nom dans une personne existante, en notant ses visages pour pouvoir annuler."""
        if source_id == cible_id:
            raise ErreurMillesime("Impossible de fusionner une personne avec elle-même.")
        cible = next((p for p in self.suggestions() if p["person_id"] == cible_id), None)
        if not cible:
            raise ErreurMillesime("Personne cible introuvable dans Immich.")
        source = self.immich.personne(source_id)
        faces = self._visages_de_personne(source_id)
        avant = {"source_id": source_id, "nom": source.get("name") or "", "naissance": source.get("birthDate"),
                 "faces": faces}
        apres = {"cible_id": cible_id, "cible_nom": cible["nom"]}
        jid = self.base.executer("INSERT INTO journal(asset_id, action, avant, apres, le) VALUES(?,?,?,?,?)",
                                 source_id, "fusionner", json.dumps(avant), json.dumps(apres), maintenant())
        self.immich.fusionner_personnes(cible_id, [source_id])
        self.base.executer("UPDATE visages SET person_id=?, person_nom=?, naissance=? WHERE person_id=?",
                           cible_id, cible["nom"], cible.get("naissance"), source_id)
        self.base.executer("DELETE FROM frises WHERE person_id IN (?, ?)", source_id, cible_id)
        self.suggestions_cache = None
        est.recalculer_propositions(self.base, self.cfg.seuil_doute)
        return {"ok": True, "journal": jid, "visages": len(faces), "cible": cible["nom"]}

    def detacher_visage(self, asset_id: str, face_id: str) -> dict:
        """2.3.0 : « ce visage n'est pas cette personne ». Immich ne sait pas laisser un visage sans personne :
        il passe dans une personne neuve, sans nom (un groupe à nommer). Noté au journal, annulable."""
        v = self.base.un("SELECT * FROM visages WHERE face_id=? AND asset_id=?", face_id, asset_id)
        if not v or not v["person_id"] or not v["person_nom"]:
            raise ErreurMillesime("Ce visage n'est rattaché à aucune personne nommée sur cette photo.")
        avant = {"face_id": face_id, "person_id": v["person_id"], "nom": v["person_nom"] or "", "naissance": v["naissance"]}
        jid = self.base.executer("INSERT INTO journal(asset_id, action, avant, apres, le) VALUES(?,?,?,?,?)",
                                 asset_id, "detacher", json.dumps(avant), json.dumps({}), maintenant())
        try:
            nouvelle = self.immich.creer_personne("")
            self.immich.reassigner_visage(face_id, nouvelle["id"])
        except ErreurImmich as e:
            raise ErreurMillesime(f"Immich a refusé : {e}. Voir le journal.") from e
        self.base.executer("UPDATE journal SET apres=? WHERE id=?", json.dumps({"person_id": nouvelle["id"]}), jid)
        self.base.executer("UPDATE visages SET person_id=?, person_nom=NULL, naissance=NULL, person_masque=0 WHERE face_id=?",
                           nouvelle["id"], face_id)
        self.base.executer("DELETE FROM frises WHERE person_id=?", v["person_id"])
        self.suggestions_cache = None
        est.recalculer_propositions(self.base, self.cfg.seuil_doute)
        return {"ok": True, "journal": jid, "nom": avant["nom"]}

    def _annuler_detacher(self, j: dict, avant: dict) -> dict:
        self.immich.reassigner_visage(avant["face_id"], avant["person_id"])
        self.base.executer("UPDATE visages SET person_id=?, person_nom=?, naissance=? WHERE face_id=?",
                           avant["person_id"], avant.get("nom") or None, avant.get("naissance"), avant["face_id"])
        self.base.executer("DELETE FROM frises WHERE person_id=?", avant["person_id"])
        self.base.executer("UPDATE journal SET annule_le=? WHERE id=?", maintenant(), j["id"])
        self.suggestions_cache = None
        est.recalculer_propositions(self.base, self.cfg.seuil_doute)
        return {"ok": True}

    def _annuler_fusion(self, j: dict, avant: dict, apres: dict) -> dict:
        """Recrée une personne et lui rend les visages notés avant la fusion."""
        nouvelle = self.immich.creer_personne(avant.get("nom") or "")
        for fid in avant.get("faces", []):
            self.immich.reassigner_visage(fid, nouvelle["id"])
        faces = avant.get("faces", [])
        if faces:
            marque = ",".join("?" * len(faces))
            self.base.executer(f"UPDATE visages SET person_id=?, person_nom=?, naissance=NULL WHERE face_id IN ({marque})",
                               nouvelle["id"], avant.get("nom") or None, *faces)
        self.base.executer("DELETE FROM frises WHERE person_id=?", apres.get("cible_id"))
        self.base.executer("UPDATE journal SET annule_le=? WHERE id=?", maintenant(), j["id"])
        self.suggestions_cache = None
        est.recalculer_propositions(self.base, self.cfg.seuil_doute)
        return {"ok": True, "person_id": nouvelle["id"], "visages": len(faces)}

    def ignorer_groupe(self, person_id: str) -> dict:
        self.base.executer("INSERT OR IGNORE INTO groupes_ignores(person_id) VALUES(?)", person_id)
        return {"ok": True}

    def sans_naissance(self) -> list[dict]:
        return self.base.tous("""
            SELECT v.person_id, v.person_nom AS nom, COUNT(DISTINCT v.asset_id) AS scans
            FROM visages v JOIN scans s ON s.asset_id = v.asset_id
            WHERE v.person_nom IS NOT NULL AND v.person_nom <> '' AND v.naissance IS NULL
            GROUP BY v.person_id ORDER BY scans DESC""")

    # ------------------------------------------------------------------ frise
    def frise(self, person_id: str, forcer: bool = False) -> dict:
        """Visages d'une personne aux âges connus : scans datés + photos numériques (hors scans non datés)."""
        c = self.base.un("SELECT * FROM frises WHERE person_id=?", person_id)
        if c and not forcer and c["maj"][:10] == maintenant()[:10]:
            return json.loads(c["contenu"])
        p = self.immich.personne(person_id)
        naissance = est.parse_date(p.get("birthDate"))
        exclus = {r["asset_id"] for r in self.base.tous("SELECT asset_id FROM scans WHERE type='non_datee'")}
        datees = {r["asset_id"]: r["date_tampon"] for r in self.base.tous("SELECT asset_id, date_tampon FROM scans "
                                                                           "WHERE type='datee'")}
        candidats = []
        for a in self.immich.rechercher({"personIds": [person_id]}, 600):
            if a["id"] in exclus:
                continue
            d = est.parse_date(datees.get(a["id"]) or (a.get("exifInfo") or {}).get("dateTimeOriginal")
                               or a.get("localDateTime"))
            if d and (not naissance or d >= naissance):
                candidats.append((d, a["id"]))
        candidats.sort()
        if len(candidats) > 12:
            pas = len(candidats) / 12
            candidats = [candidats[int(i * pas)] for i in range(12)]
        elements = []
        for d, aid in candidats:
            f = next((x for x in self.immich.visages(aid) if (x.get("person") or {}).get("id") == person_id), None)
            if f:
                elements.append({"asset_id": aid, "face_id": f["id"], "date": d.isoformat(),
                                 "age": round((d - naissance).days / 365.25, 1) if naissance else None,
                                 "source": "tampon" if aid in datees else "numérique"})
        contenu = {"person_id": person_id, "nom": p.get("name") or "", "naissance": p.get("birthDate"),
                   "elements": elements}
        self.base.executer("INSERT INTO frises(person_id, contenu, maj) VALUES(?,?,?) ON CONFLICT(person_id) "
                           "DO UPDATE SET contenu=excluded.contenu, maj=excluded.maj",
                           person_id, json.dumps(contenu), maintenant())
        return contenu

    # ------------------------------------------------------------------ état (carnet)
    def etat(self) -> dict:
        a = self.accueil()["compteurs"]
        t = self.compter_taches()
        pc = self.pc_actif()
        n = t["calibrage"] + t["a_dater"]
        en_veille = bool(pc and pc["actif"] and pc.get("veille"))
        if not n:
            message = None
        elif en_veille:
            message = f"Millésime : {n} visage(s) en cours d'analyse sur le PC"
        else:
            message = f"Millésime : {n} visage(s) à analyser — allume le PC et ouvre Docker Desktop"
        return {"a_analyser": n, "scans_a_analyser": a["a_analyser"], "pc_connecte": en_veille, "pc_en_veille": en_veille,
                "a_dater": a["a_dater"], "a_trancher": a["a_trancher"], "a_nommer": a["a_nommer"],
                "validees": a["validees"], "sans_naissance": self.sans_naissance(), "message": message}
