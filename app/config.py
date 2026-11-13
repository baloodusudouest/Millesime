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
    # Adresse d'Immich pour les liens ouverts dans le navigateur (différente de l'adresse interne
    # au réseau Docker). Vide : le navigateur ouvre Immich sur la même machine que Millésime, port 2283.
    immich_lien: str = ""
    lecture_seule: bool = False     # 1.6.0 : aucune écriture dans Immich
    # 2.2.0 : demande de passage envoyée à Transhumance quand un dossier choisi est entièrement daté
    transhumance_url: str = "http://transhumance:8097"
    jeton_transhumance: str = ""    # le même que TRANSHUMANCE_JETON_MILLESIME ; vide : aucune demande n'est envoyée

    @classmethod
    def depuis_env(cls) -> "Config":
        mdp = _env("MILLESIME_PASSWORD")
        if not mdp:
            raise RuntimeError("Variable MILLESIME_PASSWORD absente : à définir dans la stack (même valeur que CARNET_PASSWORD).")
        cle = _env("MILLESIME_IMMICH_CLE")
        if not cle:
            raise RuntimeError("Variable MILLESIME_IMMICH_CLE absente : clé API Immich dédiée à Millésime.")
        # 1.5.1 : les noms de tags et d'albums sont propres à chaque photothèque. Ils ne sont plus
        # écrits dans le code (dépôt public) : la stack les donne, et Millésime refuse de démarrer
        # sans eux plutôt que d'écrire sous un nom par défaut.
        # 2.2.0 : seul le préfixe des tags reste obligatoire dans la stack. Les deux noms d'albums se règlent
        # dans l'appli (Réglages) ; les variables, si elles sont là, en donnent la valeur de départ.
        noms = {v: _env(v) for v in ("MILLESIME_TAG_PREFIXE", "MILLESIME_ALBUM_NON_DATEES", "MILLESIME_MODELE_ALBUM")}
        if not noms["MILLESIME_TAG_PREFIXE"]:
            raise RuntimeError("Variable(s) absente(s) : MILLESIME_TAG_PREFIXE. À définir dans la stack avec le nom "
                               "réel du préfixe des tags de numérisation dans Immich (voir le README).")
        if noms["MILLESIME_MODELE_ALBUM"] and "{annee}" not in noms["MILLESIME_MODELE_ALBUM"]:
            raise RuntimeError("MILLESIME_MODELE_ALBUM doit contenir {annee}, par exemple « {annee} Numérisation ».")
        etat = Path(_env("MILLESIME_ETAT", "/state"))
        etat.mkdir(parents=True, exist_ok=True)
        return cls(
            immich_url=_env("MILLESIME_IMMICH_URL", "http://immich_server:2283").rstrip("/"),
            immich_cle=cle,
            mot_de_passe=mdp,
            jeton_calcul=_env("MILLESIME_JETON_CALCUL"),
            jeton_carnet=_env("MILLESIME_JETON_CARNET"),
            tag_prefixe=noms["MILLESIME_TAG_PREFIXE"],
            tag_non_datee=_env("MILLESIME_TAG_NON_DATEE", "Non datée"),
            tag_estimee=_env("MILLESIME_TAG_ESTIMEE", "Date estimée"),
            album_non_datees=noms["MILLESIME_ALBUM_NON_DATEES"],
            modele_album=noms["MILLESIME_MODELE_ALBUM"],
            etat_dir=etat,
            seuil_doute=float(_env("MILLESIME_SEUIL_DOUTE", "4")),
            seuil_suspect=float(_env("MILLESIME_SEUIL_SUSPECT", "12")),
            synchro_minutes=int(_env("MILLESIME_SYNCHRO_MINUTES", "60")),
            immich_lien=_env("MILLESIME_IMMICH_LIEN").rstrip("/"),
            lecture_seule=_env("MILLESIME_LECTURE_SEULE").lower() in ("oui", "1", "true", "yes"),
            transhumance_url=_env("MILLESIME_TRANSHUMANCE_URL", "http://transhumance:8097").rstrip("/"),
            jeton_transhumance=_env("MILLESIME_JETON_TRANSHUMANCE"),
        )
