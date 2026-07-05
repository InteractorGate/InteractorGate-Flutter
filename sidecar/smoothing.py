"""Filtro One-Euro para suavizar el punto de mirada.

Estable cuando la mirada esta fija (mata el temblor) y responsivo cuando se
mueve rapido (sin lag notable). Mejor que un EMA fijo para un cursor de mirada.
Ref: Casiez et al., "1e Filter" (CHI 2012).
"""
import math


class _LowPass:
    def __init__(self):
        self.y = None

    def filter(self, x, alpha):
        self.y = x if self.y is None else alpha * x + (1 - alpha) * self.y
        return self.y


class _OneEuro:
    def __init__(self, freq=30.0, mincutoff=0.6, beta=0.010, dcutoff=1.0):
        self.freq = freq
        self.mincutoff = mincutoff
        self.beta = beta
        self.dcutoff = dcutoff
        self._x = _LowPass()
        self._dx = _LowPass()
        self._last_t = None

    def _alpha(self, cutoff):
        tau = 1.0 / (2 * math.pi * cutoff)
        te = 1.0 / self.freq
        return 1.0 / (1.0 + tau / te)

    def filter(self, x, t):
        if self._last_t is not None and t > self._last_t:
            self.freq = 1.0 / (t - self._last_t)
        self._last_t = t
        prev = self._x.y if self._x.y is not None else x
        dx = (x - prev) * self.freq
        edx = self._dx.filter(dx, self._alpha(self.dcutoff))
        cutoff = self.mincutoff + self.beta * abs(edx)
        return self._x.filter(x, self._alpha(cutoff))


class GazeSmoother2D:
    """Suaviza (x, y) con dos filtros One-Euro independientes."""

    def __init__(self, mincutoff=0.6, beta=0.010):
        self._fx = _OneEuro(mincutoff=mincutoff, beta=beta)
        self._fy = _OneEuro(mincutoff=mincutoff, beta=beta)

    def update(self, x, y, t):
        return self._fx.filter(x, t), self._fy.filter(y, t)
