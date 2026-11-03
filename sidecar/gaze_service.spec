# PyInstaller spec: empaqueta el sidecar de mirada (modo servicio) como un
# bundle onedir `gaze_service/` que la app de escritorio lanza.
#
# Build:  .venv/Scripts/python.exe -m PyInstaller gaze_service.spec --noconfirm
# Salida: dist/gaze_service/gaze_service.exe
from PyInstaller.utils.hooks import collect_all, copy_metadata

# El modelo de MediaPipe (parche de ojo / iris) va junto al exe bajo models/.
datas = [("models/face_landmarker.task", "models"),
         ("models/gaze_cnn.onnx", "models"),
         ("models/gaze_cnn.meta.json", "models")]
for package in ("mediapipe", "opencv-python", "numpy", "onnxruntime"):
    datas += copy_metadata(package)
binaries = []
hiddenimports = []

# MediaPipe trae datos (.tflite/.binarypb) y binarios nativos: recolectar todo.
for pkg in ("mediapipe", "onnxruntime"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # E1 usa ONNX; los frameworks de entrenamiento siguen fuera del runtime.
    # (matplotlib/PIL SÍ hacen falta: mediapipe.drawing_utils los importa.)
    excludes=["torch", "scipy", "tensorflow"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gaze_service",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # sin ventana de consola (la lanza la app de escritorio).
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="gaze_service",
)
