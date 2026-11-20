# Journal des versions

## 2.16.0 — 20 novembre 2026 (fiche « Sillage » dans Connexion)
- Sixième fiche « Connexion » : **Sillage** (maison, `cible="sillage"`). Lu : les années que les invités proposent sous leurs photos (« Pas la bonne année ? »), relues toutes les 15 minutes et sur « Relire », arrivées dans « Reçues des invités ». Écrit : « photo traitée » quand tu acceptes, corriges ou écartes (Sillage ferme ses avis), jamais en lecture seule. Le lien existait depuis la 2.13.0 sans fiche.
- « Vérifier » : un GET `/externe/signalements` (jeton commun), rien de gardé ni confirmé. La lecture régulière de 15 minutes sert aussi d'essai (`SERVICES.noter`).
- `MILLESIME_SILLAGE_URL` et `MAISON_JETON` (rien de nouveau dans la stack). Tests : `tests/test_fiches_connexion.py` (2 de plus), écran Connexion à six tuiles.
- **Jamais essayé sur la vraie installation.**

## 2.15.1 — 20 novembre 2026 (socle 0.11.1)
- Copies communes du socle 0.11.1 : sur une fiche « Connexion », le titre devient « Pour le relier » quand le réglage se fait dans Réglages de l'appli (et non dans la stack).
- **Jamais essayé sur la vraie installation.**

## 2.15.0 — 20 novembre 2026 (fiches « Connexion » communes, contrat 3)
- **Écran « Connexion » commun** des applis maison : `frontend/src/lib/services/Services.svelte` et `FicheService.svelte`, copiés du socle 0.11.0 tels quels (empreintes testées, jamais retouchés). Cinq services, donc des tuiles à voyant (deux colonnes sur téléphone) ; la fiche s'ouvre au toucher : point d'état et état en mots, Ce qui est lu, Ce qui est écrit, Vérifier (ne teste que ce service), « Pour le relier, dans la stack » quand il n'est pas réglé. Anciens écrans `pages/Services.svelte` et `pages/Calcul.svelte` retirés ; les liens `#connexion/pc` mènent à Connexion (la fiche ne s'ouvre plus d'elle-même).
- **Serveur** (`app/main.py`, section « fiches Connexion ») : `GET /api/maison/services` et `POST /api/maison/services/{id}/verifier` (session de Millésime ou `ANNEAU_CLE`, jamais `MAISON_JETON`), `app/maison.py` du socle 0.11.0 (contrat 3). Services, textes repris de l'ancien écran :
  - `immich` : essai = version d'Immich (une demande, 5 s) et dernière relecture ; geste **« Synchroniser maintenant »** (route `POST /api/synchroniser` inchangée), qui sert aussi d'essai à Immich et à Chambre noire ; dernière écriture = dernière ligne du journal qui a écrit dans Immich. Le bouton « Ouvrir Immich » de l'ancienne fiche n'est plus là.
  - `pc-calcul` (Calculateur du PC) : essai = **dernier contact connu de Millésime seulement**, jamais d'appel au PC (un PC éteint ou en veille « ne répond pas ») ; **marche à suivre** au format de la fiche « IA du PC » de Gazette : réglages lus (état du PC et phrase de l'ancien écran, visages en attente, dernier calcul, jeton réglé ou non, passages), « Allumer normalement », « En cas de problème » (8 signes, commandes PowerShell et docker à copier), « Installation (une seule fois) » (Docker Desktop, `C:\millesime`, `calcul.yml`, lignes du `.env`), l'explication de l'ancien écran en note. Le jeton n'est jamais montré.
  - `carnet` et `home-assistant` : ce sont eux qui viennent lire ; l'essai relit la date de leur dernier passage (48 h et 2 h, comme l'ancien voyant).
  - `chambre-noire` : essai = lecture des noms (`/externe/noms`, jeton commun), sans les mettre en usage. Le second bouton « Relire maintenant » de l'ancienne fiche (même route que Synchroniser) n'est plus là : Synchroniser, sur Immich, relit aussi Chambre noire.
- Synchroniser reste permis en lecture seule (il ne fait que lire Immich), comme avant.
- `app.css` : alias des jetons attendus par les fichiers communs (`background`, `foreground`, `card`, `border`, `input`, `muted-foreground`, `primary` = lie-de-vin, `primary-foreground`, `destructive`), couleur de bordure par défaut, classes `.titre` et `.etiquette`.
- **À retirer en 2.16.0** : la partie « services » de `GET /api/accueil` (`lu_par`, `chambre_noire`, `derniere_synchro`, `synchro_minutes`, `dernier_calcul`, `pc`), que plus aucun écran ne lit ; le reste de la route (compteurs, tâches) sert toujours.
- Nouvelle variable `ANNEAU_CLE` (vide = l'Anneau ne lit pas les fiches) dans l'exemple de stack du README.
- Tests : 78 réussis et 1 sauté sans MiVOLO (9 nouveaux, `tests/test_fiches_connexion.py` : forme du contrat 3, accès, empreintes, guide du calculateur, Vérifier sans appel au PC ni écriture, en lecture seule) ; 20 tests d'écran réussis (parcours Connexion adapté).
- **Jamais essayé sur la vraie installation.** Aucune commande de la marche à suivre du PC n'a été essayée sur le vrai PC.

## 2.14.0 — 18 novembre 2026 (santé des tâches de fond)
- **Tâches suivies dans `/health`** (champ `taches`, socle 0.9.1) : `synchro-immich` (régulière, période = intervalle de Réglages › Lecture d'Immich, 5 min au moins ; redéclarée à chaque tour si l'intervalle change), `lecture-sillage` (régulière, 900 s : la lecture des dates signalées par les invités chez Sillage, toutes les 15 min), `synchro-complete` (à la demande : bouton « Synchroniser »), `copie-des-bases` (régulière, 86 400 s).
- La lecture chez Sillage garde toujours l'erreur pour elle (notée en base, montrée dans « Reçues des invités ») ; le tour est maintenant compté comme raté quand Sillage n'a pas répondu, pour que `/health` le dise (« en retard » au bout de 40 min sans réussite). Rien d'autre ne change, pas de ligne en plus au journal.
- **Copie de la base** chaque nuit à **01:40, heure de Paris** : `millesime.db` copiée de façon cohérente (API de sauvegarde de SQLite, vérifiée) vers `<MILLESIME_ETAT>/copies/millesime-derniere.db`, écrasée chaque nuit (Hyper Backup tient l'historique) ; état dans `/health` (`copie_base`).
- `/health` : champs ajoutés `version_socle`, `taches`, `copie_base` ; rien d'existant ne change. Les messages d'erreur des tâches n'y sont qu'avec le jeton commun (`Authorization: Bearer MAISON_JETON`) ou une session valide.
- `maison.py` du socle 0.9.0. Un seul worker uvicorn (registre en mémoire).
- Jamais essayé sur la vraie installation (ni la copie de nuit, ni sa remise en place).
- Tests : 69 réussis et 1 sauté sans MiVOLO (2 nouveaux, `tests/test_sante.py`).

## 2.13.0 — 18 novembre 2026 (reçues des invités)
- **Nouvelle tuile « Reçues des invités »** dans À traiter, avec son compteur (une photo par ligne), et sa page (`#recues`) : les années que les invités proposent sous leurs photos dans Sillage 0.17 (« Pas la bonne année ? »). Pour chaque photo : tous les avis (année, « environ », souvenir de l'invité affiché comme du texte, prénoms, date d'envoi), la date actuelle dans Immich, l'estimation de Millésime s'il y en a une, et « date déjà changée depuis l'avis » quand la date d'Immich n'est plus celle que l'invité voyait.
- **Gestes** : « Accepter <année> » (un bouton par année proposée), « Corriger » (Julien tape l'année), « Écarter ». Accepter et corriger passent par la même écriture qu'« À dater » (1er juillet à midi, tag `Date estimée/AAAA ±1`, ±3 si tous les avis de cette année disent « environ »), le même journal (source « avis d'invité ») et le même Annuler ; une photo d'appareil, qui n'est pas un scan, reçoit la date et le tag. Écarter n'écrit rien dans Immich. « Tout accepter » ne prend que les photos à un seul avis, à deux ans près de l'estimation de Millésime. Refusés en lecture seule.
- **Lecture chez Sillage** toutes les 15 minutes et sur « Relire » (`GET /externe/signalements`, jeton commun `MAISON_JETON`, contrat 1 ; nouvelle variable `MILLESIME_SILLAGE_URL`, défaut `http://sillage:8093`). Dernière lecture gardée en base (table `avis_invite`) : Sillage injoignable, jeton refusé ou contrat inconnu, rien ne se perd et la tuile le dit.
- **Retour à Sillage** après chaque geste (`POST /externe/signalements/traite`, qui ferme tous les avis de la photo). S'il échoue, la ligne reste « à confirmer chez Sillage » et la confirmation repart à la lecture suivante, sans rien réécrire dans Immich.
- **`/health`** donne maintenant `a_traiter` (à dater + à trancher + à nommer + à vérifier + reçues des invités, gardé 60 s) et `recues_invites`, des nombres seulement, pour la tuile de l'Anneau. Le badge de l'onglet À traiter compte aussi les reçues des invités.
- Annuler une datation ne touche plus le statut d'un scan daté par tampon (une photo datée sur l'avis d'un invité peut en être un). Le journal ne dit plus « album « undefined » » pour une photo laissée à sa place.
- Tests : 67 réussis et 1 sauté sans MiVOLO (7 nouveaux, avec un faux Sillage qui suit le contrat 1). Jamais essayé avec le vrai Sillage ni sur la vraie installation.

## 2.12.6 — 18 novembre 2026 (constats moyens de l'audit)
- **M29** : une fusion de personnes refusée par Immich (erreur, ou réponse « success: false ») est notée en échec au journal (« écriture interrompue ») et rien ne change dans Millésime ; son annulation ne défait rien si la personne d'origine existe encore. Une annulation de fusion dont Immich refuse certains visages le dit (« annulée en partie », visages restés chez la personne cible, à défaire dans Immich) au lieu de s'arrêter en route. Le rejeu des seules lectures (pas des POST) était déjà fait en 2.12.2.
- **M30** : le calculateur du PC charge le code de MiVOLO à la version donnée par la nouvelle variable `MIVOLO_REVISION` (empreinte d'un commit du modèle sur Hugging Face) ; vide, il garde la dernière version et l'écrit en avertissement. L'empreinte n'est pas encore choisie. Test de mesure 0.2.3.
- `maison.py` du socle 0.8.2 (audit M3) : réglages secrets reconnus par mots, adresse avec identifiant écartée, champ `ecartes` dans la sauvegarde (noms seulement).

## 2.12.5 — 18 novembre 2026 (plus en root)
- **L'appli ne tourne plus en root** (audit du 17/11/2026) : `entrypoint.sh` adopte le propriétaire du dossier `/state` (le compte du NAS), lui rend les fichiers créés par les versions précédentes (trois fichiers à root sur le NAS, vérifié le 18/11), puis lance l'appli avec `gosu`. `/state` à root (dossier créé par Docker) : refus avec le remède ; dépannage : `MAISON_ROOT_ACCEPTE=oui`.
- Essai de démarrage du CI avec un dossier à un compte ordinaire.

## 2.12.4 — 18 novembre 2026 (cookies Secure)
- **Cookies `Secure` en https** (audit du 17/11/2026, même correctif dans toutes les applis maison) : ouverte en https (directement, derrière Tailscale Serve qui le dit par `X-Forwarded-Proto`, ou d'après l'origine de la page), l'appli pose ses cookies de session avec l'attribut `Secure` : ils ne partent jamais en clair. En http (adresse locale), rien ne change.

## 2.12.3 — 18 novembre 2026 (révocation du cookie commun)
- **« Se déconnecter » dans l'Anneau ferme vraiment la connexion commune** (audit du 17/11/2026, même correctif dans toutes les applis maison) : le cookie commun `maison_session` porte maintenant la génération tenue par l'Anneau (« génération.expiration.signature ») ; « Se déconnecter » l'augmente, et chaque appli la lit dans l'annuaire de l'Anneau (`/externe/services`, au plus une minute de retard) : un cookie commun d'avant la déconnexion ne vaut plus nulle part. Si l'Anneau ne répond pas, le cookie reste accepté comme avant (rien ne se bloque). **Toutes les applis doivent être à jour ensemble** ; une seule reconnexion est demandée après la mise à jour.
- Module commun `maison.py` (socle 0.8.0) : `generation_commune()`, `definir_generation_commune()` ; l'annuaire lit aussi `generation_commune` (une ancienne réponse de l'Anneau, liste seule, reste lue).

## 2.12.2 — 17 novembre 2026 (corrections de l'audit, suite)
- Un âge reçu du PC de calcul qui n'est pas un nombre fini entre 0 et 120 (`Infinity`) compte comme un échec de ce visage ; avant, il bloquait toutes les synchronisations.
- Le jeton du PC de calcul n'ouvre plus que l'aperçu des photos qui attendent un calcul (avant : n'importe quelle photo de la photothèque).
- Les écritures vers Immich (POST) ne sont plus rejouées après un délai dépassé ou une erreur 5xx : un double pouvait apparaître (personne détachée, album).

## 2.12.1 — 17 novembre 2026 (connexion plus sûre)
- **Connexion plus sûre** (audit du 17/11/2026, même correctif dans toutes les applis maison) :
  - un cookie portant un caractère non ASCII donnait une erreur 500 sur toute l'API ; il est maintenant simplement refusé ;
  - les clés qui signent les cookies (celui de l'appli et le cookie commun `maison_session` posé par l'Anneau) sont tirées du mot de passe par PBKDF2 : un cookie capté sur le réseau local ne permet plus de chercher le mot de passe à grande vitesse. **Toutes les applis doivent être à jour ensemble** ; une seule reconnexion est demandée après la mise à jour ;
  - des essais de mot de passe lancés en parallèle ne contournent plus le délai : au-delà de 30 essais en 5 minutes, tout est refusé sans comparer.
- Module commun `maison.py` (socle 0.7.0) : l'annuaire de l'Anneau est relu 30 s après un échec (avant : 10 min sans adresses après un redémarrage de la stack) ; un réglage `nan` ou infini est refusé ; un `reglages.json` abîmé est mis de côté (`.corrompu`) au lieu d'être écrasé.

## 2.12.0 — 16 novembre 2026
- **Les réglages d'usage quittent la stack pour l'écran Réglages.** Nouvelle tuile **Lecture d'Immich** : le libellé des numérisations (avant `MILLESIME_TAG_PREFIXE` ; facultatif si Chambre noire est reliée) et la fréquence de relecture d'Immich (avant `MILLESIME_SYNCHRO_MINUTES`, 5 à 1440 minutes, prise en compte sans redémarrer). Les noms d'albums et les libellés suivis restent où ils étaient (Réglages, depuis la 2.2 et la 2.10).
- **Reprise une seule fois** : au premier démarrage de la 2.12.0, chaque réglage encore absent prend la valeur de son ancienne variable de la stack (`MILLESIME_TAG_PREFIXE`, `MILLESIME_SYNCHRO_MINUTES`, `MILLESIME_ALBUM_NON_DATEES`, `MILLESIME_MODELE_ALBUM`) ; une ligne au journal le dit. Ensuite ces variables ne sont plus jamais lues. Une valeur fausse (modèle sans `{annee}`, nombre illisible) est ignorée.
- **Sauvegarde chez l'Anneau** : `GET /externe/sauvegarde` (jeton commun `MAISON_JETON` ; vide : porte fermée) rend les réglages d'usage, jamais une variable, un chemin ou un secret.
- **Restaurer les réglages** (Réglages) : choisir une date, voir ce qui changerait (actuel → sauvegardé), confirmer. Ne change que les réglages, rien dans Immich : permis même en lecture seule. Anneau injoignable ou rien à restaurer : un message clair. La restauration est notée au journal.
- `GET /api/reglages` et `PUT /api/reglages` (connexion requise) ; une valeur du mauvais type est refusée avec un message clair, et rien n'est changé.
- **Anciens noms retirés** : `MILLESIME_PASSWORD` (le mot de passe est `MAISON_PASSWORD`, 12 caractères au moins, sinon Millésime ne démarre pas), `MILLESIME_JETON_CARNET` (`/api/etat` s'ouvre avec `MAISON_JETON` seul), `MILLESIME_JETON_TRANSHUMANCE` et `MILLESIME_JETON_CHAMBRE_NOIRE` (les demandes partent avec `MAISON_JETON`), `MILLESIME_IMMICH_LIEN` (l'adresse d'Immich vient de l'Anneau, sinon même machine, port 2283). Restent : `MILLESIME_LECTURE_SEULE`, `MILLESIME_JETON_HA`, `MILLESIME_JETON_CALCUL`, `MILLESIME_IMMICH_CLE`, `MILLESIME_IMMICH_URL`.
- Le libellé des numérisations n'est plus exigé au démarrage : sans lui (et sans Chambre noire), la relecture d'Immich s'arrête avec un message qui renvoie à Réglages.
- Tests : 76 réussis et 1 sauté sans MiVOLO (56 du serveur, de la connexion commune et des outils de mesure ; 20 d’écran PC et iPhone). Jamais essayé sur la vraie installation.



## 2.11.0 — 16 novembre 2026
- **Variables communes de la maison** (module commun `app/maison.py`, copié tel quel du socle). Rien ne change tant que la stack n'a pas les nouvelles variables : chaque ancien nom reste lu.
- Mot de passe : `MAISON_PASSWORD`, sinon `MILLESIME_PASSWORD` comme avant.
- Lecture seule : `MAISON_LECTURE_SEULE=oui` met toute la maison en lecture seule ; `MILLESIME_LECTURE_SEULE` (`oui` ou `non`) l'emporte pour Millésime. Le bandeau dit d'où vient la lecture seule (toute la maison ou cette appli).
- carnet ouvre `GET /api/etat` avec le jeton commun `MAISON_JETON` (ou `MAISON_JETON_ANCIEN` pendant un changement), et toujours avec `MILLESIME_JETON_CARNET`. Home Assistant (`MILLESIME_JETON_HA`) et le PC (`MILLESIME_JETON_CALCUL`) gardent leurs jetons.
- Demandes à Transhumance et lecture des noms de Chambre noire : l'ancien jeton (`MILLESIME_JETON_TRANSHUMANCE`, `MILLESIME_JETON_CHAMBRE_NOIRE`) part d'abord tant qu'il est posé, sinon `MAISON_JETON`.
- Liens « Ouvrir dans Immich » : l'adresse vient de l'Anneau (tuile « Immich », l'adresse privée si la page est ouverte par Tailscale) ; sinon `MILLESIME_IMMICH_LIEN`, sinon Immich sur la même machine, port 2283.
- Tests : 62 réussis (44 du serveur et de la connexion commune, 18 d'écran). Jamais essayé sur la vraie installation : les nouvelles variables ne sont pas encore dans la stack.

## 2.10.0 — 15 novembre 2026
- **Libellés suivis.** Millésime garde en mémoire tous les libellés de numérisation, l'actuel et les anciens, et relit à chaque fois leurs tags « Non datée » et « AAAA-MM ». Changer de libellé dans Chambre noire (ou dans la stack) n'abandonne plus les anciennes photos : l'actuel s'ajoute tout seul, les anciens restent. Demandé par Julien.
- **Réglages › Libellés suivis** : la liste (actuel, ancien, ajouté ici ; album des non datées de chacun), **Retirer** (avec confirmation ; impossible pour l'actuel) et **Ajouter un ancien libellé** à la main. Retirer ne change rien dans Immich : Millésime cesse de lire ce tag, ses photos pas encore datées quittent la liste à la relecture suivante ; le journal et ses Annuler restent.
- Valider retire la photo de l'album des non datées de n'importe quel libellé suivi (et Annuler l'y remet).
- Garde-fou revu : un libellé jamais trouvé dans Immich (nouveau, aucun envoi) n'arrête plus la relecture tant qu'un autre est trouvé ; un tag déjà vu qui disparaît d'Immich l'arrête sans rien vider et propose de retirer le libellé ; aucun tag trouvé : arrêt, comme avant.
- Sources : une ligne par libellé suivi, avec son nombre de photos non datées.
- Tests : 63 réussis. Jamais essayé sur la vraie installation.

## 2.9.0 — 15 novembre 2026
- **Noms lus dans Chambre noire.** Relié par un jeton (`MILLESIME_JETON_CHAMBRE_NOIRE`, le même que `CHAMBRE_NOIRE_JETON_MILLESIME`), Millésime lit à chaque relecture d'Immich (`GET /externe/noms` de Chambre noire) le libellé, le tag et l'album des non datées réglés dans Chambre noire (Réglages › Noms dans Immich) et les suit : un seul réglage, côté Chambre noire. Ils passent devant la stack et les Réglages (l'album des non datés n'y est plus modifiable ; l'album par année, si). Chambre noire injoignable : les derniers noms lus restent en usage et l'erreur est montrée. Nouveau libellé sans tag encore dans Immich : la relecture s'arrête sans rien vider, comme avant. Millésime n'écrit rien dans Chambre noire.
- `MILLESIME_TAG_PREFIXE` devient facultatif quand Chambre noire est reliée.
- **Connexion : tuile Chambre noire** (noms lus, dernière lecture, erreur, « Relire maintenant »).
- Tests : 62 réussis. Jamais essayé sur la vraie installation.

## 2.8.0 — 15 novembre 2026
- **Home Assistant.** Nouvelle adresse `GET /ha/etat`, avec son propre jeton (`MILLESIME_JETON_HA`, vide : adresse fermée) : photos à dater, à trancher, à nommer, visages à analyser et état du PC, en nombres seulement, jamais un nom. Le package Home Assistant `systeme/millesime.yaml` s'en sert pour les capteurs et pour te rappeler d'allumer le PC quand au moins 20 visages attendent depuis une heure. L'ancienne adresse `/api/ha/etat` (« à venir ») est retirée.
- **Connexion : tuile Home Assistant**, et la tuile carnet dit quand carnet est venu lire pour la dernière fois (voyant éteint après 48 h sans lecture).
- Tests : 60 réussis (serveur, connexion commune, outils de mesure, écrans PC et iPhone).

## 2.7.3 — 14 novembre 2026
- **Un jour précis dans le nom est reconnu.** « 1985-12-25 Noël », « 25.12.1985 », « 9 avril 1988 » ou « 1er mai 1990 » donnent ce jour-là, au lieu du 15 du mois. Vaut pour les dossiers et pour les albums ; un album au jour précis passe avant un album au mois ou à l'année. Un jour impossible (30 février) retombe sur le mois. Dans « Datables par le nom », la date proposée et la date écrite affichent ce jour ; dans « Dater », la date du dossier aussi.
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
