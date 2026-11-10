# Millésime

Dater les photos papier numérisées à partir de l'âge des visages qu'elles contiennent, avec Immich, hors ligne.

> **État actuel : test de mesure.** Avant de coder l'appli, on mesure si un modèle d'âge local est assez précis sur les scans pour aider à les dater. La conception et le verdict du conseil sont dans [`docs/conception.md`](docs/conception.md).

## Le test de mesure

Image : `ghcr.io/baloodusudouest/millesime:mesure`. Le conteneur tourne une fois, écrit ses résultats, puis s'arrête.

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

6. Il teste l'écriture de la date sur **une seule** photo `Numérisation/Non datée`, vérifie qu'elle tient après une relecture des métadonnées, puis remet la date d'origine. Ce test est **sauté** si le modèle de stockage range les fichiers par date.

Rien d'autre n'est écrit dans Immich.

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
      - TEST_ECRITURE=1
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
| `TEST_ECRITURE` | `1` | `0` pour ne rien écrire du tout dans Immich |
| `THREADS` | `2` | Nombre de threads du modèle |
| `MILLESIME_TEST_FORCER` | `0` | `1` pour refaire le test alors que `rapport.md` existe |
| `DATA_DIR` | `/data` | Modèle et résultats |

### Permissions de la clé API

Le plus simple est de donner toutes les permissions à une clé dédiée, à supprimer après le test. Le test a besoin de :

- `asset.read`, `asset.view` et `asset.update` ;
- `face.read`, `person.read` et `tag.read` ;
- `job.create` ;
- `systemConfig.read`.

### Résultats

Ils sont écrits dans `/data/resultats` :

- `rapport.md` : le résumé et le verdict, aussi affichés à la fin des logs ;
- `visages.csv` : une ligne par visage (âge réel, âge estimé, écart, taille du visage) ;
- `photos.csv` : une ligne par photo (année réelle, année estimée) ;
- `journal.txt` : le déroulé ;
- `sauvegarde_date_test.json` : la date d'origine de la photo du test d'écriture.

## Licence du modèle

`genderage.onnx` vient du pack `buffalo_l` d'InsightFace, réservé à un usage non commercial. Il n'est pas inclus dans l'image : le conteneur le télécharge au premier lancement dans `/data/models`.

## Développement

```bash
pip install -r requirements-dev.txt
python -m pytest -q    # tests contre un faux Immich (tests/faux_immich.py)
```

GitHub Actions lance les tests, puis publie l'image avec les tags `mesure`, `mesure-<version>` et `mesure-sha-<commit>`.
