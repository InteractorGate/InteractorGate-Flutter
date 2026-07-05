"""Deteccion facial + extraccion de ojos con MediaPipe FaceLandmarker (API Tasks).

Dado un frame BGR de la webcam devuelve, por ojo, un parche en escala de grises
listo para el CNN (H x W), ademas del centro del iris, la apertura del ojo (para
parpadeo) y la matriz de pose de cabeza. Todo lo que el resto del tracker (CNN,
calibracion, blink) necesita sale de aqui.
"""
import math
import os
from dataclasses import dataclass

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

_HERE = os.path.dirname(__file__)
MODEL_PATH = os.path.join(_HERE, "models", "face_landmarker.task")

# Landmarks de FaceLandmarker (478 puntos, incluye iris).
# Ojo derecho de la imagen (izquierdo del sujeto) e izquierdo de la imagen.
RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
LEFT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
RIGHT_IRIS = [468, 469, 470, 471, 472]
LEFT_IRIS = [473, 474, 475, 476, 477]
# Para apertura (EAR simple): (arriba, abajo, esquina_int, esquina_ext)
RIGHT_LID = (159, 145, 133, 33)
LEFT_LID = (386, 374, 362, 263)


@dataclass
class EyeData:
    patch: np.ndarray          # (H, W) uint8 gris, parche del ojo para el CNN
    iris: tuple                # (x, y) normalizado [0..1] del centro del iris
    openness: float            # apertura vertical/horizontal (para parpadeo)
    h_ratio: float             # iris en X relativo a las esquinas (0=int, 1=ext)
    v_ratio: float             # iris en Y relativo a los parpados (0=arriba, 1=abajo)


@dataclass
class FaceResult:
    right: EyeData
    left: EyeData
    pose_matrix: np.ndarray    # (4,4) transformacion facial, o None


def head_angles(pose_matrix):
    """(yaw, pitch) de la cabeza a partir de la matriz de pose facial (rad)."""
    if pose_matrix is None:
        return (0.0, 0.0)
    R = pose_matrix[:3, :3]
    sy = math.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
    pitch = math.atan2(-R[2, 0], sy)
    yaw = math.atan2(R[1, 0], R[0, 0])
    return (float(yaw), float(pitch))


def feature_vector(face):
    """Vector de features de mirada (12D) para el calibrador:
    iris relativo al ojo (invariante a la cabeza) + iris crudo (mas rango) +
    pose de cabeza + apertura del parpado (pista vertical fuerte: al mirar abajo
    el ojo se cierra, al mirar arriba se abre)."""
    r, l = face.right, face.left
    yaw, pitch = head_angles(face.pose_matrix)
    return [
        r.h_ratio, r.v_ratio, l.h_ratio, l.v_ratio,
        r.iris[0], r.iris[1], l.iris[0], l.iris[1],
        yaw, pitch,
        r.openness, l.openness,
    ]


class EyeTracker:
    """Extrae parches de ojo + features de cada frame usando MediaPipe."""

    def __init__(self, patch_h=36, patch_w=60, margin=0.4):
        self.patch_h = patch_h
        self.patch_w = patch_w
        self.margin = margin
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)

    def process(self, frame_bgr, timestamp_ms):
        """Devuelve FaceResult o None si no hay rostro."""
        h, w = frame_bgr.shape[:2]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = self._landmarker.detect_for_video(mp_image, int(timestamp_ms))
        if not res.face_landmarks:
            return None
        lm = res.face_landmarks[0]
        pose = None
        if res.facial_transformation_matrixes:
            pose = np.array(res.facial_transformation_matrixes[0]).reshape(4, 4)

        right = self._eye(gray, lm, RIGHT_EYE, RIGHT_IRIS, RIGHT_LID, w, h, flip=False)
        # El ojo izquierdo se voltea horizontalmente para igualar la orientacion
        # con la que se entreno (convencion tipo MPIIGaze: ambos como ojo derecho).
        left = self._eye(gray, lm, LEFT_EYE, LEFT_IRIS, LEFT_LID, w, h, flip=True)
        return FaceResult(right=right, left=left, pose_matrix=pose)

    def _eye(self, gray, lm, eye_idx, iris_idx, lid_idx, w, h, flip):
        xs = [lm[i].x * w for i in eye_idx]
        ys = [lm[i].y * h for i in eye_idx]
        cx = sum(iris_idx_x := [lm[i].x for i in iris_idx]) / len(iris_idx)
        cy = sum(lm[i].y for i in iris_idx) / len(iris_idx)

        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        bw, bh = x1 - x0, y1 - y0
        # Forzar la relacion de aspecto del parche (W:H) y agregar margen.
        target_ratio = self.patch_w / self.patch_h
        cxp, cyp = (x0 + x1) / 2, (y0 + y1) / 2
        if bw / max(bh, 1e-6) < target_ratio:
            bw = bh * target_ratio
        else:
            bh = bw / target_ratio
        bw *= (1 + self.margin)
        bh *= (1 + self.margin)
        rx0 = int(max(0, cxp - bw / 2)); rx1 = int(min(w, cxp + bw / 2))
        ry0 = int(max(0, cyp - bh / 2)); ry1 = int(min(h, cyp + bh / 2))
        crop = gray[ry0:ry1, rx0:rx1]
        if crop.size == 0:
            patch = np.zeros((self.patch_h, self.patch_w), np.uint8)
        else:
            patch = cv2.resize(crop, (self.patch_w, self.patch_h))
            if flip:
                patch = cv2.flip(patch, 1)

        # Apertura del ojo (EAR simple): alto / ancho.
        top, bot, ci, ce = lid_idx
        vert = abs(lm[top].y - lm[bot].y) * h
        horiz = abs(lm[ci].x - lm[ce].x) * w
        openness = float(vert / max(horiz, 1e-6))

        # Posicion del iris relativa al ojo (invariante a la posicion de la
        # cabeza): 0..1 entre esquina interna/externa y entre parpados.
        denom_x = lm[ce].x - lm[ci].x
        denom_y = lm[bot].y - lm[top].y
        h_ratio = float((cx - lm[ci].x) / denom_x) if abs(denom_x) > 1e-6 else 0.5
        v_ratio = float((cy - lm[top].y) / denom_y) if abs(denom_y) > 1e-6 else 0.5
        return EyeData(patch=patch, iris=(round(cx, 4), round(cy, 4)),
                       openness=round(openness, 4),
                       h_ratio=round(h_ratio, 4), v_ratio=round(v_ratio, 4))

    def close(self):
        self._landmarker.close()
