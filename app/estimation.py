"""Calibrage de MiVOLO sur les scans datés et proposition d'une année pour les scans non datés.

Principes (conception v2, verdict du conseil) :
- le calibrage n'utilise QUE les scans datés par tampon, jamais les dates validées ;
- chaque calibrage est versionné ; une proposition indique la version utilisée ;
- les bornes sont souples : une contradiction envoie la photo dans « À trancher »
  au lieu de forcer l'année (un visage mal attribué ne doit pas exclure la bonne année) ;
- la borne haute (année d'envoi dans Immich) est sûre, elle est appliquée.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import date, datetime

from .base import Base

TRANCHES = [(0, 12, "0-12 ans"), (13, 25, "13-25 ans"), (26, 50, "26-50 ans"), (51, 200, "51 ans et +")]
N_MIN_TRANCHE = 5          # en dessous, la tranche prend les valeurs globales
SD_PLANCHER = 0.5
SD_DEFAUT = 6.0            # sans calibrage
COUVERTURE = 1.28          # marge ±N ≈ 80 % de chances de contenir l'année vraie


def tranche(age: float) -> str:
    for mini, maxi, nom in TRANCHES:
        if mini <= age < maxi + 1:
            return nom
    return TRANCHES[-1][2]


def parse_date(v) -> date | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(v)[:10])
        except ValueError:
            return None


def annee_dec(d: date) -> float:
    return d.year + (d.timetuple().tm_yday - 1) / 365.25


def age_utilise(v: dict) -> float | None:
    """Âge retenu pour un visage : visage + buste si disponible, sinon visage seul."""
    return v.get("age_corps") if v.get("age_corps") is not None else v.get("age_visage")


def _robuste(valeurs: list[float]) -> tuple[float, float]:
    m = statistics.median(valeurs)
    mad = statistics.median([abs(x - m) for x in valeurs])
    return m, 1.4826 * mad + SD_PLANCHER


# ---------------------------------------------------------------------------
# Calibrage
# ---------------------------------------------------------------------------
def observations_calibrage(base: Base) -> list[dict]:
    lignes = base.tous("""
        SELECT v.*, s.date_tampon, s.date_tampon AS lot FROM visages v JOIN scans s ON s.asset_id = v.asset_id
        WHERE s.type = 'datee' AND v.naissance IS NOT NULL AND (v.age_corps IS NOT NULL OR v.age_visage IS NOT NULL)""")
    obs = []
    for v in lignes:
        n, d = parse_date(v["naissance"]), parse_date(v["date_tampon"])
        if not n or not d:
            continue
        age_vrai = (d - n).days / 365.25
        if age_vrai < 0:
            continue
        obs.append({**v, "age_vrai": age_vrai, "ecart": age_utilise(v) - age_vrai, "tranche": tranche(age_vrai),
                    "annee_vraie": annee_dec(d), "naissance_dec": annee_dec(n)})
    return obs


def parametres(obs: list[dict]) -> dict:
    if len(obs) < N_MIN_TRANCHE:
        return {"global": {"b": 0.0, "sd": SD_DEFAUT, "n": len(obs)}, "tranches": {}}
    b, sd = _robuste([o["ecart"] for o in obs])
    p = {"global": {"b": round(b, 2), "sd": round(sd, 2), "n": len(obs)}, "tranches": {}}
    par_t = defaultdict(list)
    for o in obs:
        par_t[o["tranche"]].append(o["ecart"])
    for t, e in par_t.items():
        if len(e) >= N_MIN_TRANCHE:
            bt, sdt = _robuste(e)
            p["tranches"][t] = {"b": round(bt, 2), "sd": round(sdt, 2), "n": len(e)}
    return p


def correction(p: dict, age_brut: float) -> tuple[float, float, str]:
    """(biais, écart, tranche) pour un âge brut : la tranche est déduite de l'âge corrigé globalement."""
    g = p["global"]
    t = tranche(max(0.0, age_brut - g["b"]))
    pt = p["tranches"].get(t, g)
    return pt["b"], pt["sd"], t


def annees_photo(p: dict, visages: list[dict]) -> list[dict]:
    res = []
    for v in visages:
        age = age_utilise(v)
        n = parse_date(v.get("naissance"))
        if age is None or not n:
            continue
        b, sd, t = correction(p, age)
        res.append({"face_id": v["face_id"], "person_id": v["person_id"], "nom": v.get("person_nom") or "",
                    "naissance": n.isoformat(), "age_brut": round(age, 1), "age": round(age - b, 1),
                    "annee": round(annee_dec(n) + age - b, 2), "sd": sd, "tranche": t})
    return res


def combiner(annees: list[dict]) -> tuple[float, float]:
    w = [1 / a["sd"] ** 2 for a in annees]
    moyenne = sum(a["annee"] * wi for a, wi in zip(annees, w)) / sum(w)
    # Les visages d'une même photo partagent le grain et le flou : leurs erreurs sont corrélées,
    # l'écart combiné ne descend pas sous celui du meilleur visage.
    sd = max(math.sqrt(1 / sum(w)), min(a["sd"] for a in annees))
    return moyenne, sd


def validation_croisee(obs: list[dict], k: int = 5) -> tuple[float | None, float | None]:
    """Erreur médiane sur l'année par photo, plis séparés par lot ET par personne (relecture du conseil)."""
    if len(obs) < 20:
        return None, None
    lots = sorted({o["lot"] for o in obs})
    pli_lot = {l: i % k for i, l in enumerate(lots)}
    erreurs = []
    for i in range(k):
        test = [o for o in obs if pli_lot[o["lot"]] == i]
        personnes_test = {o["person_id"] for o in test}
        appr = [o for o in obs if pli_lot[o["lot"]] != i and o["person_id"] not in personnes_test]
        if len(appr) < N_MIN_TRANCHE or not test:
            continue
        p = parametres(appr)
        par_photo = defaultdict(list)
        for o in test:
            par_photo[o["asset_id"]].append(o)
        for ls in par_photo.values():
            a = annees_photo(p, ls)
            if a:
                m, _ = combiner(a)
                erreurs.append(abs(m - ls[0]["annee_vraie"]))
    if not erreurs:
        return None, None
    return round(statistics.median(erreurs), 1), round(100 * sum(e <= 3 for e in erreurs) / len(erreurs))


def calibrer(base: Base) -> dict:
    """Recalcule le calibrage ; crée une nouvelle version seulement si les paramètres changent."""
    obs = observations_calibrage(base)
    p = parametres(obs)
    dernier = base.un("SELECT * FROM calibrages ORDER BY version DESC LIMIT 1")
    if dernier and json.loads(dernier["params"]) == p:
        return dernier
    cv, cv3 = validation_croisee(obs)
    base.executer("INSERT INTO calibrages(cree_le, params, n_visages, cv_mediane, cv_3ans) VALUES(?,?,?,?,?)",
                  datetime.now().isoformat(timespec="seconds"), json.dumps(p), len(obs), cv, cv3)
    return base.un("SELECT * FROM calibrages ORDER BY version DESC LIMIT 1")


def calibrage_courant(base: Base) -> tuple[int | None, dict]:
    c = base.un("SELECT * FROM calibrages ORDER BY version DESC LIMIT 1")
    if not c:
        return None, parametres([])
    return c["version"], json.loads(c["params"])


# ---------------------------------------------------------------------------
# Propositions
# ---------------------------------------------------------------------------
def voisins(base: Base, scan: dict) -> dict | None:
    """Scans validés du même lot d'envoi : une fourchette suggérée, jamais imposée."""
    if not scan.get("lot"):
        return None
    ans = [r["annee_validee"] for r in base.tous(
        "SELECT annee_validee FROM scans WHERE lot=? AND statut='validee' AND asset_id<>? AND annee_validee IS NOT NULL",
        scan["lot"], scan["asset_id"])]
    if not ans:
        return None
    return {"n": len(ans), "mediane": int(statistics.median(ans)), "min": min(ans), "max": max(ans)}


def proposer(base: Base, scan: dict, version: int | None, p: dict, seuil_doute: float) -> dict:
    vs = base.tous("SELECT * FROM visages WHERE asset_id=?", scan["asset_id"])
    en_attente = [v for v in vs if v["naissance"] and age_utilise(v) is None]
    annees = annees_photo(p, vs)
    details = {"calibrage": version, "visages": annees, "voisins": voisins(base, scan),
               "sans_nom": sum(1 for v in vs if not v["person_nom"]),
               "sans_naissance": sum(1 for v in vs if v["person_nom"] and not v["naissance"])}
    if en_attente and not annees:
        return {"statut": "a_analyser", "annee_proposee": None, "marge": None,
                "raison": f"{len(en_attente)} visage(s) en attente du calcul sur le PC", "details": details}
    if not annees and scan.get("date_dossier"):
        # 2.4.0 : pas de visage pour dater, mais le dossier porte une date (…/1983/01) : elle est proposée
        d = scan["date_dossier"]
        details["dossier"] = d
        return {"statut": "a_dater", "annee_proposee": int(d[:4]), "marge": 0,
                "raison": f"date lue dans le dossier ({d}), aucun visage pour la vérifier", "details": details}
    if not annees:
        return {"statut": "a_trancher", "annee_proposee": None, "marge": None,
                "raison": "aucun visage nommé avec une date de naissance", "details": details}

    moyenne, sd = combiner(annees)
    raisons = []
    haute = scan.get("annee_envoi")
    if haute and moyenne > haute + 0.99:
        moyenne = haute + 0.5
        raisons.append(f"ramenée à l'année d'envoi ({haute})")
    naiss_max = max(annees, key=lambda a: a["naissance"])
    if moyenne < int(naiss_max["naissance"][:4]):
        raisons.append(f"avant la naissance de {naiss_max['nom'] or 'une personne présente'}")
    desaccord = [a for a in annees if abs(a["annee"] - moyenne) > 2 * a["sd"]]
    if desaccord:
        raisons.append("visages en désaccord : " + ", ".join(a["nom"] or "?" for a in desaccord))
    marge = max(1, round(COUVERTURE * sd))
    if marge > seuil_doute:
        raisons.append(f"marge trop large (±{marge})")
    details["bornes"] = {"basse_souple": int(naiss_max["naissance"][:4]), "haute": haute}
    details["en_attente"] = len(en_attente)
    doute = any(not r.startswith("ramenée") for r in raisons)
    return {"statut": "a_trancher" if doute else "a_dater", "annee_proposee": int(math.floor(moyenne)),
            "marge": marge, "raison": " ; ".join(raisons) or None, "details": details}


def recalculer_propositions(base: Base, seuil_doute: float) -> int:
    version, p = calibrage_courant(base)
    n = 0
    for scan in base.tous("SELECT * FROM scans WHERE type='non_datee' AND statut NOT IN ('validee', 'plusieurs')"):
        r = proposer(base, scan, version, p, seuil_doute)
        base.executer("UPDATE scans SET statut=?, annee_proposee=?, marge=?, raison=?, details=? WHERE asset_id=?",
                      r["statut"], r["annee_proposee"], r["marge"], r["raison"], json.dumps(r["details"]),
                      scan["asset_id"])
        n += 1
    return n


def suspects(base: Base, seuil: float) -> list[dict]:
    """Visages de scans datés dont l'âge estimé (corrigé) contredit l'âge connu de plus de `seuil` ans."""
    obs = observations_calibrage(base)
    # Chaque personne est jugée avec un calibrage calculé SANS elle : sinon une tranche d'âge dominée par
    # une seule personne absorberait son erreur (groupe de visages mélangé, date de naissance fausse).
    par_personne = {}
    res = []
    for o in obs:
        pid = o["person_id"]
        if pid not in par_personne:
            par_personne[pid] = parametres([x for x in obs if x["person_id"] != pid])
        p = par_personne[pid]
        b, _, _ = correction(p, age_utilise(o))
        ecart = age_utilise(o) - b - o["age_vrai"]
        if abs(ecart) > seuil:
            res.append({"face_id": o["face_id"], "asset_id": o["asset_id"], "person_id": o["person_id"],
                        "nom": o["person_nom"], "age_connu": round(o["age_vrai"], 1),
                        "age_estime": round(age_utilise(o) - b, 1), "ecart": round(ecart, 1),
                        "date": o["date_tampon"]})
    return sorted(res, key=lambda r: -abs(r["ecart"]))
