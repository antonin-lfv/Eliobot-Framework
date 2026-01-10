<h1 align="center"><br>Eliobot (robot ESP32-S3)<br></h1>

<p align="center">
<img src="https://github.com/user-attachments/assets/fbfe0094-2d90-4b59-bac1-fa97b4c256aa" alt="Logo" height="340" >
</p>

Ce depot contient le code qui tourne sur Eliobot. Le robot execute automatiquement `main.py` au demarrage. Plusieurs programmes de demo sont disponibles via les fichiers `main_*.py`.

## Prerequis

- macOS/Linux
- le robot monte en volume USB sous `/Volumes/ELIOBOT`
- optionnel: `uv` + `mpremote` pour le REPL

## Structure du depot

- `main.py`: programme executé au demarrage (copie d'un `main_*.py`)
- `main_*.py`: exemples prets a l'emploi (web, MQTT, obstacles, animation)
- `lib/`: bibliotheques CircuitPython + `lib/elio.py`
- `www/`: interface web servie par `main_www.py`
- `ELIOBOT_INIT_FILES/`: image de reset usine
- scripts: `deploy.sh`, `reset_usine.sh`
- config: `settings.toml`, `config.json`

## Choisir le programme a lancer

Le fichier execute par CircuitPython est `main.py`. Pour utiliser un autre exemple, copiez-le avant le deploiement.

## Deploiement du code sur le robot

1) Une seule fois:

```bash
chmod +x deploy.sh
```

2) Copier le code:

```bash
./deploy.sh
```

Ce script copie `main.py`, `config.json`, `eliobot_sounds.py`, `utils.py`, `settings.toml`, ainsi que les dossiers `lib/`, `sd/` et `www/`.

## Reset usine

Le reset usine remet le contenu du robot comme dans `ELIOBOT_INIT_FILES/` (et conserve `settings.toml`).

```bash
chmod +x reset_usine.sh
./reset_usine.sh
```

## Configuration

### `settings.toml` (reseau / MQTT)

Les exemples `main_www.py` et `main_mqtt.py` lisent des variables via `os.getenv`. Placez ce fichier a la racine du robot:

```toml
SSID = "NomDuReseau"
PASSWORD = "MotDePasse"
BROKER_IP = "mon-pc.local" # seulement pour MQTT
PORT = 1883                # seulement pour MQTT
```

Pensez a mettre vos bons identifiants avant le deploiement.

### `config.json` (capteur de ligne)

```json
{"line_threshold": 75000}
```

Ce seuil est lu par `LineSensor` (voir plus bas). La calibration ecrit automatiquement ce fichier.

## Utiliser les composants (lib/elio.py)

### Moteurs

```py
AIN1 = pwmio.PWMOut(board.IO36)
AIN2 = pwmio.PWMOut(board.IO38)
BIN1 = pwmio.PWMOut(board.IO35)
BIN2 = pwmio.PWMOut(board.IO37)
vBatt_pin = analogio.AnalogIn(board.BATTERY)
motors = Motors(AIN1, AIN2, BIN1, BIN2, vBatt_pin)

motors.move_forward(60)
motors.turn_in_place(direction="left")
motors.move_one_step("forward", distance=20)  # cm
motors.turn_one_step("right", angle=90)       # degres
motors.motor_stop()
```

### Buzzer

```py
buzzer = Buzzer(pwmio.PWMOut(board.IO17, variable_frequency=True))
buzzer.sound_startup()
buzzer.play_tone(880, 0.2, 80)
```

### Matrice de LEDs (yeux)

```py
matrix = EyesMatrix(board.IO2)
matrix.set_matrix_logo(matrix.emotionHappy, (87, 49, 150))
matrix.scroll_matrix_text_both_eyes("ELIO", (0, 255, 0), speed=0.08)
```

### Capteurs d'obstacles

```py
obstacleInput = [analogio.AnalogIn(pin) for pin in (board.IO4, board.IO5, board.IO6, board.IO7)]
obstacleSensor = ObstacleSensor(obstacleInput)

if obstacleSensor.get_obstacle(1):  # 0 avant gauche, 1 avant, 2 avant droit, 3 arriere
    motors.motor_stop()
```

### Capteurs de ligne

```py
lineCmd = digitalio.DigitalInOut(board.IO33)
lineCmd.direction = digitalio.Direction.OUTPUT
lineInput = [analogio.AnalogIn(pin) for pin in (board.IO10, board.IO11, board.IO12, board.IO13, board.IO14)]
lineSensor = LineSensor(lineInput, lineCmd, motors)

lineSensor.calibrate_line_sensors()      # ecrit config.json
lineSensor.follow_line(threshold=75000)
```

### Telecommande IR

```py
ir = IRRemote(adafruit_irremote.IRReceiver(board.IOxx))
code = ir.decode_signal()
if code == IRRemote.signals["signal_ok"]:
    buzzer.sound_happy()
```

## Debug / logs USB

Pour voir les `print` et erreurs en USB:

```bash
uv run mpremote connect port:/dev/cu.usbmodemXXXX repl
```

Remplacez le port par le votre (`ls /dev/cu.usbmodem*`).
