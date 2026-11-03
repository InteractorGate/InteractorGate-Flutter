import 'package:flutter/material.dart';

import 'dwell_button.dart';

/// Barra de sugerencias de frase (predichas por la RNN del backend).
class SuggestionBar extends StatelessWidget {
  const SuggestionBar({
    super.key,
    required this.suggestions,
    required this.onPick,
    this.loading = false,
    this.dwellSeconds = 1.2,
    this.dwellEnabled = true,
    this.enabled = true,
    this.presentationId,
    this.onPresented,
  });

  final List<String> suggestions;
  final ValueChanged<String> onPick;
  final bool loading;
  final double dwellSeconds;
  final bool dwellEnabled;
  final bool enabled;
  final String? presentationId;
  final ValueChanged<String>? onPresented;

  @override
  Widget build(BuildContext context) {
    if (!enabled) return const SizedBox(height: 72);
    if (loading) {
      return const SizedBox(
        height: 72,
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (suggestions.isEmpty) {
      return const SizedBox(
        height: 72,
        child: Center(
          child: Text(
            'Escribe para ver sugerencias…',
            style: TextStyle(color: Colors.white38, fontSize: 16),
          ),
        ),
      );
    }
    final id = presentationId;
    if (id != null && onPresented != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (context.mounted) onPresented!(id);
      });
    }
    return SizedBox(
      height: 72,
      child: Row(
        children: [
          for (final s in suggestions)
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(4),
                child: DwellButton(
                  dwellSeconds: dwellSeconds,
                  dwellEnabled: dwellEnabled,
                  color: const Color(0xFF264D33),
                  onSelected: () => onPick(s),
                  child: Text(
                    s,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 18),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
