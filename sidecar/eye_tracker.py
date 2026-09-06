"""Deteccion facial + extraccion de ojos con MediaPipe FaceLandmarker (API Tasks).

Dado un frame BGR de la webcam devuelve, por ojo, un parche en escala de grises
listo para el CNN (H x W), ademas del centro del iris, la apertura del ojo (para
parpadeo) y la matriz de pose de cabeza. Todo lo que el resto del tracker (CNN,
calibracion, blink) necesita sale de aqui.
"""
import math
import os
import sys
from dataclasses import dataclass

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# Base de recursos: empaquetado (PyInstaller) los datos van a sys._MEIPASS;
# en desarrollo, junto a este archivo.
_BASE = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
MODEL_PATH = os.path.join(_BASE, "models", "face_landmarker.task")

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
    off: tuple                 # iris en el marco del PROPIO ojo (ver _eye)


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


def head_translation(pose_matrix):
    """Traslacion de la cabeza (x, y, z) desde la matriz de pose facial.

    Viene en las unidades del modelo facial canonico de MediaPipe (~cm), asi que
    sirve para medir CUANTO se movio la cabeza entre la calibracion y el uso: la
    causa candidata de que un mapeo recien calibrado deje de valer minutos
    despues. No entra en el vector de features; solo se registra para diagnostico.
    """
    if pose_matrix is None:
        return (0.0, 0.0, 0.0)
    return tuple(float(v) for v in pose_matrix[:3, 3])


# Version del vector de features. Una calibracion solo vale para la version con
# la que se hizo: si esto cambia, hay que recalibrar (load_calibration lo obliga).
FEATURES_VERSION = 2


def feature_vector(face):
    """Vector de features de mirada (12D) para el calibrador.

    v2 (2026-09-06). La v1 usaba el iris CRUDO (su coordenada en el encuadre) en
    las posiciones 4-7. Medido con la mirada fija y solo moviendo la cabeza: el
    99 % del error vertical lo explicaba la postura, a 1639 px de pantalla por cm
    de cabeza. El tablero tolera 77 px, o sea medio milimetro de cabeza. Inviable.

    Se sustituye por el iris en el marco del PROPIO ojo (`off`): invariante a
    donde este la cabeza, a la distancia y al giro de cabeza. La v1 ya tenia una
    feature asi para el vertical (`v_ratio`) pero se normaliza con la apertura
    del parpado, que se cierra al mirar abajo justo cuando el iris baja: la senal
    se cancela sola (0.404 -> 0.357 entre la fila de arriba y la de abajo de la
    rejilla). El ancho del ojo, en cambio, es rigido.

    Se conservan `v_ratio` y la apertura: aportan una pista vertical distinta y
    el ajuste ridge ya decide cuanto peso darles.
    """
    r, l = face.right, face.left
    yaw, pitch = head_angles(face.pose_matrix)
    return [
        r.h_ratio, r.v_ratio, l.h_ratio, l.v_ratio,
        r.off[0], r.off[1], l.off[0], l.off[1],
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

        # Iris en el marco del PROPIO ojo, en PIXELES (isotropo, no en las
        # coordenadas normalizadas de MediaPipe, que deforman x frente a y).
        # El eje va de la esquina interna a la externa y la unidad es el ancho
        # del ojo, que es rigido: no cambia al mirar arriba o abajo (a diferencia
        # de la apertura del parpado, que es lo que hacia inutil a v_ratio) ni al
        # acercarse a la camara. Al ser relativo al ojo, tampoco depende de donde
        # este la cabeza en el encuadre: eso es lo que se busca. Como el eje sigue
        # a las esquinas, tambien absorbe la inclinacion lateral de la cabeza.
        ax, ay = (lm[ce].x - lm[ci].x) * w, (lm[ce].y - lm[ci].y) * h
        ancho = math.hypot(ax, ay)
        if ancho > 1e-6:
            ux, uy = ax / ancho, ay / ancho          # unitario interna->externa
            dx = cx * w - (lm[ci].x + lm[ce].x) / 2 * w
            dy = cy * h - (lm[ci].y + lm[ce].y) / 2 * h
            off = (float((dx * ux + dy * uy) / ancho),      # a lo largo del ojo
                   float((-dx * uy + dy * ux) / ancho))     # perpendicular
        else:
            off = (0.0, 0.0)
        return EyeData(patch=patch, iris=(round(cx, 4), round(cy, 4)),
                       openness=round(openness, 4),
                       h_ratio=round(h_ratio, 4), v_ratio=round(v_ratio, 4),
                       off=(round(off[0], 5), round(off[1], 5)))

    def close(self):
        self._landmarker.close()
