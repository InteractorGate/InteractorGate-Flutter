"""Diagnostico: por que una calibracion recien hecha deja de valer.

El benchmark del 2026-09-06 dio 0 % de acierto con dos calibraciones distintas,
y el analisis de esos datos descarto la deriva temporal: el error NO crecia con
el numero de ensayo (pendiente +0.8 px/ensayo en X, r=0.02). Lo que habia era un
SESGO casi constante de -697 px en X y una ganancia colapsada (b=0.375 en X,
0.563 en Y). La sospecha, mirando los coeficientes, es la POSTURA: el 26 % del
peso del eje X y el 67 % del eje Y viven en features que dependen de donde esta
la cabeza en el encuadre (iris_x / iris_y crudos), y su desviacion tipica durante
la calibracion es minuscula (~0.007), asi que un desplazamiento pequeno de la
cabeza cae a muchas sigmas de lo que el modelo vio.

Este script mide esa sensibilidad directamente: el usuario fija UN punto y solo
mueve la cabeza. Si la hipotesis es cierta, el punto estimado se ira detras de la
cabeza aunque la mirada no se mueva.

Salida: px de error en pantalla por cm de cabeza, por eje, y la comparacion entre
las dos fases "quieto" (inicio y final), que aisla la deriva pura en el tiempo.

Uso:
    .venv/Scripts/python.exe diag_deriva.py
    .venv/Scripts/python.exe diag_deriva.py --out diag_deriva_2026-09-06.json

Requiere calibracion previa:  .venv/Scripts/python.exe main.py --calibrate
"""
import argparse
import json
import time

import cv2
import numpy as np

import config
from calibration import GazeMapper, load_calibration
from eye_tracker import EyeTracker, feature_vector, head_translation

WINDOW = "Diagnostico de deriva - InteractorGate"
SETTLE_S = 1.5        # transicion entre fases: se descarta

# (clave, instruccion, segundos midiendo)
FASES = [
    ("quieto_1",  "QUIETO. Mira el punto y no muevas la cabeza.",              8.0),
    ("izquierda", "Sin dejar de MIRAR EL PUNTO: cabeza ~3 cm a tu IZQUIERDA.", 7.0),
    ("derecha",   "Sin dejar de MIRAR EL PUNTO: cabeza ~3 cm a tu DERECHA.",   7.0),
    ("arriba",    "Sin dejar de MIRAR EL PUNTO: cabeza ~3 cm hacia ARRIBA.",   6.0),
    ("abajo",     "Sin dejar de MIRAR EL PUNTO: cabeza ~3 cm hacia ABAJO.",    6.0),
    ("cerca",     "Sin dejar de MIRAR EL PUNTO: ACERCATE ~8 cm.",              6.0),
    ("lejos",     "Sin dejar de MIRAR EL PUNTO: ALEJATE ~8 cm.",               6.0),
    ("quieto_2",  "Vuelve a la postura del principio. QUIETO otra vez.",       8.0),
]


def _fullscreen_window():
    cv2.namedWindow(WINDOW, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)


def _draw(nx, ny, texto, sub="", progreso=0.0):
    """Punto fijo + instruccion. A proposito NO se dibuja la mirada estimada:
    si el usuario la ve, la persigue y contamina la medida."""
    W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    canvas = np.zeros((H, W, 3), np.uint8)
    px, py = int(nx * W), int(ny * H)
    cv2.circle(canvas, (px, py), 26, (0, 0, 255), -1)
    cv2.circle(canvas, (px, py), 8, (255, 255, 255), -1)
    cv2.putText(canvas, texto, (60, 90), cv2.FONT_HERSHEY_SIMPLEX,
                1.1, (255, 255, 255), 2)
    if sub:
        cv2.putText(canvas, sub, (60, 140), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (160, 160, 160), 2)
    bw = int((W - 120) * max(0.0, min(1.0, progreso)))
    cv2.rectangle(canvas, (60, H - 90), (W - 60, H - 60), (60, 60, 60), 1)
    cv2.rectangle(canvas, (60, H - 90), (60 + bw, H - 60), (0, 180, 0), -1)
    cv2.imshow(WINDOW, canvas)
    return cv2.waitKey(1) & 0xFF


def capturar(nx, ny):
    """Recorre las fases fijando un unico punto. Devuelve las muestras crudas."""
    calib = load_calibration()
    if not calib:
        print("ERROR: no hay calibracion. Corre primero main.py --calibrate")
        return None
    mapper = GazeMapper.from_dict(calib["gaze"])
    cap = config.open_camera()
    if not cap.isOpened():
        print("ERROR: webcam no disponible")
        return None
    for _ in range(15):
        cap.read()
    tracker = EyeTracker()
    _fullscreen_window()

    muestras = []
    ts = 0
    t_inicio = time.time()
    for k, (clave, instruccion, dur) in enumerate(FASES):
        t_settle = time.time() + SETTLE_S
        while time.time() < t_settle:
            cap.read()
            _draw(nx, ny, instruccion, f"Fase {k + 1}/{len(FASES)} - preparate...")
        t0 = time.time()
        t_end = t0 + dur
        n_fase = 0
        while time.time() < t_end:
            ok, frame = cap.read()
            if not ok:
                continue
            ts += 33
            res = tracker.process(frame, ts)
            abierto = res is not None and \
                (res.right.openness + res.left.openness) / 2 >= config.OPEN_GAZE_THRESHOLD
            if abierto:
                feats = feature_vector(res)
                gx, gy = mapper.transform(feats)
                muestras.append({
                    "fase": clave,
                    "t": round(time.time() - t_inicio, 3),
                    "features": [round(v, 5) for v in feats],
                    "head": [round(v, 4) for v in head_translation(res.pose_matrix)],
                    "pred": [round(gx, 5), round(gy, 5)],
                })
                n_fase += 1
            if _draw(nx, ny, instruccion,
                     f"Fase {k + 1}/{len(FASES)} - {n_fase} muestras",
                     (time.time() - t0) / dur) == 27:
                t_end = 0
        print(f"  {clave:<10} {n_fase:>4} muestras")

    cap.release()
    cv2.destroyAllWindows()
    tracker.close()
    return muestras


def informe(muestras, nx, ny, out):
    W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    if not muestras:
        print("\nSin muestras validas.")
        return
    fases = {}
    for m in muestras:
        fases.setdefault(m["fase"], []).append(m)
    if "quieto_1" not in fases:
        print("\nLa fase de referencia (quieto_1) no reunio muestras.")
        return

    head = np.array([m["head"] for m in muestras])
    pred = np.array([m["pred"] for m in muestras])
    ref_head = np.array([m["head"] for m in fases["quieto_1"]]).mean(axis=0)
    dh = head - ref_head                                   # cabeza relativa (~cm)
    err_px = np.column_stack([(pred[:, 0] - nx) * W, (pred[:, 1] - ny) * H])

    print("\n" + "=" * 78)
    print("DIAGNOSTICO DE DERIVA - la mirada esta FIJA en todo el registro")
    print("=" * 78)
    print(f"  Punto fijado: ({nx:.2f}, {ny:.2f}) = ({nx * W:.0f}, {ny * H:.0f}) px "
          f"de {W}x{H}")
    print(f"  Muestras: {len(muestras)}   (referencia de postura: quieto_1)")
    print(f"\n  {'fase':<10}{'n':>5}{'cabeza dx':>11}{'dy':>8}{'dz (cm)':>10}"
          f"{'error X px':>13}{'error Y px':>13}")
    resumen = {}
    for clave, _, _ in FASES:
        ms = fases.get(clave)
        if not ms:
            print(f"  {clave:<10}{0:>5}   (sin muestras)")
            continue
        idx = [i for i, m in enumerate(muestras) if m["fase"] == clave]
        h = dh[idx].mean(axis=0)
        e = err_px[idx].mean(axis=0)
        print(f"  {clave:<10}{len(ms):>5}"
              f"{h[0]:>11.2f}{h[1]:>8.2f}{h[2]:>10.2f}{e[0]:>13.0f}{e[1]:>13.0f}")
        resumen[clave] = {"n": len(ms), "cabeza_cm": [round(float(v), 3) for v in h],
                          "error_px": [round(float(v), 1) for v in e]}

    # Sensibilidad: error ~ traslacion de cabeza (minimos cuadrados, 3 ejes).
    A = np.column_stack([dh, np.ones(len(dh))])
    print("\n  --- Sensibilidad a la postura (px de pantalla por cm de cabeza) ---")
    sens = {}
    for j, eje in enumerate("XY"):
        beta, *_ = np.linalg.lstsq(A, err_px[:, j], rcond=None)
        resid = err_px[:, j] - A @ beta
        var = err_px[:, j].var()
        r2 = 1 - resid.var() / var if var > 1e-9 else 0.0
        print(f"    error {eje}:  {beta[0]:+8.1f} lateral  {beta[1]:+8.1f} vertical  "
              f"{beta[2]:+8.1f} profundidad   R2={r2:.2f}")
        sens[eje] = {"px_por_cm": [round(float(b), 2) for b in beta[:3]],
                     "r2": round(float(r2), 3)}
    print("    (R2 alto = el movimiento de cabeza EXPLICA el error, con la mirada quieta)")

    # Deriva pura: misma postura, distinto momento.
    if "quieto_2" in fases:
        i1 = [i for i, m in enumerate(muestras) if m["fase"] == "quieto_1"]
        i2 = [i for i, m in enumerate(muestras) if m["fase"] == "quieto_2"]
        dh_q = dh[i2].mean(axis=0) - dh[i1].mean(axis=0)
        de = err_px[i2].mean(axis=0) - err_px[i1].mean(axis=0)
        dt = float(np.mean([m["t"] for m in fases["quieto_2"]]) -
                   np.mean([m["t"] for m in fases["quieto_1"]]))
        print(f"\n  --- Deriva pura en el tiempo (quieto_1 -> quieto_2, {dt:.0f} s) ---")
        print(f"    La cabeza volvio a {dh_q[0]:+.2f}, {dh_q[1]:+.2f}, "
              f"{dh_q[2]:+.2f} cm de la postura inicial")
        print(f"    El error cambio {de[0]:+.0f} px en X y {de[1]:+.0f} px en Y")
        print("    Si la cabeza volvio (~0 cm) y el error NO volvio, hay deriva real;")
        print("    si el error vuelve con la postura, la causa es la POSTURA.")
        resumen["deriva"] = {"segundos": round(dt, 1),
                             "cabeza_cm": [round(float(v), 3) for v in dh_q],
                             "error_px": [round(float(v), 1) for v in de]}

    salida = {"pantalla": [W, H], "objetivo": [nx, ny],
              "fases": resumen, "sensibilidad": sens, "muestras": muestras}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, indent=2, ensure_ascii=False)
    print(f"\n  Guardado en sidecar/{out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", nargs=2, type=float, metavar=("X", "Y"),
                    default=[(config.WORK_X[0] + config.WORK_X[1]) / 2,
                             (config.WORK_Y[0] + config.WORK_Y[1]) / 2],
                    help="punto a fijar, en fraccion de pantalla "
                         "(def: centro del area de trabajo)")
    ap.add_argument("--out", default="diag_deriva.json", help="archivo de salida")
    args = ap.parse_args()
    nx, ny = args.target
    ms = capturar(nx, ny)
    if ms is not None:
        informe(ms, nx, ny, args.out)
