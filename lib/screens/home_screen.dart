import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/gaze_bridge.dart';
import '../state/auth_controller.dart';
import '../state/session_controller.dart';
import '../widgets/big_cell_board.dart';
import '../widgets/composed_text_bar.dart';
import '../widgets/dwell_keyboard.dart';
import '../widgets/suggestion_bar.dart';

/// Tablero de comunicación: texto compuesto, sugerencias de la RNN y teclado
/// dwell. Es la pantalla principal tras iniciar sesión.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final session = context.watch<SessionController>();
    final auth = context.read<AuthController>();
    final gaze = context.watch<GazeBridge>();

    return Scaffold(
      appBar: AppBar(
        title: Text('InteractorGate — ${auth.user?.displayName ?? ''}'),
        actions: [
          _GazeStatusChip(connected: gaze.connected),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              children: [
                const Text('Dwell'),
                Switch(
                  value: session.dwellEnabled,
                  onChanged: session.setDwellEnabled,
                ),
              ],
            ),
          ),
          IconButton(
            tooltip: 'Cerrar sesión',
            icon: const Icon(Icons.logout),
            onPressed: () => auth.logout(),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            ComposedTextBar(text: session.text),
            const SizedBox(height: 12),
            SuggestionBar(
              suggestions: session.suggestions,
              loading: session.loadingSuggestions,
              dwellSeconds: session.dwellSeconds,
              dwellEnabled: session.dwellEnabled,
              onPick: session.applySuggestion,
            ),
            const SizedBox(height: 12),
            Expanded(
              child: session.boardMode == BoardMode.words
                  ? BigCellBoard(
                      dwellSeconds: session.dwellSeconds,
                      dwellEnabled: session.dwellEnabled,
                      onWord: session.insertWord,
                      onKeyboard: session.toggleBoardMode,
                      onBackspace: session.backspace,
                    )
                  : DwellKeyboard(
                      dwellSeconds: session.dwellSeconds,
                      dwellEnabled: session.dwellEnabled,
                      onKey: (ch) {
                        session.type(ch);
                        session.logKeySelection(ch);
                      },
                      onSpace: session.space,
                      onBackspace: session.backspace,
                      onClear: session.clear,
                      onWords: session.toggleBoardMode,
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _GazeStatusChip extends StatelessWidget {
  const _GazeStatusChip({required this.connected});

  final bool connected;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
      child: Chip(
        avatar: Icon(
          connected ? Icons.visibility : Icons.mouse,
          size: 18,
          color: connected ? Colors.greenAccent : Colors.white54,
        ),
        label: Text(connected ? 'Mirada' : 'Mouse'),
      ),
    );
  }
}
