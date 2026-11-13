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
    telemetry_service.dart  # cola cifrada + confirmación de /api/logs/
    outbox_store.dart       # eventos pendientes separados por cuenta y backend
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

El login y el registro no abren la cámara ni mueven el cursor. Después de iniciar
sesión, pulsa **Calibrar y abrir tablero** y sigue los puntos. El control por
mirada y parpadeo empieza cuando el tablero ya está visible. **ESC** cancela la
calibración sin activar el seguimiento. También puedes elegir **Usar solo mouse**.
Al cerrar sesión o la aplicación se detiene el servicio de cámara.

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
Los eventos se conservan en una cola cifrada hasta confirmar su ID y propietario.
Las peticiones HTTP tienen un límite de 15 segundos por intento. Un cierre de
ensayo fallido conserva su contenido original hasta reintentar y confirmar el
avance local.

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

Las peticiones de login, registro y perfil esperan hasta 75 segundos para permitir
la conexión inicial con Azure SQL, cuyo backend tiene un límite de conexión de
60 segundos. El login muestra un mensaje durante la espera. No se reenvían
credenciales automáticamente; la telemetría conserva su límite de 15 segundos.

## Modo de estudio E2

Tras iniciar sesión, usa **Preparar estudio E2**. Confirma el orden de inclusión
del participante y selecciona práctica S1, S2 o S3. El programa conserva en este
equipo la asignación de listas y el avance de cada cuenta. Hay diez mensajes de
práctica antes de S2, y veinte ensayos en cada sesión de medición, en bloques
alternados de cinco con y sin predicción.

El banco actual es **provisional de piloto**. No usar sus listas como instrumento
validado sin revisar su equivalencia. Las instrucciones, el banco de frases y
las pruebas manuales están en [ESTUDIO_E2.md](docs/ESTUDIO_E2.md).

## Evaluación y análisis de la tesis

El modo de investigación puede analizar exportaciones E1/E2 y respuestas SUS/QUEST,
generar tablas CSV y figuras por sesión, y abrir un informe HTML local. Conserva
exclusiones y separa datos de piloto, sintéticos y población objetivo. La evaluación
textual offline compara una RNN experimental y un bigrama sin cambiar el predictor
desplegado. Métodos, comandos y límites en [ANALISIS_E1_E2.md](docs/ANALISIS_E1_E2.md).

## Instrumento técnico E1

Para investigar los fallos del seguimiento está disponible el
[diagnóstico visual](docs/DIAGNOSTICO_VISUAL.md), con apertura ocular, postura,
estimaciones antes/después del recorte y suavizado y registros numéricos locales.

El sidecar incluye un modo de investigación para comparar la CNN genérica y el
motor calibrado: fijación de puntos, celdas sin cursor, selección con cursor y
observación de activaciones. Conserva los fallos de seguimiento y guarda evidencia
local por participante y sesión, separada de E2. Preparación, denominadores y
límites de la comparación en [INSTRUMENTO_E1.md](docs/INSTRUMENTO_E1.md).

## Continuaciones de texto

La RNN propone palabras siguientes. En el teclado, termina la palabra y pulsa
**ESPACIO** para pedir continuaciones; mientras escribes una palabra parcial no
se muestran sugerencias. Los botones de palabras completas solicitan directamente
la continuación. Aceptar una sugerencia añade su texto con un solo espacio de
separación, sin reemplazar lo escrito, y solicita la continuación siguiente.
Cualquier edición descarta las respuestas anteriores. Regla y prueba local en
[SUGERENCIAS_E2.md](docs/SUGERENCIAS_E2.md).

## Permiso de cámara

La app no inicia la cámara en el acceso. Después de identificarse, al seleccionar
**Calibrar y abrir tablero** solicita autorización explícita. **Ahora no** o cerrar
el diálogo mantiene el servicio apagado; **Usar solo mouse** abre el tablero sin
cámara y permite también navegar por teclado físico. Tras aceptar y calibrar,
**Desactivar cámara** detiene el servicio y vuelve a la preparación. El permiso
se solicita de nuevo al volver a calibrar y no se conserva entre sesiones.
Esta autorización de la aplicación no sustituye el consentimiento informado del
estudio ni los permisos de cámara de Windows.

## Registro y exportación de ensayos

**Verificar y exportar sesión** consulta los registros mediante la API de la propia
cuenta y guarda un JSON en `Documentos/InteractorGate/E2`. El resumen reconstruye
los textos y señala huecos, duplicaciones o ensayos abiertos. La cola permite
seguir escribiendo durante una interrupción de entrega; iniciar o cerrar ensayos
requiere confirmación.

Contrato, evidencia de la prueba local y límites en
[TELEMETRIA_E2.md](docs/TELEMETRIA_E2.md). Para una validación aislada puede usarse
`--dart-define=IG_API_BASE_URL=http://127.0.0.1:8000`; la compilación distribuible
continúa apuntando a Azure por defecto. Publicar primero el backend v2.
