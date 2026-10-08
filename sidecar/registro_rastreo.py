"""Registro de la calidad del rastreo durante el uso (modo servicio).

Cada INTERVALO_S segundos escribe una linea JSON con lo que paso en esa ventana:
fotogramas leidos, fallos de camara, fotogramas sin rostro, con los ojos
cerrados y clics por parpadeo. Es lo que permite saber despues si un ensayo
lento fue lento por el participante o porque el rastreo se perdio.

Va a %LOCALAPPDATA%\\InteractorGate\\registros\\<codigo>\\rastreo_<fecha>.jsonl,
junto a los archivos de sesion que escribe la app (TelemetryService). Solo
cuenta: no guarda imagenes ni coordenadas.
"""
import json
import os
import re
import time

INTERVALO_S = 10.0


def _archivo():
    usuario = re.sub(r"[^A-Za-z0-9_-]", "", os.environ.get("IG_USUARIO", ""))
    base = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "InteractorGate", "registros", usuario or "sin_codigo",
    )
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"rastreo_{time.strftime('%Y%m%d')}.jsonl")


class RegistroRastreo:
    def __init__(self):
        try:
            self._ruta = _archivo()
        except OSError:
            self._ruta = None   # sin disco: el rastreo sigue, sin registro
        self._t0 = time.time()
        self._reinicia()
        self._escribe({"evento": "inicio"})

    def _reinicia(self):
        self.leidos = self.fallos_camara = self.sin_rostro = 0
        self.ojos_cerrados = self.clics = 0

    def tick(self):
        """Llamar una vez por vuelta del bucle; vuelca la ventana si toca."""
        ahora = time.time()
        dt = ahora - self._t0
        if dt < INTERVALO_S:
            return
        self._escribe({
            "evento": "ventana",
            "segundos": round(dt, 2),
            "leidos": self.leidos,
            "fps": round(self.leidos / dt, 1),
            "fallos_camara": self.fallos_camara,
            "sin_rostro": self.sin_rostro,
            "ojos_cerrados": self.ojos_cerrados,
            "clics": self.clics,
        })
        self._t0 = ahora
        self._reinicia()

    def _escribe(self, campos):
        if self._ruta is None:
            return
        linea = {"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **campos}
        try:
            with open(self._ruta, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(linea) + "\n")
        except OSError:
            pass
