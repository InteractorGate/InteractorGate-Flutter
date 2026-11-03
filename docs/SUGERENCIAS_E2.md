# Continuaciones E2 — bloque 4

## Regla del piloto 1.0.4

La RNN del backend predice palabras siguientes a partir de palabras completas.
No es un modelo de autocompletado de prefijos.

- En el teclado, escribir `QUI` no solicita continuaciones. Completar `QUIERO`
  y pulsar **ESPACIO** solicita la continuación de `QUIERO`.
- Pulsar una palabra del tablero la considera completa y solicita directamente
  su continuación. Las sugerencias aceptadas también son palabras completas.
- Aceptar `agua` tras `QUIERO ` produce `QUIERO agua`: se eliminan únicamente
  los espacios finales anteriores y se inserta un solo espacio de separación.
  No se reemplaza la última palabra ni se añade un espacio final automático.
- Para escribir otra palabra con el teclado después de una palabra del tablero
  o una sugerencia aceptada, pulsar ESPACIO antes de sus letras.
- Borrar una letra o empezar una palabra nueva oculta las sugerencias anteriores.
  Borrar hasta dejar un espacio final puede solicitar la continuación del contexto
  restante. Limpiar no solicita predicciones.
- Sin predicción se conserva la misma escritura, pero no se solicitan ni aceptan
  sugerencias y la barra mantiene su altura vacía.

Esta regla permanece fija durante los ensayos de esta versión. No mezclar sus
registros con los pilotos anteriores para atribuir un cambio de eficacia. El
banco de frases continúa siendo provisional y la comparación de predictores
corresponde al bloque 6; este bloque no cambia pesos ni entrenamiento.

## Vigencia de una respuesta

Cada edición persistida cambia la revisión y borra la presentación anterior.
La solicitud conserva esa revisión; tanto su resultado como su error requieren
la misma sesión, revisión, texto y condición habilitada. Volver a escribir el
mismo texto después de borrar o limpiar no rehabilita una respuesta antigua.

La aceptación lleva el ID de la respuesta desde el frame mostrado hasta la
cola de ediciones. Se rechaza un clic antiguo incluso si otra respuesta repite
la frase. Cada presentación cambia la clave del botón para reiniciar el dwell.
La telemetría conserva IDs de solicitud, posiciones, textos insertados y latencia
hasta presentación con el contrato v2 existente.

## Validación

Análisis de Flutter sin incidencias y 46 pruebas aprobadas, incluidas siete pruebas
nuevas de contexto y dwell. Compilación Windows debug contra localhost completada.
El usuario aprobó las cuatro comprobaciones manuales con `LOCAL_B4`, práctica
S1 y orden de inclusión 2, el 3 de noviembre de 2026. Se contrastó la exportación
de la app con MongoDB local: 39 eventos únicos y un ensayo coherente, texto final
reconstruido coincidente, sin huecos ni secuencias repetidas. Hubo dos sugerencias
aceptadas, un borrado y dos limpiezas.

Las seis solicitudes reales de predicción en SQLite utilizaron `QUIERO`,
`QUIERO ver a mi familia`, `AGUA` o `AGUA por favor gracias`; ninguna utilizó
el prefijo `QUI`. La exportación identificó seis solicitudes y seis presentaciones.

Evidencia: `session_e5a64bc5-47d9-404f-ae9c-1eeb77264f90_1793725124629823.json`,
guardada en `Documentos/InteractorGate/E2`. SHA-256:
`76d1380746a8e3f59d22f5104c3bc46cb53611c6894f2e1479af2ea00ab97599`.
No se incorpora el archivo de eventos al repositorio. La prueba usa ratón y datos
ficticios; no acredita eficacia con participantes objetivo ni seguimiento ocular.

Publicación prevista: [Release v1.0.4](https://github.com/InteractorGate/InteractorGate-Flutter/releases/tag/v1.0.4).
El resultado de Actions y el SHA-256 del instalador se registran al cerrar la
publicación en el plan del workspace.

Prueba manual con cuenta ficticia, práctica S1 y condición **Con predicción**:

1. Escribir `QUI`: barra sin sugerencias. Completar `QUIERO` y pulsar ESPACIO:
   deben aparecer continuaciones.
2. Escribir otra letra: desaparecen las sugerencias. Borrarla y esperar la nueva
   respuesta; aceptar una continuación. Debe conservar `QUIERO` y un solo espacio
   antes del texto elegido.
3. Pulsar LIMPIAR mientras se espera una respuesta: la barra y el texto deben
   quedarse vacíos. Escribir `AGUA`, pulsar ESPACIO y aceptar una sugerencia nueva.
4. Terminar el mensaje y exportar: debe indicar **Registros coherentes**. Iniciar
   otro ensayo: texto limpio. En un bloque sin predicción, ESPACIO no muestra
   sugerencias. Las respuestas inversas y el cambio de condición se simulan además
   de forma determinista en `test/prediction_context_test.dart`.
