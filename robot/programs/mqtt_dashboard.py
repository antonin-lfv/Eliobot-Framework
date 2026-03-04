import json
import os
import wifi
import socketpool
import adafruit_minimqtt.adafruit_minimqtt as MQTT

from .hardware import (
    setup_motors, setup_buzzer, setup_matrix, setup_obstacle_sensors,
    setup_line_sensor, sleep_ms, now_ms, every_ms,
)
from elio import WiFiConnectivity

PROGRAM_NAME = "mqtt_dashboard"

# Couleurs LED par mode
LED_IDLE    = (50, 50, 50)     # Gris foncé : veille
LED_MANUAL  = (87, 49, 150)    # Violet : contrôle manuel
LED_EXPLORE = (0, 180, 80)     # Vert : exploration

# Exploration - vitesse et distance d'un pas
EXPLORE_SPEED = 60
STEP_CM       = 15
TURN_DEG      = 90

# Offsets de déplacement selon le heading : N=0, E=1, S=2, W=3
HEADING_DX = {0: 0, 1: 1, 2: 0, 3: -1}
HEADING_DY = {0: 1, 1: 0, 2: -1, 3: 0}


def run():
    print("Starting MQTT Dashboard program...")

    import json as _json
    try:
        with open("/config.json") as f:
            _cfg = _json.load(f)
        LINE_THRESHOLD = int(_cfg.get("line_threshold", 30000))
        TURN_FACTOR    = float(_cfg.get("turn_factor", 1.0))
    except Exception:
        LINE_THRESHOLD = 30000
        TURN_FACTOR    = 1.0
    print(f"Seuil capteurs de ligne : {LINE_THRESHOLD} | Facteur rotation : {TURN_FACTOR}")

    matrix  = setup_matrix()
    buzzer  = setup_buzzer()
    motors  = setup_motors()
    sensors = setup_obstacle_sensors()
    line_sensor = setup_line_sensor(motors)

    BROKER_IP = os.getenv("BROKER_IP")
    PORT      = int(os.getenv("PORT", 1883))
    SSID      = os.getenv("SSID")
    PASSWORD  = os.getenv("PASSWORD")

    buzzer.sound_startup()
    matrix.set_matrix_logo(matrix.emotionConfused, LED_IDLE)

    # ── WiFi ──────────────────────────────────────────────
    try:
        WiFiConnectivity.connect_and_setup(
            ssid=SSID, password=PASSWORD, hostname=None, buzzer=buzzer,
        )
    except Exception as e:
        print(f"WiFi failed: {e}")
        while True:
            sleep_ms(1000)

    # ── État global ────────────────────────────────────────
    # Accessible depuis les callbacks MQTT et la boucle principale.
    state = {
        # Mode courant
        "mode":        "idle",   # "idle" | "manual" | "exploration"

        # Mode manuel
        "manual_cmd":   None,    # dernière commande reçue
        "manual_until": 0,       # validité de la commande (ms) - dead-man's switch
        "manual_speed": 70,

        # State machine exploration
        "ex_state":    "check",  # "check" | "moving" | "turning_right" | "turning_left" | "uturn"
        "ex_until":    0,        # timestamp de fin d'action
        "ex_heading":  0,        # 0=N 1=E 2=S 3=W
        "ex_x":        0,
        "ex_y":        0,
        # Capteurs du dernier check (utilisés dans le step publié)
        "ex_front": False,
        "ex_left":  False,
        "ex_right": False,
        # Dernière action terminée (pour le log du dashboard)
        "ex_last_action": "start",

        # Télémétrie yeux - mis à jour par set_eyes()
        "eyes_pattern": "emotionConfused",
        "eyes_color":   list(LED_IDLE),

        # Son
        "muted": False,
    }

    # ── Helpers yeux, lignes & son ─────────────────────────

    def beep(sound_fn):
        """Joue un son seulement si le robot n'est pas muet."""
        if not state["muted"]:
            sound_fn()

    def set_eyes(pattern_name, color):
        """Affiche un pattern sur la matrice et mémorise l'état pour la télémétrie."""
        matrix.set_matrix_logo(getattr(matrix, pattern_name), color)
        state["eyes_pattern"] = pattern_name
        state["eyes_color"]   = list(color)

    def read_lines_batch():
        """Lit les 5 capteurs IR en une seule séquence on/off (40ms total).
        Retourne les valeurs brutes (ambient - lit), entiers signés 16-bit.
        Valeur positive élevée = ligne noire, négative/nulle = surface blanche.
        """
        line_sensor.lineCmd.value = True
        sleep_ms(20)
        lit = [inp.value for inp in line_sensor.lineInput]
        line_sensor.lineCmd.value = False
        sleep_ms(20)
        ambient = [inp.value for inp in line_sensor.lineInput]
        return [ambient[i] - lit[i] for i in range(5)]

    # ── Callbacks MQTT ─────────────────────────────────────

    def on_connected(client, userdata, flags, rc):
        print(f"MQTT connecté ({BROKER_IP}:{PORT})")
        client.subscribe("elio/command/#")
        set_eyes("emotionHappy", LED_IDLE)
        beep(buzzer.sound_blink)
        # Annoncer le mode initial
        client.publish("elio/telemetry/mode", state["mode"])

    def on_disconnected(client, userdata, rc):
        print("MQTT déconnecté - arrêt sécurité")
        motors.motor_stop()

    def on_message(client, topic, message):
        # ── Changement de mode ──
        if topic == "elio/command/mode":
            if message in ("idle", "manual", "exploration"):
                old = state["mode"]
                state["mode"] = message
                if message != old:
                    motors.motor_stop()
                    state["manual_cmd"]   = None
                    state["manual_until"] = 0
                    print(f"Mode: {old} → {message}")
                # Reset exploration si on y entre
                if message == "exploration":
                    state["ex_state"]       = "check"
                    state["ex_until"]       = 0
                    state["ex_last_action"] = "start"
                try:
                    client.publish("elio/telemetry/mode", message)
                except Exception:
                    pass

        # ── Commande manuelle ──
        elif topic == "elio/command/move" and state["mode"] == "manual":
            if message in ("forward", "backward", "left", "right", "stop"):
                state["manual_cmd"]   = message
                state["manual_until"] = now_ms() + 800  # valide 800ms (dead-man's switch)

        # ── Vitesse ──
        elif topic == "elio/command/speed":
            try:
                spd = int(message)
                if 0 <= spd <= 100:
                    state["manual_speed"] = spd
            except ValueError:
                pass

        # ── Mute / unmute ──
        elif topic == "elio/command/mute":
            state["muted"] = (message == "1")
            print(f"Son : {'muet' if state['muted'] else 'actif'}")

        # ── Test buzzer ──
        elif topic == "elio/command/buzzer":
            beep(buzzer.sound_blink)

        # ── Reset carte d'exploration ──
        elif topic == "elio/command/reset_map":
            state["ex_x"]           = 0
            state["ex_y"]           = 0
            state["ex_heading"]     = 0
            state["ex_state"]       = "check"
            state["ex_until"]       = 0
            state["ex_last_action"] = "start"
            print("Carte réinitialisée")

        # ── Commande de mouvement exploration (depuis le cerveau serveur) ──
        elif topic == "elio/command/explore_step" and state["mode"] == "exploration":
            if state["ex_state"] != "waiting":
                return  # pas prêt, ignorer
            rps      = motors.repetition_per_second()
            gear     = motors.SPACE_BETWEEN_WHEELS / motors.WHEEL_DIAMETER
            move_ms  = int((STEP_CM / motors.DISTANCE_PER_REVOLUTION / rps) * 1000) + 100
            turn_ms  = int((TURN_DEG / (360.0 * rps)) * gear * 1000 * TURN_FACTOR) + 100
            uturn_ms = int((180.0    / (360.0 * rps)) * gear * 1000 * TURN_FACTOR) + 100
            t = now_ms()
            if message == "forward":
                motors.move_forward(EXPLORE_SPEED)
                state["ex_state"] = "moving"
                state["ex_until"] = t + move_ms
                set_eyes("arrowUp", LED_EXPLORE)
            elif message == "turn_right":
                motors.turn_right(EXPLORE_SPEED)
                state["ex_state"] = "turning_right"
                state["ex_until"] = t + turn_ms
                set_eyes("arrowRight", LED_EXPLORE)
            elif message == "turn_left":
                motors.turn_left(EXPLORE_SPEED)
                state["ex_state"] = "turning_left"
                state["ex_until"] = t + turn_ms
                set_eyes("arrowLeft", LED_EXPLORE)
            elif message == "uturn":
                motors.turn_right(EXPLORE_SPEED)
                state["ex_state"] = "uturn"
                state["ex_until"] = t + uturn_ms
                set_eyes("emotionAngry", LED_EXPLORE)
                beep(buzzer.sound_bump)

    # ── Setup MQTT ─────────────────────────────────────────
    pool = socketpool.SocketPool(wifi.radio)
    mqtt_client = MQTT.MQTT(broker=BROKER_IP, port=PORT, socket_pool=pool,
                            socket_timeout=0.1)
    mqtt_client.on_connect    = on_connected
    mqtt_client.on_disconnect = on_disconnected
    mqtt_client.on_message    = on_message

    try:
        mqtt_client.connect()
    except Exception as e:
        print(f"MQTT connect failed: {e}")

    # ── Fonctions de comportement ──────────────────────────

    def publish_telemetry():
        try:
            if every_ms("batt", 5000):
                v = motors.get_battery_voltage()
                mqtt_client.publish("elio/telemetry/battery", f"{v:.2f}")

            if every_ms("obs", 400):
                obs = {
                    "left":  bool(sensors.get_obstacle(0)),
                    "front": bool(sensors.get_obstacle(1)),
                    "right": bool(sensors.get_obstacle(2)),
                    "back":  bool(sensors.get_obstacle(3)),
                }
                mqtt_client.publish("elio/telemetry/obstacles", json.dumps(obs))

            if every_ms("eyes", 500):
                mqtt_client.publish("elio/telemetry/eyes", json.dumps({
                    "pattern": state["eyes_pattern"],
                    "color":   state["eyes_color"],
                }))

            if every_ms("lines", 1500):
                mqtt_client.publish("elio/telemetry/lines", json.dumps(read_lines_batch()))

        except Exception as e:
            print(f"Telemetry error: {e}")

    def publish_step(action: str):
        try:
            step = {
                "x":       state["ex_x"],
                "y":       state["ex_y"],
                "heading": state["ex_heading"],
                "action":  action,
                "front":   state["ex_front"],
                "left":    state["ex_left"],
                "right":   state["ex_right"],
            }
            mqtt_client.publish("elio/telemetry/step", json.dumps(step))
        except Exception as e:
            print(f"Step publish error: {e}")

    def handle_manual(now: int):
        """Mode manuel : exécute la commande reçue. Arrêt automatique si timeout."""
        cmd = state.get("manual_cmd")
        if cmd is None or now >= state["manual_until"]:
            motors.motor_stop()
            if every_ms("idle_expr_m", 2000):
                set_eyes("emotionNeutral", LED_MANUAL)
            return

        spd = state["manual_speed"]
        if cmd == "forward":
            motors.move_forward(spd)
            set_eyes("arrowUp", LED_MANUAL)
        elif cmd == "backward":
            motors.move_backward(spd)
            set_eyes("arrowDown", LED_MANUAL)
        elif cmd == "left":
            motors.turn_in_place(spd, "left")
            set_eyes("arrowLeft", LED_MANUAL)
        elif cmd == "right":
            motors.turn_in_place(spd, "right")
            set_eyes("arrowRight", LED_MANUAL)
        elif cmd == "stop":
            motors.motor_stop()
            state["manual_cmd"] = None
            set_eyes("emotionNeutral", LED_MANUAL)

    def exploration_tick(now: int):
        """
        State machine non-bloquante - architecture ROS-like.

        Le robot est un pur exécuteur :
          check    → lit les capteurs, publie l'état, passe en waiting
          waiting  → attend la commande du serveur (elio/command/explore_step)
          moving / turning_right / turning_left / uturn → exécution du mouvement

        Le cerveau (choix de la prochaine direction) tourne sur le serveur FastAPI.
        """
        ex = state

        if now < ex["ex_until"]:
            return

        es = ex["ex_state"]

        # ── CHECK : lecture capteurs + publication ────────
        if es == "check":
            ex["ex_front"] = bool(sensors.get_obstacle(1))
            ex["ex_left"]  = bool(sensors.get_obstacle(0))
            ex["ex_right"] = bool(sensors.get_obstacle(2))
            publish_step(ex["ex_last_action"])
            ex["ex_state"] = "waiting"
            set_eyes("emotionNeutral", LED_EXPLORE)

        # ── WAITING : le serveur envoie explore_step ──────
        elif es == "waiting":
            pass  # géré dans on_message / elio/command/explore_step

        # ── TURNING RIGHT ─────────────────────────────────
        elif es == "turning_right":
            motors.motor_stop()
            ex["ex_heading"]     = (ex["ex_heading"] + 1) % 4
            ex["ex_last_action"] = "turned_right"
            ex["ex_state"]       = "check"

        # ── TURNING LEFT ──────────────────────────────────
        elif es == "turning_left":
            motors.motor_stop()
            ex["ex_heading"]     = (ex["ex_heading"] + 3) % 4
            ex["ex_last_action"] = "turned_left"
            ex["ex_state"]       = "check"

        # ── UTURN ─────────────────────────────────────────
        elif es == "uturn":
            motors.motor_stop()
            ex["ex_heading"]     = (ex["ex_heading"] + 2) % 4
            ex["ex_last_action"] = "uturn"
            ex["ex_state"]       = "check"

        # ── MOVING ────────────────────────────────────────
        elif es == "moving":
            motors.motor_stop()
            h = ex["ex_heading"]
            ex["ex_x"]           += HEADING_DX[h]
            ex["ex_y"]           += HEADING_DY[h]
            ex["ex_last_action"]  = "moved_forward"
            ex["ex_state"]        = "check"

    # ── BOUCLE PRINCIPALE ─────────────────────────────────
    reconnect_wait = 1

    while True:
        now = now_ms()

        # MQTT loop (non-bloquant, 50ms max)
        try:
            mqtt_client.loop(timeout=0.1)
            reconnect_wait = 1
        except Exception as e:
            print(f"Loop error: {e}")
            motors.motor_stop()
            sleep_ms(reconnect_wait * 1000)
            try:
                mqtt_client.reconnect()
            except Exception:
                reconnect_wait = min(reconnect_wait * 2, 30)

        # Télémétrie périodique
        publish_telemetry()

        # ── Comportement par mode ──
        mode = state["mode"]

        if mode == "idle":
            if every_ms("idle_stop", 2000):
                motors.motor_stop()
            if every_ms("idle_expr", 6000):
                set_eyes("emotionNeutral", LED_IDLE)

        elif mode == "manual":
            handle_manual(now)

        elif mode == "exploration":
            exploration_tick(now)

        sleep_ms(20)
