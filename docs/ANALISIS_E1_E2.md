# Evaluación y análisis — bloque 6, piloto 1.0.6

El bloque implementa herramientas reproducibles. No convierte los datos de
práctica en evidencia de eficacia ni completa por software las sesiones que
faltan. Los resultados del seguimiento ocular del bloque 5 siguen siendo bajos.

## Ejecutar el análisis local

Desde `sidecar`, con sus dependencias instaladas:

```powershell
python analyze_study.py --init-manifest analysis_manifest.json
python analyze_study.py --init-questionnaires questionnaires_input.csv
python analyze_study.py --manifest analysis_manifest.json
```

El manifiesto declara `dataset_label`, exportaciones `e2_exports`, carpetas
`e1_sessions`, un CSV opcional de cuestionarios y `text_evaluation` opcional.
Las rutas relativas se resuelven desde la carpeta del manifiesto. Cada corrida
crea un UUID en `Documentos/InteractorGate/Analysis`; `--output` permite elegir
otra carpeta. Las plantillas y las corridas existentes no se sobrescriben.

Ejemplo de entradas (las rutas son ilustrativas):

```json
{
  "schema_version": 1,
  "dataset_label": "Piloto local",
  "e2_exports": [
    {
      "path": "session_export.json",
      "cohort": "pilot",
      "environment": "local",
      "prediction_policy": "next_words_v1"
    }
  ],
  "e1_sessions": [{"path": "E1/codigo/uuid", "role": "primary"}],
  "questionnaires_csv": null,
  "text_evaluation": null,
  "randomizations": [],
  "e1_reference_condition": "c1"
}
```

`cohort` separa `pilot` y `target`. `environment` separa `local`, `azure` y
`synthetic`. La regla de predicción se declara según la versión usada: los
pilotos anteriores a 1.0.4 no se mezclan con `next_words_v1`. Si se desconoce,
usar `unknown`: se conserva la fila pero no entra al análisis principal.
Estos datos de procedencia no se deducen del nombre del participante.

El ejecutable distribuido ofrece los mismos comandos sin instalar Python:

```powershell
& 'C:\Program Files\InteractorGate\gaze\gaze_service.exe' --analysis-init-config 'C:\ruta\analysis_manifest.json'
& 'C:\Program Files\InteractorGate\gaze\gaze_service.exe' --questionnaires-template 'C:\ruta\questionnaires_input.csv'
& 'C:\Program Files\InteractorGate\gaze\gaze_service.exe' --analysis-config 'C:\ruta\analysis_manifest.json'
```

El último abre `report.html` en el navegador. El análisis no usa la webcam ni
necesita credenciales de Azure. La evaluación con entrenamiento de modelos de
texto es una herramienta offline distinta, descrita más abajo.

## Archivos generados y trazabilidad

- `e2_trials.csv`: una fila por ensayo conocido, incluso abierto, interrumpido
  o excluido. No contiene frases ni nombres: usa códigos, IDs, longitudes y hash
  del texto final. Son datos seudonimizados, no una garantía de anonimato.
- `e1_trials.csv`: objetivos previstos, intentos, seguimiento, selección y
  exclusiones. `not_run` permanece visible pero no entra al denominador de intentos.
- `questionnaires.csv`: puntuaciones y número de ítems válidos; sin respuestas,
  no se inventan puntuaciones.
- `analysis.json`: métricas, exclusiones, supuestos, hashes de entradas y código,
  versiones de software y procedencia. En el ejecutable se identifica su hash.
- `e1_*.png`, `e2_*.png` y `report.html`: figuras por sesión y objetivos, con
  leyendas y enlaces a las tablas. El detalle técnico queda desplegable.

Los archivos de resultados se mantienen fuera de Git. Para repetir un análisis
se conservan sus entradas, manifiesto y versión del código. Los hashes de las
entradas permiten verificar que no cambiaron; el UUID y la fecha del nuevo
resultado serán distintos aunque las métricas coincidan.

## Reglas E2

Se reconstruye el texto desde inserciones, borrados y limpiezas. Se verifican
límites, contexto, propietario, secuencias y aceptación de una sugerencia
presentada con el ID y posición correctos. Repetir una exportación no duplica
ensayos; copias contradictorias de un evento se rechazan. No se confía en el
resumen precalculado de la exportación para sustituir esta comprobación.

La fila principal exige un ensayo completo, coherente, de medición y con
transcripción correcta. La comparación de transcripción usa NFC, ignora
mayúsculas/minúsculas y espacios exteriores; conserva tildes y espacios internos.
Práctica, errores de transcripción, huecos, falta de contexto, política desconocida
y otras exclusiones se conservan con motivos. Para población objetivo, un banco
provisional o sin estado declarado tampoco es confirmatorio.

Definiciones:

- Tiempo: `duration_ms / 1000`, capturado por el reloj del ensayo.
- CPM: caracteres Unicode del texto final NFC, sin espacios exteriores, por
  minuto; incluye espacios internos.
- Selecciones de composición: letras, espacios, palabras, sugerencias, borrados,
  limpiezas y cambios de tablero. No incluye login ni iniciar/terminar ensayo.
- KSR literal: `1 - selecciones / caracteres_objetivo`. No se recorta a cero:
  puede ser negativo. Las palabras del tablero también ahorran selecciones;
  este KSR no atribuye todo el ahorro exclusivamente a la predicción.
- Aceptación: se presentan tanto aceptadas/presentaciones como
  aceptadas/candidatas ofrecidas. Sin denominador, el valor es ausente.
- Latencia: p95 lineal, índice `(n-1)*0.95`, de las sugerencias efectivamente
  mostradas. Se distinguen el conjunto principal y todas las observaciones,
  incluidas prácticas. Se reportan solicitudes y presentaciones: las respuestas
  nunca mostradas no tienen una latencia observable y no se imputan como cero.
- NAP para tiempo/selecciones: proporción de todos los pares con mejor valor
  con predicción, más medio crédito por empate; menor es mejor. Sin ambas
  condiciones elegibles no hay NAP.

Las medianas y NAP se separan por código, grupo, entorno, regla de predicción y
versión del banco. Las figuras se separan también por sesión autenticada y fase.

## Aleatorización E2: revisión de diseño necesaria

`StudyPlan` fija listas por paridad del orden de inclusión y alterna bloques de
cinco. El inicio de condición se obtiene de una semilla por participante/fase;
el orden de frases se genera dentro de cada lista. Esto no equivale a asignar
libremente cada mensaje a predicción/sin predicción. Además, las frases concretas
dependen de la condición/lista, de modo que invertir etiquetas sin considerar
esa asignación no representa automáticamente el experimento realizado.

Por defecto no se publica un p-valor de aleatorización. La función exacta acepta
un **espacio de asignaciones enumerado y equiprobable** aportado por el
investigador, con todos los IDs de ensayo elegibles, la asignación observada y
matrices booleanas alternativas. Usa como estadístico la diferencia de medianas
de tiempo (sin − con) y un contraste bilateral. No verifica por sí sola que las
alternativas hayan sido permitidas o prerregistradas: eso requiere revisar el
protocolo antes de recoger datos. No sustituirlo por permutaciones post hoc de
todos los mensajes. El ejemplo aritmético emplea expresamente un diseño ficticio
distinto, sin presentarlo como el E2 real.

## E1, pares y condiciones

Se reconstruyen los informes desde el journal, se comprueban los padres de
continuaciones por UUID/hash y se separan corridas `primary` y `archive`.
Las corridas archivadas permanecen en la tabla sin incorporarse a comparaciones.
Los puntos sin seguimiento no desaparecen; I-2 usa intentos abiertos y I-3
confirmaciones cerradas. No se reemplaza I-3 por el complemento de I-2.

Wilcoxon se prepara sobre errores medios por objetivo/repetición en ambos
motores. Se excluyen ceros de la distribución de rangos, se usan rangos medios
para empates y enumeración exacta condicional de signos; las diferencias se
redondean a diez decimales para evitar empates espurios por resta flotante.
Se documentan los supuestos de simetría e independencia. Faltan inferencias si
hay pares repetidos, geometrías/objetivos/versiones incompatibles o ningún par.
En los datos actuales hay ocho objetivos comunes, pero 620 frente a 630 mm
ojos–pantalla: el programa no calcula ese p-valor.

I-9 muestra diferencias descriptivas respecto de `e1_reference_condition`,
declarada antes del análisis. No elige la mejor condición retrospectivamente.
Con una sola condición no hay contraste ambiental. I-4 espontáneo excluye la
observación cuando hay activaciones intencionales, dudosas o sin revisar; las
cinco activaciones provocadas del piloto no se convierten en una tasa espontánea
cero. La distinción entre error operativo y error nativo de la CNN se mantiene:
[INSTRUMENTO_E1.md](INSTRUMENTO_E1.md).

## SUS y QUEST 2.0

El CSV vacío es una plantilla de **registro**, no una traducción validada del
cuestionario. Aplicar las versiones en español aprobadas para el estudio y
registrarlas en `form_version`, junto con código, grupo y `assessment_id`.
Los campos son `SUS1`–`SUS10` y `QUEST1`–`QUEST12`, con respuestas enteras 1–5;
dejar vacíos los ítems ausentes/no aplicables. No rellenarlos con cero.

SUS suma las contribuciones impares `respuesta-1` y pares `5-respuesta`, y las
multiplica por 2,5. Aquí exige diez respuestas completas y se expresa de 0 a 100,
no como porcentaje. QUEST calcula las medias de ítems válidos de dispositivo
(1–8), servicios (9–12) y total, informando los denominadores y faltantes.
No se infiere satisfacción de la rapidez ni del acierto del sistema.

## Evaluación textual offline

Desde la raíz de Flutter, usando un Python con las dependencias de PyTorch del
backend instalado y el checkout local del backend:

```powershell
python research/evaluate_text.py --backend-root ../ig-django-backend --output research/runs/text_pilot
```

La herramienta reutiliza arquitectura, tokenizador y construcción de secuencias
del backend. Entrena un modelo experimental separado y no escribe sus pesos ni
su historial en el backend. Normaliza/deduplica frases tokenizadas y fija una
partición aproximada 70/15/15 con semilla 42. Vocabulario y bigrama usan solo
entrenamiento. La RNN emplea detención temprana por pérdida de validación; alpha
del bigrama se elige entre 0,01, 0,1 y 1 por la misma partición, nunca por prueba.

Se guardan particiones, hashes de frases/código/checkpoint, historial y métricas
de ambas arquitecturas sobre exactamente las mismas posiciones. La perplejidad
usa el vocabulario común con UNK/EOS, suprimiendo PAD/BOS. Top-1 y top-3 sobre
palabras excluyen símbolos especiales y cuentan cada palabra OOV como error,
aunque se prediga UNK. También se conservan las métricas de tokens LM para que
no se confundan ambos denominadores.

Resultado del piloto actual: 72/15/16 frases; vocabulario solo de entrenamiento;
mejor época 11, alpha 0,01. En las 56 posiciones de palabra de prueba, 19 son OOV.

| Modelo | Top-1 palabras | Top-3 palabras | Perplejidad LM (72 posiciones con EOS/UNK) |
|---|---:|---:|---:|
| RNN experimental | 11/56 = 19,64 % | 18/56 = 32,14 % | 70,43 |
| Bigrama | 11/56 = 19,64 % | 20/56 = 35,71 % | 62,71 |

La RNN no supera al bigrama en este piloto. Las 103 frases ya se usaron en el
desarrollo: es una partición retrospectiva interna, no validación independiente.
No comparar directamente esta perplejidad con la del artefacto antiguo, que usa
otra partición/procedimiento. No se reemplazó automáticamente el predictor.

`--test-file` permite aportar un archivo nuevo de una frase por línea; rechaza
un archivo sin frases y solapamientos normalizados con el corpus de desarrollo. Aun así,
la independencia histórica y la representatividad de esas frases requieren
verificación del investigador. Para una prueba definitiva, reservar material
adicional antes de nuevos ajustes y documentar su procedencia; mover frases
ya usadas a otro archivo no crea una prueba independiente.

## Comprobación manual y estado

`research/manual_example.py` genera un ejemplo **sintético**, separado de los
archivos reales. Transcribe `YO VOY` (seis caracteres), con tiempos sin predicción
10/20 s y con predicción 5/15 s. Sus selecciones son 6/6 y 4/4:

- Medianas de tiempo: 15 frente a 10 s; selecciones: 6 frente a 4.
- CPM medianos: 27 frente a 48; KSR: 0 frente a 1/3.
- NAP de tiempo: 3/4; NAP de selecciones: 1.
- Latencias 100/300 ms: p95 lineal de 290 ms.
- Espacio ficticio de seis asignaciones 2+2: p bilateral de 4/6.
- Respuestas SUS sintéticas 4/2 alternadas: 75 puntos.
- QUEST sintético: dispositivo 4, servicios 3 y total 11/3.

Los 34 tests Python del sidecar incluyen esta comprobación, deduplicación,
exclusiones, OOV, pares incompatibles e I-4 no espontáneo. Las 46 pruebas Flutter
y el análisis están aprobados. La generación source de tablas/figuras pasó con
los archivos reales: tres ensayos E2 de práctica (ninguno principal), 156 filas
E1 incluidas las corridas archivadas/no iniciadas y ninguna respuesta real de
satisfacción. Se conservan los 52 intentos primarios de las dos corridas E1.
El ejecutable final generó y abrió los dos informes locales. Sus métricas,
tablas y figuras coincidieron con la ejecución source; se comprobaron los
enlaces y se inspeccionaron las figuras. Dos ejecuciones textuales repitieron
exactamente las mismas métricas. La publicación 1.0.6 queda pendiente de Actions.

Trazabilidad de esta validación local:

- Ejemplo nativo: `233ffcc8-32e3-4044-9d51-859ac7506f40`; SHA-256 de
  `analysis.json`: `37798dda623df7b87b33c4a462c3e4cf3908f334f70a251c781f64735dbf5221`.
- Piloto nativo: `a51b540b-ff6a-4ac3-893a-e82c00485a0f`; SHA-256 de
  `analysis.json`: `26fc99ac2a3f377f0beffa47e89848f381b3399bd00d8c27f23700a9f637ac91`.

Los datos originales y los resultados permanecen en `research/runs/`, excluido
de Git. Las herramientas se entregan verificadas para el piloto; completar el
experimento con población objetivo, los cuestionarios y la prueba independiente
de texto sigue siendo trabajo de recogida y revisión metodológica.

## Referencias de método

- [Parker y Vannest, NAP, artículo original](https://singlecaseresearch.org/papers/ParkerVannest2009-An%20improved%20effect%20size%20for%20single%20case%20research.pdf).
- [Brooke, SUS, capítulo original](https://hci-studies.org/methods-and-measures/downloads/SUS_Brooke1996.pdf).
- [Demers, Weiss-Lambrou y Ska, manual QUEST 2.0](https://www.sbst.dk/media/11001/Quest%202_0.pdf).
- [Documentación técnica de Wilcoxon y sus supuestos](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html).

Las referencias explican los métodos; no se han reproducido ni traducido aquí
los cuestionarios completos.
