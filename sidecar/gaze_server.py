"""Modo Mirada: publica la mirada por TCP para el frontend Flutter.

Reutiliza los modulos locales del sidecar (los mismos que usa main.py en modo
Mouse) y, en vez de mover el cursor del sistema, emite la mirada ya mapeada a
pantalla como lineas JSON sobre un socket TCP local:

    {"x": 0.42, "y": 0.71, "blink": false}\n

x/y son fraccion de pantalla [0..1] (lo que devuelve GazeMapper.transform). El
frontend Flutter (GazeBridge, lib/services/gaze_bridge.dart) se conecta a
127.0.0.1:8765, consume ese flujo y muestra el chip "Mirada". El cursor del SO
queda libre (a diferencia del modo Mouse).

Uso:
    # 1) Calibrar una vez (genera calibration.json en este directorio):
    .venv/Scripts/python.exe main.py --calibrate
    # 2) Levantar el server (antes de abrir la app Flutter):
    .venv/Scripts/python.exe gaze_server.py

Requiere las mismas dependencias que el tracker (mediapipe, opencv, numpy) y una
calibracion previa. Detener con Ctrl+C.
"""
import json
import socket
import time

import config
from blink_detector import BlinkDetector
from calibration import GazeMapper, load_calibration
from eye_tracker import EyeTracker, feature_vector
from smoothing import GazeSmoother2D

HOST = "127.0.0.1"
PORT = 8765


def _bootstrap():
    """Carga la calibracion y prepara camara + tracker (una sola vez)."""
    saved = load_calibration()
    if not saved:
        raise SystemExit(
            "No hay calibracion. Corre: python main.py --calibrate"
        )
    mapper = GazeMapper.from_dict(saved["gaze"])
    config.BLINK_THRESHOLD = saved.get("blink_threshold", config.BLINK_THRESHOLD)

    cap = config.open_camera()
    if not cap.isOpened():
        raise SystemExit("ERROR: webcam no disponible")
    for _ in range(15):          # descartar frames iniciales (autoexposicion)
        cap.read()

    return {"cap": cap, "tracker": EyeTracker(), "mapper": mapper}


def _stream(conn, ctx):
    """Loop por conexion: mirada -> JSON. Mismo criterio que main.py:run_mouse
    (parpadeo = clic; con el ojo cerrado se mantiene la ultima posicion)."""
    cap, tracker, mapper = ctx["cap"], ctx["tracker"], ctx["mapper"]
    blink = BlinkDetector(threshold=config.BLINK_THRESHOLD)
    smoother = GazeSmoother2D(mincutoff=0.5, beta=0.008)

    ts = 0
    last_x, last_y = 0.5, 0.5     # centro hasta tener una muestra valida
    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        ts += 33
        res = tracker.process(frame, ts)
        if res is None:
            continue

        # El parpadeo se evalua siempre (dispara el "clic" en Flutter).
        openness = (res.right.openness + res.left.openness) / 2
        blinked = blink.detect(openness)

        # La mirada solo es valida con el ojo abierto: si esta (casi) cerrado se
        # mantiene la ultima posicion para que el parpadeo no dispare el punto.
        if openness >= config.OPEN_GAZE_THRESHOLD:
            gx, gy = mapper.transform(feature_vector(res))
            last_x, last_y = smoother.update(gx, gy, time.time())

        payload = {
            "x": round(float(last_x), 4),
            "y": round(float(last_y), 4),
            "blink": bool(blinked),
        }
        conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))


def main():
    ctx = _bootstrap()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, PORT))
            server.listen(1)
            print(f"[gaze_server] escuchando en {HOST}:{PORT} - esperando a Flutter...")

            while True:
                conn, addr = server.accept()
                print(f"[gaze_server] cliente conectado: {addr}")
                try:
                    with conn:
                        _stream(conn, ctx)
                except (ConnectionResetError, BrokenPipeError, OSError):
                    print("[gaze_server] cliente desconectado.")
                finally:
                    print("[gaze_server] esperando nueva conexion...")
    except KeyboardInterrupt:
        print("\n[gaze_server] detenido.")
    finally:
        ctx["cap"].release()
        ctx["tracker"].close()


if __name__ == "__main__":
    main()
