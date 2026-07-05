"""Diagnostico del modo Mouse: por que no se mueve el cursor.

Imprime cada segundo: frames, rostros detectados, mirada cruda (gx,gy), punto
suavizado, pixeles objetivo, y la posicion REAL del cursor leida con GetCursorPos
tras SetCursorPos (para saber si Windows acepto el movimiento).
"""
import ctypes
from ctypes import wintypes
import time

import cv2

import config
from calibration import GazeMapper, load_calibration
from eye_tracker import EyeTracker, feature_vector
from smoothing import GazeSmoother2D

_user32 = ctypes.windll.user32


def _get_cursor():
    pt = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def main():
    saved = load_calibration()
    if not saved:
        print("ERROR: sin calibracion")
        return 1
    mapper = GazeMapper.from_dict(saved["gaze"])
    print("screen:", config.SCREEN_WIDTH, config.SCREEN_HEIGHT)

    cap = cv2.VideoCapture(config.CAM_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("ERROR: sin webcam")
        return 1
    for _ in range(15):
        cap.read()
    tracker = EyeTracker()
    smoother = GazeSmoother2D(mincutoff=0.5, beta=0.008)
    W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT

    ts, frames, faces, moved, held, railed = 0, 0, 0, 0, 0, 0
    last = {"gx": None, "gy": None, "px": None, "py": None}
    t0 = time.time()
    next_report = t0 + 1
    while time.time() - t0 < 12:
        ok, frame = cap.read()
        if not ok:
            continue
        frames += 1
        ts += 33
        res = tracker.process(frame, ts)
        if res is not None:
            faces += 1
            openness = (res.right.openness + res.left.openness) / 2
            if openness < config.OPEN_GAZE_THRESHOLD:
                held += 1                      # ojo cerrado: se mantiene posicion
            else:
                gx, gy = mapper.transform(feature_vector(res))
                sx, sy = smoother.update(gx, gy, time.time())
                px, py = int(sx * W), int(sy * H)
                _user32.SetCursorPos(px, py)
                moved += 1
                if px <= 1 or px >= W - 1 or py <= 1 or py >= H - 1:
                    railed += 1
                last.update(gx=round(gx, 3), gy=round(gy, 3), px=px, py=py)
        if time.time() >= next_report:
            print(f"t{int(time.time()-t0)}s faces={faces} moved={moved} held={held} "
                  f"railed={railed} gaze=({last['gx']},{last['gy']}) "
                  f"px=({last['px']},{last['py']}) cursor={_get_cursor()}")
            next_report += 1

    cap.release()
    tracker.close()
    pct = 100 * railed / max(moved, 1)
    print(f"\nTotal frames={frames} faces={faces} moved={moved} "
          f"held(parpadeo)={held} railed={railed} ({pct:.0f}% en el borde)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
