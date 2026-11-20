"""Tests d'écran de Millésime, sur PC et sur iPhone, contre un faux Immich.

Depuis la 1.6.0 : le parcours qui compte, « dater une photo puis valider », et son annulation."""
from __future__ import annotations

import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def adresse(tmp_path_factory):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    dossier = tmp_path_factory.mktemp("ui")
    proc = subprocess.Popen([sys.executable, "-m", "tests.interface.serveur", str(dossier), str(port)], cwd=RACINE)
    for _ in range(300):
        if (dossier / "pret").exists():
            break
        time.sleep(0.1)
    else:
        proc.terminate()
        pytest.fail("Le Millésime de démonstration n'a pas démarré.")
    yield f"http://127.0.0.1:{port}"
    proc.terminate()


@pytest.fixture(scope="module")
def navigateur():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture(params=["pc", "iphone"])
def page(request, navigateur, adresse):
    mobile = request.param == "iphone"
    ctx = navigateur.new_context(viewport={"width": 390, "height": 844} if mobile else {"width": 1280, "height": 860},
                                 is_mobile=mobile, has_touch=mobile)
    pg = ctx.new_page()
    erreurs = []
    pg.on("pageerror", lambda e: erreurs.append(str(e)))
    pg.goto(adresse)
    pg.get_by_label(re.compile("Mot de passe")).fill("essai-essai-essai")
    pg.get_by_role("button", name="Se connecter").click()
    pg.wait_for_selector("main")
    yield pg
    assert not erreurs, erreurs
    ctx.close()


def test_dater_une_photo_puis_valider_et_annuler(page):
    """Le geste répété : ouvrir Dater, lire l'année proposée, valider, pouvoir annuler."""
    # 2.0 : Dater est l'écran d'ouverture : aucun geste entre le mot de passe et « Valider »
    valider = page.get_by_role("button", name=re.compile(r"^(Valider|Confirmer) \d{4}"))
    valider.wait_for()
    annee = re.search(r"\d{4}", valider.inner_text()).group(0)
    assert page.locator("[aria-live='polite']", has_text=annee).count() == 1          # l'année affichée est celle du bouton
    assert page.locator("img[alt='Scan à dater']").count() == 1
    haut = valider.bounding_box()
    assert haut["y"] + haut["height"] <= page.viewport_size["height"] * 2.2              # atteignable sans long défilement
    valider.click()
    message = page.get_by_role("status")
    message.wait_for()
    assert annee in message.inner_text()
    message.get_by_role("button", name="Annuler").click()                                # le serveur est partagé : on remet
    page.wait_for_function("!document.querySelector('[role=status] button')")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


# ------------------------------------------------------------------ 2.0 : navigation, tuiles, Connexion, Réglages

def large(page):
    return page.viewport_size["width"] >= 900


def aller(page, onglet):
    """Par la navigation : rail sur PC, pilule sur iPhone (effacée dans Dater : on passe par « ‹ À traiter »)."""
    if not large(page) and not page.locator("nav[aria-label='Principale']").is_visible():
        page.get_by_role("link", name="‹ À traiter").click()
        page.wait_for_selector("nav[aria-label='Files à traiter']")
    page.locator(f"nav[aria-label='Principale'] a[aria-label='{onglet}']").click()


def test_20_quatre_entrees_et_pilule_effacee_dans_dater(page):
    page.get_by_role("button", name=re.compile(r"^(Valider|Confirmer) \d{4}")).wait_for()
    nav = page.locator("nav[aria-label='Principale']")
    assert nav.locator("a.onglet").count() == 4
    assert [a.get_attribute("aria-label") for a in nav.locator("a.onglet").all()] == ["Dater", "À traiter", "Connexion", "Réglages"]
    assert nav.is_visible() == large(page)                                             # iPhone : rien entre le pouce et Valider
    aller(page, "À traiter")
    page.wait_for_selector("nav[aria-label='Files à traiter'] .tuile")
    assert nav.is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def test_20_a_traiter_en_tuiles(page):
    aller(page, "À traiter")
    tuiles = page.locator("nav[aria-label='Files à traiter'] .tuile")
    tuiles.first.wait_for()
    noms = tuiles.locator(".nom-tuile").all_inner_texts()
    assert noms[:5] == ["À dater", "Datables par le nom", "À trancher", "À nommer", "À vérifier"]
    assert page.get_by_label(re.compile(r"photos datées sur")).count() == 1            # le bilan reste en tête
    tuiles.filter(has_text="À nommer").click()
    page.get_by_role("heading", name="Nommer").wait_for()
    assert page.locator("nav[aria-label='Principale'] a[aria-current='page']").get_attribute("aria-label") == "À traiter"


def test_20_connexion_par_service_et_reglages(page):
    """2.15.0 : écran « Connexion » commun (contrat 3) : six tuiles à voyant (2.16.0 : + Sillage), la fiche s'ouvre au toucher."""
    aller(page, "Connexion")
    services = page.locator("ul[aria-label='Services'] button[aria-expanded]")
    services.first.wait_for()
    noms = [n.split("\n")[0].strip() for n in services.all_inner_texts()]
    assert noms == ["Immich", "Calculateur du PC", "carnet", "Home Assistant", "Chambre noire", "Sillage"]
    services.filter(has_text="Home Assistant").click()
    fiche = page.locator("#fiche-ouverte")
    fiche.get_by_role("heading", name="Home Assistant").wait_for()
    assert "Ce qui est lu" in fiche.inner_text() and "jamais un nom" in fiche.inner_text()
    services.filter(has_text="Immich").click()
    fiche.get_by_role("heading", name="Immich").wait_for()
    fiche.get_by_role("button", name="Synchroniser maintenant").click()
    fiche.get_by_role("status").filter(has_text="Relecture faite").wait_for()   # revenu après la synchronisation
    fiche.get_by_role("button", name="Vérifier").click()
    fiche.get_by_text(re.compile(r"Vérifié (à l.instant|il y a)")).first.wait_for()
    services.filter(has_text="Calculateur du PC").click()
    fiche.get_by_role("heading", name="Calculateur du PC").wait_for()
    texte = fiche.inner_text()
    for attendu in ("Allumer normalement", "En cas de problème", "Installation (une seule fois)", "MiVOLO sur ton PC"):
        assert attendu in texte, attendu
    fiche.get_by_text("« PC non disponible » alors que le PC est allumé").click()
    fiche.get_by_text("docker ps --filter name=millesime_calcul").wait_for()
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
    aller(page, "Réglages")
    page.get_by_role("heading", name="Journal").wait_for()
    assert page.get_by_role("heading", name="Précision de l'indice").count() == 1
    page.goto(page.url.split("#")[0] + "#journal")                                     # ancienne adresse : mène à Réglages
    page.get_by_role("heading", name="Réglages", exact=True).wait_for()
    page.get_by_role("button", name="Se déconnecter").click()
    page.get_by_role("button", name="Se connecter").wait_for()


def test_220_sources_code_couleur_et_ajout(page):
    aller(page, "Réglages")
    page.get_by_role("heading", name="Ce que Millésime date").wait_for()
    legende = page.get_by_label("Légende des couleurs")
    assert legende.locator(".origine").all_inner_texts() == ["Scan tagué", "Album", "Dossier"]
    couleurs = legende.locator(".origine").evaluate_all("els => els.map(e => getComputedStyle(e).color)")
    assert len(set(couleurs)) == 3                                                       # trois origines, trois couleurs
    sources = page.get_by_role("list", name="Sources")
    sources.locator("li").first.wait_for()
    assert sources.locator("li").nth(0).locator(".origine").inner_text() == "Scan tagué"
    assert sources.locator("li .origine-dossier").count() == 1
    # Choisir un album : la liste se filtre, on en coche un, on ferme sans ajouter (le serveur est partagé)
    page.get_by_role("button", name="Ajouter des albums").click()
    choix = page.get_by_role("group", name="Choisir des albums")
    choix.wait_for()
    choix.get_by_placeholder("Filtrer les albums").fill("vieux")
    assert choix.locator("li").count() == 1 and "Vieux scans" in choix.locator("li").inner_text()
    choix.get_by_role("checkbox").check()
    assert choix.get_by_role("button", name="Ajouter (1)").is_enabled()
    choix.get_by_role("button", name="Fermer").click()
    page.get_by_role("button", name="Ajouter des dossiers").click()
    page.get_by_role("group", name="Choisir des dossiers").wait_for()
    assert page.get_by_role("heading", name="Albums des scans tagués").count() == 1
    # 2.10.0 : libellés suivis ; l'actuel n'a pas de bouton Retirer
    suivis = page.get_by_role("list", name="Libellés suivis")
    suivis.locator("li").first.wait_for()
    assert "actuel" in suivis.locator("li").first.inner_text()
    assert suivis.get_by_role("button", name="Retirer").count() == 0
    assert page.get_by_placeholder("Ajouter un ancien libellé").count() == 1
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0


def test_220_une_date_deja_la_est_comparee(page):
    aller(page, "À traiter") if False else None
    page.goto(page.url.split("#")[0] + "#dater")
    page.locator("section[aria-label='Année']").wait_for()
    for _ in range(14):                                                                  # jusqu'à une photo du dossier choisi
        if page.get_by_role("group", name="Date déjà connue").count() and \
                "Date dans Immich" in page.get_by_role("group", name="Date déjà connue").inner_text():
            break
        page.get_by_role("button", name="Passer").click()
        page.wait_for_timeout(250)
    bloc = page.get_by_role("group", name="Date déjà connue")
    bloc.wait_for()
    texte = bloc.inner_text()
    assert "Date dans Immich" in texte and "Estimée par Millésime" in texte and "Quelle date choisir ?" in texte
    assert "Cohérent" in texte or "Incohérence" in texte
    assert page.locator("section[aria-label='Année'] .origine").inner_text() == "Dossier"
    bloc.get_by_role("button", name=re.compile("Garder la date d'Immich")).click()
    message = page.get_by_role("status").filter(has_text="rien n'a été écrit")
    message.wait_for()
    message.get_by_role("button", name="Annuler").click()                                # le serveur est partagé : on remet
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0


def test_230_filtres_et_ce_n_est_pas_cette_personne(page):
    """2.3.0 : filtrer « Dater » par dossier (et ses parents) ou par nom ; détacher un visage mal attribué."""
    page.goto(page.url.split("#")[0] + "#dater")
    page.locator("section[aria-label='Année']").wait_for()
    choix = page.locator("#filtre-dossier option").all_inner_texts()
    assert any("Lot A" in c for c in choix) and any("Scans" in c for c in choix)
    total = int(re.search(r"sur (\d+)", page.get_by_text(re.compile(r"photo \d+ sur")).inner_text()).group(1))
    page.select_option("#filtre-dossier", label=next(c for c in choix if "Lot A" in c))
    filtre = page.get_by_text(re.compile(r"photo \d+ sur \d+ \(filtre"))
    filtre.wait_for()
    assert int(re.search(r"sur (\d+)", filtre.inner_text()).group(1)) < total
    page.get_by_role("button", name="Tout voir").click()
    page.fill("#filtre-nom", "zzz-personne")
    page.get_by_text("Aucune photo").wait_for()
    page.get_by_role("button", name="Tout voir").click()
    page.locator("section[aria-label='Année']").wait_for()
    reconnus = page.locator("section[aria-labelledby='titre-reconnus']")
    if reconnus.count():
        bouton = reconnus.get_by_role("button", name="Ce n'est pas cette personne").first
        bouton.click()
        reconnus.get_by_role("button", name=re.compile("Confirmer : ce n'est pas")).wait_for()   # un second appui confirme
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0


def test_260_datables_dossiers_a_gauche_photos_a_droite(page):
    """2.6.0 : la tuile ouvre la liste des dossiers et albums datables ; un clic montre leurs photos et le bouton."""
    page.goto(page.url.split("#")[0] + "#a-traiter")
    page.locator("a.tuile[href='#datables']").click()
    groupes = page.locator("aside[aria-label='Dossiers et albums'] .groupe")
    groupes.first.wait_for()
    textes = groupes.all_inner_texts()
    assert any("Noël 1992 chez mamie" in t for t in textes) and any("Vacances juillet 1987" in t for t in textes)
    groupes.filter(has_text="Vacances juillet 1987").click()
    page.locator("ul[aria-label='Photos'] img").first.wait_for()
    bouton = page.get_by_role("button", name=re.compile("Dater toutes les photos à la date de l'album"))
    assert "juillet 1987" in bouton.inner_text()
    bouton.click()
    page.get_by_role("button", name=re.compile("Confirmer : dater les 1 photos au 15 juillet 1987")).wait_for()
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0


def test_270_plusieurs_dossiers_coches(page):
    page.goto(page.url.split("#")[0] + "#datables")
    lignes = page.locator(".ligne-groupe")
    lignes.first.wait_for()
    # 2.7.1 : la case reste une case ; le nom du dossier garde sa place
    case, nom = lignes.first.locator("input.coche").bounding_box(), lignes.first.locator("button.groupe").bounding_box()
    assert case["width"] < 40 and nom["width"] > 120
    # 2.7.2 : la date proposée est en face du dossier, sur la même ligne
    proposee = lignes.first.locator(".proposee")
    assert proposee.inner_text().strip()
    b = proposee.bounding_box()
    assert b["x"] > nom["x"] + nom["width"] - 1 and abs((b["y"] + b["height"] / 2) - (nom["y"] + nom["height"] / 2)) < nom["height"] / 2
    for l in lignes.all():
        l.locator("input.coche").check()
    sel = page.get_by_role("region", name="Dossiers cochés")
    sel.wait_for()
    assert "2 dossiers ou albums cochés" in sel.inner_text()
    champ = lignes.first.locator("input.date")
    champ.fill("31/02/1992")
    assert sel.get_by_role("button", name=re.compile("Dater les")).is_disabled()                 # date illisible
    assert "date illisible" in lignes.first.inner_text()
    champ.fill("24/12/1992")
    assert "24 décembre 1992" in lignes.first.inner_text()
    sel.get_by_role("button", name=re.compile("Dater les 2 photos des 2 dossiers")).click()
    sel.get_by_role("button", name=re.compile("Confirmer : dater les 2 photos")).wait_for()
    sel.get_by_role("button", name="Tout décocher").click()
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0


# ------------------------------------------------------------------ 2.12.0 : réglages dans l'appli, restauration

def test_2120_reglages_lecture_d_immich_et_restaurer(page):
    aller(page, "Réglages")
    lecture = page.locator("section[aria-labelledby='titre-lecture']")
    lecture.get_by_label("Libellé des numérisations").wait_for()
    assert lecture.get_by_label("Libellé des numérisations").input_value() == "Numérisation"
    minutes = lecture.get_by_label(re.compile("Relire Immich"))
    assert minutes.input_value() == "60"
    enregistrer = lecture.get_by_role("button", name="Enregistrer")
    assert enregistrer.is_disabled()
    minutes.fill("2")                                                                   # hors bornes : message clair
    enregistrer.click()
    lecture.get_by_role("alert").wait_for()
    assert "entre 5" in lecture.get_by_role("alert").inner_text()
    minutes.fill("60")
    # Restaurer : dates lues chez l'Anneau, différences (actuel → sauvegardé), puis on garde l'actuel
    restaurer = page.locator("section[aria-labelledby='titre-restaurer']")
    restaurer.get_by_role("button", name="Voir les sauvegardes").click()
    restaurer.get_by_label("Sauvegarde du").wait_for()
    assert restaurer.get_by_label("Sauvegarde du").locator("option").count() == 2
    restaurer.get_by_role("button", name="Voir les différences").click()
    diff = restaurer.get_by_label("Différences avec la sauvegarde")
    diff.wait_for()
    texte = diff.inner_text()
    assert "Relecture d'Immich" in texte and "60" in texte and "120" in texte and "Ancien lot de numérisation" in texte
    assert restaurer.get_by_role("button", name=re.compile(r"^Restaurer \d réglages?$")).is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    restaurer.get_by_role("button", name="Garder les réglages actuels").click()
    assert diff.count() == 0
