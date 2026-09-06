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

# Rejilla 4x4, estrecha en los DOS ejes y por el mismo motivo. Un rango amplio da
# mas recorrido de senal, pero a partir de cierto angulo deja de compensar: el
# iris se desplaza como el SENO del angulo de mirada y el punto de pantalla
# necesita la TANGENTE, y esas dos curvas solo se parecen cerca del centro. A
# 36 cm de la pantalla las columnas en 0.08 y 0.92 caen a +-36 grados, donde ya
# no se parecen en nada (y ademas el cuello empieza a ayudar). Medido el
# 2026-09-06: con la rejilla ancha el error horizontal se quedaba en 122 px con
# 102 de margen. El tablero de la app solo ocupa 0.27-0.73, asi que 0.18-0.82 lo
# cubre de sobra.
GX = [0.18, 0.39, 0.61, 0.82]
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
CAPTURE_S = 1.0      # tiempo capturando con la cabeza quieta
MOVIMIENTO_S = 1.0   # ...y capturando mientras la cabeza se mueve (ver _collect)
RIDGE_LAMBDA = 1.0   # fuerza de regularizacion (sobre features estandarizadas)
WINDOW = "Calibracion InteractorGate"


# Indices del feature_vector (15D):
#  0 r.h  1 r.v  2 l.h  3 l.v  4 r.offx 5 r.offy 6 l.offx 7 l.offy  8 yaw 9 pitch
#  10 r.op  11 l.op  12 head_x  13 head_y  14 head_z   (posicion en cm)
OJO_X = [0, 2, 4, 6]                    # h_ratios + iris_x en el marco del ojo
OJO_Y = [1, 3, 5, 7]                    # v_ratios + iris_y en el marco del ojo


def terminos(F):
    """Matrices de diseno (una por eje) con la FORMA que dicta la geometria.

    Donde miras en la pantalla no es una funcion del ojo a secas: es donde esta
    tu cabeza MAS hacia donde apunta el ojo desde ahi.

        X = head_x + distancia * tan(angulo_horizontal_del_ojo)
        Y = head_y + distancia * tan(angulo_vertical_del_ojo)

    La posicion de la cabeza SUMA y la distancia MULTIPLICA al angulo. Dandole
    esos terminos al ajuste, moverse deja de ser un problema y pasa a ser un dato
    mas: la calibracion aprende el ojo en vez de aprender la postura. Hasta la
    v3 el modelo era plano (una combinacion lineal de features sueltas), asi que
    solo valia desde la silla donde te habias sentado a calibrar.

    Esto importa mas por el usuario final que por las pruebas: la app es para
    personas con discapacidad motora, que pueden tener movimiento de cabeza
    involuntario. "Quedate quieto" no es una instruccion aceptable ahi.

    Sobre una simulacion con la geometria real, calibrando con la cabeza quieta y
    evaluando con ella movida 3 cm en lateral, 3 en vertical y 8 en profundidad a
    la vez: el modelo plano se va a 13.4 % / 36.4 % de error y este se queda en
    1.2 % / 2.4 %. La simulacion valida el algebra, no la realidad; el numero de
    verdad sale de una sesion.

    Fuera quedan yaw/pitch (la rotacion de la cabeza) y la apertura del parpado:
    medidos sobre datos reales empeoraban al moverse. Se pueden volver a probar
    con analiza_features.py cuando haya varias sesiones.
    """
    F = np.atleast_2d(np.asarray(F, dtype=np.float64))
    z = np.abs(F[:, 14:15])                       # distancia a la camara (cm)
    ax = np.hstack([F[:, 12:13], z * F[:, OJO_X], z])
    ay = np.hstack([F[:, 13:14], z * F[:, OJO_Y], z])
    return ax, ay


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
        # mean/std son un par [eje X, eje Y]: cada eje tiene sus propios terminos.
        self.mean = [np.asarray(m) for m in mean] if mean is not None else None
        self.std = [np.asarray(s) for s in std] if std is not None else None
        self.coef_x = np.asarray(coef_x) if coef_x is not None else None
        self.coef_y = np.asarray(coef_y) if coef_y is not None else None

    def fit(self, features, targets, lam=RIDGE_LAMBDA):
        T = np.asarray(targets, dtype=np.float64)                  # (N, 2)
        ax, ay = terminos(features)
        # Cada eje tiene sus propios terminos, asi que tambien su propia
        # estandarizacion.
        self.mean = [ax.mean(axis=0), ay.mean(axis=0)]
        self.std = [ax.std(axis=0) + 1e-8, ay.std(axis=0) + 1e-8]
        self.coef_x = _ridge((ax - self.mean[0]) / self.std[0], T[:, 0], lam)
        self.coef_y = _ridge((ay - self.mean[1]) / self.std[1], T[:, 1], lam)
        return self

    def transform(self, feature_vec, recorta=True):
        """Punto de pantalla normalizado. `recorta=False` devuelve el valor
        crudo, sin sujetarlo a [0,1]: hace falta para diagnosticar, porque una
        prediccion saturada contra el borde esconde cuanto se ha ido de verdad
        (el 2026-09-06 el eje Y llegaba a 4.62 y el recorte lo disimulaba)."""
        ax, ay = terminos(feature_vec)
        zx = (ax[0] - self.mean[0]) / self.std[0]
        zy = (ay[0] - self.mean[1]) / self.std[1]
        x = np.append(zx, 1.0) @ self.coef_x
        y = np.append(zy, 1.0) @ self.coef_y
        if not recorta:
            return float(x), float(y)
        return float(np.clip(x, 0, 1)), float(np.clip(y, 0, 1))

    def to_dict(self):
        return {"mean": [m.tolist() for m in self.mean],
                "std": [s.tolist() for s in self.std],
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
        # Dos ventanas por punto: quieto y moviendose. La segunda no es un
        # capricho -- el modelo geometrico necesita ver la MISMA mirada desde
        # posturas distintas para poder separar "movio el ojo" de "movio la
        # cabeza". Sin variacion de postura esa correccion no se puede estimar.
        for etiqueta, dur in ((None, CAPTURE_S),
                              ("Sigue mirando el punto y muevete un poco",
                               MOVIMIENTO_S)):
            if etiqueta:
                _draw_target(nx, ny, etiqueta)
            t_end = time.time() + dur
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
# si se sigue a los puntos con el cuello en vez de con los ojos, o si uno se
# sienta tan cerca que las columnas extremas caen fuera del alcance ocular. Eso
# no se ve en el error de verificacion (que puede salir "regular" por muchos
# motivos) pero si en las muestras crudas. Medido el 2026-09-06: una sesion a
# 37 cm dio 46 % de error y CERO correlacion entre los ojos y el objetivo
# horizontal, porque el cuello estaba haciendo el trabajo.
#
# OJO con el cambio de criterio en v4: que la cabeza se MUEVA ya no es un
# defecto, es lo que el modelo geometrico necesita para aprender la correccion.
# Lo que sigue siendo un defecto es que la cabeza se mueva SIGUIENDO a los
# puntos, porque entonces el movimiento esta correlacionado con el objetivo y el
# ajuste no puede distinguir una cosa de la otra.
DIST_MIN_CM, DIST_MAX_CM = 38.0, 64.0
RANGO_CABEZA_MIN_CM = 1.0  # menos movimiento que esto y la correccion no se puede estimar
RANGO_CABEZA_MAX_CM = 15.0  # mas que esto no es moverse, es haberse ido
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
        if rango.max() < RANGO_CABEZA_MIN_CM:
            avisos.append(
                f"La cabeza casi no se movio ({rango[0]:.1f} cm en lateral, "
                f"{rango[1]:.1f} en vertical). El modelo necesita ver la misma "
                f"mirada desde posturas distintas para aprender a corregir el "
                f"movimiento; sin eso la calibracion solo valdra desde esta silla. "
                f"Muevete un poco cuando la ventana lo pida.")
        elif rango.max() > RANGO_CABEZA_MAX_CM:
            avisos.append(
                f"La cabeza se movio {rango.max():.0f} cm: demasiado. Es mas "
                f"probable que el seguimiento te perdiera a que sea movimiento util.")
        for j, eje in ((0, "horizontal"), (1, "vertical")):
            if (abs(_corr(validas[:, j], Tv[:, j])) > CORR_CABEZA_MAX
                    and rango[j] > AMPLITUD_CABEZA_CM):
                avisos.append(
                    f"Seguiste los puntos en {eje} moviendo la CABEZA "
                    f"({rango[j]:.1f} cm). Hay que seguirlos solo con los ojos.")

    # Se miran TODAS las features del eje, no solo los ratios. El vertical hay que
    # juzgarlo por `off_y`: v_ratio se normaliza con la apertura del parpado y
    # sale plano aunque el ojo se este moviendo perfectamente. Midiendolo con
    # v_ratio, una sesion buena (off_y a -0.76 de correlacion) se reportaba como
    # "senal vertical debil, 0.07" -- un falso positivo por mirar el termometro
    # equivocado.
    cx = max(abs(_corr(F[:, i], T[:, 0])) for i in OJO_X)
    cy = max(abs(_corr(F[:, i], T[:, 1])) for i in OJO_Y)
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
