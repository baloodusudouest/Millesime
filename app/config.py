"""Configuration lue dans les variables d'environnement de la stack."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(nom: str, defaut: str = "") -> str:
    return os.environ.get(nom, defaut).strip()


@dataclass
class Config:
    immich_url: str
    immich_cle: str
    mot_de_passe: str
    jeton_calcul: str
    jeton_carnet: str
    tag_prefixe: str
    tag_non_datee: str
    tag_estimee: str
    album_non_datees: str
    modele_album: str
    etat_dir: Path
    seuil_doute: float
    seuil_suspect: float
    synchro_minutes: int

    @classmethod
    def depuis_env(cls) -> "Config":
        mdp = _env("MILLESIME_PASSWORD")
        if not mdp:
            raise RuntimeError("Variable MILLESIME_PASSWORD absente : à définir dans la stack (même valeur que CARNET_PASSWORD).")
        cle = _env("MILLESIME_IMMICH_CLE")
        if not cle:
            raise RuntimeError("Variable MILLESIME_IMMICH_CLE absente : clé API Immich dédiée à Millésime.")
        etat = Path(_env("MILLESIME_ETAT", "/state"))
        etat.mkdir(parents=True, exist_ok=True)
        return cls(
            immich_url=_env("MILLESIME_IMMICH_URL", "http://immich_server:2283").rstrip("/"),
            immich_cle=cle,
            mot_de_passe=mdp,
            jeton_calcul=_env("MILLESIME_JETON_CALCUL"),
            jeton_carnet=_env("MILLESIME_JETON_CARNET"),
            tag_prefixe=_env("MILLESIME_TAG_PREFIXE", "Numérisation"),
            tag_non_datee=_env("MILLESIME_TAG_NON_DATEE", "Non datée"),
            tag_estimee=_env("MILLESIME_TAG_ESTIMEE", "Date estimée"),
            album_non_datees=_env("MILLESIME_ALBUM_NON_DATEES", "Non datées Numérisation"),
            modele_album=_env("MILLESIME_MODELE_ALBUM", "{annee} Numérisation"),
            etat_dir=etat,
            seuil_doute=float(_env("MILLESIME_SEUIL_DOUTE", "4")),
            seuil_suspect=float(_env("MILLESIME_SEUIL_SUSPECT", "12")),
            synchro_minutes=int(_env("MILLESIME_SYNCHRO_MINUTES", "60")),
        )
