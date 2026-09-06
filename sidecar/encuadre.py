"""Guia de encuadre: comprueba que la camara y la postura son las correctas.

Existe por lo que se midio el 2026-09-06: el mapeo de mirada apoya buena parte
de su peso en la posicion del iris DENTRO DEL ENCUADRE, asi que unos pocos
centimetros de cabeza valen cientos de pixeles de error en pantalla. Antes esa
condicion no se veia por ningun lado: se calibraba a ciegas y el fallo aparecia
en el benchmark, media hora despues.

Esta ventana la hace visible en tiempo real. Comprueba, y dice como corregir:

  1. Rostro detectado
  2. Cara centrada en el encuadre
  3. Altura de la camara (los ojos a la altura correcta del cuadro)
  4. Distancia a la pantalla
  5. Cabeza frontal (sin giro ni cabeceo)
  6. Luz suficiente y sin contraluz
  7. Encuadre estable (sin temblor)
  8. Postura igual a la de la calibracion guardada -- y cuanto error en
     pantalla cuesta la diferencia, calculado con los coeficientes de ESA
     calibracion, no con una constante inventada.

Uso:
    .venv/Scripts/python.exe encuadre.py
    .venv/Scripts/python.exe main.py --encuadre

    ESC o q  salir        s  guardar foto del encuadre actual como referencia
"""
import argparse
import statistics
import time
from collections import deque

import cv2
import numpy as np

import config
from calibration import load_calibration
from eye_tracker import EyeTracker, head_angles, head_translation

WINDOW = "Encuadre de camara - InteractorGate"

# ── Objetivos y tolerancias ──────────────────────────────────────────────────
# La cara, centrada en horizontal y con los ojos algo por encima del centro del
# cuadro: es el encuadre natural con la camara a la altura de los ojos.
OBJ_X, TOL_X = 0.50, 0.08          # fraccion del ancho del encuadre
OBJ_Y, TOL_Y = 0.45, 0.07          # fraccion del alto del encuadre
# Distancia entre pupilas en px del encuadre. Con una webcam tipica (~60 grados
# de campo horizontal) 70 px son unos 50 cm; el rango admitido es ~42-64 cm.
IPD_OBJ, IPD_MIN, IPD_MAX = 70.0, 55.0, 85.0
IPD_CM = 6.3                       # distancia interpupilar media de un adulto
FOCAL_PX = config.CAP_WIDTH / (2 * np.tan(np.radians(60) / 2))   # ~554 px
ANG_MAX = 10.0                     # grados de giro/cabeceo admitidos
LUZ_MIN, LUZ_MAX = 80, 215         # brillo medio de la zona de los ojos (0-255)
CONTRALUZ = 55                     # fondo mas brillante que la cara = contraluz
JITTER_MAX = 2.0                   # px de desviacion tipica del centro de ojos
VENTANA_JITTER = 45                # frames sobre los que se mide el temblor
ESTABLE_S = 1.5                    # tiempo en verde antes de dar el visto bueno

# Media celda del tablero (botones de 204x155 px): el margen de error que la
# app tolera antes de que la mirada caiga en la celda de al lado.
MARGEN_X_PX, MARGEN_Y_PX = 102.0, 77.0

# Indices del vector de features que dependen de donde esta la cabeza en el
# encuadre, y su posicion dentro de los regresores de cada eje (calibration.py).
X_IDX = [0, 2, 4, 6, 8]
Y_IDX = [1, 3, 5, 7, 9, 10, 11]
IRIS_X, IRIS_Y = {4, 6}, {5, 7}

VERDE, ROJO, AMBAR = (90, 220, 90), (70, 70, 235), (60, 190, 235)
GRIS, BLANCO = (140, 140, 140), (245, 245, 245)

# ── Lienzo ───────────────────────────────────────────────────────────────────
VID_W, VID_H = 720, 540
PANEL_W, MARGEN, TITULO = 450, 14, 46
LIENZO_W = VID_W + PANEL_W + 3 * MARGEN
LIENZO_H = VID_H + 2 * MARGEN + TITULO + 46      # el panel es mas alto que el video
ESCALA = VID_W / config.CAP_WIDTH


def referencia_calibracion():
    """Postura media de la calibracion guardada y su sensibilidad a moverse.

    Devuelve None si no hay calibracion o si es del formato viejo (sin muestras
    crudas): en ese caso no hay con que comparar y hay que recalibrar.
    """
    calib = load_calibration()
    if not calib or "gaze" not in calib:
        return None
    muestras = (calib.get("samples") or {}).get("head")
    if not muestras:
        return None
    h = np.array(muestras, dtype=np.float64)
    h = h[np.any(h != 0, axis=1)]           # descartar frames sin pose
    if not len(h):
        return None
    return {"head": h.mean(axis=0), "creada": calib.get("creada", "?"),
            "gaze": calib["gaze"]}


def sensibilidad_px_por_cm(gaze, px_por_cm):
    """Cuantos px de pantalla se mueve la estimacion por cada cm de cabeza.

    Sale de los propios coeficientes de la calibracion: el peso de las features
    de iris CRUDO dividido por su desviacion tipica (estan estandarizadas), y
    convertido de unidades de encuadre a centimetros con la escala que da la
    distancia interpupilar.
    """
    std = np.asarray(gaze["std"], dtype=np.float64)
    cx = np.asarray(gaze["coef_x"], dtype=np.float64)
    cy = np.asarray(gaze["coef_y"], dtype=np.float64)
    dx = sum(cx[j] / std[k] for j, k in enumerate(X_IDX) if k in IRIS_X)
    dy = sum(cy[j] / std[k] for j, k in enumerate(Y_IDX) if k in IRIS_Y)
    return (abs(dx) * px_por_cm / config.CAP_WIDTH * config.SCREEN_WIDTH,
            abs(dy) * px_por_cm / config.CAP_HEIGHT * config.SCREEN_HEIGHT)


def medir(res, gris, historial):
    """Metricas de encuadre a partir de un FaceResult y el frame en gris."""
    r, l = res.right, res.left
    cx = (r.iris[0] + l.iris[0]) / 2
    cy = (r.iris[1] + l.iris[1]) / 2
    ipd = abs(r.iris[0] - l.iris[0]) * config.CAP_WIDTH
    yaw, pitch = head_angles(res.pose_matrix)
    cara = float((r.patch.mean() + l.patch.mean()) / 2)
    historial.append((cx * config.CAP_WIDTH, cy * config.CAP_HEIGHT))
    jitter = None
    if len(historial) >= 10:
        jitter = max(statistics.pstdev([p[0] for p in historial]),
                     statistics.pstdev([p[1] for p in historial]))
    return {
        "cx": cx, "cy": cy, "ipd": ipd,
        "dist_cm": IPD_CM * FOCAL_PX / ipd if ipd > 1 else float("inf"),
        "px_por_cm": ipd / IPD_CM if ipd > 1 else 0.0,
        "yaw": np.degrees(yaw), "pitch": np.degrees(pitch),
        "luz_cara": cara, "luz_fondo": float(gris.mean()),
        "jitter": jitter, "head": np.array(head_translation(res.pose_matrix)),
    }


def evaluar(m, ref):
    """Lista de comprobaciones: (etiqueta, ok, valor, que hacer si falla)."""
    checks = []

    dx = m["cx"] - OBJ_X
    checks.append(("Cara centrada", abs(dx) <= TOL_X,
                   f"{dx * 100:+.0f} % del ancho",
                   "Muevete hasta centrar la cara en el recuadro"))

    dy = m["cy"] - OBJ_Y
    ok_y = abs(dy) <= TOL_Y
    accion = ("BAJA la camara (o sube tu silla)" if dy > 0
              else "SUBE la camara (o baja tu silla)")
    checks.append(("Altura de camara", ok_y, f"ojos a {m['cy'] * 100:.0f} % del alto",
                   accion + ": los ojos deben quedar en la linea"))

    ok_d = IPD_MIN <= m["ipd"] <= IPD_MAX
    accion = "ALEJATE de la pantalla" if m["ipd"] > IPD_MAX else "ACERCATE a la pantalla"
    checks.append(("Distancia", ok_d, f"~{m['dist_cm']:.0f} cm", accion))

    ok_a = abs(m["yaw"]) <= ANG_MAX and abs(m["pitch"]) <= ANG_MAX
    checks.append(("Cabeza frontal", ok_a,
                   f"giro {m['yaw']:+.0f}, cabeceo {m['pitch']:+.0f} grados",
                   "Mira de frente a la camara, sin girar ni inclinar la cabeza"))

    ok_luz = LUZ_MIN <= m["luz_cara"] <= LUZ_MAX
    contraluz = m["luz_fondo"] - m["luz_cara"] > CONTRALUZ
    accion = ("Quita la luz de detras (contraluz)" if contraluz else
              "Mas luz sobre la cara" if m["luz_cara"] < LUZ_MIN else
              "Menos luz directa: la cara esta quemada")
    checks.append(("Luz", ok_luz and not contraluz,
                   f"cara {m['luz_cara']:.0f} / fondo {m['luz_fondo']:.0f}", accion))

    j = m["jitter"]
    checks.append(("Encuadre estable", j is not None and j <= JITTER_MAX,
                   "midiendo..." if j is None else f"{j:.1f} px de temblor",
                   "Apoya la camara en algo fijo y quedate quieto"))

    if ref is None:
        checks.append(("Postura de calibracion", None, "sin referencia",
                       "Recalibra: la calibracion guardada es del formato viejo"))
        return checks, None

    d = m["head"] - ref["head"]
    sx, sy = sensibilidad_px_por_cm(ref["gaze"], m["px_por_cm"])
    err_x, err_y = abs(d[0]) * sx, abs(d[1]) * sy
    ok_p = err_x <= MARGEN_X_PX and err_y <= MARGEN_Y_PX
    checks.append((
        "Postura de calibracion", ok_p,
        f"{np.linalg.norm(d[:2]):.1f} cm -> {err_x:.0f} px X, {err_y:.0f} px Y",
        "Vuelve a la postura con la que calibraste (o recalibra aqui mismo)"))
    margen = {"sx": sx, "sy": sy, "d": d, "err": (err_x, err_y),
              "margen_cm_x": MARGEN_X_PX / sx if sx > 1e-6 else float("inf"),
              "margen_cm_y": MARGEN_Y_PX / sy if sy > 1e-6 else float("inf")}
    return checks, margen


# ── Dibujo ───────────────────────────────────────────────────────────────────
def _texto(img, txt, org, escala=0.5, color=BLANCO, grosor=1):
    cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, escala, color, grosor,
                cv2.LINE_AA)


def _guias(vid):
    """Recuadro objetivo de la cara y linea de los ojos."""
    ancho = int(2.4 * IPD_OBJ * ESCALA)
    alto = int(ancho * 1.30)
    cx, cy = int(OBJ_X * VID_W), int(OBJ_Y * VID_H)
    cv2.rectangle(vid, (cx - ancho // 2, cy - int(alto * 0.42)),
                  (cx + ancho // 2, cy + int(alto * 0.58)), (90, 90, 90), 1)
    for x in range(20, VID_W - 20, 26):        # linea de ojos, discontinua
        cv2.line(vid, (x, cy), (x + 13, cy), (110, 110, 110), 1)
    _texto(vid, "linea de los ojos", (24, cy - 10), 0.45, (110, 110, 110))


def _dibuja_cara(vid, m, todo_ok):
    """Ojos, eje entre pupilas y flecha hacia el objetivo (vista en espejo)."""
    color = VERDE if todo_ok else AMBAR
    ex = int((1 - m["cx"]) * VID_W)            # espejo: se ve como un espejo
    ey = int(m["cy"] * VID_H)
    semi = int(m["ipd"] * ESCALA / 2)
    cv2.line(vid, (ex - semi, ey), (ex + semi, ey), color, 2)
    for s in (-1, 1):
        cv2.circle(vid, (ex + s * semi, ey), 5, color, -1)
    tx, ty = int((1 - OBJ_X) * VID_W), int(OBJ_Y * VID_H)
    if abs(m["cx"] - OBJ_X) > TOL_X or abs(m["cy"] - OBJ_Y) > TOL_Y:
        cv2.arrowedLine(vid, (ex, ey), (tx, ty), AMBAR, 2, tipLength=0.25)


def pinta(frame, m, checks, margen, ref, ok_desde):
    lienzo = np.full((LIENZO_H, LIENZO_W, 3), 26, np.uint8)
    vid = cv2.resize(frame, (VID_W, VID_H))
    vid = cv2.flip(vid, 1)
    _guias(vid)

    reales = [c for c in checks if c[1] is not None]
    todo_ok = bool(reales) and all(c[1] for c in reales)
    if m is not None:
        _dibuja_cara(vid, m, todo_ok)
    lienzo[TITULO + MARGEN:TITULO + MARGEN + VID_H, MARGEN:MARGEN + VID_W] = vid

    # Titulo / veredicto.
    if m is None:
        _texto(lienzo, "No se detecta ningun rostro", (MARGEN, 32), 0.8, ROJO, 2)
    elif todo_ok and ok_desde and time.time() - ok_desde >= ESTABLE_S:
        _texto(lienzo, "ENCUADRE CORRECTO - listo para calibrar",
               (MARGEN, 32), 0.8, VERDE, 2)
    else:
        fallo = next((c for c in checks if c[1] is False), None)
        _texto(lienzo, fallo[3] if fallo else "Ajustando...",
               (MARGEN, 32), 0.7, AMBAR, 2)

    # Panel de comprobaciones.
    x0 = 2 * MARGEN + VID_W
    y = TITULO + MARGEN + 24
    _texto(lienzo, "COMPROBACIONES", (x0, y), 0.55, GRIS)
    y += 12
    cv2.line(lienzo, (x0, y), (x0 + PANEL_W - MARGEN, y), (60, 60, 60), 1)
    y += 30
    for etiqueta, ok, valor, _ in checks:
        color = GRIS if ok is None else (VERDE if ok else ROJO)
        marca = " ?" if ok is None else ("OK" if ok else " X")
        _texto(lienzo, marca, (x0, y), 0.55, color, 2)
        _texto(lienzo, etiqueta, (x0 + 34, y), 0.52, BLANCO)
        _texto(lienzo, valor, (x0 + 34, y + 19), 0.45, GRIS)
        y += 42

    y += 6
    cv2.line(lienzo, (x0, y), (x0 + PANEL_W - MARGEN, y), (60, 60, 60), 1)
    y += 26
    if margen:
        _texto(lienzo, "COSTE DE MOVERSE (esta calibracion)", (x0, y), 0.5, GRIS)
        y += 24
        _texto(lienzo, f"{margen['sx']:.0f} px de pantalla por cm de cabeza (X)",
               (x0, y), 0.46, BLANCO); y += 20
        _texto(lienzo, f"{margen['sy']:.0f} px por cm en vertical (Y)",
               (x0, y), 0.46, BLANCO); y += 22
        _texto(lienzo, f"Margen antes de fallar de celda: "
                       f"{margen['margen_cm_x']:.1f} cm", (x0, y), 0.46, AMBAR)
        y += 24
        if ref:
            _texto(lienzo, f"Calibracion del {ref['creada'][:16]}", (x0, y), 0.42, GRIS)
            y += 20
    elif ref is None:
        _texto(lienzo, "Sin calibracion con muestras: no se puede", (x0, y), 0.45, GRIS)
        y += 18
        _texto(lienzo, "comparar la postura. Recalibra.", (x0, y), 0.45, GRIS)
        y += 24

    _texto(lienzo, "ESC salir    s  guardar foto de referencia",
           (x0, LIENZO_H - MARGEN - 6), 0.44, GRIS)
    return lienzo, todo_ok


def run_encuadre():
    cap = config.open_camera()
    if not cap.isOpened():
        print("ERROR: webcam no disponible")
        return 1
    for _ in range(15):
        cap.read()
    tracker = EyeTracker()
    ref = referencia_calibracion()
    if ref is None:
        print("Aviso: no hay calibracion con muestras de postura; la ultima "
              "comprobacion queda sin referencia.")
    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)

    historial = deque(maxlen=VENTANA_JITTER)
    ts, ok_desde, ultimo = 0, None, None
    print("Guia de encuadre abierta. ESC para salir.")
    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        ts += 33
        res = tracker.process(frame, ts)
        if res is None:
            historial.clear()
            m, checks, margen = None, [("Rostro detectado", False, "no",
                                        "Ponte frente a la camara")], None
        else:
            gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            m = medir(res, gris, historial)
            checks, margen = evaluar(m, ref)
            checks.insert(0, ("Rostro detectado", True, "si", ""))

        lienzo, todo_ok = pinta(frame, m, checks, margen, ref, ok_desde)
        ok_desde = (ok_desde or time.time()) if todo_ok else None
        ultimo = lienzo
        cv2.imshow(WINDOW, lienzo)
        k = cv2.waitKey(1) & 0xFF
        if k in (27, ord("q")):
            break
        if k == ord("s") and ultimo is not None:
            cv2.imwrite("encuadre_referencia.png", ultimo)
            print("Guardado sidecar/encuadre_referencia.png")

    cap.release()
    cv2.destroyAllWindows()
    tracker.close()
    return 0


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter
                            ).parse_args()
    run_encuadre()
