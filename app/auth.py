"""Connexion par mot de passe unique et cookie de session signé (HMAC), comme carnet.

Le mot de passe est celui de carnet (MILLESIME_PASSWORD=${CARNET_PASSWORD} dans la stack).
« Se déconnecter » change la génération : tous les cookies émis avant deviennent invalides.
"""
from __future__ import annotations

import hashlib
import hmac
import time

COOKIE = "millesime_session"
DUREE = 30 * 86400


class Sessions:
    def __init__(self, mot_de_passe: str, generation: int = 0):
        self._mdp = mot_de_passe.encode()
        self._cle = hashlib.sha256(b"millesime-session|" + self._mdp).digest()
        self.generation = generation
        self._echecs: list[float] = []

    def attente(self) -> float:
        """1 s avant de répondre, 5 s après 5 échecs en 5 minutes."""
        t = time.monotonic()
        self._echecs = [x for x in self._echecs if t - x < 300]
        return 5.0 if len(self._echecs) >= 5 else 1.0

    def verifier_mot_de_passe(self, propose: str) -> bool:
        ok = hmac.compare_digest((propose or "").encode(), self._mdp)
        if not ok:
            self._echecs.append(time.monotonic())
        return ok

    def _signature(self, corps: str) -> str:
        return hmac.new(self._cle, corps.encode(), hashlib.sha256).hexdigest()

    def creer(self) -> str:
        corps = f"{self.generation}.{int(time.time()) + DUREE}"
        return f"{corps}.{self._signature(corps)}"

    def valide(self, jeton: str | None) -> bool:
        try:
            generation, expire, signature = (jeton or "").split(".")
        except ValueError:
            return False
        corps = f"{generation}.{expire}"
        return (hmac.compare_digest(signature, self._signature(corps)) and generation == str(self.generation)
                and expire.isdigit() and int(expire) > time.time())


def jeton_valide(entete: str | None, attendu: str) -> bool:
    """En-tête « Authorization: Bearer <jeton> », comparé en temps constant."""
    if not attendu:
        return False
    return hmac.compare_digest((entete or "").encode(), f"Bearer {attendu}".encode())
