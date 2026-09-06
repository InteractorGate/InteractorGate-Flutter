"""Validacion de precision del reconocimiento ocular (pipeline REAL de la app).

Mide los criterios de aceptacion de la memoria (§4.2.4) sobre el motor que
realmente usa InteractorGate — MediaPipe FaceLandmarker + calibracion ridge por
usuario — y NO sobre el CNN de MPIIGaze:

  - Precision en reconocimiento ocular  > 90 %
  - Tasa de error                       < 10 %

Protocolo: se dibuja el tablero 4x2 en la MISMA posicion de pantalla que ocupa
en la aplicacion y se pide al usuario mirar una celda resaltada a la vez, en
orden aleatorio y con varias repeticiones. Por cada ensayo se descarta el
periodo de transicion sacadica, se capturan muestras durante la fijacion y se
toma la mediana como punto de mirada. Se considera ACIERTO si ese punto cae
dentro de la celda pedida (que es exactamente el criterio con el que el boton
dwell de la app se activa).

Ademas se registra el tiempo hasta seleccion por permanencia (dwell) para
documentar el coste temporal de una seleccion.

Uso:
    .venv/Scripts/python.exe bench_precision.py                # 3 repeticiones
    .venv/Scripts/python.exe bench_precision.py --reps 5
    .venv/Scripts/python.exe bench_precision.py --fullscreen   # tablero a pantalla completa

Requiere una calibracion previa:
    .venv/Scripts/python.exe main.py --calibrate
"""
import argparse
import ctypes
import json
import random
import statistics
import time
from ctypes import wintypes

import cv2
import numpy as np

import config
from calibration import GazeMapper, load_calibration
from eye_tracker import EyeTracker, feature_vector
from smoothing import GazeSmoother2D

WINDOW = "Validacion de precision - InteractorGate"

# Vocabulario del tablero de la app (lib/widgets/big_cell_board.dart).
GRID = [
    ["Si", "No", "Gracias", "Agua"],
    ["Comida", "Ayuda", "Teclado", "Borrar"],
]
ROWS, COLS = len(GRID), len(GRID[0])

SETTLE_S = 1.2        # transicion sacadica: se descarta
CAPTURE_S = 1.2       # ventana de fijacion: se mide
DWELL_S = 1.2         # permanencia que exige la app para seleccionar

# Geometria de la app (lib/screens/home_screen.dart + windows/runner/main.cpp).
WIN_W, WIN_H = 900, 640
APPBAR_H, PAD, TEXTBAR_H, GAP, SUGG_H = 56, 16, 90, 12, 72


# ─────────────────────────────────────────────────────────────────────────────
# Geometria: donde esta el tablero en pantalla
# ─────────────────────────────────────────────────────────────────────────────
def board_rect_from_running_app():
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


def board_rect_default():
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


def cell_rects(board):
    """Rect en pixeles de cada celda (incluye el padding de 6 px del boton)."""
    x0, y0, x1, y1 = board
    w, h = (x1 - x0) / COLS, (y1 - y0) / ROWS
    out = []
    for r in range(ROWS):
        for c in range(COLS):
            out.append({
                "word": GRID[r][c], "row": r, "col": c,
                "x0": x0 + c * w + 6, "y0": y0 + r * h + 6,
                "x1": x0 + (c + 1) * w - 6, "y1": y0 + (r + 1) * h - 6,
            })
    return out


def hit_cell(px, py, cells):
    """Celda que contiene el punto, o None si cae fuera del tablero."""
    for i, c in enumerate(cells):
        if c["x0"] <= px <= c["x1"] and c["y0"] <= py <= c["y1"]:
            return i
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Dibujo
# ─────────────────────────────────────────────────────────────────────────────
def draw(cells, target, msg="", gaze=None, progress=0.0):
    W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    canvas = np.zeros((H, W, 3), np.uint8)
    canvas[:] = (18, 18, 18)
    for i, c in enumerate(cells):
        p0 = (int(c["x0"]), int(c["y0"]))
        p1 = (int(c["x1"]), int(c["y1"]))
        activo = i == target
        cv2.rectangle(canvas, p0, p1, (60, 130, 60) if activo else (45, 45, 45), -1)
        cv2.rectangle(canvas, p0, p1, (120, 200, 120) if activo else (70, 70, 70), 2)
        if activo and progress > 0:
            bw = int((p1[0] - p0[0]) * min(progress, 1.0))
            cv2.rectangle(canvas, (p0[0], p1[1] - 8), (p0[0] + bw, p1[1]),
                          (90, 220, 90), -1)
        (tw, th), _ = cv2.getTextSize(c["word"], cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
        cv2.putText(canvas, c["word"],
                    ((p0[0] + p1[0] - tw) // 2, (p0[1] + p1[1] + th) // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                    (255, 255, 255) if activo else (170, 170, 170), 2)
    if gaze is not None:
        cv2.circle(canvas, (int(gaze[0]), int(gaze[1])), 10, (0, 160, 255), -1)
    if msg:
        cv2.putText(canvas, msg, (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                    (200, 200, 200), 2)
    cv2.imshow(WINDOW, canvas)
    cv2.waitKey(1)


# ─────────────────────────────────────────────────────────────────────────────
# Medicion
# ─────────────────────────────────────────────────────────────────────────────
def run(reps, fullscreen):
    saved = load_calibration()
    if not saved:
        raise SystemExit("No hay calibracion. Corre primero: python main.py --calibrate")
    mapper = GazeMapper.from_dict(saved["gaze"])

    W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    if fullscreen:
        board = (int(W * 0.05), int(H * 0.15), int(W * 0.95), int(H * 0.85))
        geom = "pantalla completa"
    else:
        board = board_rect_from_running_app() or board_rect_default()
        geom = ("ventana real de la app detectada"
                if board_rect_from_running_app() else "geometria nominal de la app")
    cells = cell_rects(board)

    bw, bh = board[2] - board[0], board[3] - board[1]
    print(f"Pantalla: {W}x{H}")
    print(f"Tablero ({geom}): x {board[0]}-{board[2]}, y {board[1]}-{board[3]}"
          f"  ({bw}x{bh} px)")
    print(f"Boton: {bw / COLS - 12:.0f}x{bh / ROWS - 12:.0f} px "
          f"= {(bw / COLS) / W * 100:.1f}% x {(bh / ROWS) / H * 100:.1f}% de pantalla")
    print(f"Ensayos: {len(cells)} celdas x {reps} repeticiones = {len(cells) * reps}\n")

    cap = config.open_camera()
    if not cap.isOpened():
        raise SystemExit("ERROR: webcam no disponible")
    for _ in range(15):
        cap.read()
    tracker = EyeTracker()

    cv2.namedWindow(WINDOW, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    orden = [i for i in range(len(cells)) for _ in range(reps)]
    random.Random(42).shuffle(orden)

    ts = 0
    ensayos = []
    for n, target in enumerate(orden, 1):
        c = cells[target]
        smoother = GazeSmoother2D(mincutoff=0.5, beta=0.008)

        # 1) Transicion: se descarta (el ojo viaja hasta el objetivo).
        t_end = time.time() + SETTLE_S
        while time.time() < t_end:
            ok, frame = cap.read()
            if not ok:
                continue
            ts += 33
            res = tracker.process(frame, ts)
            if res is not None and (res.right.openness + res.left.openness) / 2 >= \
                    config.OPEN_GAZE_THRESHOLD:
                gx, gy = mapper.transform(feature_vector(res))
                smoother.update(gx, gy, time.time())
            draw(cells, target, f"Mira: {c['word']}   ({n}/{len(orden)})")

        # 2) Fijacion: se mide.
        xs, ys = [], []
        dwell_ok_desde, dwell_time = None, None
        t0 = time.time()
        t_end = t0 + CAPTURE_S
        while time.time() < t_end:
            ok, frame = cap.read()
            if not ok:
                continue
            ts += 33
            res = tracker.process(frame, ts)
            if res is None:
                continue
            if (res.right.openness + res.left.openness) / 2 < config.OPEN_GAZE_THRESHOLD:
                continue
            gx, gy = mapper.transform(feature_vector(res))
            sx, sy = smoother.update(gx, gy, time.time())
            px, py = sx * W, sy * H
            xs.append(px)
            ys.append(py)

            # Permanencia continua dentro de la celda pedida = seleccion.
            if hit_cell(px, py, cells) == target:
                dwell_ok_desde = dwell_ok_desde or time.time()
                if dwell_time is None and time.time() - dwell_ok_desde >= DWELL_S:
                    dwell_time = time.time() - t0
            else:
                dwell_ok_desde = None

            prog = 0.0 if dwell_ok_desde is None else \
                (time.time() - dwell_ok_desde) / DWELL_S
            draw(cells, target, f"Mira: {c['word']}   ({n}/{len(orden)})",
                 gaze=(px, py), progress=prog)

        if not xs:
            print(f"  {n:>3}/{len(orden)}  {c['word']:<9} SIN MUESTRAS (rostro no detectado)")
            continue

        mx, my = statistics.median(xs), statistics.median(ys)
        sel = hit_cell(mx, my, cells)
        acierto = sel == target
        ensayos.append({
            "objetivo": c["word"], "seleccion": cells[sel]["word"] if sel is not None else None,
            "acierto": acierto,
            "err_x_px": mx - (c["x0"] + c["x1"]) / 2,
            "err_y_px": my - (c["y0"] + c["y1"]) / 2,
            "muestras": len(xs),
            "dwell_s": dwell_time,
        })
        marca = "OK " if acierto else "X  "
        destino = cells[sel]["word"] if sel is not None else "fuera del tablero"
        print(f"  {n:>3}/{len(orden)}  {c['word']:<9} {marca} -> {destino:<18}"
              f" err=({mx - (c['x0'] + c['x1']) / 2:>+6.0f},"
              f"{my - (c['y0'] + c['y1']) / 2:>+6.0f}) px"
              + (f"  dwell={dwell_time:.2f}s" if dwell_time else "  dwell=no"))

        # Pausa entre ensayos.
        draw(cells, None, "...")
        time.sleep(0.4)

    cap.release()
    cv2.destroyAllWindows()
    tracker.close()
    return ensayos, board, (W, H)


def report(ensayos, board, screen):
    if not ensayos:
        print("\nSin ensayos validos.")
        return
    W, H = screen
    n = len(ensayos)
    aciertos = sum(e["acierto"] for e in ensayos)
    acc = aciertos / n * 100
    ex = [abs(e["err_x_px"]) for e in ensayos]
    ey = [abs(e["err_y_px"]) for e in ensayos]
    dwells = [e["dwell_s"] for e in ensayos if e["dwell_s"] is not None]

    print("\n" + "=" * 70)
    print("RESULTADO — criterios de la memoria §4.2.4")
    print("=" * 70)
    print(f"  Ensayos validos                 {n}")
    print(f"  Precision de reconocimiento     {acc:.1f} %"
          f"   [criterio > 90 %]  {'CUMPLE' if acc > 90 else 'NO CUMPLE'}")
    print(f"  Tasa de error                   {100 - acc:.1f} %"
          f"   [criterio < 10 %]  {'CUMPLE' if 100 - acc < 10 else 'NO CUMPLE'}")
    print(f"\n  Error absoluto medio  X         {statistics.mean(ex):.0f} px "
          f"({statistics.mean(ex) / W * 100:.1f} % de pantalla)")
    print(f"  Error absoluto medio  Y         {statistics.mean(ey):.0f} px "
          f"({statistics.mean(ey) / H * 100:.1f} % de pantalla)")
    if dwells:
        print(f"\n  Seleccion por permanencia       {len(dwells)}/{n} ensayos "
              f"({len(dwells) / n * 100:.0f} %)")
        print(f"  Tiempo medio hasta seleccion    {statistics.mean(dwells):.2f} s")

    print("\n  Aciertos por celda:")
    por_celda = {}
    for e in ensayos:
        por_celda.setdefault(e["objetivo"], []).append(e["acierto"])
    for palabra, vals in por_celda.items():
        a = sum(vals) / len(vals) * 100
        print(f"    {palabra:<9} {sum(vals)}/{len(vals)}  {a:>5.1f} %  "
              + "#" * int(a / 5))

    salida = {
        "pantalla": [W, H],
        "tablero_px": list(board),
        "ensayos": n,
        "precision_pct": round(acc, 2),
        "tasa_error_pct": round(100 - acc, 2),
        "error_medio_x_px": round(statistics.mean(ex), 1),
        "error_medio_y_px": round(statistics.mean(ey), 1),
        "error_medio_x_pct_pantalla": round(statistics.mean(ex) / W * 100, 2),
        "error_medio_y_pct_pantalla": round(statistics.mean(ey) / H * 100, 2),
        "seleccion_dwell_ratio": round(len(dwells) / n, 3),
        "dwell_medio_s": round(statistics.mean(dwells), 2) if dwells else None,
        "por_celda": {k: round(sum(v) / len(v) * 100, 1) for k, v in por_celda.items()},
        "detalle": ensayos,
    }
    with open("resultados_precision.json", "w", encoding="utf-8") as fh:
        json.dump(salida, fh, indent=2, ensure_ascii=False)
    print("\n  Guardado en sidecar/resultados_precision.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=3,
                    help="repeticiones por celda (por defecto 3 -> 24 ensayos)")
    ap.add_argument("--fullscreen", action="store_true",
                    help="tablero a pantalla completa en vez de la geometria de la app")
    args = ap.parse_args()
    report(*run(args.reps, args.fullscreen))
