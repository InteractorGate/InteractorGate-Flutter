# Sidecar de rastreo ocular — InteractorGate

Tracker de mirada por **webcam** para la app Flutter. Corre como proceso Python
aparte: detecta el rostro/iris con **MediaPipe**, mapea la mirada a la pantalla
con una **calibración por usuario**, y en **modo Mouse** mueve el cursor del
sistema (+ clic al parpadear) para operar el tablero *dwell* de la app.

> El rastreo en tiempo real corre en el **cliente** (aquí), no en el backend.
> El CNN entrenado con MPIIGaze es el modelo de mirada validado del proyecto;
> este tracker usa MediaPipe + calibración porque el CNN sobre recortes crudos
> de webcam no generaliza (domain shift). El CNN se exporta a ONNX (`models/`)
> y queda disponible para inferencia/experimentos.

## Arquitectura

```
sidecar/
  eye_tracker.py      # MediaPipe FaceLandmarker (Tasks API): rostro/iris/pose ->
                      #   parche de ojo + features de mirada (12D)
  calibration.py      # GazeMapper: ridge por eje (X/Y desacoplados) sobre
                      #   features estandarizadas; rutina de calibracion 4x4
  smoothing.py        # Filtro One-Euro (estable al fijar, responsivo al mover)
  blink_detector.py   # Parpadeo desde la apertura del ojo (EAR) -> clic
  gaze_cnn.py         # Inferencia ONNX del CNN MPIIGaze (opcional)
  config.py           # Pantalla, indice de camara, umbrales
  main.py             # Modo Mouse (cursor+clic) y --calibrate
  gaze_server.py      # Modo Mirada (TCP a Flutter) — PENDIENTE de actualizar
  models/             # face_landmarker.task + gaze_cnn.onnx (+ meta)
```

**Precisión típica** (webcam, tras calibrar): horizontal ~5%, vertical ~10-13%
de la pantalla. El vertical es el límite del método (el iris casi no se mueve
arriba/abajo). Por eso el tablero de la app usa **celdas grandes**.

## Requisitos y entorno

MediaPipe **no** soporta Python 3.13, así que el sidecar usa un venv **3.12**
aislado (creado con `uv`), independiente del backend:

```powershell
# desde ig-django-backend (tiene uv en su venv):
.\.venv\Scripts\uv.exe venv --python 3.12 ..\InteractorGate-Flutter\sidecar\.venv
.\.venv\Scripts\uv.exe pip install --python ..\InteractorGate-Flutter\sidecar\.venv\Scripts\python.exe mediapipe opencv-python numpy onnxruntime
```

Modelos en `models/`: `face_landmarker.task` (MediaPipe) y `gaze_cnn.onnx`
(exportado con `python -m ai_modules.cnn.export_onnx` en el backend).

## Uso

```powershell
cd sidecar
# 1) Calibrar (mira los puntos rojos a pantalla completa). Guarda calibration.json
.\.venv\Scripts\python.exe main.py --calibrate

# 2) Modo Mouse: la mirada mueve el cursor; parpadeo = clic
.\.venv\Scripts\python.exe main.py                 # 45s por defecto
.\.venv\Scripts\python.exe main.py --duration 120
.\.venv\Scripts\python.exe main.py --no-click      # sin clic por parpadeo
```

Con la app Flutter abierta en el tablero, el modo Mouse permite seleccionar las
celdas grandes por *dwell* (posar la mirada) y/o parpadeo.

### Ajustes (`config.py`)
- `CAM_INDEX` — índice de webcam (override con env `IG_CAM_INDEX`). Cambia si se
  reconecta la cámara o si hay una **cámara virtual** (p. ej. OBS) ocupando el 0.
- `BLINK_THRESHOLD` / `OPEN_GAZE_THRESHOLD` — parpadeo y gating de ojo cerrado
  (evita que un parpadeo dispare el cursor).

## Consejos de precisión
- Webcam **centrada y a la altura de los ojos**; buena luz de frente.
- Cierra apps que usen la cámara (OBS/Zoom/Teams) antes de calibrar.
- Recalibra si mueves la cámara o cambian mucho las condiciones de luz.

## Pendiente
- `gaze_server.py` (modo Mirada / TCP → chip "Mirada" en Flutter) aún usa la API
  antigua imaginada; falta reescribirlo sobre estos módulos.
