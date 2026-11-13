import 'package:flutter/material.dart';

import '../state/speech_controller.dart';
import 'dwell_button.dart';

/// Botón grande del modo discurso: **HABLAR** pronuncia el mensaje y, mientras
/// suena, **DETENER** lo corta. Se activa por permanencia o clic.
class SpeakButton extends StatelessWidget {
  const SpeakButton({
    super.key,
    required this.status,
    required this.enabled,
    required this.onPressed,
    this.dwellSeconds = 1.2,
    this.dwellEnabled = true,
  });

  final SpeechStatus status;
  final bool enabled;
  final VoidCallback onPressed;
  final double dwellSeconds;
  final bool dwellEnabled;

  @override
  Widget build(BuildContext context) {
    final busy = status != SpeechStatus.idle;
    final active = enabled || busy;
    final (IconData icon, String label) = switch (status) {
      SpeechStatus.idle => (Icons.volume_up, 'HABLAR'),
      SpeechStatus.loading => (Icons.hourglass_top, 'PREPARANDO'),
      SpeechStatus.speaking => (Icons.stop_circle_outlined, 'DETENER'),
    };
    return Semantics(
      button: true,
      enabled: active,
      label: busy ? 'Detener la voz' : 'Pronunciar el mensaje',
      excludeSemantics: true,
      child: IgnorePointer(
        ignoring: !active,
        child: Opacity(
          opacity: active ? 1 : 0.4,
          child: DwellButton(
            dwellSeconds: dwellSeconds,
            dwellEnabled: dwellEnabled && active,
            color: busy ? const Color(0xFF4D2626) : const Color(0xFF1F4D2B),
            onSelected: onPressed,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, size: 32),
                const SizedBox(width: 10),
                Text(
                  label,
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
