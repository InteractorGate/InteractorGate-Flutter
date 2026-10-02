import 'dart:async';

import 'package:flutter/material.dart';

/// Botón seleccionable por **permanencia (dwell)** o por clic/tap.
///
/// Al posar el puntero (que la mirada controla) sobre el botón, arranca una
/// barra de progreso; si se mantiene [dwellSeconds], dispara [onSelected].
/// Un tap (o un parpadeo=clic del tracker) lo dispara de inmediato.
///
/// La permanencia **tolera salidas breves** de [toleranceSeconds]: si el
/// puntero abandona el botón y vuelve antes de ese plazo, la cuenta se reanuda
/// donde estaba en vez de reiniciarse.
///
/// Importa porque el motor de mirada no es estable a la escala de la celda:
/// en la medición del 06/09, **20 de 32 ensayos acertaron la celda pero solo 7
/// llegaron a disparar** — el punto entraba y salía. Sin tolerancia, cada
/// excursión de un fotograma tira 1.2 s de espera del usuario.
///
/// La idea es de Kopecek & Kremlacek (2023), validada con pacientes de
/// esclerosis múltiple avanzada: «there was a possibility to deviate the gaze
/// direction from the element for 0.5 s without interrupting the confirmation
/// process». Aquí se implementa una variante **más estricta**: allí la cuenta
/// sigue corriendo durante la desviación, así que puede confirmarse con la
/// mirada fuera; aquí se **pausa y se reanuda**, de modo que nunca se dispara
/// una selección mientras el puntero está fuera del botón. Cuesta añadir a la
/// espera el tiempo que dure la excursión, y a cambio cierra esa vía de
/// activación involuntaria (*Midas touch*).
class DwellButton extends StatefulWidget {
  const DwellButton({
    super.key,
    required this.child,
    required this.onSelected,
    this.dwellSeconds = 1.2,
    this.toleranceSeconds = 0.5,
    this.dwellEnabled = true,
    this.color,
  });

  final Widget child;
  final VoidCallback onSelected;
  final double dwellSeconds;

  /// Cuánto puede salirse el puntero sin perder la permanencia acumulada.
  /// A 0 se recupera el comportamiento anterior (cancelar al salir).
  final double toleranceSeconds;
  final bool dwellEnabled;
  final Color? color;

  @override
  State<DwellButton> createState() => _DwellButtonState();
}

class _DwellButtonState extends State<DwellButton>
    with SingleTickerProviderStateMixin {
  Timer? _grace;
  late final AnimationController _progress = AnimationController(vsync: this);

  /// Hay una permanencia en curso: el puntero está dentro, o salió hace menos
  /// de [DwellButton.toleranceSeconds] y todavía puede volver.
  bool _armed = false;

  Duration get _dwell =>
      Duration(milliseconds: (widget.dwellSeconds * 1000).round());

  Duration get _tolerance =>
      Duration(milliseconds: (widget.toleranceSeconds * 1000).round());

  @override
  void initState() {
    super.initState();
    // El propio controlador de la barra lleva la cuenta: `forward()` reanuda
    // desde el progreso acumulado y tarda solo lo que falta. Asi no hay dos
    // relojes que mantener en sincronia con el de la animacion.
    _progress.addStatusListener((s) {
      if (s == AnimationStatus.completed) _fire();
    });
  }

  void _startDwell() {
    if (!widget.dwellEnabled) return;
    // Vuelta dentro de la tolerancia: se cancela el plazo de gracia y la
    // cuenta sigue donde estaba. Reiniciarla aqui era el comportamiento
    // anterior, y es lo que hacia falta arreglar.
    _grace?.cancel();
    _grace = null;
    _armed = true;
    _progress
      ..duration = _dwell
      ..forward();
  }

  void _onExit() {
    if (!_armed) return;
    _progress.stop();          // conserva el progreso; no lo pierde
    if (widget.toleranceSeconds <= 0) {
      _cancelDwell();
      return;
    }
    _grace?.cancel();
    _grace = Timer(_tolerance, _cancelDwell);
  }

  void _cancelDwell() {
    _armed = false;
    _grace?.cancel();
    _grace = null;
    _progress
      ..stop()
      ..reset();
  }

  void _fire() {
    _cancelDwell();
    widget.onSelected();
  }

  @override
  void dispose() {
    _grace?.cancel();
    _progress.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final baseColor =
        widget.color ?? Theme.of(context).colorScheme.surfaceContainerHighest;
    return MouseRegion(
      onEnter: (_) => _startDwell(),
      onExit: (_) => _onExit(),
      child: GestureDetector(
        onTap: _fire,
        child: Stack(
          fit: StackFit.expand,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: baseColor,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.white24),
              ),
              child: Center(child: widget.child),
            ),
            if (widget.dwellEnabled)
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: ClipRRect(
                  borderRadius: const BorderRadius.only(
                    bottomLeft: Radius.circular(12),
                    bottomRight: Radius.circular(12),
                  ),
                  child: AnimatedBuilder(
                    animation: _progress,
                    builder: (context, _) => LinearProgressIndicator(
                      value: _progress.value,
                      minHeight: 6,
                      backgroundColor: Colors.transparent,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
