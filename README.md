<h1 align="center">
  <br>
  Eliobot Framework v1.2
  <br>
</h1>

<h4 align="center">Framework simple et direct pour programmer <a href="https://eliobot.com">Eliobot</a> (ESP32-S3 + CircuitPython).</h4>

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

# Objectifs

- Un **seul point d'entree** (`main.py`)
- Ajout de programmes **sans modifier le framework**
- Deploiement rapide et sûr via `rsync`
- Comportement stable meme en cas d'erreur (safe mode)

<br>

# Architecture

```
Projets-eliobot/
├── deploy.sh              # Script de deploiement (override programme, dry-run...)
├── robot/                 # Tout ce qui est copie sur le robot
│   ├── main.py            # Point d'entree (auto-discovery + safe mode)
│   ├── settings.toml      # Configuration (WiFi, programme actif, MQTT...)
│   ├── config.json        # Calibration capteurs
│   ├── programs/          # Programmes applicatifs
│   │   ├── hardware.py    # Fonctions setup (motors, buzzer, matrix...)
│   │   ├── registry.py    # Auto-discovery des programmes
│   │   ├── safe_mode.py   # Programme de secours
│   │   ├── web_server.py  # Serveur web HTTP
│   │   ├── mqtt_client.py # Client MQTT
│   │   ├── obstacles.py   # Evitement d'obstacles
│   │   └── animations_fire.py # Animations LED
│   ├── lib/               # Bibliotheques (elio.py + Adafruit)
│   ├── www/               # Interface web
│   └── sd/                # Fichiers SD
└── server/
    └── control-dashboard/ # Dashboard FastAPI + broker MQTT (Raspberry Pi)
```

> Voir [server/control-dashboard/README.md](server/control-dashboard/README.md) pour l'installation et l'utilisation du dashboard.

<br>

# Quick Start

## 1. Choisir un programme

Dans `robot/settings.toml` :

```toml
PROGRAM = "web_server"
```

Les programmes disponibles sont **auto-detectes** dans `robot/programs/`.

## 2. Deployer sur le robot

```bash
./deploy.sh
```

Synchronisation automatique via `rsync`.

## 3. Changer de programme (sans editer de fichier)

```bash
./deploy.sh --program obstacles
./deploy.sh -p animations_fire
```

Afficher ce qui serait copié sans faire de modifications :

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

Utilise pour la calibration du capteur de ligne.

<br>

# Creer un programme

## Exemple minimal

Creer un fichier dans `robot/programs/` :

```python
# programs/mon_programme.py
from .hardware import setup_buzzer, setup_matrix, sleep_ms

PROGRAM_NAME = "mon_programme"  # Optionnel, sinon = nom du fichier

def run():
    # Setup
    buzzer = setup_buzzer()
    matrix = setup_matrix()

    buzzer.sound_startup()

    # Boucle principale
    while True:
        # Ta logique ici
        sleep_ms(100)
```

> Aucune modification de `main.py` ni de `__init__.py` requise.

## Deploiement sur le robot

```bash
./deploy.sh --program mon_programme
```

<br>

# API

## Fonctions hardware (`programs/hardware.py`)

```python
from .hardware import (
    setup_motors,           # Retourne l'objet Motors
    setup_buzzer,           # Retourne l'objet Buzzer
    setup_matrix,           # Retourne l'objet EyesMatrix
    setup_obstacle_sensors, # Retourne l'objet ObstacleSensor
    sleep_ms,               # Pause en millisecondes
    now_ms,                 # Temps actuel en millisecondes
    every_ms,               # Timer periodique non-bloquant
)
```

### Exemple avec timer periodique

```python
from .hardware import setup_matrix, sleep_ms, every_ms

def run():
    matrix = setup_matrix()
    toggle = False

    while True:
        # Execute toutes les 500ms
        if every_ms("blink", 500):
            if toggle:
                matrix.clear_matrix()
            else:
                matrix.set_matrix_logo(matrix.emotionHappy, (87, 49, 150))
            toggle = not toggle

        sleep_ms(10)
```

Ici, l'affichage de la matrice clignote toutes les 500ms sans bloquer la boucle principale.

## Buzzer

```python
buzzer = setup_buzzer()

# Sons basiques
buzzer.play_tone(440, 0.2)        # Frequence, duree
buzzer.play_tone(440, 0.2, 80)    # Frequence, duree, volume

# Effets sonores
buzzer.sound_startup()
buzzer.sound_bump()
buzzer.sound_happy()
buzzer.sound_laser()
buzzer.sound_alert()

# Melodies
buzzer.melody_hmm()
buzzer.melody_alert()
buzzer.melody_marseillaise()

# Emotions
buzzer.emotion_joie()
buzzer.emotion_colere()
buzzer.emotion_surprise()
```

## Motors

```python
motors = setup_motors()

# Deplacement
motors.move_forward(speed=100)
motors.move_backward(speed=100)
motors.turn_left(speed=100)
motors.turn_right(speed=100)
motors.motor_stop()

# Deplacement precis
motors.move_one_step("forward", distance=20)  # en cm
motors.turn_one_step("left", angle=90)        # en degres
```

## EyesMatrix

```python
matrix = setup_matrix()

# Affichage
matrix.clear_matrix()
matrix.set_matrix_logo(matrix.emotionHappy, (87, 49, 150))

# Emotions disponibles
matrix.emotionHappy
matrix.emotionSad
matrix.emotionAngry
matrix.emotionLove
matrix.emotionAmazed
matrix.emotionConfused
# ... et plus
```

## ObstacleSensor

```python
sensors = setup_obstacle_sensors()

# Detection (True si obstacle)
sensors.get_obstacle(0)  # Avant gauche
sensors.get_obstacle(1)  # Avant
sensors.get_obstacle(2)  # Avant droit
sensors.get_obstacle(3)  # Arriere
```

<br>

# Debug

Acces REPL USB :

```bash
uv run mpremote connect port:/dev/cu.usbmodem0115BDE5B8841 repl
```

Pour trouver le nom du port sous macOS :

```bash
ls /dev/cu.usbmodem*
```

et sous linux :

```bash
ls /dev/ttyACM*
```

<br>

# Ressources

- [Eliobot](https://eliobot.com)
- [CircuitPython](https://circuitpython.org)
- [Adafruit CircuitPython Bundle](https://github.com/adafruit/Adafruit_CircuitPython_Bundle)
