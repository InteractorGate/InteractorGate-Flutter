# Telemetría E2 — bloque 3

## Comportamiento

Cada evento tiene UUID v4, secuencia de la sesión y hora UTC del cliente. Antes de aplicar una edición, se guarda su evento en el almacenamiento cifrado de Windows. La cola está separada por backend y cuenta; no se envían pendientes de otro participante. La migración del avance anterior se realiza únicamente para el backend de producción, sin mezclarlo con las cuentas locales.

La app reintenta la entrega cada cinco segundos y muestra el número de pendientes. Una respuesta de éxito solo retira el evento si confirma su UUID, propietario y esquema v2. Un error de almacenamiento impide aplicar la edición correspondiente. Los límites de sesión y ensayo exigen entrega confirmada.

El payload v2 incluye `participant_id`, que corresponde al ID del perfil autenticado, no al orden de inclusión del estudio. El servidor lo compara con el token antes de escribir; si pertenece a otra cuenta, responde 403 y conserva el evento en el cliente.

El servidor usa una clave de documento determinista por usuario y evento. Un reenvío idéntico devuelve el evento original, incluida la primera hora de recepción; no inserta otro. Un identificador reutilizado con otro contenido devuelve 409. Los clientes anteriores siguen aceptándose como esquema legado, sin afirmar que sus registros permiten la reconstrucción completa.

El cierre de ensayo queda congelado al primer intento: texto, duración, estado e ID permanecen estables. El evento se conserva hasta confirmar el servidor y guardar el avance local. Si la app se reinicia entre esos pasos, la misma cuenta recupera ese cierre y aplica el avance una sola vez.

## Datos registrados

| Acción | Evento | Detalle |
|---|---|---|
| Letra, espacio o palabra | `selection` | Tipo de entrada, inserción, caracteres retirados y longitud resultante |
| Borrar | `delete` | Número de caracteres retirados |
| Limpiar | `clear` | Número de caracteres eliminados |
| Cambiar tablero | `settings` | Modo de palabras o teclado |
| Solicitar sugerencias | `suggestions` | ID de petición |
| Mostrar sugerencias | `suggestions` | Opciones en su orden e intervalo desde la entrada hasta el primer frame que las presenta |
| Aceptar sugerencia | `selection` | Petición, posición de la opción e inserción realizada |
| Inicio o fin de ensayo | `trial_start`, `trial_end` | Frase, condición, lista, bloque, orden, práctica, resultado y duración monotónica |

Los eventos de ensayo incluyen el UUID del ensayo y el tiempo monotónico transcurrido. `timestamp` corresponde al cliente y `received_at` a la primera recepción en el servidor; no se confunden ambos relojes. La duración se detiene al solicitar el cierre, antes de esperar su confirmación. Los registros de latencia incluyen persistencia local, red, inferencia y presentación de la respuesta válida; no se asigna latencia a una respuesta que no llegó a mostrarse.

No se envían imágenes. El servidor admite únicamente campos de telemetría definidos, valores simples y listas de texto acotadas; limita `data` a 4096 bytes. La telemetría del tablero libre registra acciones y cantidades, sin copiar el texto de las inserciones. La predicción de texto conserva su contrato previo y sigue enviando el contexto al backend; las pruebas E2 deben usar frases predefinidas, sin comunicaciones personales.

## Verificar y exportar

Entre ensayos, pulsa **Verificar y exportar sesión**. Se vacía la cola, se consulta la API autenticada de la propia cuenta y se comprueba que los eventos confirmados están presentes. El servidor reconstruye el texto mediante las inserciones, borrados y limpiezas, y lo compara con el texto final. También detecta huecos o duplicaciones de secuencia, ensayos abiertos, datos de contexto incoherentes y aceptación de sugerencias sin una presentación correspondiente.

El JSON se guarda en `Documentos/InteractorGate/E2/session_<UUID>_<hora>.json`. Contiene eventos, resumen y código seudónimo de la cuenta. **Registros coherentes** significa que la traza permite reconstruir lo ocurrido; no significa que la transcripción sea correcta ni demuestra eficacia del sistema. La práctica y las interrupciones conservan sus etiquetas para excluirlas del análisis que corresponda.

La exportación cubre la sesión autenticada actual. Conviene guardarla antes de cerrar sesión. El cálculo de indicadores, percentiles y análisis estadístico corresponde al bloque 6.

## Validación local realizada el 3 de noviembre de 2026

- Análisis de Flutter sin incidencias; 38 pruebas de Flutter aprobadas.
- Suite completa del backend: 36 pruebas aprobadas.
- HTTP real con SQLite y MongoDB local: seis reenvíos concurrentes guardaron una sola copia; otro usuario no pudo leer la sesión, y un contenido diferente con el mismo ID obtuvo 409.
- App Windows abierta contra localhost con cuentas ficticias `LOCAL_B3` y `LOCAL_B3_2`.
- Consulta de las solicitudes reales: ninguna en la condición sin predicción y solicitudes presentes en la condición con predicción.
- MongoDB local se pausó durante escritura, borrado y limpieza. El usuario confirmó aumento de pendientes, fallo del cierre conservando el mensaje, recuperación al reanudar y avance una sola vez.
- El usuario completó otro ensayo aceptando una sugerencia y exportó la sesión. Se contrastaron 53 eventos y dos ensayos: IDs y secuencias únicos, sin huecos y ambos textos finales reconstruidos correctamente.

Las pruebas son de piloto con ratón y datos ficticios. El banco de frases sigue siendo provisional.

## Repetir la prueba sin usar Azure

Con Docker y las dependencias Python del backend instaladas:

```powershell
docker desktop start --detach
# Primera creación; si ya existe, usar docker start ig-block3-mongo.
docker run -d --name ig-block3-mongo -p 127.0.0.1:27019:27017 mongo:7.0
cd ..\ig-django-backend
python tools/local_pilot.py
```

El helper utiliza SQLite en la carpeta temporal y MongoDB en loopback, sin conectar a las bases de nube. Crea únicamente cuentas ficticias locales; sus credenciales están documentadas en el propio helper.

En otra consola, desde Flutter:

```powershell
flutter pub get --enforce-lockfile
flutter run -d windows --dart-define=IG_API_BASE_URL=http://127.0.0.1:8000
```

Para simular indisponibilidad de entrega: `docker pause ig-block3-mongo`. Reanudar con `docker unpause ig-block3-mongo` y reintentar el cierre. La prueba automatizada HTTP/Mongo se ejecuta desde el backend con `python tools/verify_local_pilot.py`.

## Publicación y límites

Publicar primero el backend con el contrato v2 y después la app. Un cliente nuevo conserva los eventos y bloquea la confirmación si el servidor antiguo no devuelve su ID y propietario.

Backend desplegado mediante [PR #62](https://github.com/InteractorGate/ig-django-backend/pull/62), commit `128595c615e861b51a2c5c66c530f33045a29e3b`: el [workflow de despliegue](https://github.com/InteractorGate/ig-django-backend/actions/runs/41672313415) aprobó y Azure confirmó `telemetry_schema=2` antes de publicar el cliente 1.0.3. La evidencia de eventos detallada arriba corresponde al piloto local, no a participantes reales en Azure.

La preparación del backend alinea la instalación de PyTorch CPU con el pin 2.13.0 existente y actualiza dnspython a 2.9.1 para corregir la alerta de parser DNS reportada por GitHub. Su política de ramas exige pasar por `develop` antes de `main`.

La cola y el avance son locales, sin sincronización entre dispositivos. Se conservan hasta 10000 pendientes por cuenta; al alcanzar el límite no se aplica una edición sin guardarla. La exportación admite hasta 10000 eventos por sesión. No hay borrado automático de pendientes. Las cuentas necesitan autenticación válida para recuperar su propia cola. Una terminación forzada puede dejar un ensayo abierto; el resumen lo señala, sin inventar un cierre. La recuperación de colas y cierres tras reinicio está cubierta por pruebas automatizadas; la prueba manual de indisponibilidad no terminó el proceso de la app.
