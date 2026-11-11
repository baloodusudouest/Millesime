# Millésime — document de conception (V1)

> Dater les photos papier numérisées à partir de l'âge des visages qu'elles contiennent.
> Statut : grill-me du 03/11/2026, passé au conseil le même jour. **En attente du test de mesure (§12)** avant de figer la V1.

## 1. But

Les scans « Numérisation » arrivent dans Immich avec la date du scan, pas celle de la prise de vue. Millésime propose pour chaque scan une **année probable ± marge**, déduite de l'âge estimé de chaque visage connu et de la date de naissance de la personne. Julien valide, l'appli écrit la date et un tag dans Immich.

Hors ligne : aucun appel extérieur, modèle embarqué dans l'image.

## 2. Décisions arrêtées

| Sujet | Choix |
|---|---|
| Objectif | Dater la photo (pas seulement afficher des âges) |
| Source | Immich via API (assets, visages, personnes) |
| Dates de naissance | Champ natif `birthDate` des personnes Immich (alimenté par carnet) |
| Photos à traiter | Scans tagués `Numérisation/Non datée` **sans** tag `Date estimée/…` (les tags `Numérisation/AAAA-MM` portent la date du tampon : fiables) |
| Méthode | Hybride : modèle d'âge local + correction par la frise de la personne |
| Références de la frise | Toutes les photos datées de la personne, y compris les scans `…/AAAA-MM` (date du tampon), **sauf** les scans `Non datée` |
| Voisins | Les scans validés du même lot affinent la proposition (suggestion, jamais imposée) |
| Convention de date | 1er juillet de l'année estimée, 12:00 |
| Tag écrit | `Date estimée/AAAA ±N` (ex. `Date estimée/1985 ±2`) |
| Validation | Photo par photo : Valider / Corriger l'année / Passer |
| Doute | Marge trop large ou visages contradictoires → file « À trancher », proposée en dernier |
| Personne sans naissance | Exposée dans une liste lue la nuit par carnet → révision dédiée « Sans anniversaire » |
| Visage non nommé | Liste dans Millésime avec lien vers Immich pour le nommer |
| Analyse | Lot nocturne + bouton « Analyser maintenant » |
| Interface | Web app responsive iPhone + PC, ajoutable à l'écran d'accueil, en français |
| Accès | Tailscale + même mot de passe et même mécanisme de session que carnet |
| Livraison | Dépôt `baloodusudouest/millesime`, image GHCR via GitHub Actions, service dans `homelab.yml`, mise à jour Watchtower |
| Home Assistant | Rien en V1 ; encart « À venir » dans l'appli + pense-bête (§9) |

## 3. Contraintes matérielles

- DS1520+ (Celeron J4125, **sans AVX**), ~20 Go de RAM dont ~6 utilisés (Plex, Immich, VM HA).
- Inférence en **ONNX Runtime CPU** (Immich ML tourne déjà ainsi sur ce CPU). Pas de PyTorch/TensorFlow.
- Limiter à 2 threads et priorité basse (`nice`) pour ne pas pénaliser Plex et la VM HA. Cible mémoire < 500 Mo.
- Pas de SSH sur le NAS : tout passe par Portainer.

## 4. Architecture

```
┌──────────── Millésime (conteneur) ─────────────┐
│ FastAPI ─ SQLite ─ ONNX Runtime (modèle d'âge) │
│ Planificateur interne (lot nocturne 02:30)     │
│ UI web responsive (HTML/CSS/JS, sans CDN)       │
└──────┬──────────────────────────┬──────────────┘
       │ API Immich (clé API)      │ /api/a-completer (jeton)
       ▼                           ▼
   Immich v3.x                 carnet (lecture nocturne)
```

- Python 3.12, FastAPI, onnxruntime, numpy, Pillow, SQLite.
- Modèle d'âge embarqué dans l'image (ex. `genderage.onnx` d'InsightFace, ~1 Mo ; usage personnel non commercial). Alternative à évaluer : modèle face-only plus précis s'il tient sans AVX.
- Les visages et boîtes viennent d'Immich : Millésime ne refait pas la détection, il recadre l'aperçu de l'asset sur la boîte du visage.
- Port **8097**, données dans `/volume1/docker/millesime` (dossier déjà sauvegardé hors NAS).

### Variables d'environnement

| Variable | Rôle |
|---|---|
| `IMMICH_URL` | URL interne d'Immich |
| `IMMICH_API_KEY` | Clé API (lecture assets/personnes, écriture date et tags) |
| `MILLESIME_PASSWORD` | Même valeur et même mécanisme que carnet (à reprendre du dépôt carnet) |
| `CARNET_TOKEN` | Jeton partagé pour `/api/a-completer` |
| `TAG_NUMERISATION` | Préfixe des tags à traiter (défaut `Numérisation`) |
| `ANALYSE_HEURE` | Heure du lot nocturne (défaut `02:30`) |
| `THREADS` | Threads ONNX (défaut 2) |

## 5. Algorithme de datation

1. **Collecte** : pour chaque scan `Non datée` à traiter, visages assignés à une personne Immich ayant une `birthDate`.
2. **Âge brut** : le modèle donne un âge `a` par visage recadré.
3. **Correction par la frise** : pour chaque personne, on passe le modèle sur ses photos de référence (âge réel connu). On en tire un biais par tranche d'âge (médiane des écarts). Âge corrigé `a' = a − biais(a)`.
4. **Année par visage** : `année = année_naissance + a'`, avec une incertitude σ qui dépend de la tranche d'âge (faible chez l'enfant, forte chez l'adulte) et du nombre de références.
5. **Fusion** : combinaison pondérée des visages (produit de gaussiennes), bornée par : année ≥ naissance la plus récente des personnes présentes, année ≤ année du scan.
6. **Voisins** : les scans déjà validés du même lot ajoutent une contrainte large (σ élevé), signalée « suggérée par les voisins ».
7. **Marge** : `±N` arrondi à l'entier, minimum ±1.
8. **Doute** : marge > ±4 ou écart entre visages > 2σ → file « À trancher » avec la raison affichée.

Les estimations validées deviennent des références (la date du scan est alors fiable à ±N).

## 6. Écriture dans Immich

- À la validation : `dateTimeOriginal = AAAA-07-01T12:00:00` + tag `Date estimée/AAAA ±N` (créé si absent).
- La photo quitte la file (elle porte désormais le tag `Date estimée/…`).
- Correction ultérieure : retirer l'ancien tag `Date estimée/…` avant d'en poser un nouveau.
- Journal local de chaque écriture (ancienne date, nouvelle date, tag) pour pouvoir annuler.

⚠️ À vérifier : si le modèle de stockage Immich range les fichiers par date, changer la date déplacera le fichier depuis `Pellicule/<année du scan>/AAAA-MM Numérisation` vers l'année estimée.

## 7. Écrans

1. **File de datation** : compteurs (à dater, à trancher, validées), bouton « Analyser maintenant », état du dernier lot.
2. **Photo** : la photo, ses visages encadrés ; par visage : nom, âge estimé, année déduite ; année proposée ± marge ; mini-frise de chaque personne (visages de référence ordonnés par âge) avec la photo placée dessus ; actions Valider / Corriger (sélecteur d'année + marge) / Passer.
3. **À trancher** : même écran, raison du doute en tête.
4. **À compléter** : personnes sans date de naissance (envoyées à carnet) et visages non nommés (lien vers Immich).
5. **Réglages** : seuils de doute, heure du lot, encart **« Home Assistant — à venir »**.

Design : skills frontend-design puis Impeccable / Theme Factory (à télécharger au moment du développement), mobile d'abord, pas de ressources externes.

## 8. Lien avec carnet

- Millésime expose `GET /api/a-completer` (jeton `CARNET_TOKEN`) : personnes Immich présentes sur des scans mais sans `birthDate` (id Immich, nom, nombre de scans bloqués, vignette).
- **Changement côté carnet** : lecture nocturne de cette liste et ajout dans une révision dédiée « Sans anniversaire », distincte de la révision globale. La date saisie dans carnet redescend vers Immich par le flux carnet → Immich déjà prévu.

## 9. Pense-bête Home Assistant (à venir, hors V1)

Préparer sans implémenter : une adresse `GET /api/ha/etat` réservée (renvoie 501 en V1). Pistes :
- Capteur « photos à dater » / « à trancher » et notification iPhone quand le lot nocturne est fini.
- Journal de naissance : fournir une photo de la personne à un âge donné.
- Widget Homepage / Anneau unique : compteur + lien.
- Diaporama invités (HAOS-immich-guest-slideshow) : séquence « à cet âge-là ».
- Toute modification HA passera par le master doc du projet Home Assistant sur GitHub, synchronisé.

## 10. Déploiement

Extrait à ajouter à `homelab.yml` :

```yaml
  millesime:
    image: ghcr.io/baloodusudouest/millesime:latest
    container_name: millesime
    restart: unless-stopped
    ports:
      - "8097:8000"
    environment:
      - IMMICH_URL=http://immich-server:2283
      - IMMICH_API_KEY=${MILLESIME_IMMICH_API_KEY}
      - MILLESIME_PASSWORD=${CARNET_PASSWORD}
      - CARNET_TOKEN=${MILLESIME_CARNET_TOKEN}
      - TZ=Europe/Paris
    volumes:
      - /volume1/docker/millesime:/data
    labels:
      - com.centurylinklabs.watchtower.enable=true
```

GitHub Actions : build `linux/amd64`, test de l'inférence dans un conteneur QEMU émulant un CPU sans AVX avant publication.

## 11. Risques ouverts

- Précision des modèles d'âge sur photos anciennes (grain, noir et blanc, flou) : ±5 à 8 ans chez l'adulte sans correction.
- Peu de références pour certaines personnes (anciennes générations) → correction faible.
- Déplacement de fichiers par le modèle de stockage Immich (§6).
- Compatibilité exacte d'onnxruntime sans AVX à confirmer en CI.
- Dépendance au flux carnet → Immich pour les naissances.

## 12. Retour du conseil (03/11/2026) et suite

**Accord unanime**
- La précision du modèle d'âge sur scans anciens n'est pas prouvée : mesurer avant de coder.
- La correction apprise sur des photos numériques récentes risque de ne pas valoir pour des scans N&B granuleux de personnes jeunes.
- Le produit de gaussiennes surestime la confiance (erreurs corrélées entre visages d'une même photo).
- Une date validée qui devient référence peut polluer le biais et les voisins.
- Le déplacement de fichiers par le modèle de stockage Immich est bloquant.
- « 1er juillet 12:00 » paraît certaine et remplit les Souvenirs Immich.
- V1 trop chargée : carnet, route HA, CI QEMU, biais par tranche d'âge à sortir.

**Désaccords** : modèle au cœur vs écran de comparaison sans modèle ; photo par photo vs par lot ; périmètre élargi (naissances déduites, albums par événement, image publique — rejeté : erreurs empilées, licence InsightFace non commerciale).

**Angles morts** : indices du tirage (date du tampon déjà reportée dans le tag à la numérisation) ; fiabilité de l'attribution des visages par Immich sur vieux scans ; scan = page d'album à plusieurs tirages ; date écrasée par une ré-extraction des métadonnées.

**Recommandation du président** : V1 = écran de comparaison (visage + frise + bornes dures + fourchette par lot + indices du tirage) ; modèle ONNX seulement en indice affiché si l'erreur médiane est < ±3 ans après correction globale ; une date validée n'est jamais une référence pour le biais ; rien n'est écrit tant que le déplacement de fichiers n'est pas tranché.

**Suite décidée** : test de mesure d'abord (dossier `millesime-test`) — conteneur ponctuel Portainer sur le DS1520+, jeu de test = scans `Numérisation/AAAA-MM` (date du tampon), comparaison avec les photos numériques des mêmes personnes, test d'écriture sur une seule photo `Non datée` restaurée, clé API admin dédiée. Le rapport du test décidera du rôle du modèle et de la v2 de ce document.

## 13. Résultat du test de mesure n°1 (10/11/2026, NAS)

- **Matériel** : Celeron J4125 sans AVX ; onnxruntime 1.20.1 fonctionne, à 0,15 s par visage.
- **Immich 3.4.0** : le modèle de stockage est actif (`Pellicule/{{y}}/{{album}}/…`), donc **changer la date déplace le fichier**. C'est accepté : le scan rejoint `Pellicule/<année>/<album>/`.
- **Données** : 300 scans datés par leur tampon, dont 137 seulement ont un visage exploitable. 267 visages ne sont pas nommés. 196 visages appartiennent à 54 personnes sans date de naissance, presque toutes sans nom. 3 visages tombent avant la naissance de la personne à qui ils sont attribués.
- **InsightFace (genderage.onnx)** : erreur médiane de **14,0 ans** sur l'année de la photo. Il vieillit les enfants de 19 ans et rajeunit les plus de 51 ans. La correction apprise sur le numérique aggrave l'erreur (19,8 ans) ; calibré sur les scans eux-mêmes, il descend à 7,4 ans, ce qui reste optimiste. Ce modèle est donc écarté. Un banc d'essai publié en 2026 le classe d'ailleurs parmi les moins bons, avec 11,7 ans d'erreur moyenne même sur des photos modernes.

## 14. Décisions après le test n°1

- **2ᵉ test de mesure sur le PC de Julien** : MiVOLO v2 (visage seul, puis visage + buste estimé) et un modèle de vision local, Qwen3-VL via Ollama, qui date la photo entière. Le calcul tourne sur le PC, avec Docker Desktop. L'appli devra elle aussi proposer de **déporter les calculs sur le PC**.
- **Album après validation** : « AAAA Numérisation », en retirant la photo de « Non datées Numérisation », avec un tag qui signale une estimation calculée.
- **Étape « Nommer » dans Millésime** : les groupes de visages des scans sont classés par fréquence, puis nommés ou fusionnés dans Immich depuis l'appli. Les dates de naissance restent gérées par carnet.
- **Ordre** : test n°2, puis conception v2, puis conseil, puis code.

## 15. Résultat du test de mesure n°2 (11/11/2026, PC de Julien)

Le test a tourné sur 300 scans datés par leur tampon ; 137 d'entre eux ont au moins un visage exploitable. Matériel : i5-12600KF, AMD RX 6700. MiVOLO tourne sur le processeur (1,55 s par visage), Qwen3-VL 8B instruct tourne sur la carte graphique (17,7 s par photo).

**Erreur sur l'âge d'un visage (scans)** :

| Méthode | Erreur médiane | Enfants (0-12 ans) |
|---|---|---|
| InsightFace | 14,6 ans | 19,4 ans |
| MiVOLO v2, visage seul | 3,7 ans | 2,2 ans |
| MiVOLO v2, visage + buste | 3,6 ans | 2,2 ans |

**Erreur sur l'année de la photo**, mesurée en validation croisée par lots, c'est-à-dire avec une correction toujours calculée sur d'autres mois de tampon :

| Méthode | Erreur médiane | ≤ 3 ans |
|---|---|---|
| MiVOLO visage + buste, sans correction | 3,4 ans | 45 % |
| MiVOLO calibré sur les scans datés (biais et poids par tranche d'âge) | 2,2 ans | 64 % |
| … sur les photos avec un enfant | 2,1 ans | 90 % |
| Qwen3-VL (photo entière), sans correction | 8,2 ans (biais −8) | 15 % |

**Point de méthode** : 77 % des scans datés sont de 1995-2000. Sur l'ensemble des scans, répondre toujours « 1997 » donne une erreur médiane de 1,5 à 1,8 an, ce qui bat tous les modèles : sur cet échantillon, le chiffre global ne permet pas de les départager. **Hors 1995-2000** (27 photos), MiVOLO calibré se trompe de **2,2 ans** en médiane, contre **4,2 ans** pour « 1997 » : il distingue donc vraiment les époques. Qwen3-VL ne les distingue presque pas : corrélation 0,2 avec l'année vraie, et 7,1 ans d'erreur hors 1995-2000. Sa correction linéaire revient à répondre « 1997 ».

**Anomalies repérées** : sur les photos numériques, les visages de Paul GARNIER sont estimés 23 ans trop jeunes, et ceux de Jeanne DUVAL 13,6 ans trop jeunes. Le groupe de visages Immich mélange sans doute plusieurs personnes, ou la date de naissance est fausse. Il faut le vérifier dans Immich ; c'est un argument de plus pour l'étape « Nommer ».

**Conclusions** :
- MiVOLO v2 (visage + buste), calibré sur les scans datés, est un **indice utile** d'environ ±2 ans, fiable en présence d'enfants.
- La vision locale n'apporte rien pour dater et peut être abandonnée.
- Le frein principal reste la couverture : moins d'un scan sur deux a un visage nommé avec une date de naissance.
