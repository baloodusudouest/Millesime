"""
Faux serveur Immich minimal, pour tester le test de mesure de bout en bout
sans NAS. Il ne reproduit que les routes utilisées par mesure/mesure.py.
"""
import io
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageDraw

CLE = "cle-test"


def _donnees():
    personnes = {
        "p1": {"id": "p1", "name": "Julien B", "birthDate": "1980-05-12"},
        "p2": {"id": "p2", "name": "Alex", "birthDate": "1975-02-01"},
        "p3": {"id": "p3", "name": "Sans Date", "birthDate": None},
    }
    tags = [
        {"id": "t1", "name": "2005-02", "value": "Numérisation/2005-02"},
        {"id": "t2", "name": "2009-08", "value": "Numérisation/2009-08"},
        {"id": "t3", "name": "Non datée", "value": "Numérisation/Non datée"},
        {"id": "t4", "name": "2010", "value": "Vacances/2010"},
    ]
    assets, par_tag, par_personne = {}, {"t1": [], "t2": [], "t3": []}, {"p1": [], "p2": [], "p3": []}

    def nouvel_asset(aid, date, liste):
        assets[aid] = {
            "id": aid, "type": "IMAGE", "localDateTime": date + "T12:00:00.000Z",
            "exifInfo": {"dateTimeOriginal": date + "T12:00:00.000Z"},
            "faces": [{"person": personnes[p] if p else None,
                       "imageWidth": 1440, "imageHeight": 1080,
                       "boundingBoxX1": 200 + 400 * i, "boundingBoxY1": 300,
                       "boundingBoxX2": 400 + 400 * i, "boundingBoxY2": 550}
                      for i, p in enumerate(liste)],
        }
        for p in liste:
            if p:
                par_personne[p].append(aid)

    # Scans datés par tampon (la date Immich est celle du mois du tampon)
    for i in range(12):
        nouvel_asset(f"s1-{i}", "2005-02-15", ["p1", "p2"] if i % 2 else ["p1", None])
        par_tag["t1"].append(f"s1-{i}")
    for i in range(8):
        nouvel_asset(f"s2-{i}", "2009-08-15", ["p2", "p3"])
        par_tag["t2"].append(f"s2-{i}")
    # Scans non datés : date fictive 1900-01-01, comme dans la vraie photothèque
    for i in range(5):
        nouvel_asset(f"nd-{i}", "1900-01-01", [] if i == 2 else ["p1"])
        par_tag["t3"].append(f"nd-{i}")
    # Photos numériques datées
    for i in range(30):
        nouvel_asset(f"num-{i}", f"{2010 + i % 14}-0{1 + i % 9}-10", ["p1"] if i % 3 else ["p2"])
    return personnes, tags, assets, par_tag, par_personne


def demarrer(port: int = 0, stockage_actif: bool = False, pannes: int = 0):
    """Lance le faux Immich dans un thread ; renvoie (serveur, url, état)."""
    personnes, tags, assets, par_tag, par_personne = _donnees()
    etat = {"assets": assets, "jobs": [], "pannes": pannes}
    modele = "{{y}}/{{y}}-{{MM}}/{{filename}}"

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

        def _corps(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def _autorise(self):
            if self.headers.get("x-api-key") != CLE:
                self._json({"message": "Invalid API key"}, 401)
                return False
            return True

        def do_GET(self):
            if etat["pannes"] > 0:
                etat["pannes"] -= 1
                return self._json({"message": "indisponible"}, 503)
            if not self._autorise():
                return
            chemin = self.path.split("?")[0]
            if chemin == "/api/server/version":
                return self._json({"major": 3, "minor": 4, "patch": 0})
            if chemin == "/api/system-config":
                return self._json({"storageTemplate": {"enabled": stockage_actif, "template": modele}})
            if chemin == "/api/tags":
                return self._json(tags)
            if chemin == "/api/faces":
                return self._json(assets[self.path.split("id=")[1]]["faces"])
            m = re.fullmatch(r"/api/assets/([^/]+)/thumbnail", chemin)
            if m:
                img = Image.new("RGB", (1440, 1080), (120, 110, 100))
                ImageDraw.Draw(img).ellipse((200, 300, 400, 550), fill=(220, 180, 150))
                buf = io.BytesIO()
                img.save(buf, "JPEG")
                b = buf.getvalue()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            m = re.fullmatch(r"/api/assets/([^/]+)", chemin)
            if m:
                return self._json({k: v for k, v in assets[m.group(1)].items() if k != "faces"})
            self._json({"message": "not found"}, 404)

        def do_POST(self):
            if not self._autorise():
                return
            corps = self._corps()
            if self.path == "/api/search/metadata":
                ids = par_tag.get(corps["tagIds"][0], []) if "tagIds" in corps \
                    else par_personne.get(corps["personIds"][0], [])
                taille, page = corps["size"], corps["page"]
                tranche = ids[(page - 1) * taille: page * taille]
                suivante = str(page + 1) if page * taille < len(ids) else None
                items = [{k: v for k, v in assets[i].items() if k != "faces"} for i in tranche]
                return self._json({"assets": {"items": items, "nextPage": suivante}})
            if self.path == "/api/assets/jobs":
                etat["jobs"].append(corps)
                self.send_response(204)
                self.end_headers()
                return
            self._json({}, 404)

        def do_PUT(self):
            if not self._autorise():
                return
            m = re.fullmatch(r"/api/assets/([^/]+)", self.path)
            assets[m.group(1)]["exifInfo"]["dateTimeOriginal"] = self._corps()["dateTimeOriginal"]
            self._json({"ok": True})

    serveur = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur, f"http://127.0.0.1:{serveur.server_address[1]}", etat


if __name__ == "__main__":
    s, url, _ = demarrer(2283)
    print(f"Faux Immich sur {url} (clé : {CLE})")
    threading.Event().wait()
