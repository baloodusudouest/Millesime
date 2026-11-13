# Journal des versions


## 2.7.2 — 14 novembre 2026
- **Datables par le nom : la date en face du dossier.** Dans la liste de gauche, chaque dossier ou album a sa date proposée sur la même ligne, à droite de son nom. Une fois coché, elle devient un champ (vide : la date du nom ; sinon celle que tu tapes), avec en dessous la date qui sera écrite, ou « date illisible ». Le tableau à droite disparaît : il ne reste que le total, « Dater » et « Tout décocher ». La liste est plus large sur PC.
## 2.7.1 — 14 novembre 2026
- **Datables par le nom : la liste de gauche est de nouveau lisible.** Depuis la 2.7.0, la case à cocher de chaque dossier prenait toute la largeur de la ligne (elle recevait le style du champ de recherche) : on ne voyait que de grandes cases vides, sans le nom des dossiers. La case reprend sa taille ; un test d'écran vérifie la largeur de la case et du nom.
## 2.7.0 — 14/11/2026

- **Plusieurs dossiers ou albums d'un coup** dans « Datables par le nom » : une case devant chaque dossier ou album. Les cochés s'affichent en tableau, avec leur nombre de photos, la date lue dans leur nom — modifiable (1992, 07/1992 ou 14/07/1992) — et la date qui sera écrite. Un bouton date toutes leurs photos, chacun à sa date ; une date illisible bloque le bouton. Annulable d'un geste. Sur iPhone, le tableau des cochés passe au-dessus de la liste.
- Tests : 33 du serveur, 18 d'écran.

## 2.6.0 — 13/11/2026

- **« Datables par le nom » en deux colonnes.** À gauche, chaque dossier (celui qui porte la date, sous-dossiers compris) et chaque album dont le titre date des photos, avec sa date et son nombre de photos, et un champ pour chercher. Un clic montre à droite toutes ses photos en vignettes (un clic en grand) et le bouton « Dater toutes les photos à la date du dossier (…) » (ou de l'album), avec confirmation qui dit la date écrite. Annulable juste après, ou depuis le journal. Sur iPhone, la liste puis les photos, avec un retour.
- Correction : dans Dater, une photo d'avant un changement de filtre pouvait rester affichée (« photo 1 sur 0 »).
- Tests : 32 du serveur, 20 d'écran.

## 2.5.0 — 13/11/2026

- **Tuile « Datables par le nom »** dans À traiter : les photos qu'un nom de dossier, de sous-dossier ou un titre d'album date, sans visage pour les dater ou avec des visages qui disent la même chose. Celles dont les visages contredisent le nom n'y sont pas.
- **Ce qui se lit dans un nom** : une année à 4 chiffres n'importe où (« Noël 1992 chez mamie »), un mois en toutes lettres (« juillet 1985 », « déc. 1992 »), « 1983-07 », « …/1983/01/… », et une fourchette (« 1989-1992 ») proposée comme une estimation (année du milieu, avec sa marge). Le titre d'un album sert quand le dossier ne dit rien. Un nom de lot (« Numérisations 2010 », « 1998 Numérisation … », import, sauvegarde) est ignoré : c'est l'année du scan, pas de la photo.
- **« Tout dater d'un coup »** sur cette file : par lots de 100, chaque photo prend la date de son nom (le 15 du mois, le 1er juillet pour une année, l'année du milieu pour une fourchette), notée au journal avec le numéro du lot ; « Annuler tout ce lot » défait tout d'un geste.
- Tests : 31 du serveur, 18 d'écran.

## 2.4.0 — 13/11/2026

- **La date du dossier.** Un chemin comme « …/Date/1983/01/… », « …/1983-07 Vacances/… » ou « …/1983/… » donne une date. Une photo sans visage utile dont le dossier porte une date passe de « à trancher » à « à dater », avec cette année proposée (marge 0) ; « Prendre celle du dossier » l'écrit dans Immich (le 15 du mois, ou le 1er juillet pour une année seule), annulable. Quand il y a des visages, la date du dossier est comparée à l'estimation comme celles d'Immich et du nom du fichier. Vu le 13/11 : 3 955 photos « à trancher » faute de visage, venues de dossiers datés.
- **Synchronisation légère.** Celle de chaque heure ne relit plus les visages de toutes les photos (26 minutes le 13/11, 6 247 photos) : seulement les photos changées dans Immich, jamais lues, ou dont c'est le tour (chacune une fois par jour, réparties sur 24 heures). Les noms, dates de naissance et masquages viennent d'une seule lecture des personnes. Le bouton « Synchroniser » relit tout. La première synchro après la mise à jour relit encore tout, une fois.
- Tests : 28 du serveur, 16 d'écran.

## 2.3.0 — 13/11/2026

- **Filtrer « Dater »** par dossier — la liste montre l'arbre des dossiers, et un dossier parent garde tout ce qu'il contient, avec le nombre de photos — et/ou par nom : le fichier, le dossier ou une personne sur la photo. Le chemin de la photo s'affiche au-dessus. Les chemins arrivent à la synchronisation suivante (chaque heure, ou « Synchroniser »).
- **« Ce n'est pas cette personne »** sur chaque visage reconnu d'une photo à dater : le visage est retiré de la personne dans Immich (il passe dans un groupe neuf, sans nom, à nommer), l'estimation est refaite sans lui. Noté au journal, annulable.
- Tests : 25 du serveur, 16 d'écran.

## 2.2.1 — 13 novembre 2026
- **Toujours sombre.** Le thème clair est retiré : l'appli est sombre partout, ouverte seule comme dans l'Anneau, quel que soit le réglage du téléphone.

## 2.2.0 — 13 novembre 2026
- **Choisir dans l'appli ce que Millésime date.** Réglages › « Ce que Millésime date » : en plus des scans tagués, on ajoute des albums et des dossiers d'Immich, plusieurs à la fois, avec un filtre. Toutes les photos d'une source choisie sont à dater. Un code couleur dit d'où vient chaque chose, dans les réglages et sur l'écran « Dater » : or pour un scan tagué, bleu pour un album, orange pour un dossier (le mot est toujours écrit à côté). Un dossier ne prend que les photos rangées directement dedans.
- **Valider une photo d'album ou de dossier n'écrit que la date et le tag « Date estimée ».** Elle reste où elle est : aucun mouvement d'album. Les scans tagués gardent leur rangement par année.
- **Une date déjà là est comparée à l'estimation.** Quand la photo porte une date dans Immich (autre que le 1900 des non datés) ou dans son nom de fichier, « Dater » montre les dates côte à côte, dit s'il y a une incohérence, et demande laquelle choisir : garder celle d'Immich (rien n'est écrit), prendre celle du nom du fichier, ou valider l'estimation. Chaque choix s'annule.
- **Demande de passage à Transhumance.** Quand toutes les photos d'un dossier choisi sont datées, Millésime le signale à Transhumance (0.3.0), qui l'affiche ; rien n'est lancé. Réglage : le même jeton dans `MILLESIME_JETON_TRANSHUMANCE` et `TRANSHUMANCE_JETON_MILLESIME`. Sans jeton, un bouton le rappelle.
- **Les deux noms d'albums des scans se règlent dans l'appli** (Réglages › « Albums des scans tagués »). `MILLESIME_ALBUM_NON_DATEES` et `MILLESIME_MODELE_ALBUM` ne sont plus obligatoires dans la stack : présentes, elles donnent la valeur de départ ; un réglage enregistré passe devant. `MILLESIME_TAG_PREFIXE` reste obligatoire.
- Droit de plus pour la clé d'API : la lecture des dossiers d'Immich (vue par dossiers).
- Tests : 23 de l'appli, 12 d'écran.

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
