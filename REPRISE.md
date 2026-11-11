# Reprise — Millésime

Fichier à lire en premier dans une nouvelle session, et à mettre à jour à chaque fin de session, dans le même commit que le code.

## État (11/11/2026)

- **1.6.0 sur `main`** : mode lecture seule, test qui fige les écritures dans Immich, premier test d'écran.
- 1.5.1 : noms de tags et d'albums obligatoires dans la stack. Historique du dépôt réécrit le même jour (noms de personnes, adresse locale, chemin du NAS retirés).
- Dossier « tel que construit » et écarts avec carnet : [`docs/dossier.md`](docs/dossier.md). Avis du conseil : [`docs/2.0-conseil.md`](docs/2.0-conseil.md).
- Décisions de Julien (11/11) : quatre entrées (Dater, À traiter, Connexion, Réglages), couleur lie-de-vin, année en Bodoni gardée, trois livraisons à la suite (1.5.1, 1.6.0, 2.0.0).

## Prochaine étape

1. Julien n'a pas encore déployé la 1.5.1 (trois variables à poser dans Portainer d'abord, `homelab.yml` du projet à renvoyer quand il le demande).
2. **2.0.0** : habillage de carnet en lie-de-vin, rail sur PC et pilule sur iPhone, quatre entrées, tuiles, Connexion, Réglages. Critère : pas un geste de plus qu'en 1.5 pour valider une photo. Sauvegarde d'Immich avant la mise en service.

## Décisions tranchées

- Millésime écrit dans la vraie photothèque : Watchtower désactivé, mise à jour manuelle dans Portainer.
- Rien de personnel dans le dépôt public : noms de tags et d'albums, adresses et chemins passent par les variables de la stack. Les personnes des tests sont inventées.
- Dater ne passe jamais derrière une tuile (avis du conseil) : c'est le geste répété.
- Pas de validation par lot.

## Pièges

- Sans `MILLESIME_TAG_PREFIXE`, `MILLESIME_ALBUM_NON_DATEES` et `MILLESIME_MODELE_ALBUM`, le conteneur ne démarre pas : les poser dans Portainer **avant** de passer à la 1.5.1.
- Le calculateur du PC lit `MILLESIME_URL` dans son `.env` ; la valeur par défaut du dépôt est un exemple.
- L'historique a été réécrit : un ancien clone doit être refait, pas fusionné.
- Pousser sur `main` republie l'image `latest` quand `app/`, `frontend/` ou les tests changent.

## Retour arrière

- `MILLESIME_VERSION` dans Portainer. Les images antérieures à la 1.5.1 sont supprimées du registre : le plus ancien retour possible est la 1.5.1.
- Revenir à une ancienne image ne défait pas ce qui a été écrit dans Immich : utiliser le Journal (Annuler), ou la sauvegarde d'Immich.
