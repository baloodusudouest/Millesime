# Journal des versions

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
