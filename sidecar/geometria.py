"""Donde esta el tablero de la app en la pantalla.

Vive aparte porque lo necesitan DOS sitios y tienen que coincidir: el benchmark,
para dibujar el tablero donde la app lo pone, y la calibracion, para calibrar
donde el tablero va a estar. El 2026-09-06 no coincidian -- la calibracion usaba
una banda central fija (0.20-0.80 de la pantalla) mientras el tablero real vive
en 0.63-0.94, porque la ventana de la app esta anclada abajo. La mitad inferior
del tablero caia fuera de la zona calibrada, el modelo extrapolaba justo donde
tenia que acertar, y salia un sesgo vertical sistematico de 94 px que provocaba
9 de los 12 fallos de una corrida de 32 ensayos.
"""
import ctypes
from ctypes import wintypes

import config

# Geometria de la app (lib/screens/home_screen.dart + windows/runner/main.cpp).
WIN_W, WIN_H = 900, 640
APPBAR_H, PAD, TEXTBAR_H, GAP, SUGG_H = 56, 16, 90, 12, 72


def rect_tablero_app_abierta():
    """Rect del tablero leyendo la ventana real de la app, si esta abierta."""
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, "interactor_gate")
    if not hwnd:
        return None
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    cw, ch = rect.right, rect.bottom
    top = pt.y + APPBAR_H + PAD + TEXTBAR_H + GAP + SUGG_H + GAP
    return (pt.x + PAD, top, pt.x + cw - PAD, pt.y + ch - PAD)


def rect_tablero_nominal():
    """Rect del tablero deducido de la geometria fija de la ventana."""
    user32 = ctypes.windll.user32
    area = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0)  # SPI_GETWORKAREA
    ox = area.left + ((area.right - area.left) - WIN_W) // 2
    oy = area.bottom - WIN_H
    cx, cy = ox + 1, oy + 31          # borde + barra de titulo
    cw, ch = WIN_W - 2, WIN_H - 32
    top = cy + APPBAR_H + PAD + TEXTBAR_H + GAP + SUGG_H + GAP
    return (cx + PAD, top, cx + cw - PAD, cy + ch - PAD)


def rect_tablero():
    """El tablero real si la app esta abierta; si no, el nominal."""
    return rect_tablero_app_abierta() or rect_tablero_nominal()


def zona_calibracion(margen=0.10, limite=0.97):
    """Region a calibrar, en fraccion de pantalla: el tablero mas un margen.

    Calibrar EXACTAMENTE el tablero dejaria sus bordes en el limite del ajuste,
    que es donde peor se porta; con margen, todo el tablero queda dentro y el
    modelo interpola en vez de extrapolar. El margen es una fraccion del tamano
    del tablero, no de la pantalla, para que escale si el tablero cambia.
    """
    x0, y0, x1, y1 = rect_tablero()
    W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    mx, my = (x1 - x0) * margen, (y1 - y0) * margen
    return (max(1 - limite, (x0 - mx) / W), max(1 - limite, (y0 - my) / H),
            min(limite, (x1 + mx) / W), min(limite, (y1 + my) / H))


def rejilla(n=4, margen=0.10):
    """Coordenadas (en fraccion de pantalla) de una rejilla n x n en la zona."""
    zx0, zy0, zx1, zy1 = zona_calibracion(margen)
    gx = [zx0 + (zx1 - zx0) * i / (n - 1) for i in range(n)]
    gy = [zy0 + (zy1 - zy0) * i / (n - 1) for i in range(n)]
    return [round(v, 4) for v in gx], [round(v, 4) for v in gy]


if __name__ == "__main__":
    W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    x0, y0, x1, y1 = rect_tablero()
    print(f"Pantalla {W}x{H}")
    print(f"Tablero  {x0:.0f}-{x1:.0f} x {y0:.0f}-{y1:.0f} px "
          f"= {x0 / W:.3f}-{x1 / W:.3f} x {y0 / H:.3f}-{y1 / H:.3f}")
    print(f"Zona a calibrar {tuple(round(v, 3) for v in zona_calibracion())}")
    gx, gy = rejilla()
    print(f"Rejilla X {gx}")
    print(f"        Y {gy}")
