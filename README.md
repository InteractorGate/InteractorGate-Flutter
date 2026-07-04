# InteractorGate — Frontend (Flutter Desktop)

App de escritorio (Windows) del proyecto **InteractorGate**: tablero de
comunicación accesible controlado por **mirada y parpadeo**, con predicción de
frases (RNN del backend) y teclado de teclas grandes por **permanencia (dwell)**.

## Arquitectura

```
lib/
  main.dart                 # composición: servicios + providers
  app.dart                  # MaterialApp + AuthGate (login/home según sesión)
  config/                   # URLs de API y tema accesible
  models/                   # User, Prediction
  services/
    api_client.dart         # HTTP + Bearer JWT + refresh automático (401→refresh→retry)
    auth_service.dart       # register / login / me / logout
    prediction_service.dart # POST /api/predictions/ (RNN de texto)
    telemetry_service.dart  # POST /api/logs/ (best-effort)
    token_store.dart        # tokens en almacenamiento seguro (Windows Credential Manager)
    gaze_bridge.dart        # cliente TCP del sidecar de rastreo ocular (opcional)
  state/                    # AuthController, SessionController (ChangeNotifier)
  screens/                  # login, register, home (tablero)
  widgets/                  # DwellButton, DwellKeyboard, SuggestionBar, ComposedTextBar
sidecar/
  gaze_server.py            # publica la mirada del tracker Python por TCP
```

## Requisitos

- Flutter 3.32+ (`C:\Users\LIAN\Desktop\FlutterSDK\flutter`).
- El **backend** corriendo (local en `http://localhost:8000` o Azure).
  Cambia el destino en `lib/config/api_config.dart` (`useProd`).

## Cómo correr

```powershell
$env:Path = "C:\Users\LIAN\Desktop\FlutterSDK\flutter\bin;$env:Path"
flutter pub get
flutter run -d windows
```

## Rastreo ocular — dos modos

La app funciona **con o sin** el sidecar de mirada:

1. **Modo Mouse (funciona ya):** ejecuta el tracker Python existente
   (`python main.py` en el repo `InteractorGate`). Ese tracker **mueve el cursor
   del SO con la mirada y hace clic al parpadear**. Los botones dwell de esta app
   responden al puntero → escribes con la mirada sin nada más. El chip de estado
   muestra **"Mouse"**.

2. **Modo Mirada (integración fina):** ejecuta el sidecar, que envía las
   coordenadas de mirada por TCP a la app (para telemetría con coords reales y
   futuras funciones):
   ```powershell
   $env:IG_TRACKER_REPO = "C:\Users\LIAN\Documents\InteractorGate"
   python sidecar/gaze_server.py
   ```
   El chip de estado cambia a **"Mirada"** al conectar.

> El backend recomienda (y este diseño respeta) que el rastreo en tiempo real
> corra en el **cliente**, no en el servidor. El backend solo recibe la
> **telemetría** de eventos vía `/api/logs/`.

## Flujo de integración con el backend

1. Registro/login → tokens JWT guardados de forma segura.
2. `Authorization: Bearer` en cada llamada; ante `401`, refresh automático con
   rotación de refresh token.
3. `session_start` al abrir; predicciones de texto para autocompletar frases;
   eventos `selection`/`dwell` a `/api/logs/`.

Contrato completo: `docs/API.md` del repo `ig-django-backend`.
