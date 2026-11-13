"""Client Immich (API REST), avec nouvelles tentatives sur coupure ou erreur 5xx."""
from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger("millesime.immich")
ATTENTES = (2, 5, 15)


class ErreurImmich(Exception):
    pass


class LectureSeule(Exception):
    """Écriture refusée : Millésime tourne en lecture seule (MILLESIME_LECTURE_SEULE)."""


LECTURES_EN_POST = ("/search/",)     # recherches : des POST qui ne modifient rien


class Immich:
    def __init__(self, url: str, cle: str, lecture_seule: bool = False):
        self.lecture_seule = lecture_seule
        self.url = url.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"x-api-key": cle, "Accept": "application/json"})

    # -- transport ------------------------------------------------------------
    def _req(self, methode: str, chemin: str, **kw) -> requests.Response:
        # 1.6.0 : dernier filet du mode lecture seule, au plus près du réseau
        if self.lecture_seule and methode.upper() != "GET" and not chemin.startswith(LECTURES_EN_POST):
            raise LectureSeule("Mode lecture seule : rien n'est écrit dans Immich.")
        for essai, attente in enumerate((*ATTENTES, None), 1):
            try:
                r = self.s.request(methode, f"{self.url}/api{chemin}", timeout=60, **kw)
                if r.status_code < 500 or attente is None:
                    break
                motif = f"HTTP {r.status_code}"
            except (requests.ConnectionError, requests.Timeout) as e:
                if attente is None:
                    raise ErreurImmich(f"Immich injoignable ({e.__class__.__name__})") from e
                motif = e.__class__.__name__
            log.warning("Immich %s %s : %s, nouvel essai dans %s s (%s/%s)", methode, chemin, motif, attente,
                        essai, len(ATTENTES))
            time.sleep(attente)
        if r.status_code >= 400:
            raise ErreurImmich(f"Immich {methode} {chemin} : HTTP {r.status_code} {r.text[:200]}")
        return r

    def _json(self, methode: str, chemin: str, **kw):
        r = self._req(methode, chemin, **kw)
        return r.json() if r.content else None

    # -- lecture --------------------------------------------------------------
    def version(self) -> str:
        v = self._json("GET", "/server/version") or {}
        return f"{v.get('major')}.{v.get('minor')}.{v.get('patch')}"

    def tags(self) -> list[dict]:
        return self._json("GET", "/tags") or []

    def rechercher(self, filtres: dict, limite: int = 50000) -> list[dict]:
        resultats, page = [], 1
        while len(resultats) < limite:
            corps = {**filtres, "page": page, "size": 250, "withExif": True, "type": "IMAGE"}
            bloc = (self._json("POST", "/search/metadata", json=corps) or {}).get("assets", {})
            resultats += bloc.get("items", [])
            if not bloc.get("nextPage"):
                break
            page = int(bloc["nextPage"])
        return resultats[:limite]

    def asset(self, asset_id: str) -> dict:
        return self._json("GET", f"/assets/{asset_id}")

    def visages(self, asset_id: str) -> list[dict]:
        return self._json("GET", "/faces", params={"id": asset_id}) or []

    def apercu(self, asset_id: str) -> bytes:
        return self._req("GET", f"/assets/{asset_id}/thumbnail", params={"size": "preview"}).content

    def vignette(self, asset_id: str) -> bytes:
        """2.6.0 : la petite vignette d'une photo (grilles)."""
        return self._req("GET", f"/assets/{asset_id}/thumbnail", params={"size": "thumbnail"}).content

    def personne(self, person_id: str) -> dict:
        return self._json("GET", f"/people/{person_id}")

    def vignette_personne(self, person_id: str) -> bytes:
        return self._req("GET", f"/people/{person_id}/thumbnail").content

    def albums(self, asset_id: str | None = None) -> list[dict]:
        params = {"assetId": asset_id} if asset_id else None
        return self._json("GET", "/albums", params=params) or []

    def photos_album(self, album_id: str) -> list[dict]:
        """2.2.0 : les images d'un album."""
        return self.rechercher({"albumIds": [album_id]})

    def dossiers(self) -> list[str]:
        """2.2.0 : les dossiers qu'Immich connaît (chemins des originaux), triés."""
        return sorted(self._json("GET", "/view/folder/unique-paths") or [])

    def photos_dossier(self, chemin: str) -> list[dict]:
        """2.2.0 : les images rangées directement dans ce dossier (pas dans ses sous-dossiers)."""
        return [a for a in (self._json("GET", "/view/folder", params={"path": chemin}) or []) if a.get("type") == "IMAGE"]

    # -- écriture -------------------------------------------------------------
    def changer_date(self, asset_id: str, iso: str) -> None:
        self._req("PUT", f"/assets/{asset_id}", json={"dateTimeOriginal": iso})

    def tag_existant_ou_cree(self, valeur: str) -> dict:
        tags = self._json("PUT", "/tags", json={"tags": [valeur]}) or []
        for t in tags:
            if (t.get("value") or t.get("name")) == valeur:
                return t
        return tags[-1]

    def taguer(self, tag_id: str, ids: list[str]) -> None:
        self._req("PUT", f"/tags/{tag_id}/assets", json={"ids": ids})

    def detaguer(self, tag_id: str, ids: list[str]) -> None:
        self._req("DELETE", f"/tags/{tag_id}/assets", json={"ids": ids})

    def creer_album(self, nom: str, ids: list[str]) -> dict:
        return self._json("POST", "/albums", json={"albumName": nom, "assetIds": ids})

    def ajouter_album(self, album_id: str, ids: list[str]) -> None:
        self._req("PUT", f"/albums/{album_id}/assets", json={"ids": ids})

    def retirer_album(self, album_id: str, ids: list[str]) -> None:
        self._req("DELETE", f"/albums/{album_id}/assets", json={"ids": ids})

    def nommer_personne(self, person_id: str, nom: str) -> dict:
        return self._json("PUT", f"/people/{person_id}", json={"name": nom})

    def personnes(self, masquees: bool = False) -> list[dict]:
        """Toutes les personnes (nommées ou non), page par page ; `masquees` : celles masquées aussi."""
        res, page = [], 1
        while True:
            r = self._json("GET", "/people", params={"page": page, "size": 500, "withHidden": "true" if masquees else "false"}) or {}
            res += r.get("people", [])
            if not r.get("hasNextPage"):
                return res
            page += 1

    def fusionner_personnes(self, cible_id: str, ids: list[str]) -> list:
        """Fusionne les personnes `ids` DANS `cible_id` (leurs visages rejoignent la cible)."""
        return self._json("POST", f"/people/{cible_id}/merge", json={"ids": ids})

    def creer_personne(self, nom: str = "") -> dict:
        return self._json("POST", "/people", json={"name": nom} if nom else {})

    def reassigner_visage(self, face_id: str, person_id: str) -> None:
        # 2.0.1 : dans l'API d'Immich, l'adresse porte la PERSONNE et le corps porte le visage
        # (lu dans face.controller.ts). L'inverse, écrit jusqu'à la 2.0.0, était refusé (400).
        self._req("PUT", f"/faces/{person_id}", json={"id": face_id})
