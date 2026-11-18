#!/bin/sh
# Démarre en root, adopte le propriétaire du dossier /state (ton compte du NAS), lui rend les fichiers
# créés par les versions qui tournaient en root (avant 2.12.5), puis lance l'appli avec ses droits.
set -eu

ETAT="${MILLESIME_ETAT:-/state}"
mkdir -p "$ETAT"

PUID="$(stat -c %u "$ETAT")"
PGID="$(stat -c %g "$ETAT")"
if [ "$PUID" = "0" ] && [ "${MAISON_ROOT_ACCEPTE:-}" != "oui" ]; then
  # /state appartient à root (dossier créé par Docker) : l'appli tournerait en root. Refus, avec le remède.
  echo "ERREUR : $ETAT appartient à root ; l'appli ne tourne pas en root." >&2
  echo "Remède : donner le dossier à ton compte du NAS (File Station › Propriétés › Propriétaire, ou chown -R <UID>:<GID>)," >&2
  echo "puis redémarrer le conteneur. Dépannage seulement : MAISON_ROOT_ACCEPTE=oui dans la stack." >&2
  exit 1
fi
echo "millesime : exécution avec UID=$PUID GID=$PGID (propriétaire de $ETAT)"
chown -R "$PUID:$PGID" "$ETAT"

export HOME="$ETAT"
cd /srv
exec gosu "$PUID:$PGID" uvicorn app.main:app --host 0.0.0.0 --port 8098 --no-access-log
