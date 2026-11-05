# Diagnóstico visual de la mirada

Modo exploratorio para distinguir baja apertura ocular, extrapolación del mapeo,
recorte a pantalla y suavizado. Usa el motor calibrado y la misma extracción de
rasgos del servicio. No modifica sus umbrales ni la calibración y no controla el
cursor de Windows. La vista de cámara y los parches de ojos son temporales:
los archivos contienen únicamente señales numéricas y metadatos locales.

## Abrir

Desde `sidecar`, con su entorno Python y modelos instalados:

```powershell
python main.py --diagnose-calibration "C:\ruta\calibration_c1.json"
```

También acepta el `calibration.json` del servicio. En la versión empaquetada:

```powershell
gaze_service.exe --diagnose-calibration "C:\ruta\calibration_c1.json"
```

El perfil se elige explícitamente. Se comprueban dimensiones, finitud y desviaciones
positivas del modelo y, cuando consta, su resolución de pantalla. No se reutiliza
un perfil de resolución distinta. Una calibración de otra postura, distancia o
iluminación puede fallar aun con la misma resolución: conservar esas condiciones
para investigar el problema original.

## Inspección breve

1. Mantén el encuadre, la luz y la distancia del piloto. Empieza mirando el objetivo
   blanco central. La cámara se muestra sin espejo; el parche izquierdo se voltea
   como en la extracción del motor.
2. Selecciona objetivos con **1–9**, en filas de izquierda a derecha y arriba abajo;
   **ESPACIO** avanza. Mira cada objetivo unos cinco segundos, especialmente **7–9**.
   No sigas el punto estimado: observa el objetivo blanco. El panel cambia de lado
   para no cubrirlo; **V** oculta o muestra el panel.
3. Observa la apertura de cada ojo y su media frente al umbral. `low_aperture`
   significa bloqueo por el valor medido; no confirma que los ojos estén cerrados.
   El candidato sigue calculándose para inspección, pero no actualiza el filtro.
4. Compara las coordenadas antes del recorte con la cruz rosa recortada y el círculo
   amarillo suavizado. Valores fuera de 0–1 indican extrapolación. Los errores X/Y
   son estimación menos objetivo, en píxeles: positivo = derecha/abajo.
5. Prueba un parpadeo y una pequeña variación cómoda de cabeza. **P** pausa/reanuda;
   esos fotogramas no entran en el resumen. **ESC**, **Q** o cerrar la ventana guarda
   y termina. Hay un límite de diez minutos. No hay que aprobar una puntuación.

## Evidencia y límites

Cada ejecución crea una carpeta UUID en `Documentos/InteractorGate/Diagnostico`.
`--diagnose-output <carpeta>` cambia la carpeta base. Nunca sobrescribe E1 ni el
perfil original. Los registros incluyen:

- `session.json`: hash SHA256 y ruta del perfil, resolución, umbral y filtro.
- `samples.jsonl`: objetivo, tiempo, rasgos, apertura, pose calculada por el código,
  candidato sin recorte, coordenadas recortadas y suavizadas, pausas y fallos.
- `report.json`: motivos de bloqueo y error mediano firmado por eje y objetivo.
  Excluye los primeros 1,2 s tras cambiar de objetivo o reanudar. Separa candidatos
  (también los bloqueados) de estimaciones aceptadas; conserva fallos en el denominador.

La inspección incluye feedback visible, objetivos elegidos por el operador y un
perfil previo. Sirve para localizar problemas; **no es una nueva validación E1 ni
demuestra precisión o eficacia clínica**. No se calculan grados con una distancia
o geometría supuesta. La pose usa la función existente del proyecto y no se presenta
como una medición de error angular ocular.

Antes de ajustar umbrales, comprobar si el bloqueo al mirar abajo coincide con ojos
visiblemente abiertos y rasgos finitos. Si hay apertura suficiente pero errores
persistentes, revisar la respuesta por eje y la extrapolación del perfil.
