"""Prueba de humo de la ventana de encuadre SIN camara: ejercita medir(),
evaluar() y pinta() con un rostro sintetico y un mapper v4 real.

Existe porque importar el modulo no ejecuta nada de esto, y dos veces se ha
colado un fallo que solo aparecia al detectar el primer rostro.
"""
import os
import sys
from collections import deque

import cv2
import numpy as np

SIDECAR = r"C:\Users\usurio\Desktop\tesis\InteractorGate-Flutter\sidecar"
OUT = r"C:\Users\usurio\AppData\Local\Temp\claude\C--Users-usurio-Desktop-tesis\78a24ab9-b7d8-4b37-bdeb-6b9b41cc70e5\scratchpad"
sys.path.insert(0, SIDECAR)
os.chdir(SIDECAR)

import calibration as c
import encuadre as e
from eye_tracker import EyeData, FaceResult

rng = np.random.default_rng(4)
W_CM, H_CM = 53.0, 30.0


def features(t, head):
    hx, hy, hz = head
    z = abs(hz)
    ex = ((t[0] - 0.5) * W_CM - hx) / z
    ey = ((t[1] - 0.5) * H_CM - hy) / z
    f = [0.0] * 15
    f[0] = 0.50 + 0.28 * ex + rng.normal(0, 0.004)
    f[2] = 0.50 + 0.26 * ex + rng.normal(0, 0.004)
    f[4] = 0.01 + 0.10 * ex
    f[6] = 0.01 + 0.10 * ex
    f[1] = 0.42 + 0.30 * ey + rng.normal(0, 0.004)
    f[3] = 0.42 + 0.28 * ey + rng.normal(0, 0.004)
    f[5] = 0.12 * ey
    f[7] = 0.12 * ey
    f[12], f[13], f[14] = hx, hy, hz
    return f


# Mapper v4 real, ajustado sobre datos sinteticos.
F, T = [], []
for p in [(x, y) for y in c.GY for x in c.GX]:
    for pose in [(0, 0, -47), (1.5, 1.0, -47), (-1.5, -1.0, -49)]:
        for _ in range(15):
            h = (pose[0] + rng.normal(0, .2), pose[1] + rng.normal(0, .2),
                 pose[2] + rng.normal(0, .2))
            F.append(features(p, h)); T.append(p)
mapper = c.GazeMapper().fit(F, T)
REF = {"head": np.array([0.0, 0.0, -47.0]), "creada": "2026-09-06T13:00:00",
       "mapper": mapper}


def cara_falsa(cx, cy, ipd_px, head, brillo=135):
    patch = np.full((36, 60), brillo, np.uint8)
    semi = ipd_px / 2 / 640
    f = features((0.5, 0.5), head)
    pose = np.eye(4)
    pose[:3, 3] = head
    r = EyeData(patch=patch, iris=(cx - semi, cy), openness=0.3,
                h_ratio=f[0], v_ratio=f[1], off=(f[4], f[5]))
    l = EyeData(patch=patch, iris=(cx + semi, cy), openness=0.3,
                h_ratio=f[2], v_ratio=f[3], off=(f[6], f[7]))
    return FaceResult(right=r, left=l, pose_matrix=pose)


def caso(nombre, cx, cy, ipd, head, brillo):
    hist = deque(maxlen=45)
    res = cara_falsa(cx, cy, ipd, head, brillo)
    frame = np.full((480, 640, 3), 60, np.uint8)
    cv2.ellipse(frame, (int(cx * 640), int(cy * 480 + 25)),
                (int(ipd * 1.15), int(ipd * 1.55)), 0, 0, 360,
                (brillo, brillo - 12, brillo - 25), -1)
    gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    for _ in range(12):
        m = e.medir(res, gris, hist)
    checks, margen = e.evaluar(m, REF)
    checks.insert(0, ("Rostro detectado", True, "si", ""))
    lienzo, todo_ok = e.pinta(frame, m, checks, margen, REF, None)
    cv2.imwrite(os.path.join(OUT, nombre), lienzo)
    print(f"\n== {nombre} (todo_ok={todo_ok}) ==")
    for et, ok, val, _ in checks:
        print(f"   {'OK' if ok else ' X'}  {et:<24}{val}")
    if margen:
        print(f"   sensibilidad {margen['sx']:.0f}/{margen['sy']:.0f} px/cm | "
              f"peor caso {margen['margen_cm_x']:.1f} cm")


caso("humo_bien.png", 0.50, 0.45, 56, (0.1, 0.0, -47.0), 135)
caso("humo_cerca.png", 0.58, 0.60, 88, (2.5, -2.0, -30.0), 60)
print("\nSin excepciones: medir/evaluar/pinta funcionan de punta a punta.")
