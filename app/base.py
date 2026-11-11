"""Base SQLite de Millésime (un seul fichier dans /state)."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    asset_id      TEXT PRIMARY KEY,
    type          TEXT NOT NULL,           -- 'non_datee' | 'datee'
    date_tampon   TEXT,                    -- scans datés : date issue du tag AAAA-MM
    lot           TEXT,                    -- non datés : jour d'envoi dans Immich
    annee_envoi   INTEGER,                 -- borne haute
    statut        TEXT NOT NULL DEFAULT 'a_analyser',
                  -- a_analyser | a_dater | a_trancher | validee | plusieurs
    annee_proposee INTEGER,
    marge         INTEGER,
    raison        TEXT,
    details       TEXT,                    -- JSON : années par visage, bornes, voisins
    annee_validee INTEGER,
    vu_le         TEXT
);
CREATE TABLE IF NOT EXISTS visages (
    face_id     TEXT PRIMARY KEY,
    asset_id    TEXT NOT NULL,
    person_id   TEXT,
    person_nom  TEXT,
    naissance   TEXT,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL, img_w REAL, img_h REAL,
    age_visage  REAL,
    age_corps   REAL,
    calcule_le  TEXT
);
CREATE INDEX IF NOT EXISTS visages_asset ON visages(asset_id);
CREATE INDEX IF NOT EXISTS visages_personne ON visages(person_id);
CREATE TABLE IF NOT EXISTS calibrages (
    version   INTEGER PRIMARY KEY AUTOINCREMENT,
    cree_le   TEXT NOT NULL,
    params    TEXT NOT NULL,               -- JSON
    n_visages INTEGER,
    cv_mediane REAL,
    cv_3ans   REAL
);
CREATE TABLE IF NOT EXISTS journal (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id  TEXT NOT NULL,
    action    TEXT NOT NULL,
    avant     TEXT,
    apres     TEXT,
    le        TEXT NOT NULL,
    annule_le TEXT
);
CREATE TABLE IF NOT EXISTS groupes_ignores (person_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS frises (person_id TEXT PRIMARY KEY, contenu TEXT, maj TEXT);
CREATE TABLE IF NOT EXISTS reglages (cle TEXT PRIMARY KEY, valeur TEXT);
"""


class Base:
    def __init__(self, chemin: Path):
        self.cx = sqlite3.connect(str(chemin), check_same_thread=False, isolation_level=None)
        self.cx.row_factory = sqlite3.Row
        self.cx.execute("PRAGMA journal_mode=WAL")
        self.verrou = threading.RLock()
        with self.verrou:
            self.cx.executescript(SCHEMA)
            # migrations légères (colonnes ajoutées après la 1.0)
            cols = {r[1] for r in self.cx.execute("PRAGMA table_info(visages)")}
            if "person_masque" not in cols:
                self.cx.execute("ALTER TABLE visages ADD COLUMN person_masque INTEGER DEFAULT 0")

    @contextmanager
    def transaction(self):
        with self.verrou:
            self.cx.execute("BEGIN")
            try:
                yield self.cx
                self.cx.execute("COMMIT")
            except Exception:
                self.cx.execute("ROLLBACK")
                raise

    def tous(self, sql: str, *args) -> list[dict]:
        with self.verrou:
            return [dict(r) for r in self.cx.execute(sql, args).fetchall()]

    def un(self, sql: str, *args) -> dict | None:
        with self.verrou:
            r = self.cx.execute(sql, args).fetchone()
            return dict(r) if r else None

    def valeur(self, sql: str, *args):
        with self.verrou:
            r = self.cx.execute(sql, args).fetchone()
            return r[0] if r else None

    def executer(self, sql: str, *args) -> int:
        with self.verrou:
            return self.cx.execute(sql, args).lastrowid

    def lire(self, cle: str, defaut=None):
        v = self.valeur("SELECT valeur FROM reglages WHERE cle=?", cle)
        return json.loads(v) if v is not None else defaut

    def ecrire(self, cle: str, valeur) -> None:
        self.executer("INSERT INTO reglages(cle, valeur) VALUES(?, ?) "
                      "ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur", cle, json.dumps(valeur))
