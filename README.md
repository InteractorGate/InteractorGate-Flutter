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

- Flutter 3.44.0, compatible con las versiones fijadas en `pubspec.lock`.
- Visual Studio o Build Tools 2022 con C++ x64/x86, CMake, Windows SDK y ATL.
  ATL es necesario para compilar `flutter_secure_storage_windows` (`atlstr.h`).
- Modo de desarrollador de Windows habilitado para los enlaces de los plugins.
- El **backend** corriendo (local en `http://localhost:8000` o Azure).
  Cambia el destino en `lib/config/api_config.dart` (`useProd`).

## Cómo correr

```powershell
# Si usas el SDK temporal preparado en este equipo:
$env:Path = "$env:TEMP\ig-flutter-block1-sdk\bin;$env:Path"
flutter pub get --enforce-lockfile
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

1. Al abrir se limpia la autenticación local previa y se pide identificar al
   participante. Usar una cuenta seudónima distinta por persona (por ejemplo,
   `P01`, `P02`); no se crea ni utiliza una cuenta demo compartida.
   Para registrar una cuenta, usar un correo de estudio sin datos personales
   (por ejemplo, `p01@example.com`).
2. Registro/login → perfil autenticado → envío confirmado de `session_start` con
   un UUID nuevo. Solo entonces se abre el tablero.
3. `Authorization: Bearer` en cada llamada; ante `401`, refresh automático con
   rotación de refresh token.
4. Al cerrar sesión se esperan las operaciones pendientes y se confirma
   `session_end` antes de revocar los tokens. Después se limpian texto,
   sugerencias, UUID y ajustes del tablero. El siguiente login crea otra sesión.
5. Si falla el inicio, se mantiene el login. Si falla el cierre, se conserva la
   sesión y se muestra un error para reintentar. El cierre normal de la ventana
   solicita el mismo cierre de sesión antes de salir.

Una terminación forzada o un corte de energía no garantizan el envío del cierre.
Los eventos de selección siguen siendo best-effort; su entrega durable pertenece
al bloque de instrumentación de telemetría. Las peticiones HTTP tienen un límite
de 15 segundos por intento.

## Verificación de sesiones

El alcance, estado y criterios de cierre de los seis bloques se mantienen en el
[plan de validación E1 y E2](docs/PLAN_VALIDACION_E1_E2.md).

```powershell
flutter test test/session_lifecycle_test.dart
```

Prueba manual: entrar como `P01`, escribir, cerrar sesión y entrar como `P02`.
El tablero debe estar vacío y los registros deben tener UUID distintos y el
`user_id` de la cuenta correspondiente. Repetir con la red desconectada al cerrar:
la app debe conservar la sesión y permitir reintentar, sin cambiar de participante.

Contrato completo: `docs/API.md` del repo `ig-django-backend`.
