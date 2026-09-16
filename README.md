<h1 align="center">
  <br>
  Eliobot Framework
  <br>
</h1>

<h3 align="center">Framework pour programmer un robot <a href="https://eliobot.com">Eliobot</a> (ESP32-S3 + CircuitPython).</h3>

<br>

<p align="center">
  <img src="https://img.shields.io/badge/Version-1.3-6366f1?style=flat-square">
  <img src="https://img.shields.io/badge/CircuitPython-10.x-blueviolet?style=flat-square">
  <img src="https://img.shields.io/badge/Hardware-ESP32--S3-2e7d32?style=flat-square">
  <img src="https://img.shields.io/badge/Deploy-rsync-f57c00?style=flat-square">
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/fbfe0094-2d90-4b59-bac1-fa97b4c256aa" alt="Eliobot" height="300">
</p>

<br>

Il y a deux façons d'utiliser ce framework :

| | On Edge | Serveur |
|---|---|---|
| **Principe** | Un programme tourne directement sur le robot | Le robot est piloté à distance par un serveur |
| **Matériel requis** | Robot seul | Robot + Raspberry Pi ou ordinateur avec Docker |
| **Programmes** | `web_server`, `obstacles`, `line_follower`, `ir_control`, `dance`, `animations_fire` | `mqtt_dashboard` |
| **Cas d'usage** | Comportements autonomes embarqués | Pilotage à distance, agent IA avec MCP, exploration cartographique et expérience connectomique de mouche |

## Un agent IA pour discuter avec ElioBot et le piloter

Le dashboard intègre **Assistant ElioBot**, un agent conversationnel utilisant **Gemini ou un modèle local via Ollama**. Demander « Quel est ton état ? », « Tourne de 70 degrés à droite » ou « Lance l’exploration » permet de consulter le robot et d’agir depuis le chat.

L’agent utilise **MCP (Model Context Protocol)** pour découvrir et appeler six outils : lire l’état, se déplacer, tourner, régler la vitesse, gérer une autonomie et arrêter le robot. Le serveur vérifie chaque action puis la transmet à ElioBot par MQTT. Les résultats des outils sont visibles dans la conversation ; les rotations restent approximatives et les mouvements sont limités en durée et en vitesse.

**[Découvrir l’agent et son fonctionnement MCP dans le README du dashboard →](server/control-dashboard/README.md#agent-ia-et-outils-mcp)** · [Configurer Gemini, Ollama ou un client MCP](server/control-dashboard/ASSISTANT.md) · [Cours guidé sur le code](server/control-dashboard/COURS_CHATBOT_MCP.md)

![Assistant ElioBot intégré au dashboard](server/control-dashboard/image-assistant.png)

## Un connectome de mouche aux commandes d’ElioBot

Le framework intègre le réseau anatomique **MaleCNS v1.0 fourni par Pytorch_fly : 176 422 neurones et 25 862 574 connexions pondérées**. Les capteurs de proximité stimulent le modèle sur le serveur, puis ses sorties neuronales sont traduites en commandes pour les deux roues d’ElioBot.

Une page dédiée permet de **voir les neurones actifs, suivre la réponse motrice et tester des stimulations sans déplacer le robot**. Le câblage est issu de données anatomiques ; la dynamique du réseau et sa traduction en mouvements restent une simulation simplifiée. L’évitement des obstacles n’est pas garanti.

**[Découvrir la fonctionnalité mouche et son installation dans le README du dashboard →](server/control-dashboard/README.md#mouche-connectomique)**

![Laboratoire mouche : neurones actifs et réponse à une stimulation simulée à droite](server/control-dashboard/image-fly.png)

*Capture du laboratoire pendant un test simulé : aucune commande n’est envoyée aux moteurs.*

[Console de contrôle et installation du dashboard](server/control-dashboard/README.md) · [Détails du modèle et du protocole mouche](server/control-dashboard/FLY.md)


# Structure du projet

```
Projets-eliobot/
├── deploy.sh                        # Déploiement rsync vers le robot
├── robot/                           # Code embarqué sur le robot
│   ├── main.py                      # Point d'entrée - auto-discovery + safe mode
│   ├── settings.toml                # Config WiFi, programme actif, MQTT  (.gitignore)
│   ├── config.json                  # Calibration capteurs
│   └── programs/
│       ├── hardware.py              # Initialisations hardware
│       ├── registry.py              # Découverte sans importer les programmes
│       ├── safe_mode.py             # Mode secours automatique
│       ├── web_server.py            # ─╮
│       ├── obstacles.py             #  │  On Edge
│       ├── line_follower.py         #  │
│       ├── ir_control.py            #  │
│       ├── dance.py                 #  │
│       ├── animations_fire.py       # ─╯
│       └── mqtt_dashboard.py        # ── Serveur (ROS-like)
└── server/
    └── control-dashboard/           # Cerveau - Raspberry Pi / Docker
        ├── docker-compose.yml
        ├── README.md                # Installation, pilotages et dépannage
        ├── ASSISTANT.md             # Agent IA, Gemini, Ollama et MCP
        ├── COURS_CHATBOT_MCP.md     # Cours guidé à partir du code
        ├── FLY.md                   # Modèle neuronal et protocole mouche
        ├── prepare_fly.py           # Préparation des caches Pytorch_fly
        ├── fly-data/                # Caches locaux, exclus de Git
        ├── mosquitto/
        └── fastapi-dashboard/
            ├── app.py               # Cerveau exploration + WebSocket + REST
            ├── assistant.py         # Conversation et boucle de l’agent
            ├── robot_mcp.py         # Outils MCP de contrôle du robot
            ├── fly_brain.py         # Calcul neuronal sur le connectome complet
            └── static/
                ├── index.html       # Pages pilotage et laboratoire mouche
                ├── dashboard.css
                ├── dashboard.js
                └── eye-patterns.json # Motifs des matrices LED
```

**Mécanisme auto-discovery :** `main.py` lit `PROGRAM` dans `settings.toml` et `registry.py` liste les fichiers sans les importer, puis charge uniquement le programme sélectionné. En cas de crash, le framework arrête les sorties moteur initialisées, puis lance `safe_mode.py`. L’arrêt est également exécuté lors d’un retour normal ou d’une interruption REPL.

# Quick start

Cloner le projet :

```bash
git clone https://github.com/antonin-lfv/Projets-Eliobot.git
```

Et ouvrir un terminal dans le dossier du projet.

Puis pour déployer un programme sur le robot (exemple avec `animations_fire`) après l'avoir branché en USB :

```bash
chmod +x deploy.sh
./deploy.sh -p animations_fire
```

<br>

# 1. Utilisation On Edge

> Le programme tourne entièrement sur le robot. Aucun serveur requis.

## Programmes disponibles

| Programme | Description |
|---|---|
| `web_server` | Serveur HTTP embarqué - contrôle moteurs, buzzer et LEDs depuis un navigateur sur le réseau local |
| `obstacles` | Évitement d'obstacles autonome en boucle |
| `line_follower` | Suivi de ligne avec capteurs IR et retour visuel sur la matrice LED |
| `ir_control` | Contrôle par télécommande infrarouge avec retour émotionnel (yeux + buzzer) |
| `dance` | Chorégraphie synchronisée moteurs + buzzer + matrice LED (~25s) |
| `animations_fire` | Animations matricielles en boucle |
| `safe_mode` | Mode de secours - activé automatiquement si le programme actif crashe |

## Déployer un programme sur le robot

Vous pouvez soit créer directement le fichier `settings.toml` dans le dossier `robot/`, soit utiliser la commande `./deploy.sh` pour le créer lors du déploiement en restant dans le terminal.

Il faudra penser à ajouter les droits d'exécution au script `deploy.sh` avant de pouvoir l'utiliser :

```bash
chmod +x deploy.sh
```

Le fichier `settings.toml` doit contenir au minimum le nom du programme à exécuter, ainsi que les informations de connexion WiFi. Par exemple :

```toml
PROGRAM = "obstacles"
SSID = "VotreReseau"
PASSWORD = "VotreMotDePasse"
```

Pour déployer le programme défini dans `settings.toml` :

```bash
./deploy.sh    
```

Pour sélectionner un programme dans `settings.toml`, puis le déployer :

```bash
./deploy.sh -p line_follower
```

Pour faire une simulation sans copier les fichiers sur le robot (dry-run) :

```bash
./deploy.sh --dry-run          # Simulation sans copie
```

Pour de l'aide :

```bash
./deploy.sh --help
```

## Créer un nouveau programme

Créer un fichier dans `robot/programs/` avec une fonction `run()`. C'est tout.

```python
# robot/programs/mon_programme.py
from .hardware import setup_motors, setup_buzzer, setup_matrix, sleep_ms, every_ms

PROGRAM_NAME = "mon_programme"

def run():
    motors = setup_motors()
    buzzer = setup_buzzer()
    matrix = setup_matrix()

    buzzer.sound_startup()

    while True:
        if every_ms("check", 200):
            # Logique exécutée toutes les 200ms sans bloquer la boucle
            pass
        sleep_ms(20)
```

```bash
./deploy.sh -p mon_programme
```

> `every_ms("key", period_ms)` retourne `True` toutes les N ms sans jamais bloquer la boucle.
> Aucune modification de `main.py`, `registry.py` ou `__init__.py` requise.
> Le nom du fichier sert de nom de programme. Un alias facultatif `PROGRAM_NAME = "nom"` doit être une chaîne littérale déclarée au niveau du module ; il est lu sans exécuter le fichier.

## Calibration (`robot/config.json`)

```json
{
  "line_threshold": 30000,
  "turn_factor": 1.0,
  "move_factor": 1.0,
  "obstacle_thresholds": [10000, 10000, 10000, 10000]
}
```

| Clé | Rôle |
|---|---|
| `obstacle_thresholds` | Quatre seuils entiers 1–65535, dans l’ordre gauche, avant, droite, arrière ; détection si valeur brute < seuil |
| `line_threshold` | Ligne sombre si `ambient − lit < line_threshold` ; valeurs brutes de −65535 à 65535 |
| `turn_factor` | Multiplicateur de durée de rotation en exploration et dans le chat, de 0.1 à 5 |
| `move_factor` | Multiplicateur de durée d’avancement en exploration, de 0.1 à 5 |

Les seuils d’obstacles sont chargés par `setup_obstacle_sensors()` au démarrage et partagés par les modes manuel (télémétrie), exploration et mouche. Les valeurs par défaut restent à 10000, comme dans la [bibliothèque officielle](https://docs.eliobot.com/docs/python_lib/obstacle-sensor). Par exemple, `[15000, 10000, 15000, 10000]` relève uniquement les seuils gauche et droit. Un seuil plus élevé accepte davantage de valeurs comme obstacle ; il ne correspond pas à une distance en centimètres.

Dans la télémétrie, ouvrir **Valeurs des 4 capteurs** pour comparer valeur brute et seuil. Tester à l’arrêt avec et sans obstacle devant chaque capteur. Si les valeurs basculent directement entre deux niveaux extrêmes, changer le seuil logiciel ne déplacera pas nécessairement le point de déclenchement physique. Le rôle d’un potentiomètre et des LED témoins doit être vérifié sur la révision matérielle du robot ; ne pas le déduire du seul seuil Python. Le programme ne commande pas ces LED témoins.

Après modification de `config.json`, redéployer et redémarrer le robot. Les seuils restent distincts de `line_threshold`, réservé aux capteurs de ligne sous le robot.

Les facteurs s’appliquent à une estimation tenant compte de la tension batterie et du PWM demandé. Ils ne remplacent pas une mesure de déplacement.

Pour calibrer l’exploration à sa vitesse de 60 %, mesurer plusieurs pas de 15 cm et plusieurs rotations de 90° sur le sol utilisé. Ajuster `move_factor` par le rapport distance demandée / distance mesurée, et `turn_factor` par angle demandé / angle mesuré. Recommencer après ajustement. Les mesures blanc/noir doivent également confirmer le seuil des capteurs de ligne.

Les valeurs présentes dans `robot/config.json` peuvent différer de cet exemple : conserver sa calibration. La calibration des capteurs préserve les facteurs de mouvement existants.

## Debug REPL USB

Pour accéder à une console interactive (REPL) via USB et débugger le robot en temps réel :

```bash
uv run mpremote connect port:/dev/cu.usbmodem* repl   # macOS
uv run mpremote connect port:/dev/ttyACM0 repl         # Linux
```

Pour trouver le nom du robot, on peut taper : `ls /dev/cu.usbmodem*`

<br>

# 2. Utilisation depuis un serveur

> Le robot embarque `mqtt_dashboard`, exécute les commandes et conserve les arrêts locaux de sécurité.
> Le serveur (Raspberry Pi / Docker) est le **cerveau** : il cartographie, décide, commande.

<br>

```
┌──────────────────────────────────┐        ┌──────────────────────────────────┐
│         ROBOT (ESP32-S3)         │        │      SERVEUR (Raspberry Pi)      │
│                                  │  WiFi  │                                  │
│  mqtt_dashboard.py               │ ←────→ │  app.py  (FastAPI + MQTT)        │
│                                  │        │                                  │
│  1. Lit les capteurs             │  MQTT  │  1. Reçoit position + capteurs   │
│  2. Publie l'état                │ ─────→ │  2. Calcule la prochaine action  │
│  3. Attend une commande          │ ←───── │  3. Envoie la commande           │
│  4. Exécute le mouvement         │        │  4. Met à jour la carte          │
└──────────────────────────────────┘        └──────────────────────────────────┘
          Exécuteur pur                         Cerveau - ressources serveur,
          RAM limitée (~8MB)                  algorithmes complexes, dashboard
```

<br>

## Installation du serveur

Prérequis : Python 3.11+ et Docker avec Compose v2 sur le serveur. Le lanceur vérifie leur disponibilité.

```bash
# On copie sur le Raspberry Pi (à lancer depuis votre machine locale)
rsync -av server/control-dashboard/ root@DietPi:~/eliobot-server/control-dashboard/

# Démarrage du serveur depuis le Raspberry Pi
cd ~/eliobot-server/control-dashboard
chmod +x setup.sh && ./setup.sh
```

Dashboard accessible sur `http://<IP_DU_PI>:8000`.

**Services Docker :**

- `mosquitto` - broker MQTT Eclipse Mosquitto 2.x (port `1883`)
- `dashboard` - FastAPI + WebSocket, agent IA et serveur MCP (port `8000`)
- `ollama-manager` - gestion privée de l’instance Ollama optionnelle, sans port publié

## Lancer le serveur en local sur son ordinateur

Pour tester le dashboard sans Raspberry Pi, vous pouvez lancer les services directement depuis votre ordinateur avec Docker :

```bash
cd server/control-dashboard
docker compose up -d --build
```

Le dashboard est alors accessible sur `http://localhost:8000`, et le broker MQTT écoute sur le port `1883` de votre ordinateur.

Si le robot doit se connecter à ce serveur local, il ne faut pas mettre `localhost` dans `robot/settings.toml`, car `localhost` désignerait le robot lui-même. Il faut utiliser l'adresse IP de votre ordinateur sur le WiFi :

```bash
# macOS, WiFi
ipconfig getifaddr en0

# Linux
hostname -I
```

Puis configurer le robot avec cette IP :

```toml
PROGRAM   = "mqtt_dashboard"
BROKER_IP = "<IP_DE_VOTRE_ORDINATEUR>"
PORT      = 1883
SSID      = "VotreReseau"
PASSWORD  = "VotreMotDePasse"
```

Dans le dashboard, il est normal de voir `localhost` si vous l'ouvrez depuis le même ordinateur. Ce n'est que l'adresse web du dashboard dans votre navigateur. Pour le robot, seule la valeur `BROKER_IP` compte, et elle doit être l'IP WiFi de l'ordinateur.

Pour arrêter le serveur local :

```bash
cd server/control-dashboard
docker compose down
```

## Configuration du robot

Dans le fichier `settings.toml` du dossier `robot`, indiquez le programme `mqtt_dashboard` ainsi que les informations de connexion WiFi et l'adresse IP du broker MQTT (Raspberry Pi ou ordinateur local). Par exemple :

```toml
PROGRAM   = "mqtt_dashboard"
BROKER_IP = "<IP_DU_PI>"
PORT      = 1883
SSID      = "VotreReseau"
PASSWORD  = "VotreMotDePasse"
```

Puis déployez le programme `mqtt_dashboard` sur le robot :

```bash
./deploy.sh -p mqtt_dashboard
```

## Fonctionnalités du dashboard

<p align="center">
  <img src="server/control-dashboard/image-dashboard.png" alt="Dashboard ElioBot : télémétrie et commandes manuelles de même hauteur, exploration en dessous">
</p>

| Section | Description |
|---|---|
| **En-tête** | Statut de connexion, tension batterie et bouton Tout arrêter |
| **Agent IA avec MCP** | Chat Gemini ou Ollama ; outils de lecture des capteurs, mouvement, rotation, vitesse, autonomie et arrêt |
| **Pilotage manuel** | D-Pad avec confirmation de reprise (expiration 800 ms), vitesse 0–100 |
| **Télémétrie** | Vue du robot et zones de détection, valeurs brutes/seuils des quatre capteurs, grandes matrices LED, capteurs de ligne et boutons son |
| **Exploration** | Carte estimée du chemin, boutons Lancer/Pause/Reprendre, réinitialisation avec arrêt, journal des étapes |
| **Mouche** | Chargement du connectome, Lancer/Pause/Reprendre, activité neuronale et commandes calculées |

**Modes :**

| Mode | Description |
|---|---|
| **Manuel** | D-Pad avec dead-man's switch - arrêt si pas de commande dans les 800ms |
| **Exploration** | Le serveur envoie une commande identifiée à chaque étape, avec reprise sur perte de message |
| **Mouche** | Réseau anatomique MaleCNS complet, lecture neuronale des capteurs et commandes de roues |
| **Idle** | Robot en veille, moteurs coupés (défaut à la connexion) |

La télémétrie et le pilotage manuel occupent deux cartes de même hauteur, côte à côte sur ordinateur. La carte d’exploration est placée plus bas en pleine largeur. L’interface reprend le violet ElioBot **#574F96** et s’adapte aux petits écrans.

## Mouche connectomique et gestion du pilotage

Le dashboard propose maintenant trois pilotages : manuel, exploration et **connectome de mouche MaleCNS**. Son interface sobre fonctionne sans dépendance à un CDN : les cartes et courbes sont dessinées en SVG.

Il n’y a plus de sélecteur de mode. Lancer une autonomie coupe le manuel. Une direction manuelle pendant une autonomie demande confirmation, puis met cette autonomie en pause. Le bouton **Reprendre**, directement sur la carte pour l’exploration, permet de la relancer. **Tout arrêter** ou Échap revient en veille.

Le mode mouche relie les capteurs gauche/droit et avant au réseau anatomique complet fourni par Pytorch_fly. La lecture des neurones DNa02/DNg13 est convertie en commandes bornées à ±45 % et expirant après 500 ms. L’arrière est affiché mais ne stimule pas de population neuronale supplémentaire.

**Un obstacle à droite ne signifie pas forcément un virage à gauche, ni l’inverse.** La réponse dépend des connexions et de l’activité antérieure du réseau. Seule une protection frontale supprime l’avance lorsque le capteur avant détecte un obstacle ; elle conserve la rotation calculée. Ce modèle n’est pas un système d’évitement validé.

```bash
# Préparer les caches, puis reconstruire le serveur et déployer le robot.
python3 server/control-dashboard/prepare_fly.py /chemin/vers/Pytorch_fly
```

Voir le **[README du dashboard — Mouche connectomique](server/control-dashboard/README.md#mouche-connectomique)** pour la mise en route, et le [guide d’intégration de la mouche](server/control-dashboard/FLY.md) pour le modèle, les correspondances sensorielles et les vérifications.

Le laboratoire dédié `/fly` affiche les neurones sensoriels, les 12 neurones les plus actifs et les quatre sorties motrices. Ses boutons de stimulation permettent de voir la propagation dans le réseau complet sans déplacer le robot. Voir le guide pour distinguer ces tests de l’activité liée aux capteurs réels.

## Topics MQTT

**Robot → Serveur**

| Topic | Payload | Fréquence |
|---|---|---|
| `elio/telemetry/battery` | `float` volts | 5s |
| `elio/telemetry/obstacles` | `{front, left, right, back, raw, thresholds}` ; deux dictionnaires de diagnostics supplémentaires | cible 400 ms |
| `elio/telemetry/lines` | `[int × 5]` valeurs brutes `ambient − lit` | 1.5s |
| `elio/telemetry/eyes` | `{"pattern", "color"}` | prioritaire au changement, sinon cible 500 ms |
| `elio/telemetry/mode` | `idle` \| `manual` \| `exploration` \| `fly` | au changement et environ 1 s |
| `elio/telemetry/fly_sensors` | `{session, frame, left, front, right, back}` | jusqu’à 5 Hz en mode mouche |
| `elio/telemetry/status` | `{protocol, line_threshold, position_valid, last_error}` | environ 1 s |
| `elio/telemetry/step` | `{session, step_id, completed_id, x, y, heading, action, front, left, right, position_valid}` | après chaque action, répétée après 1 s sans réponse |

**Serveur → Robot**

| Topic | Payload |
|---|---|
| `elio/command/mode` | `idle` \| `manual` \| `exploration` \| `fly` |
| `elio/command/move` | `forward` \| `backward` \| `left` \| `right` \| `stop` |
| `elio/command/speed` | `int` 0–100 |
| `elio/command/explore_step` | JSON `{session, step_id, action}` ; action `forward`, `turn_right`, `turn_left` ou `uturn` |
| `elio/command/fly_drive` | `{session, frame, left, right}` ; roues entre −45 et 45 % |
| `elio/command/buzzer` | `1` |
| `elio/command/mute` | `1` \| `0` |
| `elio/command/reset_map` | `1` |

### Reprise et arrêt

- Chaque étape d’exploration porte un `session` et un `step_id`. Le serveur renvoie ces deux champs dans sa commande. Le robot ignore les identifiants anciens et les doublons ; `completed_id` dans l’étape suivante confirme la commande terminée.
- En attente, le robot reste arrêté et republie la même étape après une seconde. Le serveur réémet la même décision sans ajouter de doublon au journal. Un redémarrage du serveur peut ainsi reprendre le dialogue.
- Une perte de connexion MQTT arrête le mouvement et remet le robot en veille. Le retour du réseau exige de relancer explicitement le pilotage ; un déplacement interrompu n’est pas compté comme terminé.
- Les erreurs de réception MQTT, de télémétrie ou d’envoi des observations sont conservées dans `last_error` jusqu’à un redémarrage complet ou une nouvelle erreur. Le serveur les journalise sous `[Robot] Erreur embarquée`, même après reconnexion. Voir le [dépannage du dashboard](server/control-dashboard/README.md#dépannage).
- Réinitialiser la carte arrête le robot, revient en veille et crée une nouvelle session. Replacer le robot au point et à l’orientation de départ pour retrouver le même repère.
- La carte repose sur des mouvements temporisés, sans mesure de la distance réelle. Après un mouvement manuel ou interrompu, le dashboard signale une position incertaine. Même sans cette alerte, patinage et erreur de rotation peuvent produire une dérive.
- Ouvrir un dashboard ne change pas le mode. Le maintien du D-Pad cesse au relâchement, à l’annulation du pointeur, à la perte de focus ou de connexion. Le délai de 800 ms est vérifié dans la boucle robot ; les appels réseau synchrones peuvent ajouter de la latence.
- Une vitesse de 0 ne commande plus de mouvement. Les consignes positives inférieures à 15 utilisent le minimum moteur de 15 %.

### WebSocket

À la connexion, `/ws` envoie `{type: "snapshot", state: {...}}`. Ensuite, il envoie au plus toutes les 300 ms `{type: "delta", state: {...}}` avec seulement les champs changés. Les nouvelles étapes passent dans `steps_append` ; un reset remplace `state.steps`. Le navigateur conserve les 1 000 dernières étapes et ne redessine la carte que lorsque nécessaire.

### Mettre à jour cette version

Les protocoles d’exploration, de mouche et le format WebSocket ont changé : **mettre à jour le robot et le serveur ensemble**, puis recharger la page du dashboard. Les anciennes commandes d’exploration sous forme de texte brut sont ignorées.

Le code du serveur et l’interface sont embarqués dans la même image Docker. Depuis `server/control-dashboard/`, exécuter `docker compose up -d --build --no-deps dashboard` après une modification ; un simple redémarrage ne copie pas les nouveaux fichiers dans l’image.

Les durées tiennent maintenant compte de la vitesse de 60 % et n’ajoutent plus les 100 ms forfaitaires. Vérifier à nouveau les facteurs de calibration avant de se fier à la trajectoire.

<br>

# 3. API Hardware

> Disponible dans tous les programmes via `from .hardware import ...`

<br>

## Motors

```python
motors = setup_motors()

motors.move_forward(speed=70)
motors.move_backward(speed=70)
motors.turn_left(speed=70)
motors.turn_right(speed=70)
motors.turn_in_place(speed=70, direction="left")
motors.motor_stop()
```

## Buzzer

```python
buzzer = setup_buzzer()

buzzer.play_tone(440, 0.2)      # fréquence Hz, durée s
buzzer.sound_startup()
buzzer.sound_bump()
buzzer.sound_blink()
buzzer.sound_happy()
buzzer.sound_laser()
buzzer.emotion_joie()
buzzer.emotion_colere()
buzzer.melody_marseillaise()
```

## EyesMatrix

```python
matrix = setup_matrix()

matrix.set_matrix_logo(matrix.emotionHappy,   (87, 49, 150))   # violet
matrix.set_matrix_logo(matrix.emotionAngry,   (255, 0, 0))
matrix.set_matrix_logo(matrix.arrowUp,        (0, 180, 80))
matrix.set_matrix_logo(matrix.emotionNeutral, (50, 50, 50))
matrix.clear_matrix()
```

## ObstacleSensor

```python
sensors = setup_obstacle_sensors()

sensors.get_obstacle(0)  # Avant gauche
sensors.get_obstacle(1)  # Avant (centre)
sensors.get_obstacle(2)  # Avant droit
sensors.get_obstacle(3)  # Arrière
```

## LineSensor

```python
line_sensor = setup_line_sensor(motors)

# Valeur brute par capteur : ambient - lit  (-65535 à 65535)
# Convention : ligne sombre si valeur < seuil calibré
line_sensor.lineCmd.value = True
lit     = [inp.value for inp in line_sensor.lineInput]
line_sensor.lineCmd.value = False
ambient = [inp.value for inp in line_sensor.lineInput]
values  = [ambient[i] - lit[i] for i in range(5)]
```

## Timers non-bloquants

```python
from .hardware import every_ms, now_ms, sleep_ms

while True:
    if every_ms("batt", 5000):
        # Exécuté toutes les 5 secondes
        v = motors.get_battery_voltage()

    if every_ms("display", 500):
        # Exécuté toutes les 500ms
        matrix.set_matrix_logo(matrix.emotionHappy, (87, 49, 150))

    sleep_ms(20)
```

# Ressources

- [Eliobot](https://eliobot.com) - site officiel et documentation hardware
- [CircuitPython](https://circuitpython.org) - runtime embarqué
- [FastAPI](https://fastapi.tiangolo.com) - backend dashboard
- [Eclipse Mosquitto](https://mosquitto.org) - broker MQTT


# Vérifications sans matériel

Depuis la racine du projet :

```bash
uv run --no-project --with fastapi --with paho-mqtt --with numpy --with scipy --with pandas --with pyarrow python -m unittest discover -s tests -v
node --test tests/dashboard.test.cjs
```

Les tests simulent les sorties moteur, MQTT, l’horloge et le navigateur. Ils couvrent l’arrêt après erreur, l’expiration manuelle, les resets, les pertes de messages, les doublons, le chargement différé et les mises à jour WebSocket. Les essais physiques de freinage, de délai réseau et de calibration restent à effectuer sur ElioBot.

### Synchronisation des yeux en manuel

Le robot mémorise chaque changement d’expression et le publie en priorité après l’exécution de la commande manuelle. Les autres groupes de télémétrie sont servis à tour de rôle, pour éviter que les envois fréquents de statut et d’obstacles ne retardent indéfiniment les yeux sous charge réseau. Le dessin n’est plus réécrit sur les LED à chaque passage s’il est inchangé ; un arrêt ou une expiration rétablit l’expression neutre. La carte affiche l’expression reçue du robot, sans l’inventer à partir du bouton pressé. Les délais MQTT et le rafraîchissement WebSocket peuvent toujours retarder l’affichage.
