#!/usr/bin/env python3
"""Installation commune macOS, Linux/Raspberry Pi et Windows (Python 3.11+)."""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def detect_host():
    system = platform.system()
    raspberry = False
    model_file = Path("/proc/device-tree/model")
    if system == "Linux" and model_file.exists():
        raspberry = "raspberry" in model_file.read_text(errors="replace").lower()
    return {"system": system, "architecture": platform.machine(), "raspberry_pi": raspberry,
            "name": platform.node(), "ollama_recommendation": "native" if system in ("Darwin", "Windows") else "managed"}


def main():
    if sys.version_info < (3, 11):
        sys.exit("Python 3.11 ou plus récent est nécessaire.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Diagnostic sans installation ni modification")
    parser.add_argument("--ollama", action="store_true", help="Installer/démarrer le conteneur Ollama géré après le dashboard")
    args = parser.parse_args()
    host = detect_host()
    print(f"Machine : {host['system']} / {host['architecture']}" + (" / Raspberry Pi" if host['raspberry_pi'] else ""))
    print("Ollama conseillé : " + ("application native (GPU si compatible)" if host["ollama_recommendation"] == "native" else "conteneur géré par ElioBot"))
    if host["architecture"].lower() in ("armv7l", "armv6l", "i386", "i686"):
        sys.exit("Un système 64 bits est nécessaire pour cette installation.")
    if not shutil.which("docker"):
        sys.exit("Installer Docker Desktop sur Mac/Windows ou Docker Engine + Compose sur Linux, puis relancer. https://docs.docker.com/get-started/get-docker/")
    for command in (["docker", "compose", "version"], ["docker", "info", "--format", "{{.OSType}}"]):
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            sys.exit("Docker ou Compose est indisponible. Démarrer Docker et vérifier les droits de votre compte.")
        if command[1] == "info" and result.stdout.strip() != "linux":
            sys.exit("Configurer Docker Desktop pour utiliser des conteneurs Linux.")
    print("Docker et Compose : disponibles.")
    if args.check:
        return
    runtime = ROOT / "assistant-runtime"
    runtime.mkdir(mode=0o700, exist_ok=True)
    (runtime / "host.json").write_text(json.dumps(host, indent=2), encoding="utf-8")
    # Compose lit le .env existant ; ne jamais le réécrire ni afficher ses valeurs.
    result = subprocess.run(["docker", "compose", "up", "-d", "--build"], cwd=ROOT)
    if result.returncode:
        sys.exit(result.returncode)
    if args.ollama:
        print("Téléchargement de l’image Ollama ; les modèles seront choisis dans le dashboard.")
        # Appel local dans le gestionnaire : pas d'exposition de son jeton à la console.
        code = "import urllib.request,pathlib; token=pathlib.Path('/run/elio/manager-token').read_text().strip(); req=urllib.request.Request('http://localhost:8090/start',data=b'{\"gpu\":\"cpu\"}',headers={'Content-Type':'application/json','Authorization':'Bearer '+token}); print(urllib.request.urlopen(req,timeout=300).read().decode())"
        subprocess.run(["docker", "compose", "exec", "-T", "ollama-manager", "python", "-c", code], cwd=ROOT, check=True)
    print("Dashboard : http://localhost:8000 — ouvrir « Assistant ElioBot ».")
    print("Depuis un autre appareil, remplacer localhost par l’adresse réseau de cette machine.")


if __name__ == "__main__":
    main()
