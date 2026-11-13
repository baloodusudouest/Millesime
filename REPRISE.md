# Reprise — Millésime

Fichier à lire en premier dans une nouvelle session, et à mettre à jour à chaque fin de session, dans le même commit que le code.

## État (11/11/2026)

- **2.5.0 (13/11/2026)** : `date_d_un_nom` (mois en lettres, année 4 chiffres, fourchette ≤ 20 ans, lots ignorés par `_LOT`), `date_du_dossier`, `_dates_des_albums` (albums dont le titre porte une date, lus à chaque synchro), colonne `date_nom_source` ; `datables()`, `dater_par_nom(lot, n)`, `annuler_lot(lot)` ; routes `POST /api/datables/dater`, `POST /api/lots/{lot}/annuler`, `GET /api/scans?statut=datables`. Une fourchette est proposée en année du milieu ± demi-écart.
- **2.4.0 (13/11/2026)** : `date_du_dossier` / `jour_du_dossier` (service.py), colonne `scans.date_dossier` ; `estimation.proposer` met « à dater » une photo sans visage utile mais à dossier daté ; `garder_date(…, "dossier")`. Synchro légère : colonnes `maj_immich` (updatedAt d'Immich) et `visages_lus_le`, tour horaire par empreinte md5 de l'id, `_rafraichir_personnes` (une lecture de /people avec les masquées) ; `POST /api/synchroniser` = complète. À vérifier : Immich change-t-il `updatedAt` d'une photo quand on y rattache un visage ? Sinon le changement attend le tour de la photo (24 h au plus) ou « Relire la photo ».
- **2.3.0 (13/11/2026)** : colonne `scans.chemin` (originalPath, rempli à la synchro), `liste()` rend `chemin` et `noms` ; filtres côté écran dans `Dater.svelte` (arbre des dossiers, niveaux communs sautés). `detacher_visage` : Immich ne laisse pas un visage sans personne, il passe dans une personne neuve sans nom (`POST /people` puis `PUT /faces/{personne}`), journal « detacher », annulation par réattribution.
- **2.2.1** (13/11/2026) : toujours sombre (blocs `prefers-color-scheme: light` retirés, variante `dark:` partout).
- **2.2.0** (13/11/2026) : sources choisies dans l'appli (table `sources`, colonne `scans.source`, `Millesime.sources/ajouter_sources/retirer_source`, `pages/Sources.svelte`) ; date déjà là comparée à l'estimation (`dates_connues`, `_comparer`, `garder_date`, colonnes `date_connue`/`date_nom`) ; demande à Transhumance (`demander_passage`) ; noms d'albums réglables (`regler_albums`). **Jamais essayé sur la vraie installation. À vérifier en premier : les adresses `/view/folder/unique-paths` et `/view/folder?path=` et le filtre `albumIds` de la recherche, écrits de mémoire de l'API d'Immich ; et le droit que la clé doit avoir pour les dossiers.** Pour un dossier de la bibliothèque externe, Immich écrit la date dans un fichier .xmp à côté de l'original : il faut que ce dossier soit inscriptible par Immich.
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
