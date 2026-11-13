# Reprise — Millésime

Fichier à lire en premier dans une nouvelle session, et à mettre à jour à chaque fin de session, dans le même commit que le code.

## État (11/11/2026)

- **2.1.0** (13/11/2026) : connexion commune avec l'Anneau — cookie `maison_session` (accepté ; `Sessions.connecte`, `commun_valide` dans `app/auth.py`). Jamais essayée sur la vraie installation.
- **2.0.0 sur `main`** : format de carnet (habillage lie-de-vin, rail et pilule, quatre entrées, tuiles, Connexion, Réglages). Aucun changement d'API ni d'écriture.
- 1.6.0 : mode lecture seule, test qui fige les écritures dans Immich, premier test d'écran.
- 1.5.1 : noms de tags et d'albums obligatoires dans la stack. Historique du dépôt réécrit le même jour (noms de personnes, adresse locale, chemin du NAS retirés).
- Dossier « tel que construit » et écarts avec carnet : [`docs/dossier.md`](docs/dossier.md). Avis du conseil : [`docs/2.0-conseil.md`](docs/2.0-conseil.md).
- Décisions de Julien (11/11) : quatre entrées (Dater, À traiter, Connexion, Réglages), couleur lie-de-vin, année en Bodoni gardée, trois livraisons à la suite (1.5.1, 1.6.0, 2.0.0).

## Prochaine étape

1. Julien n'a pas encore déployé la 1.5.1 (trois variables à poser dans Portainer d'abord, `homelab.yml` du projet à renvoyer quand il le demande).
2. Mise en service de la 2.0.0 : sauvegarde d'Immich avant, un jour en `MILLESIME_LECTURE_SEULE=oui`, puis une validation réelle suivie d'un Annuler. Retour arrière : `MILLESIME_VERSION=1.6.0`.
3. À juger à l'usage par Julien : le lie-de-vin, la pilule effacée dans Dater sur iPhone, les tuiles.
4. Plus tard : Home Assistant (capteur « photos à dater », rappel d'allumer le PC).

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
