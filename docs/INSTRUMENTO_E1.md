# Instrumento técnico E1 — piloto 1.0.5

El instrumento sustituye el benchmark de precisión anterior. Se ejecuta de forma
local, en la pantalla principal, sobre un tablero propio de ocho celdas. No envía
fotogramas al backend ni guarda imágenes. No selecciona elementos de otras apps.

## Preparar la ficha

Desde `sidecar`, con las dependencias de `requirements.txt` instaladas:

```powershell
python bench_precision.py --init-config e1_config.json
python bench_precision.py --config e1_config.json
```

El primer comando crea una plantilla sin sobrescribir una ficha existente.
Completar código seudónimo, grupo (`pilot` o `target`), dimensiones **visibles**
de la pantalla en milímetros y condiciones. Las dimensiones nulas impiden iniciar
la medición; no se deducen del modelo comercial ni del tamaño diagonal.

La plantilla incluye luz natural/artificial, distancias nominales de 50/70 cm y
postura habitual/variación permitida. El investigador define y documenta esta
variación sin forzar movimientos; la tesis no fija sus amplitudes. El orden de
condiciones se aleatoriza con la semilla registrada. Dentro de cada condición se
evalúa primero la CNN genérica y después el motor calibrado. Ambos reciben el
mismo orden de objetivos, con la misma repetición para permitir comparaciones
pareadas. Se calibra de nuevo por condición con 16 puntos; los nueve puntos de
evaluación son diferentes de los del ajuste. No se reutiliza ni sobrescribe la
calibración de la app de comunicación.

Si un punto de calibración reúne menos muestras válidas que el mínimo, el
instrumento muestra el recuento y los motivos disponibles (apertura de ojos,
rostro o cámara). **R** repite solo ese punto; **C** omite el motor calibrado y
deja la sesión incompleta; ESC interrumpe. Cada intento queda registrado y solo
el intento aceptado por punto entra al ajuste. No se rebaja automáticamente el
umbral ni se reutiliza una calibración anterior para aparentar que se completó.

En pilotos puede fijarse `engines` a `["mediapipe_ridge_calibrated"]` para
completar el motor pendiente en otra corrida. Conservar en `continuation_of` el
UUID y SHA-256 del informe previo. La continuación genera su propio UUID e
informe; no reescribe el anterior ni afirma que ambos se ejecutaron sin pausa.
El orden de objetivos permanece reproducible con la misma ficha y semilla.
Para `cohort=target` se exigen ambos motores en el orden del protocolo.

Antes de cada condición se miden por separado ojos–cámara y ojos–pantalla. La
ficha puede especificar `eye_x_mm` y `eye_y_mm`, desplazamientos de la proyección
de los ojos respecto del centro de la pantalla (derecha/abajo positivos). Cero
supone ojos centrados; registrar esa suposición o reemplazarla por medidas.
La ficha y el registro conservan geometría, postura, iluminación, distancias,
orden, versiones de paquetes, hashes de ambos modelos y coeficientes de ajuste.

El piloto técnico acordado utiliza 60 cm nominales, grupo `pilot`, postura
habitual y pantalla aproximadamente 344 × 195 mm. No sustituye la repetición a
50/70 cm y bajo las condiciones completas del protocolo.

## Tareas y denominadores

| Tarea | Presentación | Evidencia |
|---|---|---|
| Puntos | Nueve objetivos, sin mostrar la mirada | Error angular operativo por muestra y por objetivo; cobertura de seguimiento |
| Lazo abierto | Ocho celdas solicitadas, sin cursor estimado | Celda de la mediana de muestras válidas; aciertos / ensayos iniciados |
| Lazo cerrado | Cursor estimado visible | Primera selección por permanencia o parpadeo; celda, método y tiempo |
| Observación libre | Sin intención de seleccionar | Parpadeos, activaciones sobre celdas y clasificación posterior del observador |

La fijación descarta `settle_s` y mide durante `capture_s`. La selección admite
`selection_timeout_s`, independiente de la ventana de fijación. La permanencia
se reinicia al salir de una celda o perder seguimiento, como `DwellButton`;
no se atribuye al software una tolerancia de salida de 0,5 s que no implementa.

I-2 conserva los intentos sin muestras suficientes como fallos de seguimiento;
no desaparecen del denominador. Los no iniciados se marcan `not_run` y las
interrupciones permanecen explícitas. I-3 usa selecciones incorrectas / selecciones
confirmadas; no se calcula como `1 - I-2`. Los timeouts sin selección se reportan
aparte, y no hay tasa de error cuando no hubo confirmaciones. La coincidencia con
la celda solicitada es la definición operativa de intención en esa tarea.

En observación solo un parpadeo con mirada válida sobre una celda genera una
activación del tablero del instrumento. El parpadeo fuera de las celdas no cuenta
como activación. Al finalizar se revisa cada activación: **U** no intencionada,
**I** intencionada, **D** dudosa. Las dudosas o no revisadas impiden estimar la tasa
de falsas activaciones; los parpadeos por sí solos no la determinan. Se conserva
el tiempo real de observación, sin incluir la revisión del observador.

## Qué representa el error angular

Se calcula el ángulo entre dos rayos desde la posición declarada de los ojos al
punto estimado y al objetivo, usando dimensiones físicas y distancia. La CNN
genérica conserva el mapeo fijo de ±25° del backend, sin recortar los puntos fuera
de pantalla. También se guardan sus ángulos originales. **El error operativo en
pantalla no es el error angular nativo de la CNN sobre MPIIGaze.** No hay una
transformación extrínseca calibrada de las coordenadas normalizadas de MPIIGaze a
la pantalla de esta webcam. Tampoco se atribuye la diferencia entre motores solo
a calibración: cambian la representación y el estimador (CNN frente a MediaPipe
y ridge). Esta comparación evalúa los pipelines declarados y requiere revisión
metodológica antes de interpretarla como cumplimiento del umbral bibliográfico
de I-1. La posición ocular supuesta y las medidas aproximadas limitan los grados.

## Conservación y ejecución

Cada corrida crea `Documentos/InteractorGate/E1/<código>/<UUID>/`:

- `session.json`: ficha y todos los ensayos previstos, con IDs únicos.
- `events.jsonl`: eventos y muestras numéricas, escritos incrementalmente.
- `calibration_cN.json`: ajuste independiente por condición.
- `report.json`: intentos, pendientes, seguimiento y resultados por tarea.

ESC interrumpe y guarda los datos disponibles. Una terminación forzada puede
dejar el último ensayo abierto; `trial_start` sin `trial_end` se interpreta como
interrumpido al reconstruir. Nunca se sobrescribe una corrida previa. No subir
estos archivos al repositorio ni mezclar pilotos con población objetivo.

Pulsar ESPACIO entre tareas permite descansar. Se ofrecen pausas entre ensayos
tras diez minutos; el investigador supervisa el máximo de 45 minutos y la
interrupción ante fatiga o malestar. Las mediciones de cámara se detienen al
alcanzar 45 minutos, aunque una ventana de instrucciones puede seguir esperando.

En la instalación distribuida:

```powershell
& 'C:\Program Files\InteractorGate\gaze\gaze_service.exe' --e1-init-config 'C:\ruta\e1_config.json'
# Completar la ficha creada antes de ejecutar la prueba:
& 'C:\Program Files\InteractorGate\gaze\gaze_service.exe' --e1-config 'C:\ruta\e1_config.json'
```

El seguimiento de la app debe estar detenido para no disputar la webcam. E1 usa
un proceso propio y al terminar muestra la carpeta de resultados. No cambia
cuentas ni ensayos E2. Las pruebas automáticas se ejecutan con:

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
```

La validación funcional local se completó en dos corridas enlazadas: 26 ensayos
genéricos y una continuación de 26 ensayos calibrados. La publicación prevista
es [v1.0.5](https://github.com/InteractorGate/InteractorGate-Flutter/releases/tag/v1.0.5).
La recogida completa de E1 y la validación del desempeño ocular siguen pendientes.
La primera corrida local se interrumpió después de los 26 ensayos de la CNN
genérica: quedaron 26 ensayos completados y 26 del motor calibrado como `not_run`.
Se verificó que el informe se reconstruye exactamente desde `session.json` y
`events.jsonl`; la interrupción no se presenta como un recorrido completo.
Carpeta de evidencia: `LOCAL_E1_60/aec6d5c0-6f1f-4786-9615-28ed55815232`.
SHA-256 de `report.json`:
`ffdb2284c6220021d04083073de98299e9f1f95d29c1a736a243f5d955e93493`.

Verificación automática: 19 pruebas Python del instrumento aprobadas, análisis de
Flutter sin incidencias y 46 pruebas de Flutter aprobadas. El ejecutable incluye
ONNX Runtime, ambos artefactos de modelos y los diálogos del investigador. Se
reinicia el detector de parpadeo por ensayo para que un cierre de ojos anterior
a una pausa no se convierta en una activación del ensayo siguiente.

La segunda corrida (`c57fb58d-60b2-4eea-8ca5-16280a68a6a4`) completó los 26
ensayos genéricos, con un punto angular marcado sin seguimiento suficiente.
La calibración no obtuvo muestras válidas en el punto 12/16 (`0.92, 0.64`);
se conservaron los datos y los 26 ensayos calibrados quedaron como no ejecutados.
Se añadió el reintento explícito y se preparó una continuación solo del motor
calibrado, que se completó como se detalla a continuación. No se borra ni
reemplaza el fallo de calibración original.

## Piloto funcional completado el 3 de noviembre de 2026

La continuación `ab5e6aa3-c256-445a-890d-81d515baf94a` terminó con estado
`completed`, 26/26 ensayos y ninguno sin ejecutar: nueve puntos, ocho celdas en
lazo abierto, ocho selecciones en lazo cerrado y una observación. Su vínculo por
UUID y hash al informe genérico se comprobó. Ambos informes se reconstruyeron
exactamente desde sus journals y conservan el mismo orden de objetivos y modelos.

Se aceptaron 16 puntos de calibración con 531 muestras. Quedaron registrados 18
intentos fallidos por apertura de ojos inferior al umbral. El ajuste se reprodujo
desde los intentos aceptados y coincidió numéricamente con el modelo guardado.

| Motor | Puntos angulares medidos | Media operativa por objetivo | I-2 aciertos/intentos | I-3 incorrectas/confirmadas | Sin selección |
|---|---:|---:|---:|---:|---:|
| CNN genérica | 8/9 | 8,88° | 1/8 | 6/8 | 0 |
| Motor calibrado | 9/9 | 7,93° | 0/8 | 7/7 | 1 |

**La precisión obtenida es baja.** Completar el recorrido verifica el instrumento
de registro; no aprueba el seguimiento ocular para participantes ni demuestra
una mejora del motor calibrado. Antes de las pruebas con población objetivo se
deben revisar calibración, gating de apertura ocular y desempeño. Estos valores
operativos no acreditan el umbral bibliográfico del modelo CNN.

El usuario confirmó que provocó a propósito las cinco activaciones de la
observación calibrada y las marcó intencionales. Es una comprobación funcional,
no una observación válida de falsas activaciones espontáneas para I-4. El cero
del campo de activaciones no intencionadas del informe no se interpreta como una
tasa natural demostrada. Se conserva el etiquetado original.

La cámara estuvo a 60 cm; la distancia ojos–pantalla fue 62 cm en la corrida
genérica y 63 cm en la calibrada. Hubo una pausa entre corridas, ojos centrados
supuestos, pantalla aproximada de 344 × 195 mm, luz natural y postura habitual.
Se conservan estas diferencias; no son una comparación controlada del protocolo
completo. Faltan 50/70 cm, iluminación artificial y variación de postura.

Hashes de la continuación:

- `report.json`: `bda8e61b18fcd83fc8a0114c66d9cd91dc11addb2b3b96521b495a905a73c6d8`.
- `events.jsonl`: `6b5a5833dec554d1de61d961ba52a6c5fa67b364acc62bcd2d0f5f3ea7634296`.
- `calibration_c1.json`: `f30760deec6c963f844864635bb705780f28712ce80db9f6a1de474f5f4ef594`.

Los archivos locales de mirada permanecen fuera del repositorio. El resultado
de Actions y el hash del instalador se registran en el plan del workspace al
comprobar la publicación.
