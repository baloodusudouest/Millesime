"""
Faux Immich pour tester l'appli Millésime : scans datés et non datés, visages, personnes
(nommées, sans nom, sans date de naissance), tags (upsert, affectation), albums.
Les âges « vrais » des visages servent au faux calculateur des tests.
"""
import io
import json
import re
import threading
import uuid
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageDraw

CLE = "cle-app"


def construire():
    personnes = {
        "julien": {"id": "julien", "name": "Julien B", "birthDate": "1980-05-12"},
        "alex": {"id": "alex", "name": "Alex DUVAL", "birthDate": "1985-03-02"},
        "mamie": {"id": "mamie", "name": "Jeanne DUVAL", "birthDate": "1944-09-20"},
        "sansdate": {"id": "sansdate", "name": "Rémi J", "birthDate": None},
        "inconnu1": {"id": "inconnu1", "name": "", "birthDate": None},
        "inconnu2": {"id": "inconnu2", "name": "", "birthDate": None},
    }
    tags = {"t-nd": {"id": "t-nd", "name": "Non datée", "value": "Numérisation/Non datée"}}
    assets, tag_assets, albums = {}, {"t-nd": set()}, {}
    verite = {}   # face_id -> âge vrai (pour le faux calculateur)

    def ajouter(aid, d_vraie, liste, tag_id, date_immich, envoi="2026-10-28T10:00:00.000Z"):
        faces = []
        for i, pid in enumerate(liste):
            fid = f"{aid}-f{i}"
            p = personnes.get(pid) if pid else None
            faces.append({"id": fid, "person": p, "imageWidth": 1440, "imageHeight": 1080,
                          "boundingBoxX1": 200 + 380 * i, "boundingBoxY1": 300,
                          "boundingBoxX2": 380 + 380 * i, "boundingBoxY2": 520})
            if p and p.get("birthDate"):
                verite[fid] = (d_vraie - date.fromisoformat(p["birthDate"])).days / 365.25
        assets[aid] = {"id": aid, "type": "IMAGE", "createdAt": envoi, "localDateTime": date_immich,
                       "exifInfo": {"dateTimeOriginal": date_immich}, "tags": [], "faces": faces}
        if tag_id:
            tag_assets.setdefault(tag_id, set()).add(aid)
            assets[aid]["tags"].append(tags[tag_id])

    # scans datés par tampon (calibrage) : 1990 à 2005
    for k, an in enumerate(range(1990, 2006)):
        tid = f"t-{an}"
        tags[tid] = {"id": tid, "name": f"{an}-06", "value": f"Numérisation/{an}-06"}
        for j in range(2):
            ajouter(f"d{an}-{j}", date(an, 6, 15), ["julien", "alex", "mamie"][: 2 + j], tid, f"{an}-06-15T12:00:00.000Z")
    # scans non datés : vraie année 1992..2000
    vraies = {}
    for i, an in enumerate([1992, 1994, 1996, 1998, 2000, 1993]):
        aid = f"nd{i}"
        vraies[aid] = an
        ajouter(aid, date(an, 7, 1), ["julien", "alex"] if i % 2 == 0 else ["mamie", "inconnu1"], "t-nd",
                "1900-01-01T00:00:00.000Z")
    ajouter("nd-sans", date(1995, 1, 1), ["inconnu1", "inconnu2", None], "t-nd", "1900-01-01T00:00:00.000Z")
    ajouter("nd-remi", date(1995, 1, 1), ["sansdate"], "t-nd", "1900-01-01T00:00:00.000Z")
    # photos numériques de Julien (frise)
    for an in (2008, 2014, 2020):
        ajouter(f"num{an}", date(an, 3, 1), ["julien"], None, f"{an}-03-01T09:00:00.000Z")
    albums["al-nd"] = {"id": "al-nd", "albumName": "Non datées Numérisation",
                       "assets": {a for a in tag_assets["t-nd"]}}
    return {"personnes": personnes, "tags": tags, "assets": assets, "tag_assets": tag_assets,
            "albums": albums, "verite": verite, "vraies": vraies, "ecritures": []}


def demarrer():
    E = construire()
    E["requetes"] = []

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

        def _vide(self, code=204):
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _corps(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def _ok(self):
            if self.headers.get("x-api-key") != CLE:
                self._json({"message": "Invalid API key"}, 401)
                return False
            return True

        def _asset_public(self, a):
            d = {k: v for k, v in a.items() if k != "faces"}
            d["tags"] = [E["tags"][t] for t, ids in E["tag_assets"].items() if a["id"] in ids]
            return d

        def _album_public(self, al):
            return {"id": al["id"], "albumName": al["albumName"], "assetCount": len(al["assets"])}

        def do_GET(self):
            if not self._ok():
                return
            chemin, _, qs = self.path.partition("?")
            q = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
            if chemin == "/api/server/version":
                return self._json({"major": 3, "minor": 4, "patch": 0})
            if chemin == "/api/tags":
                return self._json(list(E["tags"].values()))
            if chemin == "/api/faces":
                return self._json(E["assets"][q["id"]]["faces"])
            if chemin == "/api/albums":
                if "assetId" in q:
                    return self._json([self._album_public(a) for a in E["albums"].values() if q["assetId"] in a["assets"]])
                return self._json([self._album_public(a) for a in E["albums"].values()])
            m = re.fullmatch(r"/api/assets/([^/]+)/thumbnail", chemin)
            if m or re.fullmatch(r"/api/people/([^/]+)/thumbnail", chemin):
                img = Image.new("RGB", (1440, 1080), (110, 100, 90))
                ImageDraw.Draw(img).ellipse((200, 300, 380, 520), fill=(220, 180, 150))
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
                return self._json(self._asset_public(E["assets"][m.group(1)]))
            if chemin == "/api/people":
                return self._json({"people": list(E["personnes"].values()), "total": len(E["personnes"]),
                                   "hasNextPage": False})
            m = re.fullmatch(r"/api/people/([^/]+)", chemin)
            if m:
                return self._json(E["personnes"][m.group(1)])
            self._json({"message": "not found"}, 404)

        def do_POST(self):
            if not self._ok():
                return
            c = self._corps()
            if not self.path.startswith("/api/search/"):
                E["requetes"].append(("POST", self.path, c))      # 1.6.0 : ce que Millésime écrit vraiment
            if self.path == "/api/search/metadata":
                if "tagIds" in c:
                    ids = sorted(E["tag_assets"].get(c["tagIds"][0], set()))
                else:
                    pid = c["personIds"][0]
                    ids = sorted(a for a, x in E["assets"].items()
                                 if any((f["person"] or {}).get("id") == pid for f in x["faces"]))
                t, p = c["size"], c["page"]
                tranche = ids[(p - 1) * t: p * t]
                suivante = str(p + 1) if p * t < len(ids) else None
                return self._json({"assets": {"items": [self._asset_public(E["assets"][i]) for i in tranche],
                                              "nextPage": suivante}})
            m = re.fullmatch(r"/api/people/([^/]+)/merge", self.path)
            if m:
                cible = E["personnes"][m.group(1)]
                for sid in c["ids"]:
                    for x in E["assets"].values():
                        for f in x["faces"]:
                            if (f["person"] or {}).get("id") == sid:
                                f["person"] = cible
                    E["personnes"].pop(sid, None)
                E["ecritures"].append(("fusion", m.group(1), tuple(c["ids"])))
                return self._json([{"id": i, "success": True} for i in c["ids"]])
            if self.path == "/api/people":
                pid = "p-" + uuid.uuid4().hex[:6]
                E["personnes"][pid] = {"id": pid, "name": c.get("name", ""), "birthDate": None}
                return self._json(E["personnes"][pid], 201)
            if self.path == "/api/albums":
                aid = "al-" + uuid.uuid4().hex[:6]
                E["albums"][aid] = {"id": aid, "albumName": c["albumName"], "assets": set(c.get("assetIds", []))}
                E["ecritures"].append(("album+", c["albumName"]))
                return self._json(self._album_public(E["albums"][aid]), 201)
            self._json({}, 404)

        def do_PUT(self):
            if not self._ok():
                return
            c = self._corps()
            if not self.path.startswith("/api/search/"):
                E["requetes"].append(("PUT", self.path, c))      # 1.6.0 : ce que Millésime écrit vraiment
            if self.path == "/api/tags":
                res = []
                for v in c["tags"]:
                    t = next((t for t in E["tags"].values() if t["value"] == v), None)
                    if not t:
                        tid = "t-" + uuid.uuid4().hex[:6]
                        t = E["tags"][tid] = {"id": tid, "name": v.split("/")[-1], "value": v}
                        E["tag_assets"][tid] = set()
                    res.append(t)
                return self._json(res)
            m = re.fullmatch(r"/api/tags/([^/]+)/assets", self.path)
            if m:
                E["tag_assets"].setdefault(m.group(1), set()).update(c["ids"])
                return self._json([{"id": i, "success": True} for i in c["ids"]])
            m = re.fullmatch(r"/api/albums/([^/]+)/assets", self.path)
            if m:
                E["albums"][m.group(1)]["assets"].update(c["ids"])
                return self._json([{"id": i, "success": True} for i in c["ids"]])
            m = re.fullmatch(r"/api/assets/([^/]+)", self.path)
            if m:
                a = E["assets"][m.group(1)]
                a["exifInfo"]["dateTimeOriginal"] = a["localDateTime"] = c["dateTimeOriginal"]
                E["ecritures"].append(("date", m.group(1), c["dateTimeOriginal"]))
                return self._json(self._asset_public(a))
            m = re.fullmatch(r"/api/faces/([^/]+)", self.path)
            if m:
                # comme le vrai Immich : l'adresse porte la personne, le corps porte le visage
                if m.group(1) not in E["personnes"]:
                    return self._json({"message": "Bad Request"}, 400)
                for x in E["assets"].values():
                    for f in x["faces"]:
                        if f["id"] == c["id"]:
                            f["person"] = E["personnes"][m.group(1)]
                return self._json(E["personnes"][m.group(1)])
            m = re.fullmatch(r"/api/people/([^/]+)", self.path)
            if m:
                E["personnes"][m.group(1)]["name"] = c["name"]
                return self._json(E["personnes"][m.group(1)])
            self._json({}, 404)

        def do_DELETE(self):
            if not self._ok():
                return
            c = self._corps()
            if not self.path.startswith("/api/search/"):
                E["requetes"].append(("DELETE", self.path, c))      # 1.6.0 : ce que Millésime écrit vraiment
            m = re.fullmatch(r"/api/tags/([^/]+)/assets", self.path)
            if m:
                E["tag_assets"].get(m.group(1), set()).difference_update(c["ids"])
                return self._json([{"id": i, "success": True} for i in c["ids"]])
            m = re.fullmatch(r"/api/albums/([^/]+)/assets", self.path)
            if m:
                E["albums"][m.group(1)]["assets"].difference_update(c["ids"])
                return self._json([{"id": i, "success": True} for i in c["ids"]])
            self._json({}, 404)

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur, f"http://127.0.0.1:{serveur.server_address[1]}", E
