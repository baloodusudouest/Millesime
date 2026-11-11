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
    pg.get_by_label(re.compile("Mot de passe")).fill("essai")
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
    assert noms[:5] == ["À dater", "À trancher", "À nommer", "À vérifier", "Sans naissance"]
    assert page.get_by_label(re.compile(r"photos datées sur")).count() == 1            # le bilan reste en tête
    tuiles.filter(has_text="À nommer").click()
    page.get_by_role("heading", name="Nommer").wait_for()
    assert page.locator("nav[aria-label='Principale'] a[aria-current='page']").get_attribute("aria-label") == "À traiter"


def test_20_connexion_par_service_et_reglages(page):
    aller(page, "Connexion")
    services = page.locator("nav[aria-label='Services'] .tuile")
    services.first.wait_for()
    assert services.locator(".nom-tuile").all_inner_texts() == ["Immich", "Calculateur du PC", "carnet"]
    services.filter(has_text="Immich").click()
    page.get_by_role("button", name="Synchroniser maintenant").click()
    page.get_by_role("button", name="Synchroniser maintenant").wait_for()              # revenu après la synchronisation
    assert "Dernière relecture" in page.locator("section[aria-label='Immich']").inner_text()
    services.filter(has_text="Calculateur du PC").click()
    page.locator("section[aria-label='Calculateur du PC']").wait_for()
    aller(page, "Réglages")
    page.get_by_role("heading", name="Journal").wait_for()
    assert page.get_by_role("heading", name="Précision de l'indice").count() == 1
    page.goto(page.url.split("#")[0] + "#journal")                                     # ancienne adresse : mène à Réglages
    page.get_by_role("heading", name="Réglages").wait_for()
    page.get_by_role("button", name="Se déconnecter").click()
    page.get_by_role("button", name="Se connecter").wait_for()
