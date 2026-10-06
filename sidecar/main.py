"""Modo Mouse: controla el cursor del sistema con la mirada (+ clic al parpadear).

Usa la calibracion guardada. Mueve el cursor de Windows al punto de mirada
suavizado; un parpadeo hace clic izquierdo. Asi cualquier app (incluido el
tablero dwell de Flutter) responde a los ojos.

Uso:
    .venv/Scripts/python.exe main.py --encuadre      # guia de encuadre de camara
    .venv/Scripts/python.exe main.py --calibrate     # (re)calibrar
    .venv/Scripts/python.exe main.py                 # modo Mouse (45s por defecto)
    .venv/Scripts/python.exe main.py --duration 60   # duracion en segundos
    .venv/Scripts/python.exe main.py --no-click      # sin clic por parpadeo
"""
import argparse
import ctypes
import os
import threading
import time

import cv2

import config
from blink_detector import BlinkDetector
from calibration import GazeMapper, load_calibration, run_calibration
from encuadre import run_encuadre
from eye_tracker import EyeTracker, feature_vector
from smoothing import GazeSmoother2D

_user32 = ctypes.windll.user32


def _watch_parent(pid):
    """Termina este proceso en cuanto muere la app que lo lanzo.

    Es la segunda red contra el sidecar huerfano (la primera es el Job Object
    del runner de Windows): si la app se cierra, se cuelga o se mata desde el
    Administrador de tareas, el cursor deja de seguir la mirada al instante.
    os._exit corta tambien la calibracion a pantalla completa y libera la camara.
    """
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    k32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    SYNCHRONIZE, INFINITE = 0x00100000, 0xFFFFFFFF
    handle = k32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        os._exit(0)   # la app ya no existe

    def _wait():
        k32.WaitForSingleObject(handle, INFINITE)
        os._exit(0)

    threading.Thread(target=_wait, name="watch-parent", daemon=True).start()


def _click():
    _user32.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
    _user32.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP


def run_mouse(duration=45, click_on_blink=True):
    saved = load_calibration()
    if not saved:
        print("ERROR: no hay calibracion. Corre: python main.py --calibrate")
        return 1
    mapper = GazeMapper.from_dict(saved["gaze"])

    cap = config.open_camera()
    if not cap.isOpened():
        print("ERROR: webcam no disponible")
        return 1
    for _ in range(15):
        cap.read()
    tracker = EyeTracker()
    blink = BlinkDetector(threshold=config.BLINK_THRESHOLD)
    smoother = GazeSmoother2D(mincutoff=0.5, beta=0.008)
    W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT

    mode = "con clic por parpadeo" if click_on_blink else "SIN clic"
    limit = "sin limite (detener con Ctrl+C / TaskStop)" if duration <= 0 else f"por {duration}s"
    print(f"Modo Mouse activo ({mode}) {limit}. El cursor sigue tu mirada.")
    ts, clicks = 0, 0
    t0 = time.time()
    while duration <= 0 or time.time() - t0 < duration:
        ok, frame = cap.read()
        if not ok:
            continue
        ts += 33
        res = tracker.process(frame, ts)
        if res is None:
            continue
        # El parpadeo se evalua siempre (para el clic y para mantener el conteo).
        openness = (res.right.openness + res.left.openness) / 2
        if blink.detect(openness) and click_on_blink:
            _click()
            clicks += 1
        # Ojo cerrado: mantener la ultima posicion (no dejar que el parpadeo
        # dispare el cursor). La mirada solo es valida con el ojo abierto.
        if openness < config.OPEN_GAZE_THRESHOLD:
            continue
        gx, gy = mapper.transform(feature_vector(res))
        sx, sy = smoother.update(gx, gy, time.time())
        _user32.SetCursorPos(int(sx * W), int(sy * H))

    cap.release()
    tracker.close()
    print(f"Modo Mouse finalizado. Clics por parpadeo: {clicks}")
    return 0


def run_service(click_on_blink=True):
    """Modo servicio (lo lanza la app de escritorio): si no hay calibracion la
    ejecuta primero, y luego corre modo Mouse indefinidamente hasta que el
    proceso sea terminado (al cerrar la app)."""
    if not load_calibration():
        print("Sin calibracion: iniciando calibracion inicial...")
        if run_calibration() is None:
            print("ERROR: la calibracion no se completo.")
            return 1
    return run_mouse(duration=0, click_on_blink=click_on_blink)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Tracker de mirada InteractorGate")
    ap.add_argument("--encuadre", action="store_true",
                    help="guia de encuadre: comprueba camara y postura antes de calibrar")
    ap.add_argument("--calibrate", action="store_true", help="recalibrar y salir")
    ap.add_argument("--service", action="store_true",
                    help="modo servicio: calibra si hace falta y corre modo Mouse indefinido")
    ap.add_argument("--duration", type=int, default=45, help="segundos de modo Mouse")
    ap.add_argument("--no-click", action="store_true", help="desactivar clic por parpadeo")
    ap.add_argument("--parent-pid", type=int, default=0,
                    help="PID de la app; el tracker se apaga cuando ese proceso termina")
    args = ap.parse_args()
    if args.parent_pid:
        _watch_parent(args.parent_pid)
    if args.encuadre:
        run_encuadre()
    elif args.calibrate:
        run_calibration()
    elif args.service:
        run_service(click_on_blink=not args.no_click)
    else:
        run_mouse(duration=args.duration, click_on_blink=not args.no_click)
