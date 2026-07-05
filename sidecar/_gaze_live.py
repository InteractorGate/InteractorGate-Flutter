"""Preview en vivo: un punto sigue tu mirada usando la calibracion guardada.

Muestra una rejilla tipo tablero AAC, resalta la celda mirada, dibuja el punto
de mirada suavizado e informa la apertura del ojo + parpadeos. Sirve para juzgar
la precision real y ajustar el umbral de parpadeo. Sal con 'q' o ESC.
"""
import time

import cv2
import numpy as np

import config
from blink_detector import BlinkDetector
from calibration import GazeMapper, load_calibration
from eye_tracker import EyeTracker, feature_vector
from smoothing import GazeSmoother2D

COLS, ROWS = 4, 3          # rejilla de referencia (como un tablero)
DURATION_S = 25
WINDOW = "Mirada en vivo - InteractorGate"


def main():
    saved = load_calibration()
    if not saved:
        print("ERROR: no hay calibracion. Corre calibration.py primero.")
        return 1
    mapper = GazeMapper.from_dict(saved["gaze"])

    cap = cv2.VideoCapture(config.CAM_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("ERROR: webcam no disponible")
        return 1
    for _ in range(15):
        cap.read()
    tracker = EyeTracker()
    blink = BlinkDetector(threshold=config.BLINK_THRESHOLD)

    cv2.namedWindow(WINDOW, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT

    sx, sy = 0.5, 0.5
    smoother = GazeSmoother2D(mincutoff=0.5, beta=0.008)
    ts, blinks = 0, 0
    op_min, op_max = 9.9, 0.0
    flash_until = 0.0
    t0 = time.time()
    while time.time() - t0 < DURATION_S:
        ok, frame = cap.read()
        if not ok:
            continue
        ts += 33
        res = tracker.process(frame, ts)
        canvas = np.zeros((H, W, 3), np.uint8)
        # Rejilla de referencia
        for c in range(1, COLS):
            cv2.line(canvas, (c * W // COLS, 0), (c * W // COLS, H), (40, 40, 40), 1)
        for r in range(1, ROWS):
            cv2.line(canvas, (0, r * H // ROWS), (W, r * H // ROWS), (40, 40, 40), 1)

        if res is not None:
            gx, gy = mapper.transform(feature_vector(res))
            sx, sy = smoother.update(gx, gy, time.time())
            openness = (res.right.openness + res.left.openness) / 2
            op_min, op_max = min(op_min, openness), max(op_max, openness)
            if blink.detect(openness):
                blinks += 1
                flash_until = time.time() + 0.3

            # Celda mirada resaltada
            cc, rr = min(int(sx * COLS), COLS - 1), min(int(sy * ROWS), ROWS - 1)
            x0, y0 = cc * W // COLS, rr * H // ROWS
            cv2.rectangle(canvas, (x0, y0), (x0 + W // COLS, y0 + H // ROWS),
                          (0, 90, 0), -1)
            # Punto de mirada
            px, py = int(sx * W), int(sy * H)
            color = (0, 255, 255) if time.time() < flash_until else (0, 200, 255)
            cv2.circle(canvas, (px, py), 26, color, -1)
            cv2.putText(canvas, f"apertura {openness:.2f}  parpadeos {blinks}",
                        (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)
        else:
            cv2.putText(canvas, "sin rostro", (40, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

        cv2.imshow(WINDOW, canvas)
        if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
            break

    cap.release()
    cv2.destroyAllWindows()
    tracker.close()
    print(f"Parpadeos detectados: {blinks}")
    print(f"Apertura observada: min {op_min:.2f}  max {op_max:.2f}")
    print(f"  (umbral de parpadeo sugerido ~ {(op_min + op_max) / 2:.2f}; "
          f"actual {config.BLINK_THRESHOLD})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
