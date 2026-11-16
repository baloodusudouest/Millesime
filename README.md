# Millésime

Dater les photos papier numérisées à partir de l'âge des visages qu'elles contiennent, avec Immich, hors ligne.

> **Version 2.0.0** : une appli sur le NAS (écrans, écriture dans Immich) et un calculateur sur le PC (MiVOLO v2). La conception et les verdicts du conseil sont dans [`docs/conception-v2.md`](docs/conception-v2.md). Les deux tests de mesure qui ont précédé l'appli sont décrits plus bas.

## L'appli

| Écran | Rôle |
|---|---|
| Dater (écran d'ouverture) | Photo et visages, année proposée ± marge, bornes, frise de chaque personne ; Valider, Passer, Plusieurs années |
| À trancher | Cas douteux : marge trop large, visages en désaccord, aucun visage exploitable |
| Nommer | Groupes de visages sans nom sur les scans : nouveau nom, ou rattachement à une personne d'Immich (suggestions, aperçu côte à côte, fusion annulable) ; un visage touché s'affiche en grand |
| À vérifier | Visages dont l'âge estimé contredit l'âge connu, signe d'un groupe mélangé ou d'une naissance fausse |
| À traiter | Bilan (photos datées sur le total) et une tuile par file : À dater, À trancher, À nommer, À vérifier, Sans naissance, À calculer sur le PC |
| Connexion | Une tuile par service : Immich (relecture), Calculateur du PC (état, mode d'emploi), carnet |
| Réglages | Précision de l'indice, lecture d'Immich (libellé, fréquence), sources et noms d'albums, libellés suivis, restaurer les réglages (sauvegarde de l'Anneau), journal de chaque écriture dans Immich avec Annuler, déconnexion |

**Écriture à la validation** :

- date au 1er juillet de l'année, à 12:00 ;
- tag `Date estimée/AAAA ±N` ;
- retrait de l'album « Non datées Numérisation » ;
- ajout à l'album « AAAA Numérisation », créé si besoin.

Le modèle de stockage d'Immich range ensuite le fichier dans `Pellicule/AAAA/…`.

**Indice** : MiVOLO v2 (visage + buste estimé), calibré automatiquement sur les scans datés par tampon.

- Le calibrage est fait par tranche d'âge ; chaque version est conservée, avec sa précision mesurée par validation croisée (plis séparés par lot et par personne).
- Une date validée ne sert jamais au calibrage.
- Les bornes sont souples : une contradiction envoie la photo dans « À trancher », au lieu de forcer l'année.

### Installation sur le NAS (stack homelab)

```yaml
  millesime:
    image: ghcr.io/baloodusudouest/millesime:${MILLESIME_VERSION:-latest}
    container_name: millesime
    depends_on:
      - immich-server
    environment:
      - TZ=${TZ}
      # Variables communes de la maison (module app/maison.py) ; depuis la 2.12, seules lues pour le mot de passe et le jeton
      - MAISON_PASSWORD=${MAISON_PASSWORD}         # mot de passe commun des applis (12 caractères au moins)
      - MAISON_JETON=${MAISON_JETON:-}             # jeton commun : carnet (porte /api/etat), Anneau (sauvegarde, annuaire), Transhumance, Chambre noire
      - MAISON_LECTURE_SEULE=${MAISON_LECTURE_SEULE:-}   # « oui » : aucune appli n'écrit ; MILLESIME_LECTURE_SEULE l'emporte si posée
      - MILLESIME_LECTURE_SEULE=${MILLESIME_LECTURE_SEULE:-}   # « oui » ou « non » : force Millésime seul
      - MILLESIME_IMMICH_URL=http://immich_server:2283
      - MILLESIME_IMMICH_CLE=${MILLESIME_IMMICH_CLE}
      - MILLESIME_JETON_CALCUL=${MILLESIME_JETON_CALCUL}
      - MILLESIME_JETON_HA=${MILLESIME_JETON_HA:-}       # 2.8 : jeton de Home Assistant (/ha/etat) ; vide : adresse fermée
      # 2.12 : le libellé des numérisations, la relecture d'Immich et les noms d'albums se règlent dans Réglages.
      # Les anciennes lignes MILLESIME_TAG_PREFIXE, MILLESIME_SYNCHRO_MINUTES, MILLESIME_ALBUM_NON_DATEES et
      # MILLESIME_MODELE_ALBUM ne sont lues qu'une fois, au premier démarrage de la 2.12, pour reprendre leur valeur.
    ports:
      - "${PORT_MILLESIME:-8098}:8098"
    volumes:
      - ${DOCKER_ROOT}/millesime/state:/state
    labels:
      - "com.centurylinklabs.watchtower.enable=false"
    restart: unless-stopped
```

| Variable | Défaut | Rôle |
|---|---|---|
| `MAISON_PASSWORD` | — | Mot de passe commun des applis de la maison (12 caractères au moins) ; seul lu depuis la 2.12 |
| `MAISON_JETON` | vide | Jeton commun des échanges entre applis maison : ouvre `GET /api/etat` (carnet) et `GET /externe/sauvegarde` (Anneau), part avec les demandes à Transhumance, à Chambre noire et à l'Anneau (annuaire, sauvegardes). Vide : ces portes sont fermées. Home Assistant et le PC gardent leurs jetons |
| `MAISON_JETON_ANCIEN` | vide | Accepté en plus pendant un changement de jeton commun |
| `MAISON_LECTURE_SEULE` | vide | `oui` : aucune appli de la maison n'écrit ; `MILLESIME_LECTURE_SEULE` (`oui`/`non`) l'emporte pour Millésime |
| `MAISON_ANNEAU_URL` | `http://anneau:8094` | Adresse de l'Anneau dans la stack (annuaire des adresses, sauvegardes des réglages) |
| `MILLESIME_IMMICH_URL` | `http://immich_server:2283` | Adresse d'Immich vue depuis le conteneur (appels API) |
| `MILLESIME_IMMICH_CLE` | — | Clé API Immich dédiée |
| `MILLESIME_JETON_CALCUL` | — | Jeton partagé avec le calculateur du PC |
| `MILLESIME_JETON_HA` | vide | Jeton de `GET /ha/etat`, lu par Home Assistant ; vide : adresse fermée (2.8) |
| `MILLESIME_LECTURE_SEULE` | — | `oui` : rien n'est écrit dans Immich (premier jour d'une mise en service) ; `non` : écrit même si `MAISON_LECTURE_SEULE=oui` |
| `MILLESIME_SEUIL_DOUTE` | `4` | Marge (en années) au-delà de laquelle la photo va dans « À trancher » |
| `MILLESIME_SEUIL_SUSPECT` | `12` | Écart d'âge, en années, qui rend un visage suspect |
| `MILLESIME_TAG_NON_DATEE` | `Non datée` | Sous-tag des scans sans date |
| `MILLESIME_TAG_ESTIMEE` | `Date estimée` | Préfixe du tag écrit à la validation |

Les liens « Ouvrir dans Immich » prennent l'adresse que l'Anneau connaît (tuile « Immich », l'adresse privée si la page est ouverte par Tailscale) ; sinon Immich est cherché sur la même machine que Millésime, port 2283.

**Réglages d'usage (2.12)** : ils ne sont plus dans la stack mais dans l'écran Réglages, gardés dans `/state` et sauvegardés chaque nuit par l'Anneau (« Restaurer les réglages » les relit chez lui).

| Réglage | Type | Défaut | Repris une fois de |
|---|---|---|---|
| `tag_prefixe` — libellé des numérisations (les scans datés portent `<libellé>/AAAA-MM`, les autres `<libellé>/Non datée`) | texte, sans « / » ; facultatif si Chambre noire est reliée (son libellé passe devant) | vide | `MILLESIME_TAG_PREFIXE` |
| `synchro_minutes` — relecture d'Immich | entier, 5 à 1440 ; pris en compte sans redémarrer | `60` | `MILLESIME_SYNCHRO_MINUTES` |
| `album_non_datees` — album des scans non datés | texte (Chambre noire passe devant si elle est reliée) | vide | `MILLESIME_ALBUM_NON_DATEES` |
| `modele_album` — albums par année | texte contenant `{annee}` | vide | `MILLESIME_MODELE_ALBUM` |
| `libelles` — anciens libellés suivis (2.10) | liste | aucun | — |

Les noms de tags et d'albums ne sont jamais écrits dans le code (dépôt public) : ils sont propres à chaque photothèque. Si le tag des scans non datés est introuvable dans Immich, la synchronisation s'arrête sans rien modifier ; sans noms d'albums, valider un scan tagué est refusé.

La clé API Immich doit avoir ces permissions :

- `asset.read`, `asset.view` et `asset.update` ;
- `album.read`, `album.create`, `albumAsset.create` et `albumAsset.delete` ;
- `tag.read`, `tag.create` et `tag.asset` ;
- `face.read`, `face.update`, `person.read`, `person.create`, `person.update` et `person.merge`.

Le plus simple est de créer une clé dédiée avec toutes les permissions.

### Calculateur sur le PC (veille)

Dans `C:\\millesime`, sur un PC avec Docker Desktop, une seule fois :

```powershell
curl.exe -L -o calcul.yml https://raw.githubusercontent.com/baloodusudouest/Millesime/main/pc/calcul.yml
# Ajouter au fichier .env : MILLESIME_URL=http://192.0.2.10:8098 et MILLESIME_JETON_CALCUL=<même valeur que la stack>
docker compose -f calcul.yml up -d
```

Le calculateur tourne ensuite en **veille** tant que Docker Desktop est ouvert, et Docker Desktop le relance à chaque ouverture.

- Toutes les 5 minutes (`VEILLE_MINUTES`), il demande du travail à Millésime et calcule dès qu'un visage attend. MiVOLO n'est chargé qu'au premier visage.
- Quand la file est vide, Millésime en profite pour relire Immich, au plus toutes les 15 minutes : un visage nommé ou ajouté dans Immich est analysé en moins de 20 minutes environ.
- Les aperçus passent par Millésime : la clé Immich reste sur le NAS.
- Arrêter la veille : `docker compose -f calcul.yml down`.
- Faire une seule passe sans veille : `docker compose -f calcul.yml run --rm -e VEILLE=0 millesime-calcul`.

L'Accueil et l'écran « Calcul sur le PC » montrent en direct l’état du PC (non disponible, disponible, calcul en cours avec barre d’avancement et temps restant). `/api/etat` renvoie `pc_connecte`, et carnet ne demande d'allumer le PC que s'il ne s'est pas manifesté depuis 12 minutes.

### API pour les autres applis

- `GET /api/etat` (Bearer `MAISON_JETON`) renvoie `a_analyser`, `a_dater`, `a_trancher`, `a_nommer`, `validees`, `sans_naissance` (personnes nommées sans date de naissance) et `message` (« allume le PC… »).
- `GET /ha/etat` (Bearer `MILLESIME_JETON_HA`, 2.8) renvoie des nombres seulement : `a_dater`, `a_trancher`, `a_nommer`, `validees`, `total`, `sans_naissance` (un nombre), `a_analyser`, `pc` (`jamais_vu`, `indisponible`, `disponible`, `en_attente`, `en_cours`), `pc_pourcentage`, `pc_reste_min`, `pc_dernier_contact`.
- `GET /externe/sauvegarde` (Bearer `MAISON_JETON`, 2.12 ; `MAISON_JETON` vide : 404) renvoie les réglages d'usage pour l'Anneau (contrat de sauvegarde 1 : `contrat`, `appli`, `version`, `le`, `reglages`), jamais une variable, un chemin ou un secret.

## Test n°2 sur le PC (MiVOLO + vision locale)

Le 1er test (10/11/2026, NAS) a écarté InsightFace : il se trompe de 14 ans en médiane sur l'année d'une photo. Le test n°2 compare, sur les mêmes scans datés :

| Méthode | Ce qu'elle regarde |
|---|---|
| InsightFace | le visage (référence du 1er test) |
| MiVOLO v2, visage seul | le visage, avec un modèle de 2024 bien meilleur sur les bancs d'essai publics |
| MiVOLO v2, visage + buste | le visage et un buste estimé autour de lui |
| Vision locale (Qwen3-VL via Ollama) | la photo entière : vêtements, objets, couleurs et aspect du tirage |

Ce test est en **lecture seule**, rien n'est écrit dans Immich. Il tourne sur le PC avec Docker Desktop, et Ollama utilise la carte graphique s'il y en a une.

### Lancer le test (PowerShell)

```powershell
ollama pull qwen3-vl:8b-instruct
mkdir C:\millesime; cd C:\millesime
curl.exe -L -o compose.yml https://raw.githubusercontent.com/baloodusudouest/Millesime/main/pc/compose.yml
curl.exe -L -o .env https://raw.githubusercontent.com/baloodusudouest/Millesime/main/pc/.env.exemple
notepad .env        # mettre IMMICH_API_KEY (et corriger IMMICH_URL si besoin)
docker compose up
```

Le rapport est écrit dans `C:\millesime\data\resultats\rapport.md`, avec `visages.csv`, `photos.csv` et `vlm.csv`. Au premier lancement, les modèles sont téléchargés dans `data\models` : environ 280 Mo pour InsightFace, puis le modèle MiVOLO depuis Hugging Face.

Si la vision locale reste « injoignable », Ollama n'écoute que sur 127.0.0.1. Dans ce cas, ajoute la variable d'environnement Windows `OLLAMA_HOST=0.0.0.0`, puis redémarre Ollama.

## Le test de mesure (NAS)

Image : `ghcr.io/baloodusudouest/millesime:mesure` (InsightFace seul, léger, sans PyTorch). Le conteneur tourne une fois, écrit ses résultats, puis s'arrête.

### Ce qu'il fait

1. Il vérifie que le modèle `genderage.onnx` (InsightFace) tourne sur le processeur, y compris sans AVX.
2. Il lit le modèle de stockage d'Immich, pour savoir si changer une date déplacerait les fichiers.
3. Il prend jusqu'à 300 scans tagués `Numérisation/AAAA-MM`, dont la date vient du tampon. Pour chaque visage nommé qui a une date de naissance, il compare l'âge estimé à l'âge réel.
4. Il fait la même chose sur des photos numériques datées des mêmes personnes, pour voir si une correction apprise sur le numérique vaut aussi pour les scans.
5. Il calcule l'erreur par visage et par photo, puis rend un verdict :

   | Erreur médiane | Verdict |
   |---|---|
   | moins de 3 ans | le modèle est utile |
   | de 3 à 5 ans | indice faible |
   | plus de 5 ans | V1 sans modèle |

Depuis la version 0.2.0, le test est en lecture seule : rien n'est écrit dans Immich. Le 1er test a déjà montré que, chez toi, le modèle de stockage déplace un fichier quand sa date change.

Le test ne se relance pas tout seul. Si `resultats/rapport.md` existe, le conteneur s'arrête aussitôt : une mise à jour de la stack ne refait donc pas le test. Pour le relancer, mets `MILLESIME_TEST_FORCER=1` ou supprime `rapport.md`.

### Service à ajouter à la stack

```yaml
  millesime-mesure:
    image: ghcr.io/baloodusudouest/millesime:mesure
    container_name: millesime_mesure
    depends_on:
      - immich-server
    environment:
      - TZ=${TZ}
      - IMMICH_URL=http://immich_server:2283
      - IMMICH_API_KEY=${MILLESIME_IMMICH_CLE}
      - TAG_PREFIXE=${MILLESIME_TAG_PREFIXE}
      - TAG_NON_DATEE=Non datée
      - MAX_SCANS=300
      - REFS_PAR_PERSONNE=15
      - THREADS=2
      - MILLESIME_TEST_FORCER=${MILLESIME_TEST_FORCER:-0}
    volumes:
      - ${DOCKER_ROOT}/millesime/mesure:/data
    labels:
      - "com.centurylinklabs.watchtower.enable=false"
    mem_limit: 1g
    restart: "no"
```

### Variables

| Variable | Défaut | Rôle |
|---|---|---|
| `IMMICH_URL` | `http://immich_server:2283` | Adresse d'Immich vue depuis le conteneur |
| `IMMICH_API_KEY` | — | Clé API Immich, admin pour lire le modèle de stockage |
| `TAG_PREFIXE` | — (obligatoire) | Préfixe réel des tags de numérisation |
| `TAG_NON_DATEE` | `Non datée` | Sous-tag des scans sans date |
| `MAX_SCANS` | `300` | Nombre maximal de scans datés analysés, répartis sur toutes les périodes |
| `REFS_PAR_PERSONNE` | `15` | Nombre de photos numériques de référence par personne |
| `THREADS` | `2` (`auto` dans `mesure-pc`) | Threads processeur ; `auto` = tous les cœurs |
| `MILLESIME_TEST_FORCER` | `0` | `1` pour refaire le test alors que `rapport.md` existe |
| `INSIGHTFACE` | `1` | Méthode InsightFace |
| `MIVOLO` | `0` (`1` dans `mesure-pc`) | Méthode MiVOLO v2 |
| `MIVOLO_CORPS` | `1` | Ajoute la variante visage + buste estimé |
| `MIVOLO_MODELE` | `iitolstykh/mivolo_v2` | Modèle MiVOLO sur Hugging Face |
| `VLM_URL` | — | Adresse d'Ollama (vision locale désactivée si vide) |
| `VLM_MODELE` | `qwen3-vl:8b-instruct` | Modèle de vision d'Ollama |
| `MAX_PHOTOS_VLM` | `150` | Nombre de photos datées par la vision locale |
| `DATA_DIR` | `/data` | Modèle et résultats |

### Permissions de la clé API

Le plus simple est de donner toutes les permissions à une clé dédiée, à supprimer après le test. Le test a besoin de :

- `asset.read` et `asset.view` ;
- `face.read`, `person.read` et `tag.read` ;
- `systemConfig.read`.

### Résultats

Ils sont écrits dans `/data/resultats` :

- `rapport.md` : le résumé et le verdict, aussi affichés à la fin des logs ;
- `visages.csv` : une ligne par visage (âge réel, âge estimé, écart, taille du visage) ;
- `photos.csv` : une ligne par photo (année réelle, année estimée) ;
- `journal.txt` : le déroulé ;
- `vlm.csv` : une ligne par photo datée par la vision locale (année, fourchette, indices).

## Licences des modèles

Aucun modèle n'est inclus dans les images : ils sont téléchargés au premier lancement dans `/data/models`.

- `genderage.onnx` vient du pack `buffalo_l` d'InsightFace, réservé à un usage non commercial.
- MiVOLO v2 (`iitolstykh/mivolo_v2`) : le code est publié sous Apache-2.0 ; les conditions d'utilisation des poids sont celles de leurs auteurs.
- Qwen3-VL est téléchargé par Ollama sur le PC.

## Développement

```bash
pip install -r requirements-dev.txt uvicorn
python -m pytest -q          # appli et tests de mesure, contre de faux Immich et Ollama
cd frontend && npm ci && npx vite build
```

GitHub Actions lance les tests, dont un passage avec le vrai modèle MiVOLO. Il publie ensuite deux images :

- `mesure`, pour le NAS ;
- `mesure-pc`, pour le PC.

Chacune est aussi publiée avec les tags `-<version>` et `-sha-<commit>`.
