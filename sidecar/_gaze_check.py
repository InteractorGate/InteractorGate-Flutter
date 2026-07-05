"""Verifica que la salida del CNN de mirada responde a donde miras.

Te pide mirar a 5 posiciones (centro/izq/der/arriba/abajo); por cada una captura
frames, corre EyeTracker + GazeModel y promedia (pitch, yaw) del CNN y el centro
del iris. Al final imprime una tabla: si el CNN sigue tu mirada, yaw cambia
izquierda<->derecha y pitch cambia arriba<->abajo.
"""
import math
import os
import time

import cv2
import numpy as np

from eye_tracker import EyeTracker
from gaze_cnn import GazeModel

CAM_INDEX = 0
TARGETS = [
    ("CENTRO", "mira al centro de la pantalla"),
    ("IZQUIERDA", "mira al borde IZQUIERDO"),
    ("DERECHA", "mira al borde DERECHO"),
    ("ARRIBA", "mira al borde SUPERIOR"),
    ("ABAJO", "mira al borde INFERIOR"),
]
HERE = os.path.dirname(__file__)


def main():
    cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("ERROR: webcam no disponible")
        return 1
    for _ in range(15):
        cap.read()
    tracker = EyeTracker()
    model = GazeModel()
    print("Modelo CNN + MediaPipe listos. Sigue las instrucciones:\n")

    ts = 0
    rows = []
    saved_patch = False
    for name, hint in TARGETS:
        print(f">>> {name}: {hint}  (3s)")
        for c in (3, 2, 1):
            print(f"    {c}...", flush=True)
            time.sleep(1)
        pitch, yaw, irx, iry, n = [], [], [], [], 0
        t_end = time.time() + 1.6
        while time.time() < t_end:
            ok, frame = cap.read()
            if not ok:
                continue
            ts += 33
            res = tracker.process(frame, ts)
            if res is None:
                continue
            patches = np.stack([res.right.patch, res.left.patch]).astype(np.float32)
            ang = model.predict(patches)          # (2,2) -> [right, left] x (pitch,yaw)
            pitch.append(float(ang[:, 0].mean()))
            yaw.append(float(ang[:, 1].mean()))
            irx.append((res.right.iris[0] + res.left.iris[0]) / 2)
            iry.append((res.right.iris[1] + res.left.iris[1]) / 2)
            n += 1
            if not saved_patch:
                cv2.imwrite(os.path.join(HERE, "_eye_patch.png"), res.right.patch)
                saved_patch = True
        if n:
            rows.append((name, np.mean(pitch), np.mean(yaw), np.mean(irx), np.mean(iry), n))
            print(f"    -> pitch {np.mean(pitch):+.3f} | yaw {np.mean(yaw):+.3f} "
                  f"| iris ({np.mean(irx):.3f},{np.mean(iry):.3f}) | {n} frames\n")
        else:
            print("    -> sin rostro en esta toma\n")

    cap.release()
    tracker.close()

    print("=" * 64)
    print(f"{'Target':10} {'CNN pitch':>10} {'CNN yaw':>10} {'iris_x':>8} {'iris_y':>8}")
    for name, p, y, ix, iy, n in rows:
        print(f"{name:10} {p:>+10.3f} {y:>+10.3f} {ix:>8.3f} {iy:>8.3f}")
    if len(rows) >= 5:
        d = {r[0]: r for r in rows}
        yaw_span = d["DERECHA"][2] - d["IZQUIERDA"][2]
        pitch_span = d["ABAJO"][1] - d["ARRIBA"][1]
        irx_span = d["DERECHA"][3] - d["IZQUIERDA"][3]
        iry_span = d["ABAJO"][4] - d["ARRIBA"][4]
        print("\nRangos (der-izq / abajo-arriba):")
        print(f"  CNN yaw  (izq->der):   {yaw_span:+.3f} rad")
        print(f"  CNN pitch(arr->abj):   {pitch_span:+.3f} rad")
        print(f"  iris_x   (izq->der):   {irx_span:+.3f}")
        print(f"  iris_y   (arr->abj):   {iry_span:+.3f}")
    print("Parche de ojo guardado en _eye_patch.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
