"""Sidecar de rastreo ocular para el frontend Flutter.

Reutiliza el tracker Python existente (repo InteractorGate) y publica la mirada
ya mapeada a pantalla como líneas JSON sobre un socket TCP local:

    {"x": 0.42, "y": 0.71, "blink": false}\n

x/y son fracción de pantalla [0..1]. El frontend Flutter (GazeBridge) se conecta
a 127.0.0.1:8765 y consume ese flujo.

Uso:
    # 1) Ten una calibración hecha en el repo del tracker (python main.py --calibrate)
    # 2) Ejecuta este sidecar apuntando a ese repo:
    set IG_TRACKER_REPO=C:\\Users\\LIAN\\Documents\\InteractorGate
    python sidecar/gaze_server.py

Requiere las mismas dependencias que el tracker (mediapipe, opencv, numpy).
"""

import json
import os
import socket
import sys

HOST = "127.0.0.1"
PORT = 8765

# Ruta al repo del tracker Python. Ajusta por env var IG_TRACKER_REPO si difiere.
TRACKER_REPO = os.environ.get(
    "IG_TRACKER_REPO",
    r"C:\Users\LIAN\Documents\InteractorGate",
)


def _bootstrap_tracker():
    """Carga el tracker existente y la calibración guardada."""
    if not os.path.isdir(TRACKER_REPO):
        raise SystemExit(f"No existe el repo del tracker: {TRACKER_REPO}")

    sys.path.insert(0, TRACKER_REPO)
    # La calibración se guarda con ruta relativa; trabajar desde el repo.
    os.chdir(TRACKER_REPO)

    import calibration
    import config
    from camera import Camera
    from eye_tracker import EyeTracker
    from blink_detector import BlinkDetector

    saved = calibration.load_calibration()
    if saved is None:
        raise SystemExit(
            "No hay calibración. Corre 'python main.py --calibrate' en el tracker."
        )

    mapper = calibration.GazeMapper.from_dict(saved["gaze"])
    config.BLINK_THRESHOLD = saved.get("blink_threshold", config.BLINK_THRESHOLD)

    return {
        "config": config,
        "camera": Camera(),
        "tracker": EyeTracker(),
        "blink": BlinkDetector(),
        "mapper": mapper,
    }


def _stream(conn, ctx):
    config = ctx["config"]
    camera = ctx["camera"]
    tracker = ctx["tracker"]
    blink = ctx["blink"]
    mapper = ctx["mapper"]

    while True:
        frame = camera.get_frame()
        if frame is None:
            break

        raw = tracker.get_raw_gaze(frame)
        if raw is None:
            continue

        sx, sy = mapper.transform(raw.norm_x, raw.norm_y, raw.yaw, raw.pitch)
        blinked = blink.detect(raw.eye_ratio)

        payload = {
            "x": round(sx / config.SCREEN_WIDTH, 4),
            "y": round(sy / config.SCREEN_HEIGHT, 4),
            "blink": bool(blinked),
        }
        conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))


def main():
    ctx = _bootstrap_tracker()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(1)
        print(f"[gaze_server] escuchando en {HOST}:{PORT} — esperando a Flutter…")

        while True:
            conn, addr = server.accept()
            print(f"[gaze_server] cliente conectado: {addr}")
            try:
                with conn:
                    _stream(conn, ctx)
            except (ConnectionResetError, BrokenPipeError):
                print("[gaze_server] cliente desconectado.")
            finally:
                print("[gaze_server] esperando nueva conexión…")

    # Nunca se alcanza; el tracker libera la cámara al terminar el proceso.


if __name__ == "__main__":
    main()
