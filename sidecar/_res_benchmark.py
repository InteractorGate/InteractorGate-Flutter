"""Benchmark cruzado resolucion x FPS x calidad de la senal de mirada.

Para cada resolucion mide:
  - FPS end-to-end reales (captura + MediaPipe FaceLandmarker).
  - Ancho del ojo en pixeles (cuanto detalle tiene MediaPipe del ojo).
  - Jitter de las features de mirada (std de h_ratio/v_ratio mientras fijas la
    vista) -> ruido de la senal = precision real. MENOS es mejor.

El usuario debe MIRAR FIJO un punto (centro) y NO moverse durante toda la corrida.
"""
import time

import cv2
import numpy as np

from eye_tracker import EyeTracker

# (ancho, alto, usar_mjpg)
RESOLUTIONS = [
    (640, 480, False),
    (960, 540, True),
    (1280, 720, True),
    (1920, 1080, True),
]
FRAMES = 40


def bench(w, h, mjpg, tracker, ts_start):
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if mjpg:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    for _ in range(8):
        cap.read()
    aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    hs, vs, faces = [], [], 0
    ts = ts_start
    t0 = time.time()
    for _ in range(FRAMES):
        ok, frame = cap.read()
        if not ok:
            continue
        ts += 40
        res = tracker.process(frame, ts)
        if res is not None:
            faces += 1
            hs.append(res.right.h_ratio)
            vs.append(res.right.v_ratio)
    dt = time.time() - t0
    cap.release()
    fps = FRAMES / dt if dt else 0
    h_std = float(np.std(hs)) if len(hs) > 3 else float('nan')
    v_std = float(np.std(vs)) if len(vs) > 3 else float('nan')
    return {"req": f"{w}x{h}", "real": f"{aw}x{ah}", "fps": fps,
            "faces": faces, "h_jitter": h_std, "v_jitter": v_std}, ts


def main():
    tracker = EyeTracker()
    print(">>> MIRA FIJO EL CENTRO DE LA PANTALLA y no te muevas (~30s).")
    for c in (3, 2, 1):
        print(f"    {c}..."); time.sleep(1)

    rows, ts = [], 0
    for w, h, mjpg in RESOLUTIONS:
        print(f"  probando {w}x{h}...", flush=True)
        r, ts = bench(w, h, mjpg, tracker, ts)
        rows.append(r)
    tracker.close()

    print("\n" + "=" * 74)
    print(f"{'pedido':>10} {'real':>10} {'FPS':>6} {'rostros':>8} "
          f"{'h_jitter':>10} {'v_jitter':>10}")
    for r in rows:
        print(f"{r['req']:>10} {r['real']:>10} {r['fps']:>6.0f} "
              f"{r['faces']:>4}/{FRAMES} {r['h_jitter']:>10.4f} {r['v_jitter']:>10.4f}")
    print("\nMENOS jitter = senal mas precisa. Buscamos el mejor jitter con FPS aceptable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
