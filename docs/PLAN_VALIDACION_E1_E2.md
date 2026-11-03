# Plan de preparación de InteractorGate para E1 y E2

Este documento reúne los seis bloques identificados al revisar la integración de la app de escritorio, el seguimiento ocular y el backend de la tesis. El objetivo es disponer de una versión con la que puedan ejecutarse los experimentos y reconstruirse sus resultados a partir de registros verificables.

Se creó después de implementar el bloque 1. Los seis bloques se habían descrito previamente en el chat; este archivo no constituye un registro anterior a esa implementación.

## Alcance y fuentes

- **Backend:** `ig-django-backend`, con Django, autenticación JWT, predicciones y telemetría.
- **App de escritorio:** `InteractorGate-Flutter`, con la interfaz Flutter y el proceso Python de seguimiento ocular en `sidecar`.
- **Protocolo de referencia:** `Capstone_1ASI0644_2026-1_chero_li.docx`, secciones 1.2.3 y 4.5.
- **Antecedentes:** los documentos de contexto del backend describen etapas históricas. El estado actual debe comprobarse con el código, las pruebas y los resultados de ejecución.

El plan organiza el trabajo técnico. No sustituye el protocolo de investigación ni acredita por sí mismo el cumplimiento de sus indicadores.

## Estado general

| Bloque | Objetivo | Estado | Verificación pendiente |
|---|---|---|---|
| 1 | Separar participantes y sesiones | Cerrado; publicado en v1.0.1 | [Workflow aprobado](https://github.com/InteractorGate/InteractorGate-Flutter/actions/runs/41572180738) |
| 2 | Crear el modo de estudio para E2 | Validado localmente para piloto: 27 pruebas y cuatro comprobaciones manuales aprobadas | Inspección directa de registros de Azure pendiente por conectividad; publicación v1.0.2 en Actions/Releases |
| 3 | Registrar los datos para calcular indicadores | Cerrado para piloto; backend v2 desplegado y cliente 1.0.3 publicado | [PR #9](https://github.com/InteractorGate/InteractorGate-Flutter/pull/9), [corrección #10](https://github.com/InteractorGate/InteractorGate-Flutter/pull/10), [Release v1.0.3](https://github.com/InteractorGate/InteractorGate-Flutter/releases/tag/v1.0.3), [workflow aprobado](https://github.com/InteractorGate/InteractorGate-Flutter/actions/runs/41676291838) |
| 4 | Corregir los comportamientos de sugerencias que afectan E2 | Cerrado para piloto; 46 pruebas y cuatro comprobaciones manuales aprobadas; exportación de 39 eventos contrastada | [Release v1.0.4](https://github.com/InteractorGate/InteractorGate-Flutter/releases/tag/v1.0.4), [workflow aprobado](https://github.com/InteractorGate/InteractorGate-Flutter/actions/runs/41679994667) |
| 5 | Completar el instrumento técnico de E1 | Instrumento verificado funcionalmente en local: 19 pruebas Python, 46 Flutter y corridas enlazadas de 26+26 ensayos | Publicación [v1.0.5](https://github.com/InteractorGate/InteractorGate-Flutter/releases/tag/v1.0.5); baja precisión ocular, I-4 espontáneo y condiciones completas de E1 pendientes |
| 6 | Completar la evaluación textual y el análisis | Pendiente | Comparar predictores y generar resultados por participante |

“Implementado” indica que existe el cambio de software. “Verificado en entorno real” requiere ejecutar el flujo completo y conservar evidencia.

## Bloque 1 Separar participantes y sesiones

**Propósito:** asociar cada sesión al participante autenticado y evitar que el siguiente participante herede texto, sugerencias o identificadores.

### Implementado

- Se retiraron el acceso automático y las credenciales demo del código de la app.
- Cada apertura pide identificar al participante; el login y el registro muestran el código de participante.
- Tras autenticar y recuperar el perfil, se envía `session_start` con un UUID nuevo y se exige confirmación antes de abrir el tablero.
- El cierre espera las operaciones pendientes y exige confirmación de `session_end` antes de retirar las credenciales.
- Se limpian texto, sugerencias, UUID y ajustes del tablero tras confirmar el cierre.
- Si falla la confirmación del cierre, se conserva la sesión para reintentar.
- El cierre normal de la ventana utiliza el mismo flujo de cierre de sesión.

### Evidencia disponible

- Análisis de Flutter sobre `lib` y `test`: sin incidencias.
- Suite local: **14 pruebas aprobadas**, de las cuales **11 son nuevas** para este bloque.
- Pruebas: [session_lifecycle_test.dart](../test/session_lifecycle_test.dart).
- Procedimiento manual: [README de Flutter](../README.md#verificación-de-sesiones).
- Se utilizó un SDK temporal de Flutter 3.44.0 compatible con `pubspec.lock`; no se modificó ese archivo de versiones.
- Compilación Windows en modo debug completada y aplicación abierta mediante `flutter run -d windows --no-pub`. Se observó la pantalla de inicio de sesión en la ventana de InteractorGate.
- Se instalaron Visual Studio Build Tools 2022 con C++, CMake, Windows SDK y ATL, y se habilitó el modo de desarrollador para los enlaces de los plugins.
- El endpoint `/healthz/` del backend configurado en Azure respondió `{"status":"ok"}`. Esto comprueba disponibilidad HTTP, no el flujo de autenticación ni la persistencia de eventos.
- El usuario confirmó como satisfactorias las pruebas manuales 1–8: apertura, contraseña incorrecta, acceso, cambio de participante, cierre sin conexión, recuperación de conexión, cierre normal de ventana y cierre de ventana sin conexión. Aclaró posteriormente que los códigos disponibles en Azure son `P00`, `P01` y `P02`; la comprobación del cambio de participante utiliza `P01` y `P02`.
- Verificación de solo lectura en Azure del 2 de noviembre de 2026, tras repetir el flujo con la compilación local actual: `P01` y `P02` tienen una sesión completa cada una. Se comprobaron cuatro eventos de inicio y cierre, UUID v4 distintos, ningún cruce entre cuentas, ningún evento duplicado, ningún cierre anterior al inicio y ninguna sesión abierta en la consulta del día. La consulta solo leyó identificadores y límites de sesión; no se exportaron mensajes, coordenadas ni credenciales.

### Para cerrar la verificación en entorno real

- [x] Entrar como P01, escribir, cerrar sesión y entrar como P02 (confirmado por el usuario).
- [x] Comprobar en el servidor que cada cuenta tiene un UUID distinto y los eventos de inicio y cierre correspondientes (consulta directa de SQL y Cosmos).
- [x] Confirmar que P02 encuentra el tablero vacío y los ajustes reiniciados (confirmado por el usuario).
- [x] Desconectar la red antes del cierre y comprobar que la app conserva la sesión y permite reintentarlo (confirmado por el usuario).
- [x] Probar el cierre normal de la ventana en Windows y su cancelación sin conexión (confirmado por el usuario).

**Límites:** los eventos de selección siguen siendo best-effort; su entrega durable corresponde al bloque 3. Una terminación forzada no garantiza `session_end`. Este bloque no modificó la calibración del seguimiento ocular. La compilación de plugins nativos requiere soporte de enlaces simbólicos en Windows, normalmente mediante el modo de desarrollador.

## Bloque 2 Crear el modo de estudio para E2

**Propósito:** ejecutar la comparación con y sin predicción sobre la misma interfaz, identificando cada ensayo.

### Implementado

- Selector del investigador para práctica S1 y medición S2/S3; el programa asigna automáticamente el bloque y la condición del ensayo conforme al plan.
- Frase objetivo visible y controles para iniciar, terminar e interrumpir. Una interrupción conserva la posición y permite repetir la misma frase con otro UUID.
- Sin predicción: no se llama al predictor, no se aceptan sugerencias y se conserva vacío el mismo espacio de 72 píxeles de la barra, sin desplazar el tablero.
- Mismos controles de composición; dwell permanece fijo durante el estudio.
- Banco **provisional de piloto**, autorizado por el usuario: 40 frases únicas en dos listas de 20, más diez frases distintas para práctica. Longitudes de medición: A, 17–27 caracteres (media 21,10); B, 18–26 (media 21,85). Ninguna de las 50 coincide exactamente, tras normalización, con las 103 secuencias del corpus actual. La equivalencia de frecuencia de palabras queda pendiente de revisión metodológica; no se declara demostrada.
- Contrabalanceo por orden de inclusión confirmado por el investigador: impares usan A con predicción y pares usan B. Una semilla reproducible conserva el orden; S2 y S3 utilizan mitades distintas de cada lista, en cuatro bloques alternados de cinco por sesión, con condición inicial aleatorizada.
- Diez mensajes de práctica, cinco por condición, separados mediante `practice=true`. Se bloquea S2 hasta completarlos y S3 hasta terminar S2.
- Asignación y avance guardados por cuenta en el almacenamiento seguro del equipo. Al volver a entrar se conserva el siguiente ensayo; el cambio de participante carga otro progreso.
- Envío confirmado de `settings`, `trial_start` y `trial_end` al backend existente, con UUID, frase, condición, lista, bloque, orden, sesión del protocolo y resultado. El cierre de cuenta o ventana interrumpe el ensayo activo antes de cerrar la sesión.

### Evidencia y verificaciones pendientes

- `flutter analyze --no-pub lib test`: sin incidencias.
- `flutter test --no-pub`: **27 pruebas aprobadas**, incluidas 13 nuevas para este bloque.
- Pruebas de ausencia de solicitudes sin predicción, transiciones con peticiones pendientes, errores de entrega, persistencia entre accesos, interrupciones y recorrido completo S2/S3 con 40 ensayos distintos.
- Compilación Windows debug completada; aplicación abierta localmente y pantalla de identificación observada.
- Verificación de interacción con `P01`: se observó por accesibilidad la práctica y el avance en S2. El 3 de noviembre el usuario confirmó las cuatro comprobaciones solicitadas: bloqueo de S2 antes de práctica, diez mensajes de práctica y al menos un bloque por condición en S2, interrupción/reinicio y reintento sin conexión conservando el mensaje, y recuperación del siguiente ensayo tras volver a entrar.
- La consulta independiente de los registros del 3 de noviembre no pudo completarse: SQL rechaza la lectura directa por firewall y la conexión directa a Cosmos agota su tiempo de selección de servidor. No se modificaron reglas de red. La ausencia de solicitudes sin predicción está comprobada mediante pruebas del cliente; el contraste independiente de conteos de SQL no se considera aprobado.
- [x] Completar la validación manual de práctica y de un bloque por condición en S2 (confirmado por el usuario con P01).
- [ ] Comprobar en Azure la asociación y los metadatos de los ensayos de piloto.
- Publicación del piloto: consultar el resultado de [Build & Release](https://github.com/InteractorGate/InteractorGate-Flutter/actions/workflows/release.yml) y el instalador en el [Release v1.0.2](https://github.com/InteractorGate/InteractorGate-Flutter/releases/tag/v1.0.2). El resultado y commit de publicación se registran en el archivo de seguimiento de la raíz del workspace.

Instrucciones y listas completas: [ESTUDIO_E2.md](ESTUDIO_E2.md). Pruebas: [study_mode_test.dart](../test/study_mode_test.dart).

**Límites:** el avance se conserva en este equipo, sin sincronización entre dispositivos. Un ACK perdido o un error local después de confirmar un evento puede producir límites duplicados al reintentar; la deduplicación y entrega durable de todas las acciones pertenecen al bloque 3. Una terminación forzada puede dejar un ensayo sin cierre. Las pausas, el máximo de 45 minutos y la separación entre días se supervisan por el investigador. El banco sigue siendo de piloto y debe volver a contrastarse con el corpus si este se amplía.

**Archivos de partida:** `lib/state/session_controller.dart`, `lib/screens/home_screen.dart`, `lib/services/prediction_service.dart` y `lib/widgets/suggestion_bar.dart` dentro de Flutter.

**Criterio de cierre:** completar un bloque de cada condición, verificar que la condición sin predicción no realiza peticiones de predicción y conservar el identificador, la frase, la condición y el orden de cada ensayo.

**Indicador principal:** I-7. Este bloque depende del bloque 1 y necesita los registros del bloque 3 para generar evidencia analizable.

## Bloque 3 Registrar los datos para calcular indicadores

**Propósito:** reconstruir lo ocurrido en cada ensayo sin completar información manualmente después de las pruebas.

### Implementado y verificado

- Cola cifrada por cuenta y backend, persistida antes de aplicar las ediciones. Reenvío secuencial y recuperación al autenticarse de nuevo con el mismo propietario.
- UUID por evento, secuencia de sesión, contexto de ensayo y relojes de cliente/servidor separados. Inserciones, espacios, palabras, borrados, limpiezas, cambios de modo y aceptación por posición.
- Registro de solicitudes y de sugerencias efectivamente presentadas, con latencia hasta el frame que las muestra.
- Cierre de ensayo inmutable durante los reintentos, conservado hasta confirmar también el avance local. Recuperación de ese cierre tras reinicio sin duplicar el resultado.
- Backend idempotente para el contrato v2, compatible con eventos legados. Payload diferente con la misma clave obtiene 409; reenvío idéntico conserva el documento y la primera recepción.
- Verificación y exportación por la API de la cuenta, con reconstrucción del texto, detección de huecos, secuencias repetidas y ensayos incompletos.
- Sin imágenes; campos acotados. La telemetría del tablero libre omite texto de inserciones; las frases de E2 se identifican como práctica/piloto según corresponda.

### Evidencia

- Flutter: análisis sin incidencias y 39 pruebas aprobadas. Backend: 36 pruebas aprobadas.
- Prueba HTTP/Mongo real: seis reenvíos concurrentes, una sola copia, aislamiento entre cuentas y conflicto 409 ante un payload distinto.
- El usuario confirmó el piloto Windows local con MongoDB pausado y reanudado: pendientes conservados, cierre fallido sin perder el mensaje, recuperación y avance único.
- Archivo exportado de la app contrastado con MongoDB: 53 eventos y dos ensayos, sin IDs o secuencias repetidos, sin huecos y textos finales reconstruidos coincidentes. También se verificó ausencia de solicitudes reales de predicción en la condición desactivada.
- Detalle, contrato y límites: [TELEMETRIA_E2.md](TELEMETRIA_E2.md). La validación local no se presenta como verificación del despliegue en Azure.
- Backend publicado tras la revisión requerida: [PR #62](https://github.com/InteractorGate/ig-django-backend/pull/62), commit `128595c615e861b51a2c5c66c530f33045a29e3b`. [Despliegue #41672313415](https://github.com/InteractorGate/ig-django-backend/actions/runs/41672313415) aprobado; `/healthz/` respondió `{"status":"ok","telemetry_schema":2}`. Esta comprobación acredita el contrato activo, no sustituye la prueba integrada local con los datos del piloto.

**Archivos de partida:** `lib/services/telemetry_service.dart`, `lib/state/session_controller.dart`, los callbacks de `home_screen.dart` y los serializadores y vistas de `ig-django-backend/interaction_logs`.

**Criterio de cierre:** reconstruir desde los registros una sesión de prueba, incluyendo correcciones y sugerencias, y repetir la comprobación con una desconexión y posterior reconexión. Los conteos deben coincidir con las acciones ejecutadas y los reintentos no deben duplicarlos.

**Indicadores principales:** I-7 e I-8. Los datos de selecciones y activaciones también deben coordinarse con el instrumento de E1 para I-3 e I-4.

## Bloque 4 Corregir los comportamientos de sugerencias que afectan E2

**Propósito:** asegurar que cada sugerencia corresponde al texto actual y que su aceptación compone el mensaje de la forma definida para el experimento.

### Trabajo previsto

- Completar la protección frente a peticiones superpuestas y respuestas fuera de orden.
- Definir cuándo solicitar continuaciones, teniendo en cuenta que la RNN predice palabras siguientes y no completa necesariamente una palabra parcial.
- Evitar que aceptar una continuación produzca textos como `QUI agua` al escribir una palabra incompleta.
- Verificar que limpiar el texto, terminar un ensayo o cambiar de condición invalida las peticiones anteriores.
- Fijar una regla de inserción y mantenerla durante todos los ensayos.

**Implementación del piloto 1.0.4:** cada edición persistida invalida la respuesta anterior. La revisión se captura dentro de la cola de ediciones; una respuesta o un error solo puede modificar la barra si mantiene sesión, revisión, texto y condición vigentes. La aceptación exige el ID de la respuesta mostrada, y una respuesta nueva reinicia el dwell aunque repita una etiqueta.

**Regla fija:** el teclado solicita palabras siguientes tras ESPACIO. Los botones de palabras completas y la aceptación de sugerencias solicitan una continuación directamente. Aceptar añade un solo espacio de separación; no reemplaza ni completa una palabra parcial. Se conserva el mismo comportamiento de escritura en la condición sin predicción.

**Validación automática:** análisis de Flutter sin incidencias, 46 pruebas aprobadas y compilación Windows debug contra localhost completada. Se verificaron respuestas inversas, borrado y vuelta al mismo texto, limpieza, errores antiguos, aceptación antigua con texto repetido, transición a la condición sin predicción y reinicio de dwell.

**Validación manual:** el usuario aprobó las cuatro comprobaciones con `LOCAL_B4`, S1 y orden de inclusión 2. Se contrastaron 39 eventos y un ensayo coherente contra MongoDB local: IDs únicos, sin huecos, texto reconstruido coincidente y dos sugerencias aceptadas. Las seis solicitudes reales del predictor en SQLite contienen palabras completas, sin solicitar `QUI`. Publicación 1.0.4 pendiente. Detalle y hash de la evidencia: [SUGERENCIAS_E2.md](SUGERENCIAS_E2.md). Se utilizó ratón y datos ficticios.

**Archivos de partida:** `lib/state/session_controller.dart`, `lib/services/prediction_service.dart` y `ig-django-backend/ai_modules/rnn/infer.py`.

**Criterio de cierre:** probar respuestas en orden inverso, borrado durante una petición, cambio de condición y aceptación tras una palabra parcial. Solo deben mostrarse sugerencias válidas para el estado vigente.

**Indicadores relacionados:** I-7 e I-8.

## Bloque 5 Completar el instrumento técnico de E1

**Propósito:** medir el seguimiento ocular con las condiciones y definiciones del protocolo.

### Trabajo previsto

- Comparar la GazeCNN genérica y el motor calibrado en el mismo participante, según la sección 4.5.4 de la tesis.
- Registrar la geometría necesaria para calcular el error angular respecto del objetivo mostrado.
- Medir por separado la celda estimada sin cursor y la selección confirmada con cursor.
- Identificar las activaciones no intencionadas y sus tiempos; el número de parpadeos por sí solo no permite saber si fueron intencionados.
- Registrar iluminación, distancia, postura, motor, calibración y orden de las condiciones.
- Conservar también los ensayos sin seguimiento y reportar cómo se tratan en los denominadores.
- Guardar resultados por participante y sesión, evitando sobrescribir archivos.

**Punto de partida:** el benchmark anterior de `InteractorGate-Flutter/sidecar/bench_precision.py` usaba solo el motor calibrado, mostraba la mirada y clasificaba mediante la mediana de muestras; esos resultados no sustituían todas las mediciones exigidas por E1.

**Implementación 1.0.5:** el instrumento reemplaza ese benchmark por tareas separadas de puntos, celdas sin cursor, selección con cursor y observación. Compara CNN/ONNX genérica y ridge calibrado por condición, conserva muestras y fallos, clasifica activaciones y crea carpetas por participante/UUID. No sobrescribe la calibración de comunicación. Geometría, definición del error operativo, denominadores y comandos en [INSTRUMENTO_E1.md](INSTRUMENTO_E1.md).

**Estado del piloto:** 19 pruebas Python y 46 pruebas Flutter aprobadas, análisis sin incidencias y ejecutable local comprobado con webcam. La corrida genérica de 26 ensayos y su continuación calibrada de 26 se conservan enlazadas por UUID/hash, con informes reconstruidos desde los eventos. Los 16 puntos aceptados y 531 muestras reprodujeron el ajuste guardado; 18 intentos fallidos de calibración permanecen registrados. La continuación terminó `completed`.

**Resultado de desempeño:** precisión baja: I-2 de 1/8 para la CNN y 0/8 para el calibrado; I-3 de 6/8 y 7/7 selecciones incorrectas, respectivamente, con un timeout calibrado. Las cinco activaciones de observación calibrada fueron provocadas a propósito según confirmó el usuario; no validan I-4 espontáneo. El piloto utiliza luz natural, postura habitual, pantalla aproximada de 344 × 195 mm y cámara a 60 cm; ojos–pantalla de 62/63 cm y pausa entre corridas. Se valida el instrumento de registro, no la precisión requerida para participantes ni la comparación completa de E1. Faltan las condiciones de 50/70 cm y la revisión metodológica de la métrica angular. Evidencia y hashes en [INSTRUMENTO_E1.md](INSTRUMENTO_E1.md). Publicación 1.0.5 pendiente.

**Otros archivos relevantes:** `sidecar/calibration.py`, `sidecar/eye_tracker.py`, `sidecar/gaze_cnn.py` y los módulos CNN del backend.

**Criterio de cierre:** completar un piloto de las condiciones del protocolo y conservar datos por ensayo para calcular I-1 a I-5 e I-9. El informe debe distinguir error angular, acierto de celda y selección confirmada.

**Precisión metodológica:** la comparación descrita cambia de una CNN genérica a un motor calibrado basado en MediaPipe y regresión. Debe explicitarse esa diferencia al interpretar los resultados y el alcance de la atribución a la calibración.

## Bloque 6 Completar la evaluación textual y el análisis

**Propósito:** convertir los registros técnicos y de interacción en resultados reproducibles para la tesis.

### Trabajo previsto

- Evaluar top-1, top-3 y perplejidad de la RNN y de un predictor n-grama sobre el mismo conjunto de prueba, separado del entrenamiento y de los ajustes.
- Exportar una fila por ensayo con los identificadores y las variables necesarias, sin incluir nombres personales.
- Calcular por participante tiempo por mensaje, caracteres por minuto, selecciones, KSR y aceptación de sugerencias.
- Calcular el percentil 95 de la latencia extremo a extremo.
- Preparar los análisis por participante previstos en la tesis: gráficos por sesión, NAP y prueba de aleatorización para E2, y comparación pareada por objetivos para E1.
- Recoger QUEST 2.0 y SUS mediante formularios separados si resulta más sencillo, asociados al código del participante.
- Separar los resultados del piloto de los de la población objetivo y conservar las exclusiones e interrupciones reportables.

**Archivos de partida:** `ig-django-backend/ai_modules/rnn/train.py`, los resultados del bloque 5 y los registros del bloque 3. Los scripts de evaluación y análisis todavía deben implementarse.

**Criterio de cierre:** regenerar las tablas, métricas y gráficos desde los datos exportados y comprobarlos con una sesión de ejemplo cuyos resultados se hayan calculado manualmente. Los resultados deben reportarse aunque no cumplan las metas.

**Indicadores principales:** I-6, I-7, I-8 e I-10; consolidación de los resultados de E1.

## Orden de ejecución y primer hito

Antes de implementar el bloque 2, corresponde ejecutar y validar localmente el bloque 1 y completar su publicación según el flujo de cierre acordado. Los bloques 2, 3 y 4 deben converger en un piloto completo de E2; después se completa el instrumento de E1 y el análisis del bloque 6.

Primer hito verificable:

- [ ] Identificar un participante ficticio de prueba e iniciar una sesión.
- [ ] Ejecutar ensayos de ambas condiciones con frases de prueba.
- [ ] Registrar las acciones, los tiempos y las sugerencias.
- [ ] Terminar la sesión y exportar los ensayos.
- [ ] Reconstruir los resultados desde los registros, sin rellenar datos faltantes manualmente.

Ese hito verifica el funcionamiento del procedimiento; no demuestra todavía eficacia en la población objetivo.

## Condiciones antes de las pruebas con participantes

Además de estos seis bloques, deben resolverse los problemas ya identificados de almacenamiento de imágenes, aceptación de entradas inválidas, dependencias del despliegue e interpolación insegura en el workflow de GitHub Actions. No se consideran corregidos por el bloque 1.

También debe acordarse el lugar de las sesiones: la tesis declara domicilios y se ha planteado realizarlas en el centro de rehabilitación. Cualquier ajuste debe quedar reflejado en el protocolo y la documentación correspondiente, junto con el consentimiento y la aprobación ética previstos en la tesis.

## Mantenimiento del plan

Al trabajar en cada bloque, registrar aquí los cambios, las pruebas realizadas, sus resultados y las verificaciones pendientes. No marcar una verificación manual o de infraestructura como aprobada a partir de una prueba simulada.

## Flujo de cierre acordado para cada bloque

1. Terminar la implementación del bloque y actualizar este plan con su alcance real.
2. Ejecutar las pruebas automatizadas y el análisis correspondientes al cambio.
3. Ejecutar el programa en local y comprobar el flujo del bloque, incluyendo los casos de error relevantes. Registrar qué se ejecutó y el resultado observado.
4. Si aparece un fallo, corregirlo y repetir la comprobación afectada antes de publicar.
5. Cuando la validación local sea satisfactoria, revisar los cambios y hacer commit y push a GitHub en los repositorios afectados, excluyendo credenciales, datos de participantes y archivos generados ajenos al cambio.
6. Ejecutar o seguir el flujo de despliegue o publicación configurado para cada repositorio y comprobar su resultado. Un commit o un push, por sí solos, no acreditan que el despliegue haya terminado.
7. Registrar el commit, la evidencia de validación local y el resultado de la publicación antes de pasar al siguiente bloque.

El usuario ha autorizado este flujo de commit y push condicionado a una validación local satisfactoria. Si una comprobación requiere interacción manual, conservarla como pendiente hasta que se observe o el usuario comunique su resultado.

Los workflows actuales se activan con cambios en `main`: el backend despliega en Azure mediante `.github/workflows/deploy.yml`; Flutter construye el instalador y publica un GitHub Release mediante `.github/workflows/release.yml`.

**Situación del bloque 1:** implementación, 14 pruebas automatizadas, compilación Windows, pruebas interactivas 1–8 y comprobación de los eventos en Azure terminadas. Cambios en el [PR #7](https://github.com/InteractorGate/InteractorGate-Flutter/pull/7). La publicación del instalador 1.0.1 se comprueba mediante el resultado de [Build & Release](https://github.com/InteractorGate/InteractorGate-Flutter/actions/workflows/release.yml) y la presencia de `InteractorGate-Setup.exe` en el [Release v1.0.1](https://github.com/InteractorGate/InteractorGate-Flutter/releases/tag/v1.0.1); la validación local por sí sola no acredita esa publicación.
