# Resultados preliminares de accesibilidad WCAG 2.1

## Actualización tras las correcciones - 4 de noviembre de 2026

Los hallazgos H01-H04 descritos más abajo corresponden al estado anterior a las correcciones. Se conserva ese diagnóstico como evidencia histórica. El PDF actualizado incluye esta síntesis de correcciones y distingue el diagnóstico original.

- **H01:** `DwellButton` utiliza ahora `TextButton`, con navegación por foco, activación con Enter/Espacio y borde de foco de 3 píxeles. La pantalla principal excluye del foco el tablero bloqueado para respetar las restricciones de sesión y estudio.
- **H02:** retroceso expone el nombre «Borrar último carácter» y el rol y acción de botón del control estándar. El progreso visual de permanencia se excluye de la semántica para evitar que interfiera con el nombre del botón.
- **H03:** la instrucción de sugerencias usa `Colors.white70`; una prueba calcula el contraste usando el color del widget y el fondo del tema y exige al menos 4,5:1.
- **H04:** login y registro usan `Form` y `TextFormField` con errores por campo vacío. El registro también identifica confirmación vacía y contraseñas diferentes antes de enviar. La validación del servidor se conserva.
- Se corrigió además la inicialización del controlador de animación para que desmontar una tecla sin activarla no genere la aserción observada durante la auditoría.

Las pruebas actuales están en `test/accessibility_test.dart`; el comando histórico `flutter test --no-pub docs/wcag_probe_test.dart` ejecuta esas mismas regresiones. Ya comprueban el comportamiento corregido, en lugar de afirmar la existencia de las barreras originales. La suite completa del cliente pasó **52 pruebas**, incluidas seis de accesibilidad. Estas comprobaciones no acreditan conformidad AA global: continúan pendientes la evaluación con lector de pantalla de Windows, escala de texto, usuarios y los restantes criterios de la matriz.

Verificación adicional: `flutter analyze --no-pub` terminó sin incidencias. Las seis regresiones se repitieron tras añadir comprobaciones del borde de foco y de activación única por permanencia.

---

Fecha: 4 de noviembre de 2026 (Perú). Aplicación: InteractorGate, Flutter Desktop para Windows, versión declarada `1.0.6+7`. Referencia Git: `1fee36800996b3eb259638351d141457813f44f7`; se revisaron los archivos locales, que pueden incluir cambios posteriores al commit.

## Alcance y método

Evaluación técnica parcial orientada a nivel A y AA: lectura del código de login, registro, tablero, teclado, sugerencias, texto compuesto, configuración de estudio y exportación. Se revisaron también el tema y las pruebas existentes. No se modificó la aplicación para corregir los problemas.

Se usan [WCAG 2.1](https://www.w3.org/TR/WCAG21/) como referencia y [WCAG2ICT](https://www.w3.org/TR/wcag2ict-22/) como guía informativa para software no web. WCAG2ICT no constituye una certificación ni añade requisitos normativos. Esta revisión no cubre todos los criterios A/AA ni permite declarar conformidad global.

No se encontró un informe WCAG anterior en la documentación revisada. `thesis-extracted.txt`, líneas 528 y 692, describe la evaluación prevista y recomienda auditorías empíricas; esas menciones no son resultados de una auditoría ejecutada. Las pruebas de sesiones y E1/E2 tampoco equivalen a una evaluación WCAG.

Estados utilizados: **barrera en código** = implementación concreta que impide o compromete un requisito; **evidencia favorable parcial** = mecanismo favorable sin validación completa; **pendiente** = requiere observación o prueba adicional. La severidad es una prioridad interna, no una categoría de WCAG.

## Hallazgos

| ID | Criterio y nivel | Resultado y evidencia | Impacto / prioridad | Corrección propuesta |
|---|---|---|---|---|
| H01 | 2.1.1 Teclado (A) | Barrera en código: `DwellButton` usa `MouseRegion` y `GestureDetector.onTap`, sin mecanismo de foco o activación por teclado. Lo reutilizan tablero, teclado y sugerencias. Ver [dwell_button.dart](../lib/widgets/dwell_button.dart), líneas 75–79. | La composición depende del puntero; excluye a quienes necesitan teclado o dispositivos que lo emulan. Alta. | Dar foco y activación estándar a este componente compartido y verificar Tab, Mayús+Tab, Enter y Espacio. |
| H02 | 1.1.1 Contenido no textual (A); 4.1.2 Nombre, función, valor (A) | Barrera en código: la tecla de retroceso presenta únicamente `Icon(Icons.backspace_outlined)`, sin `semanticLabel` o etiqueta equivalente. Ver [dwell_keyboard.dart](../lib/widgets/dwell_keyboard.dart), línea 93. Además debe verificarse el rol de botón de todas las celdas personalizadas. | El lector de pantalla puede exponer una acción sin nombre. Alta. | Añadir nombre «Borrar último carácter» y asegurar rol/acción accesibles en el componente compartido. |
| H03 | 1.4.3 Contraste mínimo (AA) | Barrera calculable: la instrucción de sugerencias usa `Colors.white38`, tamaño 16, sobre el fondo `#121212`. Ver [suggestion_bar.dart](../lib/widgets/suggestion_bar.dart), línea 43, y [app_theme.dart](../lib/config/app_theme.dart). La mezcla alfa se evalúa con la fórmula de luminancia WCAG en la prueba adjunta; debe alcanzar 4,5:1 para este texto normal. | Dificulta leer la instrucción necesaria para obtener continuaciones. Media. | Aumentar contraste y medir también los estados restantes. El comentario «alto contraste» del tema no acredita cumplimiento. |
| H04 | 3.3.1 Identificación de errores (A) | Barrera en código: enviar login o registro con campos principales vacíos ejecuta `return` sin mensaje de error ni identificación del campo. Ver [login_screen.dart](../lib/screens/login_screen.dart), línea 28, y [register_screen.dart](../lib/screens/register_screen.dart), líneas 31–34. | El usuario no recibe explicación de por qué no avanza. Media. | Mostrar errores textuales asociados a cada campo vacío y comprobar su anuncio accesible. |

Los cuatro hallazgos son grupos de problemas; no representan cuatro criterios únicos ni un porcentaje de cumplimiento. H02 afecta dos criterios. Las pruebas de widget complementan la lectura de código, pero no sustituyen la comprobación con tecnologías de asistencia en Windows.

## Evidencia favorable y puntos abiertos

| Criterio | Estado | Evidencia / comprobación necesaria |
|---|---|---|
| 1.3.1 Información y relaciones (A) | Evidencia favorable parcial | Los formularios usan `InputDecoration.labelText`. Comprobar la asociación real en el árbol de accesibilidad y las etiquetas de controles como el interruptor «Dwell». |
| 1.4.1 Uso del color (A) | Evidencia favorable parcial | El estado de entrada distingue «Mirada» y «Mouse» mediante texto e icono; los errores incluyen texto. No se verificaron todos los estados. |
| 1.4.4 Cambio de tamaño del texto (AA) | Pendiente | Probar texto al 200 % sin recortes o pérdida funcional; la barra de sugerencias tiene altura fija de 72 y la pantalla principal una `Column` sin desplazamiento general. Son riesgos, no desbordamientos observados. |
| 1.4.10 Reajuste (AA) | Pendiente | Evaluar ventana reducida y escala de pantalla, aplicando la interpretación para software de escritorio y justificando las excepciones pertinentes. |
| 1.4.11 Contraste no textual (AA) | Pendiente | Medir límites necesarios para reconocer controles, iconos, progreso y estados; no basta medir texto. |
| 1.4.12 Espaciado del texto (AA) | Pendiente | Determinar aplicación según WCAG2ICT y capacidad de la plataforma; no asumir conformidad o fallo por ausencia de CSS. |
| 2.1.2 Sin trampas de teclado (A) | Pendiente | Recorrer formularios, diálogo E2 y exportación, incluyendo cierre y retorno del foco. |
| 2.2.1 Tiempo ajustable (A) | Pendiente | Hay permanencia de 1,2 s y un interruptor para desactivarla en tablero libre. Existe `setDwellSeconds` en el controlador, sin control visible para ese valor; estudiar aplicabilidad y alternativas durante E2 antes de atribuir incumplimiento. |
| 2.4.3 Orden del foco (A); 2.4.7 Foco visible (AA) | Pendiente | Evaluar el orden y la visibilidad en todos los flujos; H01 ya impide enfocar las celdas mediante su implementación actual. |
| 2.4.6 Encabezados y etiquetas (AA); 3.3.2 Etiquetas o instrucciones (A) | Evidencia favorable parcial | Formularios con etiquetas visibles; botones principales con texto y cierre de sesión con `tooltip`. Verificar comprensión de «Dwell» y controles del estudio. |
| 2.5.1 Gestos del puntero (A) | Evidencia favorable parcial | Las celdas usan clic y permanencia, sin exigir gestos multipunto o trayectorias. Falta recorrer todos los controles con la modalidad prevista. |
| 2.5.2 Cancelación del puntero (A) | Evidencia favorable parcial | `onTap` activa por clic y `onExit` cancela el temporizador de permanencia. La prueba adjunta comprueba salir antes del plazo; evaluar activaciones involuntarias con mirada por separado. |
| 2.5.3 Etiqueta en el nombre (A) | Pendiente | Comparar etiquetas visibles y nombres expuestos en Windows; atender primero la tecla sin nombre de H02. |
| 3.1.1 Idioma (A) | Pendiente | Interfaz en español; `MaterialApp` no declara `locale` ni configuración de localización. Verificar idioma efectivo de la semántica y lectura en español; no inferir el resultado solo del código. |
| 3.2.1 Al recibir el foco (A); 3.2.2 Al recibir entradas (A) | Pendiente | Comprobar cambios de modo, actualización de sugerencias y apertura de diálogos. Distinguir foco de teclado y permanencia del puntero. |
| 3.3.3 Sugerencias ante errores (AA) | Pendiente | Provocar correo inválido, contraseñas distintas y fallo de autenticación; evaluar claridad y acción correctiva del mensaje recibido. |
| 4.1.3 Mensajes de estado (AA) | Pendiente | Texto de errores, cola pendiente y nuevas sugerencias cambia sin `Semantics(liveRegion: true)` explícito. Comprobar anuncios reales; widgets estándar como `SnackBar` pueden aportar semántica propia. |

El tamaño de objetivo de **44 × 44** corresponde a **2.5.5, nivel AAA, en WCAG 2.1**. No se usa como requisito AA de esta auditoría. Los tamaños grandes del diseño son una decisión favorable, sin acreditar por sí solos cumplimiento WCAG ni selección ocular fiable.

## Evidencia reproducible

Archivo: [wcag_probe_test.dart](wcag_probe_test.dart). Contiene cuatro comprobaciones de diagnóstico: ausencia de activación por teclado frente a clic, nombre semántico vacío de retroceso, contraste insuficiente de la instrucción y cancelación de permanencia al salir.

Resultado ejecutado el 4 de noviembre de 2026: **4/4 comprobaciones de diagnóstico pasaron**. Contraste calculado de la instrucción: **3,625:1**, inferior a **4,5:1**. Se utilizó el SDK temporal indicado en el README y `--no-pub`, sin instalar dependencias. H04 se sustenta en revisión de código, sin prueba de envío de formulario en esta sesión.

Observación adicional fuera del conteo WCAG: al desmontar teclas sin activarlas apareció una aserción de Flutter porque `dispose()` accede al controlador de animación `late` todavía sin inicializar. La prueba semántica activa las teclas después de medir su etiqueta para evitar esa incidencia de desmontaje. No se corrigió ni se atribuye un fallo WCAG a esa aserción; requiere revisión funcional separada.

```powershell
flutter test --no-pub docs/wcag_probe_test.dart
```

**Atención:** estas pruebas describen el estado auditado y afirman la existencia de barreras; que pasen no significa que la aplicación sea accesible. Después de corregirlas, deben convertirse en pruebas de la conducta accesible esperada.

## Protocolo para completar la auditoría

1. Registrar compilación, resolución, escala de Windows, versión de Flutter y lector de pantalla. Usar cuenta de prueba, sin datos personales.
2. Recorrer solo con teclado: login, registro, tablero, cambio a teclado, escritura, sugerencias, borrado, estudio E2, exportación y cierre. Registrar foco, orden y activación de cada acción.
3. Repetir con Narrador o NVDA: nombre, rol, estado, idioma y anuncios de carga, errores y sugerencias. Registrar el texto efectivamente anunciado.
4. Evaluar 200 % de texto, ventana reducida, mensajes largos y listas de sugerencias extensas; capturar recortes y pérdida funcional.
5. Medir colores renderizados en todos los estados; guardar primer plano, fondo, ratio, tamaño y peso de letra.
6. Comprobar mirada/permanencia con hardware calibrado y participantes pertinentes: salida antes del plazo, activaciones accidentales, recuperación del error y acceso a controles del flujo completo. Esto complementa WCAG y no se sustituye por SUS o QUEST.
7. Completar la matriz de todos los criterios A/AA: cumple, no cumple, no aplicable con justificación o no evaluado. Adjuntar por caso captura/registro, pasos, resultado esperado, observado y responsable. Repetir tras corregir.

## Redacción utilizable en la tesis

> El 4 de noviembre de 2026 se revisó la accesibilidad de InteractorGate Desktop con referencia a WCAG 2.1, niveles A y AA, y la guía informativa WCAG2ICT para software no web. Se identificaron y corrigieron cuatro grupos de barreras: activación por teclado de los controles de composición, nombre accesible de retroceso, contraste de una instrucción e identificación de campos obligatorios vacíos. La suite del cliente aprobó 52 pruebas, incluidas seis de accesibilidad, y el análisis estático de Flutter terminó sin incidencias. Las pruebas verificaron los comportamientos corregidos, el borde de foco y la cancelación y activación única por permanencia. La evaluación integral con lector de pantalla de Windows, ampliación de texto y usuarios permanece pendiente; por ello, los resultados no constituyen una declaración de conformidad AA ni un porcentaje de cumplimiento.
