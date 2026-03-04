#!/usr/bin/env bash
set -euo pipefail

# -------- Defaults --------
ROBOT="/Volumes/ELIOBOT"
DRY_RUN=0
PROGRAM_OVERRIDE=""

usage() {
  cat <<'EOF'
Usage:
  ./deploy.sh [options]

Options:
  -p, --program <name>   Override PROGRAM in robot/settings.toml before deploy
  -r, --robot <path>     Robot mount path (default: /Volumes/ELIOBOT)
  -n, --dry-run          Show what would be copied/deleted (rsync dry-run)
  -h, --help             Show help

Examples:
  ./deploy.sh
  ./deploy.sh --program obstacles
  ./deploy.sh -p web_server
  ./deploy.sh --dry-run
  ./deploy.sh --robot /Volumes/ELIOBOT
EOF
}

# -------- Args parsing --------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--program)
      PROGRAM_OVERRIDE="${2:-}"
      shift 2
      ;;
    -r|--robot)
      ROBOT="${2:-}"
      shift 2
      ;;
    -n|--dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "❌ Option inconnue: $1"
      usage
      exit 1
      ;;
  esac
done

# -------- Checks --------
if [ ! -d "$ROBOT" ]; then
  echo "❌ Robot non monté: '$ROBOT'"
  echo "➡️  Vérifie que le volume est bien monté, puis réessaye."
  exit 1
fi

if [ ! -f "robot/settings.toml" ]; then
  echo "⚠️  Fichier robot/settings.toml introuvable — création d'une version minimale..."
  cat > robot/settings.toml <<'EOF'
PROGRAM = "animations_fire"
SSID = ""
PASSWORD = ""
EOF
  echo "📝 robot/settings.toml créé avec PROGRAM=\"animations_fire\"."
  echo "➡️  Pense à renseigner SSID et PASSWORD avant de déployer si tu veux le WiFi."
fi

# -------- Update PROGRAM in settings.toml if requested --------
if [[ -n "$PROGRAM_OVERRIDE" ]]; then
  echo "🛠️  Override PROGRAM -> '$PROGRAM_OVERRIDE' (robot/settings.toml)"

  # Remplace la ligne PROGRAM = "..."
  # - compatible macOS (BSD sed) + Linux
  # On écrit dans un fichier temporaire puis on remplace
  tmpfile="$(mktemp)"
  if grep -qE '^[[:space:]]*PROGRAM[[:space:]]*=' robot/settings.toml; then
    sed -E "s|^[[:space:]]*PROGRAM[[:space:]]*=.*$|PROGRAM = \"${PROGRAM_OVERRIDE}\"|g" robot/settings.toml > "$tmpfile"
  else
    # Si pas de PROGRAM, on l'ajoute en haut
    {
      echo "PROGRAM = \"${PROGRAM_OVERRIDE}\""
      cat robot/settings.toml
    } > "$tmpfile"
  fi
  mv "$tmpfile" robot/settings.toml
fi

ACTIVE_PROGRAM="$(grep -E '^[[:space:]]*PROGRAM[[:space:]]*=' robot/settings.toml | head -n1 | cut -d'=' -f2- | tr -d ' "')"

echo "🚀 Déploiement vers Eliobot..."
echo "📌 Robot: $ROBOT"
echo "🎯 Programme: ${ACTIVE_PROGRAM:-"(non défini)"}"
echo "--------------------------------"

# -------- rsync --------
RSYNC_FLAGS=(-a --delete
  --exclude ".DS_Store"
  --exclude "__pycache__/"
  --exclude "*.pyc"
)

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "🧪 DRY RUN: aucun fichier ne sera réellement copié."
  RSYNC_FLAGS+=(--dry-run --itemize-changes)
fi

rsync "${RSYNC_FLAGS[@]}" robot/ "$ROBOT/"

echo "✅ Déploiement terminé"