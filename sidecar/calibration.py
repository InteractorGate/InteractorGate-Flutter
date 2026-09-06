"""Calibracion por usuario: aprende el mapeo mirada->pantalla.

`GazeMapper` estandariza el vector de features de mirada (iris en el marco del
propio ojo + distancia a la camara) y ajusta una regresion **ridge**
(regularizada) hacia el punto de pantalla normalizado [0..1]. Se calibra mirando
una rejilla 4x4 de puntos, presentados en orden aleatorio.

Uso:
    .venv/Scripts/python.exe calibration.py            # calibra + verifica + guarda
"""
import json
import random
import time

import cv2
import numpy as np

import config
from eye_tracker import (FEATURES_VERSION, EyeTracker, feature_vector,
                         head_translation)

# Rejilla 4x4. En HORIZONTAL conviene el rango amplio: cuanto mas se mueven los
# ojos entre puntos, mas fuerte la senal, y el ojo llega de sobra a los lados
# (correlacion medida entre h_ratio y la columna pedida: 0.94-0.97).
GX = [0.08, 0.36, 0.64, 0.92]
# El vertical NO puede abrirse tanto como el horizontal. El recorrido comodo del
# ojo hacia arriba y abajo es la mitad que a los lados, asi que a ~40 cm de la
# pantalla las filas en 0.08 y 0.92 caen a +-19 grados y el cuello acaba haciendo
# el trabajo. Medido tres veces el 2026-09-06: la cabeza se movia 5 cm en
# vertical, correlacionaba -0.97 con la fila pedida, y la senal ocular vertical
# se quedaba en 0.04 de correlacion. Con la rejilla estrecha el ojo llega solo.
# 0.20-0.80 cubre de sobra la zona de trabajo de la app (WORK_Y = 0.24-0.80).
GY = [0.20, 0.40, 0.60, 0.80]
CALIB_POINTS = [(x, y) for y in GY for x in GX]
VERIFY_POINTS = [(0.25, 0.25), (0.75, 0.25), (0.5, 0.5), (0.25, 0.75), (0.75, 0.75)]

# Los puntos se presentan en ORDEN ALEATORIO, y no es un detalle: recorriendo la
# rejilla fila por fila, la coordenada Y del objetivo queda perfectamente
# correlacionada con el TIEMPO. Entonces cualquier cosa que derive durante la
# sesion -- que el usuario se eche atras, que la cabeza baje poco a poco -- entra
# en el ajuste como si fuera senal de mirada vertical. Medido el 2026-09-06 con
# la rejilla ordenada: la distancia correlacionaba +0.34 con la fila pedida y la
# altura de la cabeza -0.39, sin tener nada que ver con la mirada. Como la
# verificacion tambien iba ordenada, reproducia el mismo artefacto y devolvia un
# error enganosamente bueno (6.9 % en Y) que el benchmark, que si aleatoriza,
# desmentia (8.3 % de acierto). Aleatorizar rompe esa correlacion.

FIXATE_S = 1.4       # tiempo para llegar al punto y estabilizar la mirada
CAPTURE_S = 1.0      # tiempo capturando features por punto
RIDGE_LAMBDA = 1.0   # fuerza de regularizacion (sobre features estandarizadas)
WINDOW = "Calibracion InteractorGate"


# Indices del feature_vector (13D) por eje, para que el ruido vertical no
# contamine el horizontal (que es el eje preciso).
#  0 r.h  1 r.v  2 l.h  3 l.v  4 r.offx 5 r.offy 6 l.offx 7 l.offy  8 yaw 9 pitch
#  10 r.op  11 l.op  12 distancia
#
# Elegidos midiendo (analiza_features.py sobre la sesion del 2026-09-06), con el
# criterio de que aguanten cuando la cabeza se mueve, no de que ajusten bien
# donde se calibro. Error con la cabeza movida, por variante de eje X:
#   ratios + distancia    6.9 %   <- elegida
#   ratios + iris + dist  9.7 %
#   + yaw                12.3 %   (la pose de cabeza mete postura por la puerta
#                                  de atras: es lo que se quiere evitar)
# Y para el eje Y: ratios + iris + distancia da 7.1 % con R2 de postura 0.01,
# frente a 23.1 % sin la distancia. La apertura del parpado ayuda dentro de la
# sesion pero empeora al moverse, asi que fuera.
#
# ATENCION: elegido sobre UNA sesion de UN usuario. Conviene reconfirmarlo con
# mas sesiones antes de darlo por definitivo.
X_IDX = [0, 2, 12]                      # h_ratios + distancia
Y_IDX = [1, 3, 5, 7, 12]                # v_ratios + iris_y del ojo + distancia


def _ridge(Z, y, lam):
    """Ridge con bias sin regularizar. Z estandarizado (N, D). Devuelve (D+1,)."""
    Zb = np.hstack([Z, np.ones((len(Z), 1))])
    reg = lam * np.eye(Zb.shape[1])
    reg[-1, -1] = 0.0
    return np.linalg.solve(Zb.T @ Zb + reg, Zb.T @ y)


class GazeMapper:
    """features de mirada -> punto de pantalla (x, y). Dos regresores ridge
    independientes (uno por eje) sobre features estandarizadas."""

    def __init__(self, mean=None, std=None, coef_x=None, coef_y=None):
        self.mean = np.asarray(mean) if mean is not None else None
        self.std = np.asarray(std) if std is not None else None
        self.coef_x = np.asarray(coef_x) if coef_x is not None else None
        self.coef_y = np.asarray(coef_y) if coef_y is not None else None

    def fit(self, features, targets, lam=RIDGE_LAMBDA):
        X = np.asarray(features, dtype=np.float64)                 # (N, 13)
        T = np.asarray(targets, dtype=np.float64)                  # (N, 2)
        self.mean = X.mean(axis=0)
        self.std = X.std(axis=0) + 1e-8
        Z = (X - self.mean) / self.std
        self.coef_x = _ridge(Z[:, X_IDX], T[:, 0], lam)
        self.coef_y = _ridge(Z[:, Y_IDX], T[:, 1], lam)
        return self

    def transform(self, feature_vec):
        z = (np.asarray(feature_vec, dtype=np.float64) - self.mean) / self.std
        x = np.append(z[X_IDX], 1.0) @ self.coef_x
        y = np.append(z[Y_IDX], 1.0) @ self.coef_y
        return float(np.clip(x, 0, 1)), float(np.clip(y, 0, 1))

    def to_dict(self):
        return {"mean": self.mean.tolist(), "std": self.std.tolist(),
                "coef_x": self.coef_x.tolist(), "coef_y": self.coef_y.tolist()}

    @classmethod
    def from_dict(cls, d):
        return cls(mean=d["mean"], std=d["std"],
                   coef_x=d["coef_x"], coef_y=d["coef_y"])


def _fullscreen_window():
    cv2.namedWindow(WINDOW, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)


def _draw_target(nx, ny, label=""):
    W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    canvas = np.zeros((H, W, 3), np.uint8)
    px, py = int(nx * W), int(ny * H)
    cv2.circle(canvas, (px, py), 24, (0, 0, 255), -1)
    cv2.circle(canvas, (px, py), 8, (255, 255, 255), -1)
    if label:
        cv2.putText(canvas, label, (40, 60), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, (200, 200, 200), 2)
    cv2.imshow(WINDOW, canvas)
    cv2.waitKey(1)


def _collect(cap, tracker, points, ts0):
    """Muestra cada punto EN ORDEN ALEATORIO, descarta la transicion y captura
    features al fijar (ver la nota sobre el orden junto a CALIB_POINTS).

    Devuelve tambien la traslacion de cabeza de cada muestra: es lo que permite
    saber, mas tarde, desde que postura se calibro."""
    points = list(points)
    random.shuffle(points)
    feats, targets, heads = [], [], []
    ts = ts0
    for k, (nx, ny) in enumerate(points):
        _draw_target(nx, ny, f"Mira el punto {k + 1}/{len(points)}")
        t_fix = time.time() + FIXATE_S            # descartar mientras el ojo llega
        while time.time() < t_fix:
            cap.read()
            cv2.waitKey(1)
        t_end = time.time() + CAPTURE_S
        while time.time() < t_end:
            ok, frame = cap.read()
            if not ok:
                continue
            ts += 33
            res = tracker.process(frame, ts)
            if res is not None:
                feats.append(feature_vector(res))
                targets.append((nx, ny))
                heads.append(head_translation(res.pose_matrix))
    return feats, targets, ts, heads


def run_calibration():
    cap = config.open_camera()
    if not cap.isOpened():
        print("ERROR: webcam no disponible")
        return None
    for _ in range(15):
        cap.read()
    tracker = EyeTracker()
    _fullscreen_window()

    print("Calibracion: mira cada punto rojo hasta que cambie.")
    print("(La postura que tengas AHORA es la que habra que reproducir "
          "despues; comprobala con main.py --encuadre.)")
    feats, targets, ts, heads = _collect(cap, tracker, CALIB_POINTS, 0)
    if len(feats) < 40:
        print(f"ERROR: muy pocas muestras ({len(feats)}). Rostro no detectado?")
        cap.release(); cv2.destroyAllWindows(); tracker.close()
        return None

    mapper = GazeMapper().fit(feats, targets)

    vfeats, vtargets, _, vheads = _collect(cap, tracker, VERIFY_POINTS, ts)
    cap.release(); cv2.destroyAllWindows(); tracker.close()

    # El ajuste ya es valido: guardarlo antes de verificar, para no perderlo
    # si la verificacion no reune muestras suficientes. Se guardan tambien las
    # muestras crudas: sin ellas no se puede reanalizar una calibracion mala a
    # posteriori (ni comparar juegos de features) sin repetir la sesion.
    # Se guardan tambien las muestras de VERIFICACION: son las mismas caras y la
    # misma postura unos minutos despues, asi que son el unico registro de lo que
    # cambia con el tiempo dentro de una sesion. El 2026-09-06 el eje Y pasaba de
    # 3.0 % (validacion cruzada dentro del ajuste) a 34.9 % en ellas.
    muestras = _samples_dict(feats, targets, heads)
    muestras["verify"] = _samples_dict(vfeats, vtargets, vheads)
    save_calibration(mapper, samples=muestras)

    avisos = revisa_sesion(feats, targets, heads)
    if avisos:
        print("\nREVISION DE LA SESION -- esta calibracion NO es fiable:")
        for a in avisos:
            print(f"  - {a}")
        print("  Repitela: main.py --encuadre (hasta que este todo en verde) y "
              "luego main.py --calibrate, con la cabeza quieta.")
    else:
        print("\nRevision de la sesion: postura estable y senal ocular en ambos ejes.")

    if len(vfeats) < 5:
        print(f"Muestras calibracion: {len(feats)} | verificacion: {len(vfeats)}")
        print("AVISO: la verificacion no reunio muestras suficientes (rostro no "
              "detectado). No se puede estimar el error, pero la calibracion "
              "SI se guardo.")
        print(f"Calibracion guardada -> {config.CALIB_FILE}")
        return mapper

    preds = np.array([mapper.transform(f) for f in vfeats])
    gts = np.array(vtargets)
    diff = preds - gts
    err_norm = np.linalg.norm(diff, axis=1)
    diag_px = np.hypot(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    print(f"\nMuestras calibracion: {len(feats)} | verificacion: {len(vfeats)}")
    print(f"Error medio: {err_norm.mean() * 100:.1f}% de pantalla "
          f"(~{err_norm.mean() * diag_px:.0f} px) | max {err_norm.max() * 100:.1f}%")
    print(f"  eje X: {np.abs(diff[:, 0]).mean() * 100:.1f}%  |  "
          f"eje Y: {np.abs(diff[:, 1]).mean() * 100:.1f}%")

    print(f"Calibracion guardada -> {config.CALIB_FILE}")
    return mapper


# ── Revision de la sesion ────────────────────────────────────────────────────
# Una calibracion puede salir mal por como se hizo la sesion, no por el ajuste:
# si la cabeza se pasea, si se sigue a los puntos con el cuello en vez de con los
# ojos, o si uno se sienta tan cerca que las columnas extremas caen fuera del
# alcance ocular. Eso no se ve en el error de verificacion (que puede salir
# "regular" por muchos motivos) pero si en las muestras crudas. Medido el
# 2026-09-06: una sesion a 37 cm con 11.7 cm de vaiven lateral dio 46 % de error
# y CERO correlacion entre los ojos y el objetivo horizontal.
DIST_MIN_CM, DIST_MAX_CM = 38.0, 64.0
RANGO_CABEZA_CM = 4.0      # recorrido tolerable de la cabeza durante la sesion
CORR_MIRADA_MIN = 0.40     # correlacion minima ojos<->objetivo para que haya senal
CORR_CABEZA_MAX = 0.50     # por encima de esto, se siguio a los puntos con la cabeza
# ...pero solo si ademas se movio de verdad: en la sesion buena del 2026-09-06 la
# cabeza correlacionaba -0.97 con el objetivo Y moviendose 4 MILIMETROS. Una
# correlacion sin amplitud no mueve la mirada; avisar de eso es un falso positivo.
AMPLITUD_CABEZA_CM = 2.0


def _corr(a, b):
    if np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def revisa_sesion(feats, targets, heads):
    """Defectos de la sesion de calibracion. Devuelve la lista de avisos."""
    F, T, H = (np.asarray(x, dtype=np.float64) for x in (feats, targets, heads))
    avisos = []

    mask = np.any(H != 0, axis=1) if len(H) else np.zeros(0, bool)
    validas, Tv = H[mask], T[mask]
    if len(validas):
        dist = abs(validas[:, 2].mean())
        if dist and not DIST_MIN_CM <= dist <= DIST_MAX_CM:
            cerca = dist < DIST_MIN_CM
            porque = ("los puntos de los bordes caen fuera del alcance comodo del "
                      "ojo y el cuello acaba haciendo el trabajo" if cerca else
                      "los ojos se mueven muy poco entre puntos y la senal se "
                      "confunde con el ruido")
            avisos.append(f"Estabas a ~{dist:.0f} cm: demasiado "
                          f"{'cerca' if cerca else 'lejos'}. Asi {porque}.")
        rango = (validas[:, :2].max(axis=0) - validas[:, :2].min(axis=0))
        if rango.max() > RANGO_CABEZA_CM:
            avisos.append(
                f"La cabeza se movio {rango[0]:.1f} cm en lateral y {rango[1]:.1f} cm "
                f"en vertical durante la calibracion. Cada cm obliga al ojo a rotar "
                f"para no perder el punto, y eso entra en las features como si fuera "
                f"mirada.")
        for j, eje in ((0, "horizontal"), (1, "vertical")):
            if (abs(_corr(validas[:, j], Tv[:, j])) > CORR_CABEZA_MAX
                    and rango[j] > AMPLITUD_CABEZA_CM):
                avisos.append(
                    f"Seguiste los puntos en {eje} moviendo la CABEZA "
                    f"({rango[j]:.1f} cm). Hay que seguirlos solo con los ojos.")

    cx = max(abs(_corr(F[:, 0], T[:, 0])), abs(_corr(F[:, 2], T[:, 0])))
    cy = max(abs(_corr(F[:, 1], T[:, 1])), abs(_corr(F[:, 3], T[:, 1])))
    if cx < CORR_MIRADA_MIN:
        avisos.append(f"Sin senal ocular horizontal (correlacion {cx:.2f}): los ojos "
                      f"no acompanaron a los puntos de izquierda a derecha.")
    if cy < CORR_MIRADA_MIN:
        avisos.append(f"Senal ocular vertical debil (correlacion {cy:.2f}).")
    return avisos


def _samples_dict(feats, targets, heads):
    """Muestras crudas de la calibracion, para reanalisis offline."""
    return {
        "features": [[round(v, 5) for v in f] for f in feats],
        "targets": [[round(x, 4), round(y, 4)] for x, y in targets],
        "head": [[round(v, 4) for v in h] for h in heads],
    }


def save_calibration(mapper, samples=None):
    data = {"gaze": mapper.to_dict(),
            "blink_threshold": config.BLINK_THRESHOLD,
            "screen": [config.SCREEN_WIDTH, config.SCREEN_HEIGHT],
            "creada": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "features_version": FEATURES_VERSION}
    if samples is not None:
        data["samples"] = samples
    with open(config.CALIB_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def load_calibration():
    """Calibracion guardada, o None si no existe o es de otra version.

    Los coeficientes solo tienen sentido para el vector de features con el que se
    ajustaron: usar una calibracion v1 con features v2 no da un resultado peor,
    da uno sin significado. Mejor tratarla como inexistente y recalibrar.
    """
    try:
        with open(config.CALIB_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    version = data.get("features_version", 1)
    if version != FEATURES_VERSION:
        print(f"AVISO: la calibracion guardada es de la version {version} de las "
              f"features y ahora se usa la {FEATURES_VERSION}. Hay que recalibrar: "
              f"main.py --calibrate")
        return None
    return data


if __name__ == "__main__":
    run_calibration()
