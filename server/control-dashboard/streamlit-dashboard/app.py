"""
Eliobot Dashboard
Dashboard Streamlit temps réel pour contrôler et monitorer le robot.
"""

import copy
import json
import os
import threading
import time
from collections import deque
from datetime import datetime

import paho.mqtt.client as mqtt
import plotly.graph_objects as go
import streamlit as st

# ============================================================
# CONFIGURATION
# ============================================================
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
REFRESH_S = 1.0  # Auto-refresh toutes les secondes

# Coordonnées selon le heading : N=0, E=1, S=2, W=3
HEADING_ARROW = {0: "↑", 1: "→", 2: "↓", 3: "←"}
HEADING_LABEL = {0: "Nord", 1: "Est", 2: "Sud", 3: "Ouest"}
HEADING_DX    = {0: 0, 1: 1, 2: 0, 3: -1}
HEADING_DY    = {0: 1, 1: 0, 2: -1, 3: 0}

MODE_LABELS = {
    "idle":        "⏸ Veille",
    "manual":      "🕹️ Manuel",
    "exploration": "🗺️ Exploration",
}

ACTION_LABELS = {
    "start":          "🚀 Départ",
    "moved_forward":  "⬆️ Avancé",
    "turned_right":   "↩️ Tourné droite",
    "turned_left":    "↪️ Tourné gauche",
    "uturn":          "🔄 Demi-tour",
    "check":          "🔍 Vérification",
}


# ============================================================
# CLIENT MQTT — Singleton partagé entre tous les reruns
# ============================================================
class RobotMQTTClient:
    """Client MQTT thread-safe qui tourne en arrière-plan."""

    def __init__(self, broker: str, port: int):
        self._lock = threading.Lock()
        self._data = {
            "connected": False,
            "last_seen": None,
            "battery_v": None,
            "obstacles": {"front": False, "left": False, "right": False, "back": False},
            "mode": "idle",
            "steps": deque(maxlen=1000),
        }
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
            client_id="eliobot-dashboard",
        )
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message    = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=15)

        try:
            self._client.connect_async(broker, port, keepalive=60)
            self._client.loop_start()
        except Exception as e:
            print(f"[MQTT] Connexion impossible : {e}")

    # ------ Callbacks internes (appelés depuis le thread MQTT) ------

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            with self._lock:
                self._data["connected"] = True
            client.subscribe([
                ("elio/telemetry/battery",   0),
                ("elio/telemetry/obstacles",  0),
                ("elio/telemetry/mode",       0),
                ("elio/telemetry/step",       0),
            ])
        else:
            with self._lock:
                self._data["connected"] = False

    def _on_disconnect(self, client, userdata, rc):
        with self._lock:
            self._data["connected"] = False

    def _on_message(self, client, userdata, msg):
        topic   = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace")
        with self._lock:
            self._data["last_seen"] = datetime.now()
            try:
                if topic == "elio/telemetry/battery":
                    self._data["battery_v"] = float(payload)

                elif topic == "elio/telemetry/obstacles":
                    self._data["obstacles"] = json.loads(payload)

                elif topic == "elio/telemetry/mode":
                    if payload in ("idle", "manual", "exploration"):
                        self._data["mode"] = payload

                elif topic == "elio/telemetry/step":
                    step = json.loads(payload)
                    step["ts"] = datetime.now().strftime("%H:%M:%S")
                    self._data["steps"].append(step)

            except Exception as e:
                print(f"[MQTT] Erreur parsing {topic}: {e}")

    # ------ API publique ------

    def get_snapshot(self) -> dict:
        """Retourne une copie thread-safe des données courantes."""
        with self._lock:
            return {
                "connected": self._data["connected"],
                "last_seen":  self._data["last_seen"],
                "battery_v":  self._data["battery_v"],
                "obstacles":  copy.copy(self._data["obstacles"]),
                "mode":       self._data["mode"],
                "steps":      list(self._data["steps"]),
            }

    def clear_steps(self):
        with self._lock:
            self._data["steps"].clear()

    def publish(self, topic: str, payload: str):
        try:
            self._client.publish(topic, payload, qos=0)
        except Exception as e:
            print(f"[MQTT] Erreur publish {topic}: {e}")


@st.cache_resource
def get_client() -> RobotMQTTClient:
    return RobotMQTTClient(MQTT_BROKER, MQTT_PORT)


# ============================================================
# HELPERS VISUALISATION
# ============================================================

def battery_pct(voltage: float | None) -> int | None:
    if voltage is None:
        return None
    return max(0, min(100, int((voltage - 3.0) / (4.2 - 3.0) * 100)))


def make_sensor_figure(obstacles: dict) -> go.Figure:
    """Vue de dessus du robot avec capteurs colorés."""
    fig = go.Figure()

    # Corps du robot
    fig.add_shape(
        type="rect", x0=-0.22, y0=-0.35, x1=0.22, y1=0.35,
        fillcolor="#7d3c98", line_color="#4a235a", line_width=2,
    )
    # Indicateur avant (petite flèche)
    fig.add_annotation(
        x=0, y=0.1, text="▲", showarrow=False,
        font=dict(size=22, color="white"),
    )

    # Définition des capteurs (x, y, label, clé dans le dict)
    sensor_defs = [
        (-0.50,  0.42, "Av. G.", "left"),
        ( 0.00,  0.68, "Avant",  "front"),
        ( 0.50,  0.42, "Av. D.", "right"),
        ( 0.00, -0.68, "Arrière","back"),
    ]
    for sx, sy, label, key in sensor_defs:
        blocked = obstacles.get(key, False)
        color   = "#e74c3c" if blocked else "#27ae60"
        text_pos = "top center" if sy > 0 else "bottom center"
        fig.add_trace(go.Scatter(
            x=[sx], y=[sy],
            mode="markers+text",
            marker=dict(size=28, color=color, line=dict(color="white", width=1.5)),
            text=[label],
            textposition=text_pos,
            textfont=dict(size=11, color="#2c3e50"),
            showlegend=False,
            hovertext=f"{label} : {'⛔ obstacle' if blocked else '✅ libre'}",
            hoverinfo="text",
        ))

    fig.update_layout(
        xaxis=dict(range=[-1.1, 1.1], visible=False),
        yaxis=dict(range=[-1.1, 1.1], visible=False, scaleanchor="x"),
        height=270,
        margin=dict(l=5, r=5, t=10, b=5),
        plot_bgcolor="#f4f6f7",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def make_map_figure(steps: list, current: dict | None) -> go.Figure:
    """Carte d'exploration : chemin, obstacles inférés, position actuelle."""
    fig = go.Figure()

    if steps:
        xs = [s["x"] for s in steps]
        ys = [s["y"] for s in steps]

        # Chemin parcouru
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="lines+markers",
            line=dict(color="#3498db", width=2),
            marker=dict(size=5, color="#3498db"),
            name="Chemin",
        ))

        # Obstacles inférés depuis le capteur avant
        obs_x, obs_y = [], []
        for s in steps:
            h = s.get("heading", 0)
            if s.get("front"):
                obs_x.append(s["x"] + HEADING_DX[h])
                obs_y.append(s["y"] + HEADING_DY[h])

        if obs_x:
            fig.add_trace(go.Scatter(
                x=obs_x, y=obs_y,
                mode="markers",
                marker=dict(size=14, color="#e74c3c", symbol="x-thin-open",
                            line=dict(width=3, color="#e74c3c")),
                name="Obstacles",
            ))

    # Position actuelle du robot
    if current:
        h = current.get("heading", 0)
        fig.add_trace(go.Scatter(
            x=[current["x"]], y=[current["y"]],
            mode="markers+text",
            marker=dict(size=18, color="#8e44ad", symbol="circle",
                        line=dict(color="white", width=2)),
            text=[HEADING_ARROW[h]],
            textposition="middle center",
            textfont=dict(size=14, color="white"),
            name="Eliobot",
        ))
    else:
        fig.add_trace(go.Scatter(
            x=[0], y=[0],
            mode="markers",
            marker=dict(size=14, color="#8e44ad", symbol="circle"),
            name="Eliobot (départ)",
        ))

    fig.update_layout(
        xaxis=dict(showgrid=True, gridcolor="#ecf0f1", zeroline=True,
                   zerolinewidth=2, zerolinecolor="#bdc3c7", title="X (pas)"),
        yaxis=dict(showgrid=True, gridcolor="#ecf0f1", zeroline=True,
                   zerolinewidth=2, zerolinecolor="#bdc3c7", scaleanchor="x",
                   title="Y (pas)"),
        height=460,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ============================================================
# PAGE CONFIG & AUTO-REFRESH
# ============================================================
st.set_page_config(
    page_title="Eliobot Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# INIT SESSION STATE
# ============================================================
if "held_cmd" not in st.session_state:
    st.session_state.held_cmd = None   # commande directionnelle maintenue

if "last_speed" not in st.session_state:
    st.session_state.last_speed = 70

# ============================================================
# LECTURE DONNÉES
# ============================================================
client = get_client()
data   = client.get_snapshot()

connected  = data["connected"]
battery_v  = data["battery_v"]
obstacles  = data["obstacles"]
robot_mode = data["mode"]
steps      = data["steps"]
last_seen  = data["last_seen"]
current    = steps[-1] if steps else None

# Republication automatique de la commande maintenue (dead-man's switch)
# Le robot s'arrête si aucune commande n'arrive dans la fenêtre côté robot.
if st.session_state.held_cmd and robot_mode == "manual":
    client.publish("elio/command/move", st.session_state.held_cmd)

# ============================================================
# HEADER
# ============================================================
col_title, col_status, col_battery = st.columns([3, 2, 1.5])

with col_title:
    st.title("🤖 Eliobot Dashboard")
    if robot_mode in MODE_LABELS:
        st.caption(f"Mode actuel : **{MODE_LABELS[robot_mode]}**")

with col_status:
    if connected:
        st.success("● Robot connecté")
        if last_seen:
            delta = (datetime.now() - last_seen).seconds
            st.caption(f"Dernier signal : {last_seen.strftime('%H:%M:%S')} ({delta}s)")
    else:
        st.error("● Robot déconnecté")
        st.caption(f"Broker : {MQTT_BROKER}:{MQTT_PORT}")

with col_battery:
    pct = battery_pct(battery_v)
    if battery_v is not None:
        icon = "🪫" if pct < 20 else "🔋"
        st.metric(f"{icon} Batterie", f"{battery_v:.2f} V", f"{pct}%")
    else:
        st.metric("🔋 Batterie", "—")

st.divider()

# ============================================================
# SIDEBAR — CONTRÔLE
# ============================================================
with st.sidebar:
    st.header("⚙️ Contrôle")

    # --- Mode ---
    mode_options = list(MODE_LABELS.keys())
    current_idx  = mode_options.index(robot_mode) if robot_mode in mode_options else 0
    selected_mode = st.selectbox(
        "Mode",
        options=mode_options,
        format_func=lambda x: MODE_LABELS[x],
        index=current_idx,
        key="mode_select",
    )
    if st.button("✅ Appliquer le mode", use_container_width=True, type="primary"):
        client.publish("elio/command/mode", selected_mode)
        if selected_mode != "manual":
            st.session_state.held_cmd = None  # reset commande maintenue

    st.divider()

    # --- Vitesse ---
    speed = st.slider(
        "Vitesse", min_value=20, max_value=100, value=st.session_state.last_speed,
        step=5, disabled=(robot_mode != "manual"), key="speed_slider",
    )
    if speed != st.session_state.last_speed:
        client.publish("elio/command/speed", str(speed))
        st.session_state.last_speed = speed

    st.divider()

    # --- D-Pad ---
    st.subheader("D-Pad")
    manual = (robot_mode == "manual")

    if st.session_state.held_cmd and manual:
        st.info(f"En mouvement : {st.session_state.held_cmd}")

    # Ligne 1 : bouton haut
    _, col_up, _ = st.columns([1, 1, 1])
    with col_up:
        if st.button("⬆️", use_container_width=True, disabled=not manual, key="btn_fwd"):
            st.session_state.held_cmd = "forward"
            client.publish("elio/command/move", "forward")

    # Ligne 2 : gauche / stop / droite
    col_l, col_s, col_r = st.columns(3)
    with col_l:
        if st.button("⬅️", use_container_width=True, disabled=not manual, key="btn_left"):
            st.session_state.held_cmd = "left"
            client.publish("elio/command/move", "left")
    with col_s:
        if st.button("⏹", use_container_width=True, disabled=not manual, key="btn_stop",
                     type="secondary"):
            st.session_state.held_cmd = None
            client.publish("elio/command/move", "stop")
    with col_r:
        if st.button("➡️", use_container_width=True, disabled=not manual, key="btn_right"):
            st.session_state.held_cmd = "right"
            client.publish("elio/command/move", "right")

    # Ligne 3 : bouton bas
    _, col_dn, _ = st.columns([1, 1, 1])
    with col_dn:
        if st.button("⬇️", use_container_width=True, disabled=not manual, key="btn_bwd"):
            st.session_state.held_cmd = "backward"
            client.publish("elio/command/move", "backward")

    if not manual:
        st.caption("Passe en mode **Manuel** pour contrôler le robot.")

    st.divider()

    # --- Actions utilitaires ---
    if st.button("🔄 Réinitialiser la carte", use_container_width=True):
        client.clear_steps()
        client.publish("elio/command/reset_map", "1")
        st.rerun()

    with st.expander("ℹ️ Connexion MQTT"):
        st.code(f"Broker  : {MQTT_BROKER}\nPort    : {MQTT_PORT}\nTopics  : elio/#")

# ============================================================
# CONTENU PRINCIPAL — 2 ONGLETS
# ============================================================
tab_board, tab_explore = st.tabs(["📊 Tableau de bord", "🗺️ Exploration"])

# ──────────────────────────────────────────────────────────
# ONGLET 1 : TABLEAU DE BORD
# ──────────────────────────────────────────────────────────
with tab_board:
    col_left, col_right = st.columns([1, 1])

    # --- Colonne gauche : capteurs visuels ---
    with col_left:
        st.subheader("Capteurs d'obstacles")
        st.plotly_chart(make_sensor_figure(obstacles),
                        use_container_width=True, key="sensor_fig")

        # Indicateurs texte sous le graphique
        s_cols = st.columns(4)
        for i, (label, key) in enumerate([
            ("Av. G.", "left"), ("Avant", "front"), ("Av. D.", "right"), ("Arrière", "back")
        ]):
            with s_cols[i]:
                if obstacles.get(key):
                    st.error(f"🔴 {label}")
                else:
                    st.success(f"🟢 {label}")

    # --- Colonne droite : état général ---
    with col_right:
        st.subheader("État du robot")

        # Batterie
        if battery_v is not None:
            pct = battery_pct(battery_v)
            color = "red" if pct < 20 else "orange" if pct < 40 else "green"
            st.markdown(f"**Batterie** : `{battery_v:.2f} V` — `{pct}%`")
            st.progress(pct / 100)
        else:
            st.warning("Batterie : données non reçues")

        st.divider()

        # Mode
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Mode", MODE_LABELS.get(robot_mode, robot_mode))
        col_m2.metric("Connexion", "✅ OK" if connected else "❌ Off")

        st.divider()

        # Position (si exploration active)
        if current:
            col_p1, col_p2, col_p3 = st.columns(3)
            col_p1.metric("Position X", current.get("x", 0))
            col_p2.metric("Position Y", current.get("y", 0))
            col_p3.metric("Direction", HEADING_ARROW[current.get("heading", 0)])
            st.metric("Étapes parcourues", len(steps))
        else:
            st.info("Lance le mode **Exploration** pour voir la position en temps réel.")

# ──────────────────────────────────────────────────────────
# ONGLET 2 : EXPLORATION
# ──────────────────────────────────────────────────────────
with tab_explore:
    # Indicateur de mode en haut
    if robot_mode == "exploration":
        st.success("🗺️ Mode Exploration actif — le robot navigue en autonomie")
    else:
        st.info("Passe en mode **Exploration** depuis la sidebar pour démarrer la navigation autonome.")

    # Carte
    st.plotly_chart(make_map_figure(steps, current),
                    use_container_width=True, key="explore_map")

    # Journal des déplacements
    if steps:
        st.subheader(f"Journal ({len(steps)} étapes)")

        # 20 dernières étapes (ordre inversé = plus récent en haut)
        log_rows = []
        for s in reversed(steps[-30:]):
            heading = s.get("heading", 0)
            log_rows.append({
                "Heure":     s.get("ts", ""),
                "Position":  f"({s.get('x', 0)}, {s.get('y', 0)})",
                "Direction": f"{HEADING_ARROW[heading]} {HEADING_LABEL[heading]}",
                "Action":    ACTION_LABELS.get(s.get("action", ""), s.get("action", "")),
                "Avant":     "🔴" if s.get("front") else "🟢",
                "G.":        "🔴" if s.get("left")  else "🟢",
                "D.":        "🔴" if s.get("right") else "🟢",
            })

        st.dataframe(log_rows, use_container_width=True, hide_index=True)

        # Stats rapides
        total_obstacles = sum(
            1 for s in steps if s.get("front") or s.get("left") or s.get("right")
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Étapes totales",  len(steps))
        c2.metric("Détections obstacle", total_obstacles)
        if steps:
            s = steps[-1]
            dist = (s.get("x", 0)**2 + s.get("y", 0)**2) ** 0.5
            c3.metric("Distance départ (estimée)", f"{dist:.1f} pas")
    else:
        st.info("Le journal apparaîtra ici dès que le robot commence à explorer.")

# ============================================================
# AUTO-REFRESH natif (pas de composant tiers)
# ============================================================
time.sleep(REFRESH_S)
st.rerun()
