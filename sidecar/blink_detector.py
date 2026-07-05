"""Deteccion de parpadeo a partir de la apertura del ojo (para el "clic").

Un parpadeo = el ojo se cierra (apertura < umbral) durante >= min_frames y luego
se vuelve a abrir. Se dispara UNA vez al reabrir, con un tiempo de refractario
para no encadenar clics.
"""
import time


class BlinkDetector:
    def __init__(self, threshold=0.18, min_frames=2, refractory_s=0.6):
        self.threshold = threshold
        self.min_frames = min_frames
        self.refractory_s = refractory_s
        self._closed = 0
        self._last_blink = 0.0

    def detect(self, openness):
        """Devuelve True en el frame donde se completa un parpadeo."""
        now = time.time()
        blink = False
        if openness < self.threshold:
            self._closed += 1
        else:
            if (self._closed >= self.min_frames
                    and now - self._last_blink > self.refractory_s):
                blink = True
                self._last_blink = now
            self._closed = 0
        return blink
