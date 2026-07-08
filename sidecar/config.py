"""Constantes compartidas del tracker (referenciadas por gaze_server.py)."""
import ctypes
import os
import sys

import cv2

_HERE = os.path.dirname(__file__)


def _user_data_dir():
    """Carpeta escribible por usuario para datos de la app (calibracion).

    Empaquetado (PyInstaller) el sidecar corre desde Program Files, que es de
    solo lectura; la calibracion debe ir a %LOCALAPPDATA%\\InteractorGate.
    En desarrollo se usa el propio directorio del sidecar.
    """
    if getattr(sys, "frozen", False):
        base = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "InteractorGate",
        )
        os.makedirs(base, exist_ok=True)
        return base
    return _HERE


def _screen_size():
    """Resolucion real de la pantalla en Windows (con conciencia de DPI)."""
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        u = ctypes.windll.user32
        return int(u.GetSystemMetrics(0)), int(u.GetSystemMetrics(1))
    except Exception:
        return 1920, 1080


SCREEN_WIDTH, SCREEN_HEIGHT = _screen_size()

# Apertura del ojo por debajo de esto = ojo cerrado (parpadeo). Se ajusta con
# los datos reales durante la calibracion.
BLINK_THRESHOLD = 0.18

# Con apertura por debajo de esto NO se actualiza la mirada (ojo cerrado): se
# mantiene la ultima posicion para que un parpadeo no dispare el cursor.
OPEN_GAZE_THRESHOLD = 0.15

# Suavizado exponencial del punto de mirada (0=nada, ~0.6 estable, 1=congelado).
GAZE_SMOOTHING = 0.6

# Zona de trabajo de la mirada (fraccion de pantalla): una CAJA CENTRAL. La
# calibracion y el cursor operan dentro de ella, evitando los bordes (donde el
# vertical se satura y "no baja") y coincidiendo con la ventana reducida de la
# app. Coincide aprox. con una ventana ~900x640 centrada en 1920x1080.
WORK_X = (0.27, 0.73)
WORK_Y = (0.24, 0.80)

CALIB_FILE = os.path.join(_user_data_dir(), "calibration.json")
# Indice de la webcam. Puede cambiar si se reconecta la camara; overridable por
# env var IG_CAM_INDEX. (0 tipico; se reenumera a veces al reconectar.)
CAM_INDEX = int(os.environ.get("IG_CAM_INDEX", 0))

# Resolucion de captura. Un benchmark (resolucion x FPS x ruido de la senal)
# determino que 640x480 es optima: menor jitter (crudo, sin compresion MJPG) y
# mejor FPS. Mas resolucion NO ayuda (MediaPipe redimensiona internamente) y
# ademas baja FPS + agrega artefactos MJPG. Ver _res_benchmark.py.
CAP_WIDTH = 640
CAP_HEIGHT = 480


def open_camera(index=None):
    """Abre la webcam con la resolucion optima determinada por benchmark."""
    cap = cv2.VideoCapture(CAM_INDEX if index is None else index, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAP_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAP_HEIGHT)
    return cap
