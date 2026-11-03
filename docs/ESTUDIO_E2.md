# Estudio E2 — guía del piloto

Estado: implementación, análisis y 27 pruebas automatizadas aprobados. El usuario confirmó las cuatro comprobaciones manuales con P01, incluida práctica, ambas condiciones en S2, interrupción, reintento sin conexión y recuperación del avance. La inspección directa de bases de datos está pendiente por conectividad; la publicación del piloto se consulta en [Releases](https://github.com/InteractorGate/InteractorGate-Flutter/releases/tag/v1.0.2).

## Alcance del banco

El usuario autorizó preparar frases provisionales para probar el programa. `pilot-v1` contiene 40 frases de medición y diez de práctica. Las listas no son todavía un instrumento validado: falta revisar equivalencia de frecuencia de palabras, comprensión y pertinencia con los investigadores. Ninguna frase coincide exactamente, tras normalización, con las 103 secuencias del corpus actual en `ig-django-backend/ai_modules/rnn/corpus.py`. Repetir la comprobación si cambia el entrenamiento. La ausencia de frases completas repetidas no acredita generalización del predictor.

La lista A tiene una media de 21,10 caracteres (17–27) y B de 21,85 (18–26), incluidos espacios. Se conservan las mismas frases y orden por participante durante esta versión del piloto.

## Preparación y ejecución

1. Entrar con una cuenta seudónima individual y seleccionar **Preparar estudio E2**.
2. Confirmar el orden de inclusión según el registro del investigador. El número sugerido por el código no sustituye ese registro. Impares: A con predicción y B sin predicción; pares: asignación inversa. La elección queda fija para esa cuenta en este equipo.
3. Seleccionar **S1 — Práctica**. Cada ensayo requiere **Iniciar ensayo**, componer un mensaje y **Terminar mensaje**. Los diez mensajes (cinco por condición) quedan marcados como práctica, fuera de la medición. El tablero no admite escritura antes de iniciar.
4. Seleccionar **S2 — Primera mitad** después de la práctica. Hay cuatro bloques alternados de cinco frases, diez por condición. La condición inicial se aleatoriza de forma reproducible por participante y sesión.
5. Seleccionar **S3 — Segunda mitad** después de S2. Utiliza las otras veinte frases, sin repetir objetivos de medición.
6. **Interrumpir ensayo** registra el texto parcial y el estado `interrupted`, sin avanzar la frase. Un nuevo inicio crea otro UUID. Se puede pausar entre ensayos. Cambiar de sesión o volver al tablero libre requiere terminar o interrumpir primero el ensayo activo.
7. Cerrar sesión o la ventana interrumpe un ensayo activo antes de registrar el cierre de la sesión. Si falla la entrega, se conserva el estado para reintentar.

Con predicción se utiliza el servicio actual. Sin predicción se bloquean las solicitudes y la aceptación de sugerencias y se reserva el mismo espacio vacío de la barra. El teclado, las palabras y el dwell son los mismos; el ajuste de dwell queda bloqueado durante el estudio. Las decisiones sobre el predictor definitivo y las palabras incompletas siguen en los bloques 4 y 6.

El investigador supervisa pausas cada diez minutos, máximo de 45 minutos por sesión, separación de al menos un día y suspensión ante fatiga o malestar. El programa permite elegir S2/S3 el mismo día para el piloto técnico; eso no equivale a cumplir el calendario del protocolo.

## Qué queda registrado

- `settings`: sesión del protocolo, número de inclusión, lista con predicción, semilla, versión del banco, orden de las frases y dwell.
- `trial_start`: UUID del ensayo, frase objetivo e identificador, condición, lista, bloque, orden, sesión del protocolo y `practice`.
- `trial_end`: mismos identificadores, estado completado/interrumpido, texto final y duración local de composición con reloj monotónico. La duración comienza tras confirmar el inicio y se detiene al solicitar el fin; no incluye la espera de la confirmación final.
- Los eventos del banco llevan `provisional=true`. El backend asocia `user_id` al token autenticado.

El avance y la asignación se guardan por cuenta en el almacenamiento seguro del equipo. Los resultados de ensayo quedan en Azure. El bloque 3 incorporará instrumentación de todas las acciones, recuperación y deduplicación. Un ACK perdido o un error al guardar el avance local puede duplicar límites al reintentar; una terminación forzada puede dejar un ensayo abierto. No mezclar los datos de este piloto con resultados de participantes objetivo.

## Prueba manual de aceptación

Usar una cuenta de piloto en el mismo equipo. Para comprobar técnicamente los controles pueden usarse mensajes cortos de prueba; esos registros no representan ensayos de eficacia.

1. Intentar preparar S2 antes de completar práctica: debe impedirlo con un mensaje claro.
2. Completar los diez mensajes de práctica; observar cinco con y cinco sin predicción. En la condición sin predicción la barra queda vacía y no cambia la posición del teclado.
3. Preparar S2 y completar sus diez primeros mensajes: un bloque de cinco de cada condición. Confirmar frase visible, tablero vacío al iniciar y avance solo después de terminar.
4. En el siguiente ensayo, escribir, interrumpir e iniciar de nuevo: debe conservar la misma frase, limpiar el texto y generar otro UUID.
5. Desconectar la red al terminar un ensayo: debe mostrar el error y conservar el mensaje. Reconectar y terminar de nuevo. No cambiar de cuenta durante el reintento.
6. Cerrar sesión y volver a entrar: seleccionar S2 de nuevo y comprobar que conserva el siguiente ensayo. Comprobar que otra cuenta mantiene su propio avance y asignación.
7. Consultar en Azure los eventos del piloto para comprobar coincidencia de UUID de inicio y fin, datos de condición y práctica, orden y ausencia de cruces entre cuentas.

Las pruebas automatizadas verifican que ningún camino de composición llama al predictor sin predicción, que las respuestas antiguas no se aplican a otro ensayo y que S2/S3 contienen cuarenta frases distintas.

## Listas provisionales de medición

| ID A | Frase A | Caracteres | ID B | Frase B | Caracteres |
|---|---|---:|---|---|---:|
| A1 | quiero tomar agua | 17 | B1 | quiero tomar leche | 18 |
| A2 | necesito agua tibia | 19 | B2 | necesito leche tibia | 20 |
| A3 | quiero comer arroz | 18 | B3 | quiero comer fruta | 18 |
| A4 | necesito comer algo | 19 | B4 | necesito beber algo | 19 |
| A5 | quiero descansar ahora | 22 | B5 | quiero acostarme ahora | 22 |
| A6 | necesito una manta | 18 | B6 | necesito una almohada | 21 |
| A7 | puedes acercar la mesa | 22 | B7 | puedes acercar la silla | 23 |
| A8 | puedes abrir la puerta | 22 | B8 | puedes cerrar la ventana | 24 |
| A9 | quiero mirar el patio | 21 | B9 | quiero mirar la calle | 21 |
| A10 | quiero escuchar la radio | 24 | B10 | quiero escuchar un cuento | 25 |
| A11 | necesito hablar con alguien | 27 | B11 | necesito estar con alguien | 26 |
| A12 | quiero ver a mi hermano | 23 | B12 | quiero ver a mi hermana | 23 |
| A13 | por favor trae mi vaso | 22 | B13 | por favor trae mi plato | 23 |
| A14 | por favor mueve la silla | 24 | B14 | por favor mueve la mesa | 23 |
| A15 | me siento mejor hoy | 19 | B15 | me siento tranquilo hoy | 23 |
| A16 | me duele el brazo | 17 | B16 | me duele la pierna | 18 |
| A17 | quiero cambiar de canal | 23 | B17 | quiero cambiar de ropa | 22 |
| A18 | necesito lavar mis manos | 24 | B18 | necesito secar mis manos | 24 |
| A19 | quiero cenar con todos | 22 | B19 | quiero comer con todos | 22 |
| A20 | puedes dejar la luz | 19 | B20 | puedes dejar la puerta | 22 |

## Frases de práctica (no analizadas)

1. hola me puedes escuchar
2. quiero probar el teclado
3. puedo escribir un mensaje
4. vamos a practicar juntos
5. necesito ajustar mi silla
6. hoy vamos a escribir
7. puedo borrar una letra
8. vamos a probar otra vez
9. este mensaje es de prueba
10. quiero terminar la prueba
