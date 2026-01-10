#!/usr/bin/env bash
set -euo pipefail
    
ROBOT="/Volumes/ELIOBOT"
SRC="$(cd "$(dirname "$0")" && pwd)/ELIOBOT_INIT_FILES"

if [ ! -d "$ROBOT" ]; then
  echo "❌ CIRCUITPY non monté"
  exit 1
fi

if [ ! -d "$SRC" ]; then
  echo "❌ Dossier ELIOBOT_INIT_FILES introuvable"
  exit 1
fi

echo "⚠️  RESET USINE E L I O B O T"
echo "➡️  Tout le contenu de $ROBOT va être remplacé"
echo "➡️  Source : $SRC"
echo
read -p "Tape EXACTEMENT 'RESET' pour continuer : " CONFIRM

if [ "$CONFIRM" != "RESET" ]; then
  echo "❌ Annulé"
  exit 1
fi

echo "🧨 Suppression et copie en cours..."

rsync -a --delete \
  --exclude ".DS_Store" \
  --exclude "settings.toml" \  # Ne pas supprimer les paramètres
  "$SRC/" "$ROBOT/"

echo "✅ Reset usine terminé"
echo "🔁 Le robot va redémarrer automatiquement"