"""
Faux Sillage pour tester la tuile « Reçues des invités » de Millésime (2.13.0), selon le contrat 1 entre les deux applis :

- GET  /externe/signalements (jeton commun, Bearer) → {"contrat": 1, "signalements": [avis non traités]}
- POST /externe/signalements/traite {"asset", "issue"} → {"fermes": n} : ferme TOUS les avis non traités de la photo
  (toutes invitations) ; rejouable sans effet (deuxième appel : fermes 0, code 200).

Les prénoms et les mots sont inventés. `S["panne_traite"]` fait échouer le POST (503) ; `S["panne"]` fait échouer tout ;
`S["contrat"]` change le numéro de contrat rendu.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ISSUES = ("acceptee", "corrigee", "ecartee")


def avis(ident, asset, annee, environ=False, mot="", date_affichee=None, invites=("Prénom A",),
         le="2026-11-18T10:00:00+01:00"):
    return {"id": ident, "asset": asset, "annee": annee, "environ": environ, "mot": mot,
            "date_affichee": date_affichee, "invites": list(invites), "le": le}


def demarrer(jeton: str):
    S = {"avis": [], "traites": {}, "requetes": [], "panne": False, "panne_traite": False, "contrat": 1}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _jeton_ok(self):
            if self.headers.get("Authorization") != f"Bearer {jeton}":
                self._json({"detail": "Jeton manquant ou invalide."}, 401)
                return False
            return True

        def do_GET(self):
            S["requetes"].append(("GET", self.path, None))
            if S["panne"]:
                return self._json({"detail": "panne"}, 503)
            if not self._jeton_ok():
                return
            if self.path == "/externe/signalements":
                ouverts = [a for a in S["avis"] if a["id"] not in S["traites"]]
                return self._json({"contrat": S["contrat"], "signalements": ouverts})
            self._json({"detail": "Not Found"}, 404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            corps = json.loads(self.rfile.read(n) or b"{}")
            S["requetes"].append(("POST", self.path, corps))
            if S["panne"] or S["panne_traite"]:
                return self._json({"detail": "panne"}, 503)
            if not self._jeton_ok():
                return
            if self.path == "/externe/signalements/traite":
                if corps.get("issue") not in ISSUES or not corps.get("asset"):
                    return self._json({"detail": "Demande invalide."}, 400)
                fermes = 0
                for a in S["avis"]:
                    if a["asset"] == corps["asset"] and a["id"] not in S["traites"]:
                        S["traites"][a["id"]] = corps["issue"]
                        fermes += 1
                return self._json({"fermes": fermes})
            self._json({"detail": "Not Found"}, 404)

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur, f"http://127.0.0.1:{serveur.server_address[1]}", S
