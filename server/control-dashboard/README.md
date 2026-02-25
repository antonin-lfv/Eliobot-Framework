# control-dashboard

Dashboard FastAPI + broker MQTT pour monitorer et contrôler le robot en temps réel depuis un Raspberry Pi.

<div align="center">
  <a>
    <img src="server/control-dashboard/image_dashboard.png" alt="preview">
  </a>
</div>

## Architecture

```
control-dashboard/
├── docker-compose.yml          # Orchestration des services
├── setup.sh                    # Script d'installation (Raspberry Pi)
├── mosquitto/
│   └── mosquitto.conf          # Configuration du broker MQTT
└── fastapi-dashboard/          # Dashboard FastAPI + WebSocket
    ├── app.py                  # Backend FastAPI (MQTT + WebSocket + REST)
    ├── static/
    │   └── index.html          # Frontend SPA (HTML + JS + Plotly CDN)
    ├── pyproject.toml          # Dépendances Python
    └── Dockerfile              # Image Docker (python:3.12-slim + uv)
```

**Services Docker :**
- `mosquitto` — Broker MQTT Eclipse Mosquitto 2.x (port `1883`)
- `dashboard` — Dashboard FastAPI (port `8000`)

Les deux services communiquent via un réseau Docker interne (`elio-net`). Le dashboard atteint le broker via le nom de service `mosquitto`, sans passer par l'hôte.

**Pourquoi FastAPI plutôt que Streamlit ?**

Avec Streamlit, la page entière se rechargait toutes les secondes (`st.rerun()`), rendant l'interface saccadée et le D-pad inutilisable en maintien. FastAPI + WebSocket envoie uniquement les données changées (push toutes les 300ms) ; le DOM est mis à jour directement en JS sans rechargement. Le D-pad utilise `pointerdown`/`pointerup` avec dead-man's switch côté client.

---

## Prérequis

- Raspberry Pi / DietPi (ou tout Linux) avec accès réseau
- Docker Engine + plugin Compose v2

---

## Installation sur DietPi

Sur DietPi, Docker et Docker Compose s'installent via `dietpi-software` (plus fiable que le script générique) :

```bash
# Docker Engine
dietpi-software install 162

# Docker Compose (plugin v2)
dietpi-software install 134
```

Installer aussi le plugin buildx (requis par Docker Compose v2) :
```bash
apt-get install -y docker-buildx-plugin
```

Puis copier les fichiers depuis le Mac :
```bash
# Sur le Mac — la barre oblique finale sur la source est importante (copie le contenu, pas le dossier)
rsync -av /chemin/vers/Projets-eliobot/server/control-dashboard/ root@DietPi:~/eliobot-server/control-dashboard/
```

---

## Démarrage rapide

```bash
cd ~/eliobot-server/control-dashboard
chmod +x setup.sh
./setup.sh
```

Le script build l'image et démarre les services. À la fin il affiche l'IP à configurer sur le robot.

**Configuration robot** (`robot/settings.toml`) :

```toml
PROGRAM   = "mqtt_dashboard"
BROKER_IP = "<IP_DU_PI>"
PORT      = 1883
```

**Déploiement du programme** :

```bash
./deploy.sh -p mqtt_dashboard
```

---

## Commandes utiles

```bash
# Démarrer les services
docker compose up -d

# Voir les logs en temps réel
docker compose logs -f

# Voir uniquement les logs du broker
docker compose logs -f mosquitto

# Rebuild après modification de app.py ou index.html
docker compose up -d --build dashboard

# Arrêter
docker compose down

# Arrêter et supprimer les volumes (reset données MQTT)
docker compose down -v
```

---

## Topics MQTT

### Robot → Serveur (télémétrie)

| Topic | Payload | Fréquence |
|---|---|---|
| `elio/telemetry/battery` | `float` — tension en volts (ex: `3.85`) | 5s |
| `elio/telemetry/obstacles` | JSON `{"front": bool, "left": bool, "right": bool, "back": bool}` | 400ms |
| `elio/telemetry/mode` | `idle` \| `manual` \| `exploration` | Au changement |
| `elio/telemetry/step` | JSON — étape d'exploration (voir ci-dessous) | Chaque pas |

**Format d'un step d'exploration :**
```json
{
  "x": 3, "y": 2,
  "heading": 1,
  "action": "moved_forward",
  "front": false, "left": true, "right": false
}
```
`heading` : `0=Nord`, `1=Est`, `2=Sud`, `3=Ouest`

### Serveur → Robot (commandes)

| Topic | Payload | Description |
|---|---|---|
| `elio/command/mode` | `idle` \| `manual` \| `exploration` | Changer le mode |
| `elio/command/move` | `forward` \| `backward` \| `left` \| `right` \| `stop` | Déplacement (mode manuel) |
| `elio/command/speed` | `int` 0–100 | Vitesse moteurs |
| `elio/command/reset_map` | `1` | Réinitialiser la carte exploration |

---

## Dashboard

Accessible sur `http://<IP_DU_PI>:8000`

| Section | Description |
|---|---|
| Header | Statut connexion, dernier signal reçu, niveau batterie |
| Sidebar | Sélecteur de mode, slider vitesse, D-Pad de contrôle |
| Tableau de bord | Vue capteurs obstacles (SVG), niveau batterie, état du robot, position |
| Exploration | Carte Plotly du chemin parcouru, obstacles détectés, journal des déplacements |

**Statut de connexion** — 3 états :
- 🟢 **Robot actif** — signal MQTT reçu dans les 10 dernières secondes
- 🟡 **Robot absent** — broker connecté mais aucun signal depuis >10s (robot éteint)
- 🔴 **Broker déconnecté** — connexion MQTT perdue

**Mode Manuel** : les boutons D-Pad maintiennent le mouvement tant qu'ils sont pressés (`pointerdown`). Le robot s'arrête automatiquement si aucune commande n'arrive dans les 800ms côté robot (dead-man's switch), et côté client la commande est renvoyée toutes les 500ms.

**Mode Exploration** : le robot navigue en autonomie (règle de la main droite). Le dashboard affiche sa trajectoire et les obstacles détectés en temps réel.

---

## Développement

`app.py` et `static/` sont montés en volume dans le container. Pour recharger après une modif Python, redémarre le container :
```bash
docker compose restart dashboard
```

Pour modifier les dépendances :
```bash
# Éditer fastapi-dashboard/pyproject.toml, puis rebuild
docker compose up -d --build dashboard
```

---

## Notes & problèmes connus

**Plugin buildx manquant**

```
Docker Compose requires buildx plugin to be installed
```
Installer avec : `apt-get install -y docker-buildx-plugin`

**Dossier dupliqué après rsync**

Si `pwd` affiche `.../control-dashboard/control-dashboard`, le rsync a copié le dossier au lieu de son contenu (barre oblique finale manquante sur la source). Fix :
```bash
cd ~/eliobot-server/control-dashboard
mv control-dashboard/* .
rmdir control-dashboard
```

**Dashboard inaccessible (ARM/DietPi)**

FastAPI + uvicorn fonctionne nativement sur ARM (pas de composant JS compilé). Si le port 8000 est bloqué, vérifier `ufw` ou `iptables`.

**Deux `BROKER_IP` dans `settings.toml`**

CircuitPython prend la première valeur trouvée. Ne pas laisser deux clés identiques — commenter l'entrée inutilisée.
