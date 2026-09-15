"""Adaptation du moteur incarné de Pytorch_fly aux capteurs d'ElioBot.

Même réseau intact et même intégration que flyconnectome.laboratory.advance.
Les capteurs de proximité et la conversion en PWM sont des conventions ajoutées.
Aucun graphe synthétique, aucune politique entraînée ni odeur inventée.
"""
from pathlib import Path
import hashlib
import json
import threading
import time


class FlyBrain:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = threading.Lock()
        self.weight = None
        self.state = {"status": "unloaded", "steps": 0, "error": None,
                      "source": "MaleCNS v1.0", "neurons": 0, "edges": 0}

    def snapshot(self):
        # Remplacement atomique du dictionnaire, sans attendre le calcul neuronal.
        return dict(self.state)

    def load(self):
        with self.lock:
            if self.weight is not None:
                return self.snapshot()
            self.state = {**self.state, "status": "loading", "error": None}
            try:
                import numpy as np
                import pandas as pd
                import scipy.sparse as sp
                manifest = json.loads((self.directory / 'manifest.json').read_text())
                if manifest.get('source') != 'MaleCNS v1.0' or manifest.get('model') != 'laboratory_v1/intact':
                    raise ValueError('La provenance du réseau intact est absente.')
                for filename in ('weight.npz', 'neuron_meta.feather'):
                    path = self.directory / filename
                    digest = hashlib.sha256()
                    with path.open('rb') as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            digest.update(block)
                    if digest.hexdigest() != manifest['sha256'][filename]:
                        raise ValueError('Données modifiées : préparer à nouveau le connectome.')
                weight = sp.load_npz(self.directory / 'weight.npz').tocsr()
                meta = pd.read_feather(self.directory / 'neuron_meta.feather')
                if weight.shape != (len(meta), len(meta)) or len(meta) != 176422 or weight.nnz != 25862574:
                    raise ValueError('Le cache ne correspond pas au connectome MaleCNS complet attendu.')
                if not np.isfinite(weight.data).all():
                    raise ValueError('Poids neuronaux invalides.')
                self.groups = {
                    name+'_'+side: np.flatnonzero(meta.type.isin(types) & (meta.somaSide == side))
                    for name, types in [('vision', ['LPLC2']), ('motor', ['DNa02', 'DNg13'])]
                    for side in ('L', 'R')
                }
                if any(len(group) == 0 for group in self.groups.values()):
                    raise ValueError('Populations sensorielles ou motrices absentes.')
                self.np = np
                self.labels = meta['type'].fillna('Non annoté').astype(str).to_numpy()
                self.body_ids = meta['bodyId'].astype(str).to_numpy()
                self.sides = meta['somaSide'].fillna('?').astype(str).to_numpy()
                weight.data.flags.writeable = False
                self.weight = weight
                self.x = np.zeros(weight.shape[0], np.float32)
                self.state = {**self.state, "status": "ready", "neurons": len(meta),
                              "edges": weight.nnz, "groups": {k: len(v) for k, v in self.groups.items()},
                              "memory_mb": round((weight.data.nbytes + weight.indices.nbytes + weight.indptr.nbytes)/1024**2, 1)}
                self.state = {**self.state, **self._activity_view()}
            except Exception as exc:
                self.weight = None
                self.state = {**self.state, "status": "error", "error": str(exc)}
            return self.snapshot()

    def reset(self):
        with self.lock:
            if self.weight is not None:
                self.x.fill(0)
            self.state = {**self.state, "status": "ready" if self.weight is not None else "unloaded", "steps": 0, "activity": 0.0, "speed": 0.0,
                          "turn": 0.0, "left": 0, "right": 0, "motor_L": 0.0, "motor_R": 0.0,
                          "vision_L": 0.0, "vision_R": 0.0, "guard": False,
                          "compute_ms": 0.0, "error": None}
            if self.weight is not None:
                self.state = {**self.state, **self._activity_view()}

    def _activity_view(self):
        """Valeurs réelles et identifiants, sans inventer de positions anatomiques."""
        np = self.np
        magnitude = np.abs(self.x)
        count = min(12, len(self.x))
        indices = np.argpartition(magnitude, -count)[-count:]
        indices = indices[np.argsort(-magnitude[indices], kind='stable')]

        def neuron(index):
            i = int(index)
            return {"id": str(self.body_ids[i]) if hasattr(self, 'body_ids') else str(i),
                    "type": str(self.labels[i]) if hasattr(self, 'labels') else 'Test',
                    "side": str(self.sides[i]) if hasattr(self, 'sides') else '?',
                    "value": round(float(self.x[i]), 5)}

        return {"active_count": int(np.count_nonzero(magnitude >= .05)),
                "sensory": {side: [neuron(i) for i in self.groups['vision_'+side]] for side in ('L', 'R')},
                "motor_neurons": [neuron(i) for side in ('L', 'R') for i in self.groups['motor_'+side]],
                "top_neurons": [neuron(i) for i in indices if magnitude[i] >= .00001]}

    def probe(self, sensors, steps=32):
        # État indépendant : un test ne modifie jamais l'activité pilotant le robot.
        with self.lock:
            if self.weight is None:
                raise RuntimeError('Charger le connectome avant une stimulation.')
            simulation = FlyBrain(self.directory)
            for name in ('np', 'weight', 'groups', 'labels', 'body_ids', 'sides'):
                if hasattr(self, name):
                    setattr(simulation, name, getattr(self, name))
            simulation.x = self.np.zeros_like(self.x)
            simulation.state = {**self.state, "steps": 0}
        return [simulation.tick(sensors) for _ in range(steps)]

    def tick(self, sensors):
        with self.lock:
            if self.weight is None:
                raise RuntimeError('Le connectome doit être chargé avant de démarrer.')
            started = time.monotonic()
            np = self.np
            # Une détection frontale stimule les deux côtés ; l'arrière n'a pas
            # de correspondance visuelle ajoutée. Les capteurs restent binaires.
            left = 4.0 if sensors['left'] or sensors['front'] else 0.0
            right = 4.0 if sensors['right'] or sensors['front'] else 0.0
            current = np.zeros_like(self.x)
            current[self.groups['vision_L']] = left
            current[self.groups['vision_R']] = right
            self.x = (.7 * self.x + .3 * np.tanh(self.weight @ self.x + current)).astype(np.float32)
            if not np.isfinite(self.x).all():
                raise ValueError('Activité neuronale non finie ; mouvement arrêté.')
            l, r = self.x[self.groups['motor_L']], self.x[self.groups['motor_R']]
            speed = float(3 * (np.abs(l).mean() + np.abs(r).mean()) / 2)
            turn = float(np.clip(3 * (l.mean() - r.mean()), -2, 2))
            # Gains conventionnels : 3 unités -> 45 % ; 2 rad/unités -> 40 %.
            forward, rotation = speed * 15, turn * 20
            guard = bool(sensors['front'] and forward > 0)
            if guard:
                forward = 0  # Supprime l'avance, conserve la rotation neuronale.
            wheels = [int(round(np.clip(v, -45, 45))) for v in (forward-rotation, forward+rotation)]
            wheels = [v if abs(v) >= 15 else 0 for v in wheels]
            self.state = {**self.state, "steps": self.state['steps']+1,
                          "activity": float(np.abs(self.x).mean()),
                          "vision_L": left, "vision_R": right,
                          "motor_L": float(l.mean()), "motor_R": float(r.mean()),
                          "speed": speed, "turn": turn, "left": wheels[0], "right": wheels[1],
                          "guard": guard, "compute_ms": round((time.monotonic()-started)*1000, 2)}
            self.state = {**self.state, **self._activity_view()}
            return self.snapshot()
