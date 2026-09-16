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
LED_FLY     = (50, 100, 180)
LED_EXPLORE = (0, 180, 80)     # Vert : exploration

# Exploration - vitesse et distance d'un pas
EXPLORE_SPEED = 60
STEP_CM       = 15
TURN_DEG      = 90
STEP_RETRY_MS = 1000

# Offsets de déplacement selon le heading : N=0, E=1, S=2, W=3
HEADING_DX = {0: 0, 1: 1, 2: 0, 3: -1}
HEADING_DY = {0: 1, 1: 0, 2: -1, 3: 0}


def run():
    print("Starting MQTT Dashboard program...")

    try:
        with open("/config.json") as f:
            _cfg = json.load(f)
        LINE_THRESHOLD = int(_cfg.get("line_threshold", 30000))
        TURN_FACTOR    = float(_cfg.get("turn_factor", 1.0))
        MOVE_FACTOR    = float(_cfg.get("move_factor", 1.0))
        if not (0.1 <= TURN_FACTOR <= 5 and 0.1 <= MOVE_FACTOR <= 5):
            raise ValueError("Facteurs de calibration hors limites")
    except Exception:
        LINE_THRESHOLD = 30000
        TURN_FACTOR    = 1.0
        MOVE_FACTOR    = 1.0
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
        "session": "".join("%02x" % b for b in os.urandom(8)),
        "step_id": 0,
        "pending_step": None,
        "retry_at": 0,
        "completed_id": None,
        "position_valid": True,
        "fly_frame": 0, "fly_pending": None, "fly_sent_at": 0,
        "fly_next_at": 0, "fly_until": 0, "fly_wheels": (0, 0),
        "mode":        "idle",   # "idle" | "manual" | "exploration" | "fly"

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
        "eyes_color":   LED_IDLE,
        "eyes_dirty": True,
        "telemetry_cursor": 0,
        "telemetry_last": None,
        "telemetry_due": [0, 0, 0, 0, 0],
        "last_error": None,

        # Son
        "muted": False,
    }

    # ── Helpers yeux, lignes & son ─────────────────────────

    def beep(sound_fn):
        """Joue un son seulement si le robot n'est pas muet."""
        if (not state["muted"] and state["manual_cmd"] in (None, "stop")
                and state["ex_state"] in ("check", "waiting")
                and state["mode"] != "fly"):
            sound_fn()

    def set_eyes(pattern_name, color):
        """Affiche un pattern sur la matrice et mémorise l'état pour la télémétrie."""
        if state["eyes_pattern"] == pattern_name and state["eyes_color"] == color:
            return
        matrix.set_matrix_logo(getattr(matrix, pattern_name), color)
        state["eyes_pattern"] = pattern_name
        state["eyes_color"]   = color
        state["eyes_dirty"] = True

    def read_lines_batch():
        """Lit les 5 capteurs IR en une seule séquence on/off (40ms total).
        Retourne les valeurs brutes (ambient - lit), de -65535 à 65535.
        Convention du suivi de ligne : ligne sombre si valeur < seuil calibré.
        """
        line_sensor.lineCmd.value = True
        sleep_ms(20)
        lit = [inp.value for inp in line_sensor.lineInput]
        line_sensor.lineCmd.value = False
        sleep_ms(20)
        ambient = [inp.value for inp in line_sensor.lineInput]
        return [ambient[i] - lit[i] for i in range(5)]

    def record_error(stage, error):
        # Conservé après reconnexion : le serveur peut lire la cause même sans USB.
        state["last_error"] = {"stage": stage, "message": str(error)[:200],
                               "uptime_ms": now_ms(), "session": state["session"]}

    # ── Callbacks MQTT ─────────────────────────────────────

    def cancel_motion():
        motors.motor_stop()
        if state["ex_state"] not in ("check", "waiting"):
            state["position_valid"] = False
        state["manual_cmd"] = None
        state["manual_until"] = 0
        state["ex_state"] = "check"
        state["ex_until"] = 0
        state["pending_step"] = None
        state["completed_id"] = None
        state["fly_pending"] = None
        state["fly_until"] = 0
        state["fly_wheels"] = (0, 0)

    def on_connected(client, userdata, flags, rc):
        # Une reconnexion ne doit jamais reprendre un mouvement ancien.
        cancel_motion()
        state["mode"] = "idle"
        print(f"MQTT connecté ({BROKER_IP}:{PORT}) — en veille")
        client.subscribe("elio/command/#")
        set_eyes("emotionHappy", LED_IDLE)
        beep(buzzer.sound_blink)
        client.publish("elio/telemetry/mode", "idle")

    def on_disconnected(client, userdata, rc):
        print("MQTT déconnecté - arrêt sécurité")
        cancel_motion()
        state["mode"] = "idle"

    def on_message(client, topic, message):
        # ── Changement de mode ──
        if topic == "elio/command/mode":
            if message in ("idle", "manual", "exploration", "fly"):
                old = state["mode"]
                if message != old or message == "idle":
                    cancel_motion()
                    state["mode"] = message
                    state["ex_last_action"] = "start"
                    print(f"Mode: {old} → {message}")
                try:
                    client.publish("elio/telemetry/mode", message)
                except Exception:
                    pass

        # ── Commande manuelle ──
        elif topic == "elio/command/move" and state["mode"] == "manual":
            if message in ("forward", "backward", "left", "right", "stop"):
                state["manual_cmd"]   = message
                state["manual_until"] = now_ms() + 800  # valide 800ms (dead-man's switch)
                if message == "stop":
                    motors.motor_stop()

        elif topic == "elio/command/fly_drive" and state["mode"] == "fly":
            pending = state["fly_pending"]
            if pending is None or now_ms() - state["fly_sent_at"] > 600:
                return
            try:
                command = json.loads(message)
                if (not isinstance(command, dict)
                        or command.get("session") != state["session"]
                        or type(command.get("frame")) is not int
                        or command.get("frame") != pending["frame"]):
                    return
                wheels = (command.get("left"), command.get("right"))
                if any(type(v) is not int or not -45 <= v <= 45 for v in wheels):
                    return
            except (ValueError, TypeError):
                return
            state["fly_pending"] = None
            state["fly_wheels"] = wheels
            state["fly_until"] = now_ms() + 500

        # ── Vitesse ──
        elif topic == "elio/command/speed":
            try:
                spd = int(message)
                if 0 <= spd <= 100:
                    state["manual_speed"] = spd
                    if spd == 0:
                        motors.motor_stop()
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
            cancel_motion()
            state["mode"] = "idle"
            state["session"] = "".join("%02x" % b for b in os.urandom(8))
            state["step_id"] = 0
            state["position_valid"] = True
            state["ex_x"]           = 0
            state["ex_y"]           = 0
            state["ex_heading"]     = 0
            state["ex_state"]       = "check"
            state["ex_until"]       = 0
            state["ex_last_action"] = "start"
            client.publish("elio/telemetry/mode", "idle")
            print("Carte réinitialisée — robot arrêté")

        # ── Commande de mouvement exploration (depuis le cerveau serveur) ──
        elif topic == "elio/command/explore_step" and state["mode"] == "exploration":
            pending = state["pending_step"]
            if state["ex_state"] != "waiting" or pending is None:
                return
            try:
                command = json.loads(message)
                if (not isinstance(command, dict)
                        or command.get("session") != state["session"]
                        or command.get("step_id") != pending["step_id"]):
                    return
                message = command.get("action")
                if message not in ("forward", "turn_right", "turn_left", "uturn"):
                    return
            except (ValueError, TypeError):
                return
            # Consommer l'identifiant avant d'actionner les moteurs : pas de rejeu.
            state["pending_step"] = None
            state["completed_id"] = command["step_id"]
            rps = motors.repetition_per_second(EXPLORE_SPEED)
            gear = motors.SPACE_BETWEEN_WHEELS / motors.WHEEL_DIAMETER
            move_ms = int(STEP_CM / motors.DISTANCE_PER_REVOLUTION / rps * 1000 * MOVE_FACTOR)
            turn_ms = int(TURN_DEG / (360.0 * rps) * gear * 1000 * TURN_FACTOR)
            uturn_ms = turn_ms * 2
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
        # Les flèches changées passent en priorité ; les autres groupes tournent
        # équitablement, même quand le réseau ralentit le pilotage manuel.
        periods = (500, 1000, 5000, 400, 1500)  # yeux, statut, batterie, obstacles, ligne
        now = now_ms()
        group = None
        if state["eyes_dirty"] and state["telemetry_last"] != 0:
            group = 0
        else:
            for offset in range(5):
                candidate = (state["telemetry_cursor"] + offset) % 5
                if now >= state["telemetry_due"][candidate]:
                    group = candidate
                    break
        if group is None:
            return
        try:
            if group == 0:
                mqtt_client.publish("elio/telemetry/eyes", json.dumps({
                    "pattern": state["eyes_pattern"], "color": state["eyes_color"],
                }))
                state["eyes_dirty"] = False
            elif group == 1:
                mqtt_client.publish("elio/telemetry/mode", state["mode"])
                mqtt_client.publish("elio/telemetry/status", json.dumps({
                    "protocol": 2,
                    "line_threshold": LINE_THRESHOLD,
                    "turn_factor": TURN_FACTOR,
                    "position_valid": state["position_valid"],
                    "last_error": state["last_error"],
                }))
            elif group == 2:
                v = motors.get_battery_voltage()
                mqtt_client.publish("elio/telemetry/battery", f"{v:.2f}")
            elif group == 3:
                raw = [sensors.get_raw(i) for i in range(4)]
                names = ("left", "front", "right", "back")
                obs = {
                    names[i]: raw[i] < sensors.thresholds[i] for i in range(4)
                }
                obs["raw"] = dict(zip(names, raw))
                obs["thresholds"] = dict(zip(names, sensors.thresholds))
                mqtt_client.publish("elio/telemetry/obstacles", json.dumps(obs))
            elif group == 4:
                mqtt_client.publish("elio/telemetry/lines", json.dumps(read_lines_batch()))
            state["telemetry_due"][group] = now + periods[group]
            state["telemetry_last"] = group
            # Un envoi urgent des yeux ne remet pas la rotation au début.
            if not (group == 0 and state["telemetry_cursor"] != 0):
                state["telemetry_cursor"] = (group + 1) % 5
        except Exception as e:
            cancel_motion()
            state["mode"] = "idle"
            print(f"Telemetry error: {e}")
            record_error("telemetry", e)

    def publish_step():
        # Réémettre exactement la même étape après une perte de message.
        state["retry_at"] = now_ms() + STEP_RETRY_MS
        try:
            mqtt_client.publish("elio/telemetry/mode", state["mode"])
            mqtt_client.publish("elio/telemetry/step", json.dumps(state["pending_step"]))
        except Exception as e:
            print(f"Step publish error: {e}")

    def handle_manual(now):
        """Mode manuel : exécute la commande reçue. Arrêt automatique si timeout."""
        cmd = state.get("manual_cmd")
        if cmd is None or now >= state["manual_until"] or state["manual_speed"] == 0:
            motors.motor_stop()
            state["manual_cmd"] = None
            if cmd is not None or every_ms("idle_expr_m", 2000):
                set_eyes("emotionNeutral", LED_MANUAL)
            return

        if cmd != "stop":
            state["position_valid"] = False
        spd = state["manual_speed"]
        if cmd == "forward":
            motors.move_forward(spd)
            set_eyes("arrowUp", LED_MANUAL)
        elif cmd == "backward":
            motors.move_backward(spd)
            set_eyes("arrowDown", LED_MANUAL)
        elif cmd == "left":
            motors.turn_left(spd)
            set_eyes("arrowLeft", LED_MANUAL)
        elif cmd == "right":
            motors.turn_right(spd)
            set_eyes("arrowRight", LED_MANUAL)
        elif cmd == "stop":
            motors.motor_stop()
            state["manual_cmd"] = None
            set_eyes("emotionNeutral", LED_MANUAL)

    def handle_fly(now):
        """Commandes de roues bornées, expirantes et liées à une observation."""
        motors.motor_stop()
        if now < state["fly_until"]:
            left, right = state["fly_wheels"]
            if sensors.get_obstacle(1) and left + right > 0:
                rotation = int((right - left) / 2)
                left, right = -rotation, rotation
            if left or right:
                state["position_valid"] = False
            if left >= 15:
                motors.spin_left_wheel_forward(left)
            elif left <= -15:
                motors.spin_left_wheel_backward(-left)
            if right >= 15:
                motors.spin_right_wheel_forward(right)
            elif right <= -15:
                motors.spin_right_wheel_backward(-right)
        else:
            state["fly_wheels"] = (0, 0)
        if now < state["fly_next_at"]:
            return
        if state["fly_pending"] is not None and now - state["fly_sent_at"] < 600:
            return
        state["fly_frame"] += 1
        state["fly_pending"] = {
            "session": state["session"], "frame": state["fly_frame"],
            "left": bool(sensors.get_obstacle(0)), "front": bool(sensors.get_obstacle(1)),
            "right": bool(sensors.get_obstacle(2)), "back": bool(sensors.get_obstacle(3)),
        }
        state["fly_sent_at"] = now
        state["fly_next_at"] = now + 200
        try:
            mqtt_client.publish("elio/telemetry/fly_sensors", json.dumps(state["fly_pending"]))
        except Exception as e:
            motors.motor_stop()
            state["fly_until"] = 0
            print("Capteurs mouche :", e)
            record_error("fly_sensors", e)
        if every_ms("fly_eyes", 1000):
            set_eyes("emotionNeutral", LED_FLY)

    def exploration_tick(now):
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
            motors.motor_stop()
            ex["step_id"] += 1
            ex["pending_step"] = {
                "session": ex["session"], "step_id": ex["step_id"],
                "completed_id": ex["completed_id"],
                "x": ex["ex_x"], "y": ex["ex_y"], "heading": ex["ex_heading"],
                "action": ex["ex_last_action"],
                "front": ex["ex_front"], "left": ex["ex_left"], "right": ex["ex_right"],
                "position_valid": ex["position_valid"],
            }
            ex["ex_state"] = "waiting"
            publish_step()
            set_eyes("emotionNeutral", LED_EXPLORE)

        # ── WAITING : le serveur envoie explore_step ──────
        elif es == "waiting":
            if now >= ex["retry_at"]:
                publish_step()

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
        # Les échéances moteur sont évaluées avant et après les opérations réseau.
        if state["mode"] == "manual":
            handle_manual(now_ms())
        elif state["mode"] == "exploration":
            exploration_tick(now_ms())
        elif state["mode"] == "fly":
            handle_fly(now_ms())

        # Réception MQTT avec un timeout court.
        try:
            mqtt_client.loop(timeout=0.1)
            reconnect_wait = 1
        except Exception as e:
            cancel_motion()
            state["mode"] = "idle"
            print(f"Loop error: {e}")
            record_error("mqtt_loop", e)
            sleep_ms(reconnect_wait * 1000)
            try:
                mqtt_client.reconnect()
            except Exception:
                reconnect_wait = min(reconnect_wait * 2, 30)
            continue

        # ── Comportement par mode ──
        mode = state["mode"]

        if mode == "idle":
            if every_ms("idle_stop", 2000):
                motors.motor_stop()
            if every_ms("idle_expr", 6000):
                set_eyes("emotionNeutral", LED_IDLE)

        elif mode == "manual":
            handle_manual(now_ms())

        elif mode == "exploration":
            exploration_tick(now_ms())
        elif mode == "fly":
            handle_fly(now_ms())

        # Un groupe par passage pour limiter le délai entre deux contrôles moteur.
        publish_telemetry()
        sleep_ms(20)
