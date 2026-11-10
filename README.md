# Millésime

Dater les photos papier numérisées à partir de l'âge des visages qu'elles contiennent, avec Immich, hors ligne.

> **État actuel : test de mesure.** Avant de coder l'appli, on mesure si un modèle d'âge local est assez précis sur les scans pour aider à les dater. La conception et le verdict du conseil sont dans [`docs/conception.md`](docs/conception.md).

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
ollama pull qwen3-vl:8b
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
      - TAG_PREFIXE=Numérisation
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
| `TAG_PREFIXE` | `Numérisation` | Préfixe des tags de numérisation |
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
| `VLM_MODELE` | `qwen3-vl:8b` | Modèle de vision d'Ollama |
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
pip install -r requirements-dev.txt
python -m pytest -q    # tests contre un faux Immich (tests/faux_immich.py)
```

GitHub Actions lance les tests, dont un passage avec le vrai modèle MiVOLO. Il publie ensuite deux images :

- `mesure`, pour le NAS ;
- `mesure-pc`, pour le PC.

Chacune est aussi publiée avec les tags `-<version>` et `-sha-<commit>`.
