# Millésime — conception v2

> **Objet** : dater les scans de photos papier « Non datée » dans Immich.
> **Statut** : v2 rédigée le 11/11/2026, après deux tests de mesure. Elle remplace la v1 (`conception.md`, qui garde l'historique et les résultats détaillés).
> **Étape suivante** : passage au conseil, puis code.

## 1. Le problème

Un proche numérise des tirages papier avec l'appli de scan, qui les envoie dans Immich :

- les scans dont un tampon au dos donne la date reçoivent le tag `Numérisation/AAAA-MM` ;
- les autres reçoivent `Numérisation/Non datée`, une date fictive au 01/01/1900 et l'album « Non datées Numérisation ».

Millésime aide Julien à donner une année plausible à ces scans non datés, puis l'écrit dans Immich.

## 2. Ce que les tests ont établi

| Constat | Conséquence |
|---|---|
| InsightFace se trompe de 14 ans sur l'année d'une photo | abandonné |
| MiVOLO v2 (visage + buste) estime l'âge d'un visage à 3,6 ans près, et à 2,2 ans pour les enfants | retenu comme **indice** |
| MiVOLO calibré sur les scans datés donne l'année à 2,2 ans près en médiane (validation croisée), et à moins de 3 ans pour 90 % des photos avec un enfant | correction automatique |
| Hors 1995-2000, MiVOLO calibré se trompe de 2,2 ans, contre 4,2 ans pour une année fixe | il distingue bien les époques |
| Qwen3-VL (photo entière) vieillit les photos de 8 ans et ne distingue pas les époques (corrélation 0,2) | abandonné |
| Le modèle de stockage Immich déplace le fichier quand la date change | accepté : c'est le rangement voulu |
| Seuls 137 scans datés sur 300 ont un visage nommé avec une date de naissance ; 268 visages ne sont pas nommés et 54 personnes n'ont pas de date de naissance | il faut une étape « Nommer » |
| Certains groupes de visages Immich semblent mélanger des personnes (Paul GARNIER, Jeanne DUVAL) | signalement des visages suspects |
| MiVOLO prend 1,5 s par visage sur le PC (i5-12600KF) ; le NAS (J4125) n'a pas été mesuré | les calculs se font sur le PC |

## 3. Décisions

| Sujet | Choix |
|---|---|
| Méthode | **Écran de comparaison**, avec l'estimation de MiVOLO affichée comme indice |
| Indice | MiVOLO v2, visage + buste estimé, calibré automatiquement sur les scans datés, avec un biais et un écart par tranche d'âge |
| Bornes dures | après la naissance la plus récente des personnes présentes ; avant la date du scan |
| Voisins | les scans validés du même lot de numérisation suggèrent une fourchette, sans l'imposer |
| Références | les dates validées ne servent **jamais** au calibrage, qui utilise seulement les scans datés par tampon |
| Calculs | **sur le PC uniquement**, avec un calculateur Docker lancé à la main |
| Alerte | carnet affiche « N photos à analyser : allume le PC et lance l'analyse », avec un lien vers le mode d'emploi |
| Nommer | groupes de visages des scans classés par fréquence, à nommer ou fusionner dans Immich depuis Millésime ; les dates de naissance restent gérées par carnet |
| Visages suspects | un visage dont l'âge estimé contredit l'âge connu de plus de 12 ans sur une photo datée est signalé « à vérifier » |
| Validation | photo par photo : Valider, Corriger l'année, Passer ; file « À trancher » quand c'est douteux |
| Écriture | date au 1er juillet de l'année à 12:00, tag `Date estimée/AAAA ±N`, retrait de l'album « Non datées Numérisation », ajout à l'album « AAAA Numérisation » (créé si besoin) |
| Annulation | journal local de chaque écriture, avec un bouton Annuler (date, tag et album d'origine) |
| Vision locale | abandonnée |
| Accès | Tailscale, avec le même mot de passe et le même mécanisme de session que carnet |
| Home Assistant | rien en V1 ; encart « À venir » |

## 4. Architecture

```
            PC (Docker Desktop, lancé à la main)
            ┌──────────────────────────────┐
            │ millesime-calcul             │
            │ MiVOLO v2 (PyTorch, CPU)     │──┐ récupère des tâches,
            └──────────────────────────────┘  │ renvoie les âges
                                              ▼ (HTTP + jeton)
NAS ┌──────────────────────────────────────────────┐
    │ millesime (FastAPI + SQLite + Svelte)        │──► Immich (clé API, reste sur le NAS)
    │ file des tâches, calibrage, écrans, écriture │──► /api/etat ◄── carnet (lecture nocturne)
    └──────────────────────────────────────────────┘
```

- **millesime** (NAS, port 8098, image `ghcr.io/baloodusudouest/millesime:latest`) : FastAPI, SQLite et une interface Svelte 5 + Tailwind en mode sombre, pensée pour l'iPhone et le PC. Il ne fait **aucun calcul de modèle**. Il prépare les tâches : un visage = un aperçu recadré + une boîte. Il recalcule le calibrage, propose une année, affiche les écrans et écrit dans Immich.
- **millesime-calcul** (PC, image `millesime:calcul`, issue de `mesure-pc`) :
  1. au démarrage, il demande les tâches en attente à `millesime` ;
  2. il télécharge les aperçus **par `millesime`**, qui sert de relais vers Immich : la clé Immich ne quitte pas le NAS ;
  3. il calcule les âges et les renvoie par lots de 20 ;
  4. il s'arrête quand la file est vide.

  Le NAS ne contacte jamais le PC : c'est le PC qui vient chercher le travail.
- **Tâches** :
  - les visages des scans « Non datée » ;
  - une seule fois, les visages des scans datés, pour le calibrage ;
  - chaque nouveau scan, à la passe suivante.

  Les résultats sont gardés en base : un visage déjà calculé ne l'est plus.
- **Calibrage** : pour chaque tranche d'âge, le biais médian et l'écart robuste sont tirés des visages des scans datés, et recalculés à chaque arrivée de résultats. La validation croisée par lots est affichée dans « État », pour que la précision réelle soit visible.
- **Proposition d'année** : chaque visage donne une année (naissance + âge corrigé), pondérée selon l'écart de sa tranche d'âge. Ces années sont combinées, puis bornées. La marge ±N vient de l'écart combiné, avec un plancher de ±1. Les erreurs des visages d'une même photo étant corrélées, la marge n'est jamais inférieure à l'écart de la meilleure tranche présente.
- **À trancher** : la photo y va si sa marge dépasse ±4 ans, si les visages se contredisent (écart supérieur à 2 σ), ou si aucun visage n'est exploitable.

## 5. Écrans

1. **Accueil** :
   - compteurs : à analyser (attend le PC), à dater, à trancher, à nommer, visages suspects, validées ;
   - date de la dernière analyse et précision du calibrage ;
   - lien « Lancer l'analyse sur le PC » vers le mode d'emploi.
2. **Dater (une photo)** :
   - la photo, avec ses visages encadrés ;
   - pour chaque visage : le nom, l'âge estimé et l'année déduite ;
   - la **frise** de chaque personne : ses visages aux âges connus, ordonnés, avec la photo placée sur la frise ;
   - l'année proposée ± marge, les bornes et la suggestion des voisins ;
   - les boutons Valider, Corriger (sélecteur d'année) et Passer.
3. **À trancher** : le même écran, avec la raison du doute en tête.
4. **Nommer** :
   - les groupes de visages sans nom présents sur des scans, triés par nombre de scans ;
   - pour chaque groupe : quelques visages, puis Nommer (nom au format « Prénom NOM »), Fusionner avec une personne existante ou Ignorer ;
   - l'écriture se fait dans Immich ;
   - les personnes nommées sans date de naissance partent dans la liste lue par carnet.
5. **À vérifier** : visages suspects, avec un lien vers la personne dans Immich.
6. **Mode d'emploi du calcul** :
   - installer Docker Desktop (une seule fois) ;
   - copier `compose.yml` et `.env` dans `C:\millesime` ;
   - lancer `docker compose up` ;
   - suivre l'avancement dans Millésime.
7. **Réglages** : seuils, journal des écritures avec Annuler, encart « Home Assistant — à venir ».

## 6. Liens avec les autres applis

- **carnet** :
  - il lit `GET /api/etat` chaque nuit (jeton) : `a_analyser`, `a_dater`, `a_nommer`, `sans_naissance` ;
  - s'il y a des photos à analyser, il affiche dans « État » la carte « Millésime : N photos à analyser, allume le PC », avec un lien vers le mode d'emploi ;
  - les personnes sans date de naissance arrivent dans la révision « Sans anniversaire » ;
  - côté carnet, c'est un petit ajout : une source de plus dans « État », et la liste « Sans anniversaire ».
- **Immich** : lecture des scans, des visages et des personnes ; écriture de la date, des tags, des albums, des noms de personnes et des fusions. Clé dédiée « millesime ».
- **Home Assistant** (plus tard) : `/api/etat` servira aussi à un capteur et à une notification « allume le PC ».

## 7. Déploiement

- **NAS** : service `millesime` dans `homelab.yml`.
  - Variables : `MILLESIME_IMMICH_CLE`, `MILLESIME_PASSWORD=${CARNET_PASSWORD}`, `MILLESIME_JETON_CALCUL`, `MILLESIME_JETON_CARNET`.
  - Données dans `${DOCKER_ROOT}/millesime/state`.
  - Port 8098. Watchtower désactivé, puisque l'appli écrit dans Immich.
- **PC** : `C:\millesime\compose.yml` et `.env`, avec l'adresse de Millésime et le jeton de calcul. Plus besoin de clé Immich sur le PC.
- **CI** :
  - tests avec un faux Immich ;
  - un test du calculateur avec le vrai MiVOLO ;
  - images `latest` (NAS) et `calcul` (PC).

## 8. Ordre de construction

1. **Nommer** et **À vérifier** : c'est ce qui augmente la couverture, et c'est utile tout de suite, même sans calcul.
2. File des tâches et calculateur sur le PC, avec le calibrage.
3. Écran Dater, écriture dans Immich et journal d'annulation.
4. `/api/etat` et la carte dans carnet.

## 9. Risques ouverts

- L'échantillon de calibrage est concentré sur 1995-2000 (77 %). Les scans non datés sont peut-être plus anciens, donc la précision réelle risque d'être moins bonne que mesurée.
- La date « 1er juillet 12:00 » paraît certaine dans Immich et fera ressortir ces photos dans les Souvenirs chaque 1er juillet.
- Un scan peut être une page d'album qui réunit des tirages d'années différentes.
- Fusionner des personnes dans Immich est irréversible.
- Le calcul dépend du PC : s'il n'est pas allumé, rien n'avance. C'est accepté, et l'alerte de carnet est là pour le rappeler.

## 10. Verdict du conseil (11/11/2026)

**Accord** :
- Le diagnostic tient : MiVOLO calibré est un indice utile, et la vision locale est écartée.
- Le plan est trop gros pour un travail ponctuel.
- Il manque la **taille du stock « Non datée »**, qui décide de l'architecture.
- À garder : le journal d'annulation, la règle « date validée ≠ calibrage » et la validation photo par photo.
- La **fusion de personnes depuis Millésime** est le plus dangereux : irréversible, sur des groupes déjà mélangés.

**Désaccords** :
- Calcul sur le PC en script ponctuel, ou d'abord un test de MiVOLO (ONNX) sur le NAS.
- Faut-il masquer l'indice tant que la frise n'a pas été regardée ?
- Faut-il élargir le périmètre ? Le conseil a rejeté l'élargissement : déduire des naissances puis les réutiliser pour dater tourne en rond.

**Angles morts** :
- Le tampon date le tirage, pas la prise de vue.
- La validation croisée par lots mélange les mêmes personnes, donc la précision affichée est optimiste.
- On n'a pas mesuré si l'indice aide vraiment Julien.
- On peut noter au moment du scan les indices du tirage (format, bords, noir et blanc, marque au dos) et ses souvenirs.

**Recommandation du président** :
- **Garder** :
  - un écran Dater (Valider, Corriger, Passer, tri des cas douteux) ;
  - un bouton « Plusieurs années / ne pas dater » ;
  - l'écriture de la date, du tag et de l'album annuel ;
  - le journal avec Annuler ;
  - la connexion de carnet.
- **Couper** :
  - la fusion ;
  - la file de tâches et le relais ;
  - le recalibrage continu (calibrage figé et versionné) ;
  - les bornes dures, sauf pour un visage confirmé à la main.
- **Reporter en V1.1** : Nommer dans Millésime, la frise, les visages suspects, `/api/etat` et la carte carnet.
- **Arbitrages contre deux choix de Julien** :
  - pas d'alerte « allume le PC » en V1 ;
  - les noms se donnent d'abord dans Immich.

**Première étape** : compter le stock (`mesure/compter.py`).

## 11. Taille du stock (11/11/2026, `compter.py`)

- **398 scans « Non datée »**, dont 357 (89 %) ont au moins un visage détecté.
- **144 scans (36 %) sont datables aujourd'hui**, c'est-à-dire qu'ils ont au moins un visage nommé avec une date de naissance.
- 787 visages, dont 167 nommés ; 165 de ces visages nommés ont une date de naissance.
- 64 groupes de visages sans nom. Les 10 plus fréquents réunissent 141 visages : 31, 22, 17, 16, 14, 9, 9, 8, 8 et 7.
- Le calcul MiVOLO de tout le stock prend environ **8 minutes** sur le PC.

**Conséquence** : le stock est petit et le calcul court. Cela confirme le président du conseil : un script ponctuel sur le PC suffit, sans file de tâches ni alerte. Le levier principal est de nommer la dizaine de groupes de visages les plus fréquents dans Immich, ce qui peut faire passer la couverture bien au-delà de 36 %.

## 12. Version 1.0 construite (11/11/2026)

Julien a choisi la conception v2 complète, avec l'écran Nommer **sans fusion** et l'indice visible. Les points retenus du conseil :

- **pas de fusion** : seulement nommer ou ignorer ; les corrections de groupes se font dans Immich ;
- **bornes souples** : une contradiction avec la naissance envoie la photo dans « À trancher » ; seule la borne haute (année d'envoi) est appliquée ;
- **calibrage versionné** : une nouvelle version n'est créée que si les paramètres changent ; la validation croisée sépare les plis par lot **et par personne** ;
- **visages suspects** : chaque personne est jugée avec un calibrage calculé sans elle, sinon une tranche d'âge dominée par une seule personne absorberait son erreur ;
- **marge** : 1,28 × l'écart combiné (≈ 80 % de couverture visée), jamais sous l'écart du meilleur visage, puisque les erreurs des visages d'une même photo sont corrélées ;
- **confirmation** : Valider demande un second geste quand la marge dépasse ±2 ;
- **bouton « Plusieurs années »** pour les pages d'album à plusieurs tirages ;
- **journal d'annulation** : date, tag et albums d'origine restaurés.

**Reste à faire côté carnet** : afficher la carte « N visages à analyser, allume le PC » et la liste « Sans anniversaire », à partir de `GET /api/etat`. Millésime expose déjà ces données.

## 13. Version 1.1 (11/11/2026)

À la demande de Julien, l'écran Nommer évolue :

- **Suggestions des noms d'Immich** : les personnes présentes sur des scans d'abord, puis les autres par ordre alphabétique. Un nom qui existe déjà (casse et accents ignorés) est refusé comme nouveau nom, pour éviter un doublon dans Immich.
- **Rattachement (fusion) annulable** :
  - un aperçu côte à côte du groupe et de la personne choisie, puis une confirmation ;
  - avant la fusion, Millésime note **tous** les visages du groupe, y compris hors scans ;
  - Annuler recrée une personne et lui rend ces visages un par un (`PUT /faces/{id}`) ;
  - le nommage simple devient lui aussi annulable.
- **Photo en grand** : un visage touché ouvre la photo entière, avec le visage encadré.
