<h1 align="center">
  <br>
  🤖 Eliobot Framework v1.1
  <br>
</h1>

<h4 align="center">Framework modulaire et extensible pour programmer <a href="https://eliobot.com">Eliobot</a> (ESP32-S3 + CircuitPython).</h4>

<p align="center">
  <img src="https://img.shields.io/badge/CircuitPython-10.x-blueviolet.svg" alt="CircuitPython Eliobot">
  <img src="https://img.shields.io/badge/Hardware-ESP32--S3-green.svg" alt="ESP32-S3">
  <img src="https://img.shields.io/badge/Deploy-rsync-orange.svg" alt="rsync">
</p>

<p align="center">
  <a href="#-architecture">Architecture</a> •
  <a href="#-utilisation-rapide">Utilisation</a> •
  <a href="#%EF%B8%8F-configuration">Configuration</a> •
  <a href="#-créer-un-programme">Créer un programme</a> •
  <a href="#-api">API</a>
</p>

<p align="center">
<img src="https://github.com/user-attachments/assets/fbfe0094-2d90-4b59-bac1-fa97b4c256aa" alt="Eliobot" height="340">
</p>

---

# 🔎 Objectifs

- Un **seul point d'entrée** (`main.py`)
- **Aucune duplication** de scripts
- Ajout de programmes **sans modifier le framework**
- Déploiement rapide et sûr
- Comportement stable même en cas d'erreur (safe mode)

<br>

# 📁 Architecture

```
Projets-eliobot/
├── deploy.sh              # Script de déploiement (override programme, dry-run…)
├── robot/                 # Tout ce qui est copié sur le robot
│   ├── main.py            # Point d'entrée (auto-discovery + safe mode)
│   ├── settings.toml      # Configuration (WiFi, programme actif, MQTT…)
│   ├── config.json        # Calibration capteurs
│   ├── programs/          # Programmes applicatifs
│   │   ├── base.py        # Classe Program (setup / loop)
│   │   ├── registry.py    # Auto-discovery des programmes
│   │   ├── safe_mode.py   # Programme de secours
│   │   ├── web_server.py  # Serveur web HTTP
│   │   ├── mqtt_client.py # Client MQTT
│   │   ├── obstacles.py   # Évitement d'obstacles
│   │   └── animations_fire.py # Animations LED
│   ├── lib/               # Bibliothèques (elio.py + Adafruit)
│   ├── www/               # Interface web
│   └── sd/                # Fichiers SD
```

<br>

# Quick Start

## 1. Choisir un programme

Dans `robot/settings.toml` :

```toml
PROGRAM = "web_server"
```

Les programmes disponibles sont **auto-détectés** dans `robot/programs/`.

## 2. Déployer sur le robot

```bash
./deploy.sh
```

Synchronisation automatique via `rsync`.

## 3. Changer de programme (sans éditer de fichier)

```bash
./deploy.sh --program obstacles
./deploy.sh -p animations
```

Afficher ce qui serait copié :

```bash
./deploy.sh --dry-run
```

<br>

# Configuration

### `robot/settings.toml`

```toml
PROGRAM = "web_server"

SSID = "VotreReseau"
PASSWORD = "VotreMotDePasse"

BROKER_IP = "raspberrypi.local"
PORT = 1883
```

### `robot/config.json`

```json
{
    "line_threshold": 75000
}
```

Utilisé pour la calibration du capteur de ligne.

<br>

# Créer un programme

### 1. Créer un fichier dans `robot/programs/`

```python
from .base import Program
from elio import Buzzer
import board
import pwmio

PROGRAM_NAME = "mon_programme"

class MonProgramme(Program):

    def setup(self):
        print("🎉 Mon programme démarre")
        self.buzzer = Buzzer(pwmio.PWMOut(board.IO17, variable_frequency=True))
        self.buzzer.sound_startup()

    def loop(self):
        self.sleep_ms(100)
```

> Aucune modification de `main.py` ni de `__init__.py` requise.

### 2. Activer le programme

```bash
./deploy.sh --program mon_programme
```

<br>

# API

## Classe `Program`

```python
class Program:
    def setup(self):
        pass

    def loop(self):
        pass

    def run(self):
        ...
```

**Helpers intégrés :**
- `sleep_ms(ms)`
- `now_ms()`
- `every_ms(name, period_ms)`

## Buzzer

```python
buzzer.play_tone(440, 0.2)
buzzer.play_tone(440, 0.2, 80)

buzzer.sound_startup()
buzzer.sound_bump()
buzzer.sound_happy()

buzzer.melody_hmm()
buzzer.melody_alert()
buzzer.melody_marseillaise()
```

<br>

# Debug

Accès REPL USB :

```bash
uv run mpremote connect port:/dev/cu.usbmodem* repl
```

<br>

# Ressources

- [Eliobot](https://eliobot.com)
- [CircuitPython](https://circuitpython.org)
- [Adafruit CircuitPython Bundle](https://github.com/adafruit/Adafruit_CircuitPython_Bundle)
