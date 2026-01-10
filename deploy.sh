#!/usr/bin/env bash
set -euo pipefail

ROBOT="/Volumes/ELIOBOT"

if [ ! -d "$ROBOT" ]; then
  echo "❌ ELIOBOT non monté, veuillez connecter le robot et réessayer."
  exit 1
fi

echo "🚀 Déploiement vers Eliobot..."

# Fichiers racine
rsync -a main.py config.json eliobot_sounds.py utils.py settings.toml "$ROBOT/"

# Dossier lib
rsync -a --delete \
  --exclude "__pycache__/" \
  lib/ "$ROBOT/lib/"

# Dossier sd
rsync -a sd/ "$ROBOT/sd/"

# Dossier www
rsync -a www/ "$ROBOT/www/"

echo "✅ Déploiement terminé"