"""Prueba de webcam + MediaPipe FaceLandmarker (API Tasks). Headless.
Calienta la camara, da cuenta regresiva, captura ~5s, mide brillo y guarda un
frame de muestra para inspeccion.

Uso:  .venv/Scripts/python.exe _camera_check.py
"""
import os
import sys
import time

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

CAM_INDEX = 0
WARMUP = 15
N_FRAMES = 120
HERE = os.path.dirname(__file__)
MODEL_PATH = os.path.join(HERE, "models", "face_landmarker.task")
SAMPLE_JPG = os.path.join(HERE, "_camera_sample.jpg")

LEFT_IRIS = [468, 469, 470, 471, 472]


def main():
    if not os.path.exists(MODEL_PATH):
        print("ERROR: falta el modelo:", MODEL_PATH)
        return 1

    cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("ERROR: no se pudo abrir la webcam (indice %d)" % CAM_INDEX)
        return 1
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Webcam abierta: {w}x{h}. Calentando...")
    for _ in range(WARMUP):
        cap.read()

    print(">>> MIRA A LA CAMARA. Capturo en:")
    for c in (3, 2, 1):
        print(f"    {c}...", flush=True)
        time.sleep(1)
    print(">>> Capturando ~5s, mira a la pantalla y mueve un poco los ojos.")

    options = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        output_facial_transformation_matrixes=True,
    )
    landmarker = vision.FaceLandmarker.create_from_options(options)

    detected, iris_ok, pose_ok, samples = 0, 0, 0, []
    brightness = []
    saved = False
    t0 = time.time()
    for i in range(N_FRAMES):
        ok, frame = cap.read()
        if not ok:
            continue
        brightness.append(float(np.mean(frame)))
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = landmarker.detect_for_video(mp_image, int((time.time() - t0) * 1000))
        if res.face_landmarks:
            detected += 1
            lm = res.face_landmarks[0]
            if len(lm) >= 478:
                iris_ok += 1
                cx = sum(lm[j].x for j in LEFT_IRIS) / len(LEFT_IRIS)
                cy = sum(lm[j].y for j in LEFT_IRIS) / len(LEFT_IRIS)
                samples.append((round(cx, 3), round(cy, 3)))
            if res.facial_transformation_matrixes:
                pose_ok += 1
            if not saved:  # guarda el primer frame con rostro
                cv2.imwrite(SAMPLE_JPG, frame)
                saved = True
    if not saved and brightness:  # sin rostro: guarda un frame igual para ver
        ok, frame = cap.read()
        if ok:
            cv2.imwrite(SAMPLE_JPG, frame)
    dt = time.time() - t0
    cap.release()
    landmarker.close()

    fps = N_FRAMES / dt if dt else 0
    mean_b = sum(brightness) / len(brightness) if brightness else 0
    print(f"\nFrames: {N_FRAMES} en {dt:.1f}s (~{fps:.0f} FPS)")
    print(f"Brillo medio del frame: {mean_b:.1f}/255  (si ~0 -> camara negra/tapada)")
    print(f"Rostro detectado: {detected}/{N_FRAMES}")
    print(f"Iris (478 lmk):   {iris_ok}/{N_FRAMES}")
    print(f"Pose de cabeza:   {pose_ok}/{N_FRAMES}")
    print(f"Frame de muestra guardado: {SAMPLE_JPG}")
    if samples:
        print(f"Centro iris izq (muestras): {samples[:6]}")
        print("OK: MediaPipe rastrea rostro + iris + pose.")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
