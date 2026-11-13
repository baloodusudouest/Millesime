# Journal des versions

## 2.1.0 — 13 novembre 2026
- **Connexion commune.** Connecté à l'Anneau, on n'a plus à se connecter ici : l'appli accepte le cookie « maison_session » que l'Anneau pose, quand elle est servie par la même adresse que lui. Le cookie est signé avec le mot de passe commun : une appli qui a un autre mot de passe continue de demander le sien. Il vaut trente jours, ou jusqu'au changement du mot de passe ; « Se déconnecter » le retire du navigateur.

## 2.0.1 — 12 novembre 2026
- **Correction** : annuler une fusion de personnes échouait sur le vrai Immich. Millésime inversait la personne et le visage dans la demande de rattachement (Immich répondait 400). Trouvé pendant la migration, vérifié dans le code d'Immich. Le faux Immich des tests se comporte maintenant comme le vrai sur ce point.

## 2.0.0 — 11 novembre 2026
Millésime prend le format de carnet. Aucune adresse de l'API ne change, ni la base, ni ce qui est écrit dans Immich (le test des écritures de la 1.6.0 passe sans modification).
- **Habillage commun** : fonds neutres chauds, Inter, sombre par défaut et clair quand l'appareil le demande. La couleur de Millésime est le **lie-de-vin** ; l'or reste ce qui est validé ; l'année proposée et les grands nombres restent en Bodoni.
- **Navigation de carnet** : rail à gauche sur PC, pilule d'icônes en bas sur iPhone, en quatre entrées — **Dater, À traiter, Connexion, Réglages**.
- **Dater est l'écran d'ouverture** : aucun geste entre le mot de passe et « Valider ». Sur iPhone, la pilule s'efface dans Dater et dans À trancher ; un lien « ‹ À traiter » en haut ramène à la navigation.
- **À traiter en tuiles** : le bilan (datées sur le total) en tête, puis À dater, À trancher, À nommer, À vérifier, Sans naissance, À calculer sur le PC. Une tuile ouvre sa file.
- **Connexion, une tuile par service** : Immich (dernière relecture, Synchroniser maintenant), Calculateur du PC (état en direct, mode d'emploi), carnet (ce qu'il lit).
- **Réglages** : précision de l'indice, journal des écritures avec Annuler, version, déconnexion.
- Les anciennes adresses (`#accueil`, `#calcul`, `#journal`) mènent aux nouveaux écrans. L'encart « Home Assistant, à venir » est retiré.
- Tests : 18 de l'appli, 9 des outils de mesure, 4 d'écran sur PC et sur iPhone.

## 1.6.0 — 11 novembre 2026
Les filets avant la refonte. Rien ne change dans les écrans ni dans ce que Millésime écrit.
- **Mode lecture seule** (`MILLESIME_LECTURE_SEULE=oui`) : Millésime lit Immich, reçoit les calculs du PC et propose des années, mais n'écrit rien dans Immich. Valider, Annuler, nommer et fusionner sont refusés avant toute trace dans le journal ; le client Immich refuse lui-même toute écriture ; un bandeau le rappelle.
- **Test qui fige les écritures** : ce qu'une validation et son annulation envoient à Immich est comparé à une liste de référence. Une refonte ne peut plus changer ce qui est écrit sans faire échouer ce test.
- **Premier test d'écran**, sur PC et sur iPhone : ouvrir Dater, valider l'année proposée, annuler.
- Versions de l'interface figées.
- Tests : 18 de l'appli, 9 des outils de mesure, 1 d'écran sur deux formats.

## 1.5.1 — 11 novembre 2026
- **Les noms de tags et d'albums sortent du code.** `MILLESIME_TAG_PREFIXE`, `MILLESIME_ALBUM_NON_DATEES` et `MILLESIME_MODELE_ALBUM` n'ont plus de valeur par défaut : la stack les donne. Sans eux, Millésime refuse de démarrer.
- **Garde contre un nom mal saisi** : si le tag des scans non datés est introuvable dans Immich, la synchronisation s'arrête avec un message et ne touche à rien.
- Même règle pour les outils de mesure (`TAG_PREFIXE` obligatoire).
- L'historique du dépôt a été réécrit le même jour pour en retirer des noms de personnes, une adresse du réseau local et un chemin du NAS. Les images des versions 1.0 à 1.5.0 sont à supprimer du registre.
- Tests : 16 de l'appli, 9 des outils de mesure.

## 1.0 à 1.5.0 — du 3 au 11 novembre 2026
Voir `docs/conception-v2.md`, sections 12 à 17.
