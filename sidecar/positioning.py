"""Vista de posicion previa a la calibracion.

Muestra la camara en espejo con un ovalo guia y cinco comprobaciones en vivo
(rostro, distancia, centrado, cabeza derecha e iluminacion). Cuando todas se
cumplen durante HOLD_S segundos, la calibracion continua sola. El acompanante
puede pulsar Enter para continuar igual o Esc para cancelar.

La distancia es una ESTIMACION: usa la distancia media entre pupilas de un
adulto (IPD_MM) y el campo de vision horizontal tipico de una webcam
(CAMERA_HFOV_DEG). Puede variar unos centimetros entre personas y camaras.
"""
import math
import time
from dataclasses import dataclass

import cv2
import numpy as np

import config

try:  # Texto con tildes; si no hay Pillow o fuente, se usa texto sin tildes.
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None

# Rangos objetivo (mismos que el manual de usuario y el paper).
DISTANCE_CM = (50.0, 70.0)
IPD_MM = 63.0                # distancia media entre pupilas en adultos
CAMERA_HFOV_DEG = 60.0       # campo de vision horizontal tipico de una webcam
CENTER_X_TOL = 0.12          # desvio horizontal permitido del centro (fraccion)
CENTER_Y = (0.28, 0.60)      # rango vertical permitido del punto entre los ojos
MAX_ROLL_DEG = 10.0          # inclinacion lateral de la cabeza
MAX_YAW_RATIO = 0.18         # nariz desplazada respecto de los ojos (giro)
BRIGHTNESS = (60.0, 210.0)   # brillo medio del rostro (0-255)
HOLD_S = 2.0                 # tiempo con todo correcto antes de continuar
SMOOTHING = 0.7              # suavizado de la distancia mostrada

KEY_ENTER = (10, 13)
KEY_ESC = 27


@dataclass
class Check:
    key: str
    label: str
    ok: bool
    detail: str


def estimate_distance_cm(ipd_px, frame_width,
                         hfov_deg=CAMERA_HFOV_DEG, ipd_mm=IPD_MM):
    """Distancia ojos-camara aproximada con el modelo de camara estenopeica.

    Supone la cabeza de frente; la comprobacion "Cabeza derecha" limita el giro.
    """
    if ipd_px <= 0:
        return None
    focal_px = (frame_width / 2) / math.tan(math.radians(hfov_deg / 2))
    return ipd_mm * focal_px / ipd_px / 10


def assess(geometry, distance_cm=None):
    """Comprobaciones de postura. `geometry` es None si no se detecta rostro."""
    if geometry is None:
        return [Check("face", "Rostro detectado", False,
                      "No se ve su rostro: mire hacia la cámara")]
    w, _ = geometry.frame_size
    if distance_cm is None:
        distance_cm = estimate_distance_cm(geometry.ipd_px, w)
    checks = [Check("face", "Rostro detectado", True, "Bien")]

    lo, hi = DISTANCE_CM
    if distance_cm is None:
        checks.append(Check("distance", "Distancia", False, "No se puede estimar"))
    elif distance_cm < lo:
        checks.append(Check("distance", "Distancia", False,
                            f"≈ {distance_cm:.0f} cm: aléjese un poco (meta {lo:.0f}-{hi:.0f} cm)"))
    elif distance_cm > hi:
        checks.append(Check("distance", "Distancia", False,
                            f"≈ {distance_cm:.0f} cm: acérquese un poco (meta {lo:.0f}-{hi:.0f} cm)"))
    else:
        checks.append(Check("distance", "Distancia", True, f"≈ {distance_cm:.0f} cm"))

    # Instrucciones en espejo: lo que la persona ve es su reflejo.
    mx = 1 - geometry.eye_mid[0]
    my = geometry.eye_mid[1]
    if mx < 0.5 - CENTER_X_TOL:
        hint = "Muévase un poco hacia su derecha"
    elif mx > 0.5 + CENTER_X_TOL:
        hint = "Muévase un poco hacia su izquierda"
    elif my < CENTER_Y[0]:
        hint = "Su rostro está muy arriba: baje un poco"
    elif my > CENTER_Y[1]:
        hint = "Su rostro está muy abajo: suba un poco"
    else:
        hint = None
    checks.append(Check("center", "Centrado", hint is None, hint or "Bien"))

    if abs(geometry.roll_deg) > MAX_ROLL_DEG:
        checks.append(Check("head", "Cabeza derecha", False, "Enderece la cabeza"))
    elif abs(geometry.yaw_ratio) > MAX_YAW_RATIO:
        checks.append(Check("head", "Cabeza derecha", False,
                            "Gire la cara de frente a la pantalla"))
    else:
        checks.append(Check("head", "Cabeza derecha", True, "Bien"))

    b = geometry.brightness
    if b < BRIGHTNESS[0]:
        checks.append(Check("light", "Iluminación", False,
                            "Poca luz en el rostro: encienda una luz frente a usted"))
    elif b > BRIGHTNESS[1]:
        checks.append(Check("light", "Iluminación", False,
                            "Demasiada luz: evite luz directa sobre la cara"))
    else:
        checks.append(Check("light", "Iluminación", True, "Bien"))
    return checks


# ---------------------------------------------------------------- dibujo ----

def _font(size, bold=False):
    if Image is None:
        return None
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return None


_FONTS = {}


def _text(canvas, items):
    """Dibuja [(texto, (x, y), tam, color_bgr, negrita)] con tildes si es posible."""
    font_ok = Image is not None and _font(20) is not None
    if not font_ok:
        for text, (x, y), size, color, _ in items:
            ascii_text = text.encode("ascii", "replace").decode()
            cv2.putText(canvas, ascii_text, (x, y + size), cv2.FONT_HERSHEY_SIMPLEX,
                        size / 32, color, 2)
        return canvas
    img = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img)
    for text, (x, y), size, color, bold in items:
        key = (size, bold)
        if key not in _FONTS:
            _FONTS[key] = _font(size, bold)
        draw.text((x, y), text, font=_FONTS[key], fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


GREEN, RED, WHITE, GREY = (90, 200, 90), (80, 80, 230), (235, 235, 235), (160, 160, 160)


def _render(frame, geometry, checks, hold):
    W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    canvas = np.zeros((H, W, 3), np.uint8)
    all_ok = all(c.ok for c in checks) and len(checks) == 5

    # Vista previa en espejo, a la izquierda.
    view = cv2.flip(frame, 1)
    fh, fw = view.shape[:2]
    scale = min(W * 0.55 / fw, H * 0.75 / fh)
    vw, vh = int(fw * scale), int(fh * scale)
    view = cv2.resize(view, (vw, vh))
    ox, oy = int(W * 0.04), (H - vh) // 2
    canvas[oy:oy + vh, ox:ox + vw] = view

    # Ovalo guia (zona del rostro a la distancia correcta).
    color = GREEN if all_ok else WHITE
    centre = (ox + vw // 2, oy + int(vh * 0.47))
    axes = (int(vw * 0.17), int(vh * 0.30))
    cv2.ellipse(canvas, centre, axes, 0, 0, 360, color, 3, cv2.LINE_AA)
    if geometry is not None:
        ex = ox + int((1 - geometry.eye_mid[0]) * vw)
        ey = oy + int(geometry.eye_mid[1] * vh)
        cv2.circle(canvas, (ex, ey), 9, GREEN if all_ok else RED, -1, cv2.LINE_AA)

    # Panel de comprobaciones, a la derecha.
    px = ox + vw + int(W * 0.04)
    items = [("Ajuste su posición", (px, oy), 46, WHITE, True),
             ("Antes de calibrar, ubíquese dentro del óvalo.", (px, oy + 66), 26, GREY, False)]
    y = oy + 130
    marks = []
    for c in checks:
        items.append((c.label, (px + 48, y), 34, GREEN if c.ok else RED, True))
        items.append((c.detail, (px + 48, y + 44), 26, WHITE, False))
        marks.append((px + 16, y + 24, c.ok))
        y += 100
    if all_ok:
        items.append(("¡Muy bien! Mantenga esta posición…", (px, y + 10), 30, GREEN, True))
    items.append(("Acompañante: Enter = continuar igual   ·   Esc = cancelar",
                  (px, oy + vh - 30), 22, GREY, False))
    canvas = _text(canvas, items)
    for mx, my, ok in marks:  # visto bueno o cruz, dibujados (no dependen de la fuente)
        cv2.circle(canvas, (mx, my), 16, GREEN if ok else RED, -1, cv2.LINE_AA)
        if ok:
            pts = np.array([(mx - 8, my), (mx - 2, my + 6), (mx + 8, my - 6)], np.int32)
            cv2.polylines(canvas, [pts], False, (0, 0, 0), 3, cv2.LINE_AA)
        else:
            cv2.line(canvas, (mx - 6, my - 6), (mx + 6, my + 6), (0, 0, 0), 3, cv2.LINE_AA)
            cv2.line(canvas, (mx - 6, my + 6), (mx + 6, my - 6), (0, 0, 0), 3, cv2.LINE_AA)

    # Barra de espera antes de continuar.
    if hold > 0:
        bar_w = int((W - px - int(W * 0.05)) * min(hold / HOLD_S, 1))
        cv2.rectangle(canvas, (px, y + 60), (px + bar_w, y + 74), GREEN, -1)
    return canvas


def run_positioning(cap, tracker, ts0, window):
    """Bucle de la vista de posicion. Devuelve (resumen, ts).

    Lanza InterruptedError con Esc o al cerrar la ventana.
    """
    ts = ts0
    started = time.time()
    good_since = None
    distance = None
    while True:
        ok, frame = cap.read()
        if not ok:
            key = cv2.waitKey(30) & 0xff
            if key == KEY_ESC:
                raise InterruptedError("Calibracion cancelada")
            continue
        ts += 33
        res = tracker.process(frame, ts)
        geometry = None if res is None else res.geometry
        if geometry is not None:
            raw = estimate_distance_cm(geometry.ipd_px, geometry.frame_size[0])
            if raw is not None:
                distance = raw if distance is None else SMOOTHING * distance + (1 - SMOOTHING) * raw
        checks = assess(geometry, distance if geometry is not None else None)
        all_ok = len(checks) == 5 and all(c.ok for c in checks)
        now = time.time()
        if all_ok:
            good_since = good_since or now
        else:
            good_since = None
        hold = now - good_since if good_since else 0.0
        cv2.imshow(window, _render(frame, geometry, checks, hold))
        key = cv2.waitKey(1) & 0xff
        if key == KEY_ESC or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
            raise InterruptedError("Calibracion cancelada")
        forced = key in KEY_ENTER
        if hold >= HOLD_S or forced:
            return {
                "distance_cm": None if distance is None else round(distance, 1),
                "all_checks_ok": all_ok,
                "forced_by_companion": bool(forced and not all_ok),
                "failed_checks": [c.key for c in checks if not c.ok],
                "seconds": round(now - started, 1),
            }, ts
