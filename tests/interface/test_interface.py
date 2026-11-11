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
    pg.locator("nav[aria-label='Principale']").locator("visible=true").first.wait_for()
    yield pg
    assert not erreurs, erreurs
    ctx.close()


def test_dater_une_photo_puis_valider_et_annuler(page):
    """Le geste répété : ouvrir Dater, lire l'année proposée, valider, pouvoir annuler."""
    page.goto(page.url.split("#")[0] + "#dater")
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
