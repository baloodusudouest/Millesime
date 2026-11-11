"""Cœur de Millésime : synchronisation avec Immich, file de calcul, écriture, Nommer, frise, état."""
from __future__ import annotations

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
        self.immich = immich or Immich(cfg.immich_url, cfg.immich_cle)
        self.verrou_synchro = threading.Lock()
        self.apercus = Cache(24)
        self.visages_immich = Cache(256)
        self.suggestions_cache = None

    # ------------------------------------------------------------------ synchro
    def synchroniser(self) -> dict:
        """Relit les scans « Non datée » et datés, leurs visages et les personnes, puis recalcule."""
        if not self.verrou_synchro.acquire(blocking=False):
            raise ErreurMillesime("Synchronisation déjà en cours.")
        try:
            debut = datetime.now()
            pref = self.cfg.tag_prefixe + "/"
            tags = self.immich.tags()
            non_datee = next((t for t in tags if (t.get("value") or "") == pref + self.cfg.tag_non_datee), None)
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
            if non_datee:
                for a in self.immich.rechercher({"tagIds": [non_datee["id"]]}):
                    vus.add(a["id"])
                    envoi = est.parse_date(a.get("createdAt") or a.get("fileCreatedAt"))
                    self._enregistrer_scan(a["id"], "non_datee", None, envoi.isoformat() if envoi else None,
                                           envoi.year if envoi else None, a["id"] in estimees)
            for t, d in dates:
                for a in self.immich.rechercher({"tagIds": [t["id"]]}):
                    if a["id"] not in vus:
                        vus.add(a["id"])
                        self._enregistrer_scan(a["id"], "datee", d, None, None, False)
            # scans disparus d'Immich (ou retagués) : retirés
            for r in self.base.tous("SELECT asset_id FROM scans"):
                if r["asset_id"] not in vus:
                    self.base.executer("DELETE FROM visages WHERE asset_id=?", r["asset_id"])
                    self.base.executer("DELETE FROM scans WHERE asset_id=?", r["asset_id"])
            n_visages = 0
            for r in self.base.tous("SELECT asset_id FROM scans WHERE statut <> 'validee' OR type='datee'"):
                n_visages += self._synchro_visages(r["asset_id"])
            cal = est.calibrer(self.base)
            est.recalculer_propositions(self.base, self.cfg.seuil_doute)
            bilan = {"le": maintenant(), "duree_s": round((datetime.now() - debut).total_seconds(), 1),
                     "scans": len(vus), "visages": n_visages, "calibrage": cal["version"] if cal else None}
            self.base.ecrire("derniere_synchro", bilan)
            log.info("Synchronisation : %s", bilan)
            return bilan
        finally:
            self.verrou_synchro.release()

    def _enregistrer_scan(self, asset_id, type_, date_tampon, lot, annee_envoi, deja_estime):
        existant = self.base.un("SELECT * FROM scans WHERE asset_id=?", asset_id)
        if existant:
            self.base.executer("UPDATE scans SET type=?, date_tampon=?, lot=COALESCE(?, lot), "
                               "annee_envoi=COALESCE(?, annee_envoi) WHERE asset_id=?",
                               type_, date_tampon, lot, annee_envoi, asset_id)
            if deja_estime and existant["statut"] != "validee":
                self.base.executer("UPDATE scans SET statut='validee' WHERE asset_id=?", asset_id)
        else:
            self.base.executer("INSERT INTO scans(asset_id, type, date_tampon, lot, annee_envoi, statut) "
                               "VALUES(?,?,?,?,?,?)", asset_id, type_, date_tampon, lot, annee_envoi,
                               "validee" if deja_estime else ("a_analyser" if type_ == "non_datee" else "datee"))

    def _synchro_visages(self, asset_id: str) -> int:
        faces = self.immich.visages(asset_id)
        ids = set()
        for f in faces:
            p = f.get("person") or {}
            ids.add(f["id"])
            self.base.executer("""
                INSERT INTO visages(face_id, asset_id, person_id, person_nom, naissance, x1, y1, x2, y2, img_w, img_h)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(face_id) DO UPDATE SET person_id=excluded.person_id, person_nom=excluded.person_nom,
                    naissance=excluded.naissance, x1=excluded.x1, y1=excluded.y1, x2=excluded.x2, y2=excluded.y2,
                    img_w=excluded.img_w, img_h=excluded.img_h""",
                f["id"], asset_id, p.get("id"), p.get("name") or None, (p.get("birthDate") or None),
                f["boundingBoxX1"], f["boundingBoxY1"], f["boundingBoxX2"], f["boundingBoxY2"],
                f.get("imageWidth"), f.get("imageHeight"))
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
        return {"enregistres": n, "restants": self.compter_taches()}

    # ------------------------------------------------------------------ images
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
                              "suspects": len(est.suspects(self.base, self.cfg.seuil_suspect))},
                "taches": self.compter_taches(), "calibrage": cal,
                "derniere_synchro": self.base.lire("derniere_synchro"),
                "dernier_calcul": self.base.lire("dernier_calcul")}

    def liste(self, statut: str) -> list[dict]:
        ordre = "marge ASC, asset_id" if statut == "a_dater" else "asset_id"
        return self.base.tous(f"SELECT asset_id, annee_proposee, marge, raison FROM scans "
                              f"WHERE type='non_datee' AND statut=? ORDER BY {ordre}", statut)

    def scan(self, asset_id: str) -> dict:
        s = self.base.un("SELECT * FROM scans WHERE asset_id=?", asset_id)
        if not s:
            raise ErreurMillesime("Scan inconnu.")
        s["details"] = json.loads(s["details"] or "{}")
        s["visages"] = self.base.tous("SELECT face_id, person_id, person_nom, naissance, x1, y1, x2, y2, img_w, img_h, "
                                      "age_visage, age_corps FROM visages WHERE asset_id=?", asset_id)
        s["lien_immich"] = f"{self.cfg.immich_url}/photos/{asset_id}"
        # groupes sans nom présents sur la photo, avec leur nombre total de visages (pour les nommer sur place)
        s["a_nommer"] = self.base.tous(f"""
            SELECT v.person_id, MIN(v.face_id) AS face_id, ? AS asset_id,
                   (SELECT COUNT(*) FROM visages w WHERE w.person_id = v.person_id) AS visages
            FROM visages v WHERE v.asset_id=? AND v.person_id IS NOT NULL
              AND (v.person_nom IS NULL OR v.person_nom = '')
            GROUP BY v.person_id""", asset_id, asset_id)
        for g in s["a_nommer"]:
            g["exemples"] = [{"face_id": g["face_id"], "asset_id": asset_id}]
            g["lien_immich"] = f"{self.cfg.immich_url}/people/{g['person_id']}"
        s["sans_personne"] = [v["face_id"] for v in s["visages"] if not v["person_id"]]
        return s

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
        apres = {"date": f"{annee}-07-01T12:00:00.000Z", "tag": f"{self.cfg.tag_estimee}/{annee} ±{marge}",
                 "album": self.cfg.modele_album.format(annee=annee)}
        jid = self.base.executer("INSERT INTO journal(asset_id, action, avant, apres, le) VALUES(?,?,?,?,?)",
                                 asset_id, "valider", json.dumps(avant), json.dumps(apres), maintenant())
        try:
            for t in tags_estimes:
                self.immich.detaguer(t["id"], [asset_id])
            self.immich.changer_date(asset_id, apres["date"])
            tag = self.immich.tag_existant_ou_cree(apres["tag"])
            self.immich.taguer(tag["id"], [asset_id])
            apres["tag_id"] = tag["id"]
            nd = next((al for al in albums_avant if al["nom"] == self.cfg.album_non_datees), None)
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
                if al["nom"] == self.cfg.album_non_datees:
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
            g["lien_immich"] = f"{self.cfg.immich_url}/people/{g['person_id']}"
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
        return {"a_analyser": t["calibrage"] + t["a_dater"], "scans_a_analyser": a["a_analyser"],
                "a_dater": a["a_dater"], "a_trancher": a["a_trancher"], "a_nommer": a["a_nommer"],
                "validees": a["validees"], "sans_naissance": self.sans_naissance(),
                "message": (f"Millésime : {t['calibrage'] + t['a_dater']} visage(s) à analyser — "
                            "allume le PC et lance l'analyse") if t["calibrage"] + t["a_dater"] else None}
