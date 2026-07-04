import 'dart:async';

import 'package:flutter/material.dart';

/// Botón seleccionable por **permanencia (dwell)** o por clic/tap.
///
/// Al posar el puntero (que la mirada controla) sobre el botón, arranca una
/// barra de progreso; si se mantiene [dwellSeconds], dispara [onSelected].
/// Un tap (o un parpadeo=clic del tracker) lo dispara de inmediato.
class DwellButton extends StatefulWidget {
  const DwellButton({
    super.key,
    required this.child,
    required this.onSelected,
    this.dwellSeconds = 1.2,
    this.dwellEnabled = true,
    this.color,
  });

  final Widget child;
  final VoidCallback onSelected;
  final double dwellSeconds;
  final bool dwellEnabled;
  final Color? color;

  @override
  State<DwellButton> createState() => _DwellButtonState();
}

class _DwellButtonState extends State<DwellButton>
    with SingleTickerProviderStateMixin {
  Timer? _timer;
  late final AnimationController _progress = AnimationController(vsync: this);
  bool _hovering = false;

  Duration get _dwell =>
      Duration(milliseconds: (widget.dwellSeconds * 1000).round());

  void _startDwell() {
    if (!widget.dwellEnabled) return;
    _hovering = true;
    _progress
      ..duration = _dwell
      ..forward(from: 0);
    _timer?.cancel();
    _timer = Timer(_dwell, () {
      if (_hovering) _fire();
    });
  }

  void _cancelDwell() {
    _hovering = false;
    _timer?.cancel();
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
    _timer?.cancel();
    _progress.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final baseColor =
        widget.color ?? Theme.of(context).colorScheme.surfaceContainerHighest;
    return MouseRegion(
      onEnter: (_) => _startDwell(),
      onExit: (_) => _cancelDwell(),
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
