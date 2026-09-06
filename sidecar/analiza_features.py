"""Compara juegos de features del mapeo mirada->pantalla, offline.

Responde a la pregunta que dejo abierta el bench del 2026-09-06: el mapeo usa
features que dependen de DONDE esta la cabeza en el encuadre (iris_x / iris_y
crudos, 26 % del peso en X y 67 % en Y). Aqui se reajusta la misma calibracion
con distintos subconjuntos de features y se mide cual aguanta mejor.

Dos medidas, complementarias:
  1. Validacion cruzada dejando fuera un punto de la rejilla (deja-un-punto):
     precision DENTRO de la sesion de calibracion, con la cabeza donde estaba.
  2. Error sobre la sesion de diagnostico (`diag_deriva.py`), donde la mirada
     esta fija y lo unico que cambia es la postura: precision FUERA de la postura
     de calibracion. Esta es la que importa.

Un juego de features puede ganar en (1) y perder en (2): eso es exactamente el
sobreajuste a la postura que se sospecha.

Uso:
    .venv/Scripts/python.exe analiza_features.py
    .venv/Scripts/python.exe analiza_features.py --calib calibration.json \
        --diag diag_deriva.json
"""
import argparse
import json

import numpy as np

NOMBRES = ["r.h_ratio", "r.v_ratio", "l.h_ratio", "l.v_ratio",
           "r.iris_x", "r.iris_y", "l.iris_x", "l.iris_y",
           "yaw", "pitch", "r.openness", "l.openness"]
# Features cuyo valor depende de la posicion de la cabeza en el encuadre.
DEPENDE_POSICION = {4, 5, 6, 7}

# (nombre, indices del eje X, indices del eje Y)
VARIANTES = [
    ("actual (produccion)", [0, 2, 4, 6, 8], [1, 3, 5, 7, 9, 10, 11]),
    ("sin iris crudo",      [0, 2, 8],       [1, 3, 9, 10, 11]),
    ("solo ratios de iris", [0, 2],          [1, 3]),
    ("ratios + apertura",   [0, 2],          [1, 3, 10, 11]),
]
RIDGE_LAMBDA = 1.0


def _ridge(Z, y, lam):
    """Ridge con bias sin regularizar (identico al de calibration.py)."""
    Zb = np.hstack([Z, np.ones((len(Z), 1))])
    reg = lam * np.eye(Zb.shape[1])
    reg[-1, -1] = 0.0
    return np.linalg.solve(Zb.T @ Zb + reg, Zb.T @ y)


def ajustar(X, T, x_idx, y_idx, lam=RIDGE_LAMBDA):
    """Devuelve un predictor features->(x, y) para los indices dados."""
    mean, std = X.mean(axis=0), X.std(axis=0) + 1e-8
    Z = (X - mean) / std
    cx = _ridge(Z[:, x_idx], T[:, 0], lam)
    cy = _ridge(Z[:, y_idx], T[:, 1], lam)

    def predice(F):
        Zf = (np.asarray(F, dtype=np.float64) - mean) / std
        px = np.hstack([Zf[:, x_idx], np.ones((len(Zf), 1))]) @ cx
        py = np.hstack([Zf[:, y_idx], np.ones((len(Zf), 1))]) @ cy
        return np.column_stack([np.clip(px, 0, 1), np.clip(py, 0, 1)])

    return predice


def cv_deja_un_punto(X, T, x_idx, y_idx):
    """Error medio por eje dejando fuera, por turnos, cada punto de la rejilla."""
    puntos = sorted({tuple(t) for t in T.tolist()})
    ex, ey = [], []
    for p in puntos:
        fuera = np.all(np.isclose(T, p), axis=1)
        if fuera.all() or fuera.sum() == 0:
            continue
        predice = ajustar(X[~fuera], T[~fuera], x_idx, y_idx)
        P = predice(X[fuera])
        ex.append(np.abs(P[:, 0] - p[0]).mean())
        ey.append(np.abs(P[:, 1] - p[1]).mean())
    return float(np.mean(ex)), float(np.mean(ey))


def error_en_diagnostico(predice, D, objetivo):
    """Error medio y sensibilidad a la postura sobre la sesion de diagnostico."""
    F = np.array([m["features"] for m in D])
    head = np.array([m["head"] for m in D])
    P = predice(F)
    err = P - np.array(objetivo)
    ref = head[[i for i, m in enumerate(D) if m["fase"] == "quieto_1"]]
    dh = head - (ref.mean(axis=0) if len(ref) else head.mean(axis=0))
    A = np.column_stack([dh, np.ones(len(dh))])
    r2 = []
    for j in (0, 1):
        beta, *_ = np.linalg.lstsq(A, err[:, j], rcond=None)
        var = err[:, j].var()
        r2.append(1 - (err[:, j] - A @ beta).var() / var if var > 1e-12 else 0.0)
    return (float(np.abs(err[:, 0]).mean()), float(np.abs(err[:, 1]).mean()),
            float(r2[0]), float(r2[1]))


def main(calib_path, diag_path, tol_x, tol_y):
    calib = json.load(open(calib_path, encoding="utf-8"))
    if "samples" not in calib:
        print(f"ERROR: {calib_path} no trae muestras crudas.\n"
              "Recalibra con la version nueva (main.py --calibrate): desde el "
              "2026-09-06 la calibracion guarda sus muestras para poder "
              "reanalizarla sin repetir la sesion.")
        return
    X = np.array(calib["samples"]["features"], dtype=np.float64)
    T = np.array(calib["samples"]["targets"], dtype=np.float64)
    print(f"Calibracion: {len(X)} muestras, {len({tuple(t) for t in T.tolist()})} "
          f"puntos   (creada {calib.get('creada', 'fecha desconocida')})")

    D, objetivo = None, None
    if diag_path:
        try:
            diag = json.load(open(diag_path, encoding="utf-8"))
            D, objetivo = diag["muestras"], diag["objetivo"]
            print(f"Diagnostico: {len(D)} muestras fijando {objetivo}")
        except FileNotFoundError:
            print(f"(sin {diag_path}: corre diag_deriva.py para la segunda medida)")

    cab = f"\n{'variante':<22}{'CV deja-un-punto':>22}"
    if D:
        cab += f"{'con la cabeza movida':>24}{'R2 postura':>14}"
    print(cab)
    print(f"{'':<22}{'err X %':>11}{'err Y %':>11}"
          + (f"{'err X %':>13}{'err Y %':>11}{'X':>7}{'Y':>7}" if D else ""))
    for nombre, xi, yi in VARIANTES:
        cvx, cvy = cv_deja_un_punto(X, T, xi, yi)
        linea = f"{nombre:<22}{cvx * 100:>11.1f}{cvy * 100:>11.1f}"
        if D:
            predice = ajustar(X, T, xi, yi)
            dx, dy, r2x, r2y = error_en_diagnostico(predice, D, objetivo)
            linea += f"{dx * 100:>13.1f}{dy * 100:>11.1f}{r2x:>7.2f}{r2y:>7.2f}"
        print(linea)

    print(f"\nTolerancia que exige el tablero: {tol_x:.1f} % en X, {tol_y:.1f} % en Y")
    print("  CV deja-un-punto = precision con la cabeza donde se calibro.")
    if D:
        print("  Con la cabeza movida = precision cuando la postura cambia; es la"
              " columna que decide.")
        print("  R2 postura = cuanto del error lo explica el movimiento de cabeza"
              " (1.0 = todo).")
    peso = {}
    for nombre, xi, yi in VARIANTES:
        peso[nombre] = (len(set(xi) & DEPENDE_POSICION), len(set(yi) & DEPENDE_POSICION))
    print("\nFeatures dependientes de la postura por variante (X, Y): "
          + ", ".join(f"{k}: {v[0]}/{v[1]}" for k, v in peso.items()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calib", default="calibration.json")
    ap.add_argument("--diag", default="diag_deriva.json")
    # Botones de 204x155 px en 1920x1080 -> ver validacion OE4 en la memoria.
    ap.add_argument("--tol-x", type=float, default=5.3)
    ap.add_argument("--tol-y", type=float, default=7.2)
    args = ap.parse_args()
    main(args.calib, args.diag, args.tol_x, args.tol_y)
