"""Configuration lue dans les variables d'environnement de la stack.

2.12.0 : la stack ne donne plus que ce qui relie Millésime aux autres (adresse et clé d'Immich, jetons de Home Assistant
et du PC, lecture seule). Les réglages d'usage (libellé des numérisations, relecture d'Immich, noms d'albums, libellés
suivis) se règlent dans l'écran Réglages : voir `Millesime.reglages()` ; les anciennes variables
(MILLESIME_TAG_PREFIXE, MILLESIME_SYNCHRO_MINUTES, MILLESIME_ALBUM_NON_DATEES, MILLESIME_MODELE_ALBUM) ne sont lues
qu'une fois, au premier démarrage de la 2.12.0, pour reprendre leur valeur.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import maison


def _env(nom: str, defaut: str = "") -> str:
    return os.environ.get(nom, defaut).strip()


# Anciennes variables de la stack reprises au premier démarrage (clé du réglage → variable)
REPRISES = {
    "tag_prefixe": "MILLESIME_TAG_PREFIXE",
    "synchro_minutes": "MILLESIME_SYNCHRO_MINUTES",
    "album_non_datees": "MILLESIME_ALBUM_NON_DATEES",
    "modele_album": "MILLESIME_MODELE_ALBUM",
}


@dataclass
class Config:
    immich_url: str
    immich_cle: str
    mot_de_passe: str
    jeton_calcul: str
    tag_non_datee: str
    tag_estimee: str
    etat_dir: Path
    seuil_doute: float
    seuil_suspect: float
    lecture_seule: bool = False     # 1.6.0 : aucune écriture dans Immich
    lecture_seule_origine: str = ""  # 2.11.0 : « maison » (MAISON_LECTURE_SEULE), « appli » (MILLESIME_LECTURE_SEULE) ou « »
    # 2.2.0 : demande de passage envoyée à Transhumance quand un dossier choisi est entièrement daté
    transhumance_url: str = "http://transhumance:8097"
    jeton_ha: str = ""            # 2.8.0 : jeton de Home Assistant (/ha/etat) ; vide : adresse fermée
    jeton_transhumance: str = ""    # 2.12.0 : MAISON_JETON seul ; vide : aucune demande
    # 2.9.0 : noms des non datées lus dans Chambre noire (/externe/noms) ; jeton vide : noms des Réglages
    chambre_noire_url: str = "http://chambre-noire:8100"
    jeton_chambre_noire: str = ""   # 2.12.0 : MAISON_JETON seul
    # 2.13.0 : dates signalées par les invités, lues chez Sillage (/externe/signalements) ; jeton vide : non relié
    sillage_url: str = "http://sillage:8093"
    jeton_sillage: str = ""         # MAISON_JETON seul

    @classmethod
    def depuis_env(cls) -> "Config":
        mdp = maison.mot_de_passe()                       # 2.12.0 : MAISON_PASSWORD seul
        if len(mdp) < 12:
            raise RuntimeError("MAISON_PASSWORD est absent ou trop court (12 caractères au moins) : "
                               "Millésime ne démarre pas. À définir dans la stack (mot de passe commun des applis).")
        cle = _env("MILLESIME_IMMICH_CLE")
        if not cle:
            raise RuntimeError("Variable MILLESIME_IMMICH_CLE absente : clé API Immich dédiée à Millésime.")
        # 2.12.0 : demandes envoyées aux autres applis maison (Transhumance, Chambre noire, Anneau ; Sillage en 2.13.0) : MAISON_JETON
        jeton = maison.jeton_a_envoyer()
        etat = Path(_env("MILLESIME_ETAT", "/state"))
        etat.mkdir(parents=True, exist_ok=True)
        return cls(
            immich_url=_env("MILLESIME_IMMICH_URL", "http://immich_server:2283").rstrip("/"),
            immich_cle=cle,
            mot_de_passe=mdp,
            jeton_calcul=_env("MILLESIME_JETON_CALCUL"),
            tag_non_datee=_env("MILLESIME_TAG_NON_DATEE", "Non datée"),
            tag_estimee=_env("MILLESIME_TAG_ESTIMEE", "Date estimée"),
            etat_dir=etat,
            seuil_doute=float(_env("MILLESIME_SEUIL_DOUTE", "4")),
            seuil_suspect=float(_env("MILLESIME_SEUIL_SUSPECT", "12")),
            # 2.11.0 : MAISON_LECTURE_SEULE pour toute la maison ; MILLESIME_LECTURE_SEULE (oui/non) l'emporte ici
            lecture_seule=maison.lecture_seule("MILLESIME_LECTURE_SEULE"),
            lecture_seule_origine=maison.origine_lecture_seule("MILLESIME_LECTURE_SEULE"),
            transhumance_url=_env("MILLESIME_TRANSHUMANCE_URL", "http://transhumance:8097").rstrip("/"),
            jeton_ha=_env("MILLESIME_JETON_HA"),
            jeton_transhumance=jeton,
            chambre_noire_url=_env("MILLESIME_CHAMBRE_NOIRE_URL", "http://chambre-noire:8100").rstrip("/"),
            jeton_chambre_noire=jeton,
            sillage_url=_env("MILLESIME_SILLAGE_URL", "http://sillage:8093").rstrip("/"),
            jeton_sillage=jeton,
        )
