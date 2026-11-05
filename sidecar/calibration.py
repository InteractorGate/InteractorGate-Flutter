"""Calibracion por usuario: aprende el mapeo mirada->pantalla.

`GazeMapper` estandariza el vector de features de mirada (iris relativo + iris
crudo + pose de cabeza) y ajusta una regresion **ridge** (regularizada) hacia el
punto de pantalla normalizado [0..1]. Se calibra mirando una rejilla de puntos a
pantalla completa.

Uso:
    .venv/Scripts/python.exe calibration.py            # calibra + verifica + guarda
"""
import json
import shutil
import time
from pathlib import Path

import cv2
import numpy as np

import config
from eye_tracker import EyeTracker, feature_vector

# Rejilla 4x4 en rango AMPLIO: mientras mas se mueven los ojos entre puntos,
# mas fuerte la senal (sobre todo en vertical). La zona central de trabajo se
# consigue con la VENTANA reducida de la app, no comprimiendo la calibracion.
GX = [0.08, 0.36, 0.64, 0.92]
GY = [0.08, 0.36, 0.64, 0.92]
CALIB_POINTS = [(x, y) for y in GY for x in GX]
VERIFY_POINTS = [(0.25, 0.25), (0.75, 0.25), (0.5, 0.5), (0.25, 0.75), (0.75, 0.75)]

FIXATE_S = 1.4       # tiempo para llegar al punto y estabilizar la mirada
CAPTURE_S = 1.0      # tiempo capturando features por punto
RIDGE_LAMBDA = 1.0   # fuerza de regularizacion (sobre features estandarizadas)
WINDOW = "Calibracion InteractorGate"


# Indices del feature_vector (12D) por eje, para que el ruido vertical no
# contamine el horizontal (que es el eje preciso).
#  0 r.h  1 r.v  2 l.h  3 l.v  4 r.ix 5 r.iy 6 l.ix 7 l.iy  8 yaw 9 pitch 10 r.op 11 l.op
X_IDX = [0, 2, 4, 6, 8]                 # h_ratios + iris_x + head yaw
Y_IDX = [1, 3, 5, 7, 9, 10, 11]         # v_ratios + iris_y + head pitch + apertura


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
        X = np.asarray(features, dtype=np.float64)                 # (N, 12)
        T = np.asarray(targets, dtype=np.float64)                  # (N, 2)
        self.mean = X.mean(axis=0)
        self.std = X.std(axis=0) + 1e-8
        Z = (X - self.mean) / self.std
        self.coef_x = _ridge(Z[:, X_IDX], T[:, 0], lam)
        self.coef_y = _ridge(Z[:, Y_IDX], T[:, 1], lam)
        return self

    def transform(self, feature_vec):
        x, y = self.transform_unclipped(feature_vec)
        return float(np.clip(x, 0, 1)), float(np.clip(y, 0, 1))

    def transform_unclipped(self, feature_vec):
        """Prediction before screen clipping, exposed for visual diagnostics."""
        z = (np.asarray(feature_vec, dtype=np.float64) - self.mean) / self.std
        x = np.append(z[X_IDX], 1.0) @ self.coef_x
        y = np.append(z[Y_IDX], 1.0) @ self.coef_y
        return float(x), float(y)

    def to_dict(self):
        return {"mean": self.mean.tolist(), "std": self.std.tolist(),
                "coef_x": self.coef_x.tolist(), "coef_y": self.coef_y.tolist()}

    @classmethod
    def from_dict(cls, d):
        mapper = cls(mean=d["mean"], std=d["std"],
                     coef_x=d["coef_x"], coef_y=d["coef_y"])
        for name, shape in (("mean", (12,)), ("std", (12,)),
                            ("coef_x", (6,)), ("coef_y", (8,))):
            array = getattr(mapper, name)
            if array.shape != shape or not np.isfinite(array).all():
                raise ValueError(f"Perfil incompatible: {name}; recalibrar")
        if np.any(mapper.std <= 0):
            raise ValueError("Perfil incompatible: desviacion no positiva")
        return mapper


def _fullscreen_window():
    cv2.namedWindow(WINDOW, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)


def _check_cancel():
    if cv2.waitKey(1) & 0xff == 27 or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
        raise InterruptedError("Calibracion cancelada")


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
    _check_cancel()


def _collect(cap, tracker, points, ts0):
    """Muestra cada punto, descarta la transicion y captura features al fijar."""
    feats, targets = [], []
    ts = ts0
    for k, (nx, ny) in enumerate(points):
        _draw_target(nx, ny, f"Mira el punto {k + 1}/{len(points)}")
        t_fix = time.time() + FIXATE_S            # descartar mientras el ojo llega
        while time.time() < t_fix:
            cap.read()
            _check_cancel()
        t_end = time.time() + CAPTURE_S
        while time.time() < t_end:
            _check_cancel()
            ok, frame = cap.read()
            if not ok:
                continue
            ts += 33
            res = tracker.process(frame, ts)
            if res is not None:
                feats.append(feature_vector(res))
                targets.append((nx, ny))
    return feats, targets, ts


def run_calibration():
    cap = config.open_camera()
    if not cap.isOpened():
        print("ERROR: webcam no disponible")
        cap.release()
        return None
    tracker = None
    try:
        for _ in range(15):
            cap.read()
        tracker = EyeTracker()
        _fullscreen_window()
        print("Calibracion: mira cada punto rojo hasta que cambie.")
        feats, targets, ts = _collect(cap, tracker, CALIB_POINTS, 0)
        if len(feats) < 40:
            print(f"ERROR: muy pocas muestras ({len(feats)}). Rostro no detectado?")
            return None
        mapper = GazeMapper().fit(feats, targets)
        vfeats, vtargets, _ = _collect(cap, tracker, VERIFY_POINTS, ts)
    except InterruptedError:
        print("Calibracion cancelada; no se inicia el seguimiento.")
        return None
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if tracker is not None:
            tracker.close()

    # El ajuste ya es valido: guardarlo antes de verificar, para no perderlo
    # si la verificacion no reune muestras suficientes.
    save_calibration(mapper)

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


def save_calibration(mapper):
    data = {"gaze": mapper.to_dict(),
            "blink_threshold": config.BLINK_THRESHOLD,
            "screen": [config.SCREEN_WIDTH, config.SCREEN_HEIGHT]}
    target = Path(config.CALIB_FILE)
    temporary = target.with_name(f".{target.name}.{time.time_ns()}.tmp")
    try:
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if target.exists():
            shutil.copy2(target, target.with_name(
                f"{target.stem}.backup-{time.time_ns()}.json"))
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def load_calibration():
    try:
        with open(config.CALIB_FILE, encoding="utf-8") as fh:
            saved = json.load(fh)
        GazeMapper.from_dict(saved["gaze"])
        return saved
    except FileNotFoundError:
        return None
    except (ValueError, KeyError, TypeError):
        print("Perfil guardado incompatible. Se requiere recalibrar; "
              "el perfil anterior se conserva hasta guardar el nuevo con copia.")
        return None


if __name__ == "__main__":
    run_calibration()
