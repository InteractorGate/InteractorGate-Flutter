"""Inferencia ligera del CNN de mirada (ONNX Runtime, sin PyTorch).

Carga el artefacto exportado del backend (`gaze_cnn.onnx` + `gaze_cnn.meta.json`)
y estima la direccion de mirada (pitch, yaw) a partir de un parche de ojo en
escala de grises. Pensado para empaquetarse en el ejecutable del tracker.
"""
import json
import os

import numpy as np
import onnxruntime as ort

_HERE = os.path.dirname(__file__)
DEFAULT_ONNX = os.path.join(_HERE, "models", "gaze_cnn.onnx")
DEFAULT_META = os.path.join(_HERE, "models", "gaze_cnn.meta.json")


class GazeModel:
    """CNN appearance-based: parche de ojo (H x W, gris) -> (pitch, yaw) rad."""

    def __init__(self, onnx_path=DEFAULT_ONNX, meta_path=DEFAULT_META):
        self.session = ort.InferenceSession(
            onnx_path, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)
        self.img_h, self.img_w = meta["image_size"]
        self.mean = float(meta["norm"]["mean"])
        self.std = float(meta["norm"]["std"])

    def predict(self, patches):
        """patches: (N, H, W) o (H, W) uint8/float en [0,255]. Devuelve (N, 2)."""
        arr = np.asarray(patches, dtype=np.float32)
        if arr.ndim == 2:
            arr = arr[None, :, :]
        x = (arr / 255.0 - self.mean) / self.std
        x = x[:, None, :, :].astype(np.float32)          # (N, 1, H, W)
        out = self.session.run(None, {self.input_name: x})[0]
        return out                                        # (N, 2) = pitch, yaw
