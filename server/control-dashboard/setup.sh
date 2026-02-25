#!/bin/bash
# Eliobot - Script de configuration serveur (Raspberry Pi)
set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

echo -e "${BOLD}========================================"
echo -e "  Eliobot Server Setup"
echo -e "========================================${RESET}"
echo ""

# ============================================================
# 1. Vérifier / installer Docker
# ============================================================
if ! command -v docker &>/dev/null; then
    echo -e "${YELLOW}[1/3] Docker non trouvé. Installation...${RESET}"
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo -e "${GREEN}Docker installé !${RESET}"
    echo ""
    echo -e "${YELLOW}IMPORTANT : Reconnectez-vous (logout/login) pour activer les droits Docker,"
    echo -e "puis relancez ce script : ./setup.sh${RESET}"
    exit 0
fi
echo -e "${GREEN}[1/3] Docker OK${RESET} ($(docker --version | cut -d' ' -f3 | tr -d ','))"

# ============================================================
# 2. Vérifier Docker Compose (plugin v2)
# ============================================================
if ! docker compose version &>/dev/null 2>&1; then
    echo -e "${YELLOW}[2/3] Plugin Docker Compose non trouvé. Installation...${RESET}"
    sudo apt-get update -qq
    sudo apt-get install -y docker-compose-plugin
fi
echo -e "${GREEN}[2/3] Docker Compose OK${RESET} ($(docker compose version --short))"

# ============================================================
# 3. Démarrer les services
# ============================================================
echo -e "${YELLOW}[3/3] Build et démarrage des services...${RESET}"
cd "$(dirname "$0")"
docker compose up -d --build

# Attendre que les services soient prêts
echo -n "En attente du broker MQTT"
for i in $(seq 1 15); do
    if docker compose exec -T mosquitto mosquitto_sub -t '$SYS/#' -C 1 -i setup-check -W 2 &>/dev/null; then
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

# ============================================================
# Résumé
# ============================================================
HOSTNAME_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${BOLD}${GREEN}========================================"
echo -e "  Services démarrés !"
echo -e "========================================${RESET}"
echo ""
echo -e "  ${BOLD}Dashboard Streamlit${RESET}  →  http://${HOSTNAME_IP}:8501"
echo -e "  ${BOLD}MQTT Broker${RESET}          →  ${HOSTNAME_IP}:1883"
echo ""
echo -e "${BOLD}Configuration robot (robot/settings.toml) :${RESET}"
echo -e "  BROKER_IP = \"${HOSTNAME_IP}\""
echo -e "  PORT = 1883"
echo ""
echo -e "${YELLOW}Logs :${RESET} docker compose logs -f"
echo -e "${YELLOW}Stop  :${RESET} docker compose down"
echo ""
