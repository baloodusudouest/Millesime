# Reprise — Millésime

Fichier à lire en premier dans une nouvelle session, et à mettre à jour à chaque fin de session, dans le même commit que le code.

## État (15/11/2026)

- **2.10.0 (15/11/2026)** : libellés suivis (`libelles()` dans `reglages.libelles`, l'actuel ajouté et mis à jour à chaque lecture ; `ajouter_libelle`, `retirer_libelle`, `/api/libelles`, `/api/libelles/retirer` ; `albums_non_datees()` pour Valider et Annuler ; `synchroniser` relit tous les libellés, s'arrête seulement si un tag déjà vu (`vu_le`) a disparu ou si aucun n'est trouvé). Jamais essayé sur la vraie installation.
- **2.9.0 (15/11/2026)** : noms des non datées lus dans Chambre noire (`lire_chambre_noire`, à chaque `synchroniser` ; `tag_prefixe`, `tag_non_datee_complet`, `album_non_datees` passent par eux quand le jeton `MILLESIME_JETON_CHAMBRE_NOIRE` est posé ; derniers noms gardés dans `reglages.chambre_noire_noms`). Tuile Chambre noire dans Connexion. Jamais essayé sur la vraie installation.
- **2.8.0 (15/11/2026)** : `GET /ha/etat` (jeton `MILLESIME_JETON_HA`, vide = fermé ; `Millesime.etat_ha`, nombres seulement) pour le package HA `systeme/millesime.yaml` ; `/api/ha/etat` retiré. Lectures notées (`carnet_vu`, `ha_vu`, rendues dans `accueil().lu_par`) ; tuile Home Assistant dans Connexion. Jamais essayé sur la vraie installation.
- **2.7.0 à 2.7.3 (14/11/2026)** : « Datables par le nom » : plusieurs dossiers ou albums cochés d'un coup, chacun à sa date modifiable (1992, 07/1992, 14/07/1992), date proposée en face du dossier, jour précis reconnu dans un nom (« 1985-12-25 », « 9 avril 1988 »).
- **2.6.0 (13/11)** : Datables en deux colonnes. **2.5.0** : `date_d_un_nom`, `datables()`, `dater_par_nom`, `annuler_lot` (annulation par lot). **2.4.0** : date lue dans le dossier, synchro légère (`maj_immich`, tour horaire, `_rafraichir_personnes`). **2.3.0** : filtres par dossier dans Dater, « ce n'est pas cette personne » (`detacher_visage`). **2.2.x** : sources (albums et dossiers) choisies dans l'appli, date déjà là comparée à l'estimation, demande à Transhumance, noms d'albums dans Réglages ; toujours sombre. **2.1.0** : cookie commun `maison_session`. **2.0.x** : format de carnet (rail et pilule, quatre entrées, tuiles).
- **1.4 à 1.6 (11/11)** : calculateur du PC en veille avec suivi en direct (`etat_pc`, `pc_passe`), noms de tags obligatoires (1.5.1, historique réécrit), lecture seule et test qui fige les écritures (1.6.0).
- **Adresses d'Immich vérifiées le 15/11/2026** contre la spécification OpenAPI d'Immich 3.4 (`open-api/immich-openapi-specs.json`) : `/view/folder/unique-paths`, `/view/folder?path=`, le filtre `albumIds` de `/search/metadata`, `PUT /faces/{id}`, `/people/{id}/merge` existent tels qu'écrits. La clé de Millésime doit avoir le droit `folder.read` (en plus de `asset.read/update`, `face.*`, `person.*`, `tag.*`, `album.*`). Jamais appelées sur la vraie installation.
- Dossier « tel que construit » : [`docs/dossier.md`](docs/dossier.md). Avis du conseil : [`docs/2.0-conseil.md`](docs/2.0-conseil.md).

## Prochaine étape

1. **Mise en service** (à faire avec Julien, rien n'a encore été essayé sur la vraie installation depuis la 1.5) : sauvegarde d'Immich ; `MILLESIME_LECTURE_SEULE=oui` et `MILLESIME_VERSION=2.8.0` dans Portainer ; vérifier la version dans Réglages ; Sources (albums et dossiers listés ? sinon droit `folder.read` de la clé) ; Datables ; un jour à regarder ; puis lecture seule retirée, une validation réelle et son Annuler.
2. **Home Assistant** : `MILLESIME_JETON_HA` dans la stack, package `systeme/millesime.yaml` v1.0 (master doc 1.78), deux secrets, redémarrage.
3. **carnet** (2.21.0) : tuile Millésime dans Connexion et tuile « Sans anniversaire » dans À traiter, par `GET /api/etat` (`CARNET_MILLESIME_URL`, `CARNET_MILLESIME_JETON` = `MILLESIME_JETON_CARNET`).
4. À vérifier : Immich change-t-il `updatedAt` d'une photo quand on y rattache un visage (sinon attendre le tour de 24 h ou « Relire la photo ») ; le cookie commun avec l'Anneau ; un dossier de la bibliothèque externe doit être inscriptible par Immich (fichier .xmp).
5. À juger à l'usage par Julien : le lie-de-vin, la pilule effacée dans Dater sur iPhone, les tuiles.

## Décisions tranchées

- Millésime écrit dans la vraie photothèque : Watchtower désactivé, mise à jour manuelle dans Portainer.
- Rien de personnel dans le dépôt public : noms de tags et d'albums, adresses et chemins passent par les variables de la stack. Les personnes des tests sont inventées.
- Dater ne passe jamais derrière une tuile (avis du conseil) : c'est le geste répété.
- Pas de validation par lot.

## Pièges

- 2.0 : l'écran « Connexion » (les services) est `frontend/src/pages/Services.svelte` ; `pages/Connexion.svelte` est la page du mot de passe.
- 2.0 : le thème garde les noms de couleurs d'origine (`verre`, `etiquette`, `lie`, `or`…) ; seules leurs valeurs ont changé. Le clair se fait par `prefers-color-scheme`.
- `tests/test_app.py::test_160_ce_que_valider_envoie_a_immich` fige les écritures : s'il échoue, c'est que quelque chose a changé dans ce que Millésime écrit dans la photothèque.
- Sans `MILLESIME_TAG_PREFIXE`, `MILLESIME_ALBUM_NON_DATEES` et `MILLESIME_MODELE_ALBUM`, le conteneur ne démarre pas : les poser dans Portainer **avant** de passer à la 1.5.1.
- Le calculateur du PC lit `MILLESIME_URL` dans son `.env` ; la valeur par défaut du dépôt est un exemple.
- L'historique a été réécrit : un ancien clone doit être refait, pas fusionné.
- Pousser sur `main` republie l'image `latest` quand `app/`, `frontend/` ou les tests changent.

## Retour arrière

- `MILLESIME_VERSION` dans Portainer. Les images antérieures à la 1.5.1 sont supprimées du registre : le plus ancien retour possible est la 1.5.1.
- Revenir à une ancienne image ne défait pas ce qui a été écrit dans Immich : utiliser le Journal (Annuler), ou la sauvegarde d'Immich.
