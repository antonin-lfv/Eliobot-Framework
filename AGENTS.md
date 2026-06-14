# Eliobot Framework — Mémoire projet

## Vue d'ensemble

Framework pour programmer un robot **Eliobot** (ESP32-S3 + CircuitPython).
Architecture en deux parties : le code qui tourne sur le robot (`robot/`) et le serveur de contrôle sur Raspberry Pi (`server/`).

**Version courante : 1.3**

---

## Structure du projet

```
Projets-eliobot/
├── README.md              # Documentation principale (v1.3)
├── deploy.sh              # Script rsync de déploiement sur le robot
├── examples.md            # Exemples de code
├── pyproject.toml         # Config Python (uv)
├── uv.lock
├── robot/                 # Tout ce qui est copié sur le robot
│   ├── main.py            # Point d'entrée : auto-discovery + safe mode
│   ├── settings.toml      # Config (WiFi, PROGRAM, MQTT) — dans .gitignore
│   ├── config.json        # Calibration capteurs (line_threshold)
│   ├── utils.py           # Utilitaires (get_eyes_matrices...)
│   ├── programs/          # Programmes applicatifs (auto-découverts)
│   │   ├── hardware.py    # Fonctions setup hardware (moteurs, buzzer, matrix...)
│   │   ├── registry.py    # Auto-discovery des programmes
│   │   ├── safe_mode.py   # Mode secours si crash
│   │   ├── web_server.py  # Serveur HTTP embarqué
│   │   ├── mqtt_client.py # Client MQTT simple (télémétrie)
│   │   ├── mqtt_dashboard.py # Client MQTT avancé (dashboard complet)
│   │   ├── obstacles.py   # Évitement autonome (main droite)
│   │   ├── line_follower.py # Suivi de ligne IR
│   │   ├── ir_control.py  # Contrôle télécommande IR
│   │   ├── dance.py       # Chorégraphie (~25s)
│   │   └── animations_fire.py # Animations LED matricielles
│   ├── lib/               # Bibliothèques CircuitPython (elio.py + Adafruit)
│   ├── www/               # Interface web pour web_server
│   └── sd/                # Fichiers SD
└── server/
    └── control-dashboard/ # Dashboard FastAPI + broker MQTT
        ├── docker-compose.yml
        ├── setup.sh
        ├── image_dashboard.png   # Screenshot du dashboard (utilisé dans README principal)
        ├── mosquitto/
        │   └── mosquitto.conf
        └── fastapi-dashboard/
            ├── app.py            # Backend FastAPI (MQTT bridge + WebSocket + REST)
            ├── Dockerfile
            ├── pyproject.toml
            └── static/
                ├── index.html    # Frontend SPA (HTML/JS/Plotly CDN)
                └── eliobot.png   # Image robot (utilisée dans le dashboard web)
```

---

## Mécanisme central : auto-discovery des programmes

- `main.py` lit `settings.toml` → clé `PROGRAM`
- `registry.py` scan le dossier `programs/` et charge le module dynamiquement
- Si le programme plante → `safe_mode.py` prend le relais automatiquement
- **Ajouter un programme** = créer un fichier `.py` dans `robot/programs/` avec une fonction `run()`
- Pas besoin de toucher `main.py`, `__init__.py`, ou `registry.py`

---

## Déploiement

```bash
./deploy.sh                    # Déploie avec le PROGRAM actuel dans settings.toml
./deploy.sh -p mqtt_dashboard  # Override du programme
./deploy.sh --dry-run          # Simulation sans copie
```

Utilise `rsync` vers le robot (via USB ou WiFi/mDNS).

---

## Programmes disponibles

| Programme | Description |
|---|---|
| `web_server` | Serveur HTTP — contrôle navigateur |
| `mqtt_client` | Client MQTT simple — télémétrie |
| `mqtt_dashboard` | Client MQTT avancé — télémétrie + manuel + exploration |
| `obstacles` | Évitement autonome |
| `line_follower` | Suivi de ligne IR |
| `ir_control` | Contrôle télécommande IR |
| `dance` | Chorégraphie moteurs + LEDs + buzzer |
| `animations_fire` | Animations matricielles |
| `safe_mode` | Mode secours (automatique) |

---

## Dashboard MQTT-FastAPI

### Contexte
Remplace une version Streamlit (qui rechargeait toute la page toutes les secondes). FastAPI + WebSocket envoie uniquement les deltas (push 300ms). D-pad utilisable en maintien grâce à `pointerdown`/`pointerup` + dead-man's switch.

### Services Docker
- `mosquitto` — Broker MQTT Eclipse Mosquitto 2.x → port `1883`
- `dashboard` — FastAPI + uvicorn → port `8000`
- Réseau interne `elio-net` (dashboard → broker via hostname `mosquitto`)

### Installation sur DietPi
```bash
dietpi-software install 162   # Docker Engine
dietpi-software install 134   # Docker Compose plugin v2
apt-get install -y docker-buildx-plugin
rsync -av server/control-dashboard/ root@DietPi:~/eliobot-server/control-dashboard/
cd ~/eliobot-server/control-dashboard && chmod +x setup.sh && ./setup.sh
```

### Topics MQTT
**Robot → Serveur :**
- `elio/telemetry/battery` — float (tension volts), 5s
- `elio/telemetry/obstacles` — JSON `{front, left, right, back}`, 400ms
- `elio/telemetry/mode` — `idle|manual|exploration`, au changement
- `elio/telemetry/step` — JSON step exploration `{x, y, heading, action, front, left, right}`

**Serveur → Robot :**
- `elio/command/mode` — `idle|manual|exploration`
- `elio/command/move` — `forward|backward|left|right|stop`
- `elio/command/speed` — int 0–100
- `elio/command/reset_map` — `1`

### Statuts connexion
- 🟢 signal reçu dans les 10 dernières secondes
- 🟡 broker connecté mais robot absent (>10s sans signal)
- 🔴 broker déconnecté

---

## Hardware Eliobot

- **MCU** : ESP32-S3
- **Runtime** : CircuitPython 10.x
- **Bibliothèque principale** : `elio.py` dans `robot/lib/`
- **Classes** : `Motors`, `Buzzer`, `EyesMatrix`, `ObstacleSensor`, `LineSensor`, `IRRemote`, `WiFiConnectivity`

### Capteurs obstacles
- Index 0 = avant gauche
- Index 1 = avant (centre)
- Index 2 = avant droit
- Index 3 = arrière

### hardware.py — fonctions disponibles
```python
setup_motors()           # → Motors
setup_buzzer()           # → Buzzer
setup_matrix()           # → EyesMatrix
setup_obstacle_sensors() # → ObstacleSensor
setup_line_sensor()      # → LineSensor
setup_ir_remote()        # → IRRemote
sleep_ms(n)              # Pause millisecondes
now_ms()                 # Timestamp ms
every_ms("key", n)       # Timer non-bloquant
```

---

## Fichiers importants à connaître

| Fichier | Rôle |
|---|---|
| `robot/main.py` | Chargement programme + safe mode |
| `robot/programs/hardware.py` | Toutes les initialisations hardware |
| `robot/programs/registry.py` | Auto-discovery (ne pas modifier) |
| `robot/settings.toml` | Config robot (dans .gitignore) |
| `server/control-dashboard/fastapi-dashboard/app.py` | Backend dashboard |
| `server/control-dashboard/fastapi-dashboard/static/index.html` | Frontend dashboard |
| `deploy.sh` | Script de déploiement rsync |

---

## .gitignore — fichiers exclus

- `robot/settings.toml` (WiFi/MQTT credentials)
- `.venv`, `.env`
- `__pycache__`, `*.py[oc]`
- `.DS_Store`
- `AGENTS.md` (ce fichier)

---

## Préférences et conventions

- Langue du projet : **français** (commentaires, README, messages)
- Pas de type hints dans le code CircuitPython (contraintes mémoire)
- Programmes autonomes : chaque fichier dans `programs/` est indépendant
- Déploiement via `uv` + `mpremote` pour debug REPL USB
- Port USB macOS : `/dev/cu.usbmodem*` / Linux : `/dev/ttyACM*`
