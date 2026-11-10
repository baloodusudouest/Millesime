"""Faux serveur Ollama minimal : /api/tags, /api/chat (réponse JSON fixe), /api/ps."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def demarrer(annee: int = 2006, modele: str = "qwen3-vl:8b", reponse_brute: str | None = None):
    etat = {"appels": 0}

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

        def do_GET(self):
            if self.path == "/api/tags":
                return self._json({"models": [{"name": modele}]})
            if self.path == "/api/ps":
                return self._json({"models": [{"name": modele, "size": 8 * 2**30, "size_vram": 6 * 2**30}]})
            self._json({}, 404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            corps = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/chat":
                etat["appels"] += 1
                assert corps["messages"][0]["images"], "image manquante"
                assert corps["format"]["type"] == "object"
                contenu = reponse_brute if reponse_brute is not None else json.dumps(
                    {"annee": annee, "annee_min": annee - 3, "annee_max": annee + 3,
                     "indices": "couleurs du tirage"})
                return self._json({"message": {"role": "assistant", "content": contenu}})
            self._json({}, 404)

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur, f"http://127.0.0.1:{serveur.server_address[1]}", etat
