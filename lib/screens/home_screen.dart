import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../services/frases_e2.dart';
import '../services/gaze_bridge.dart';
import '../state/auth_controller.dart';
import '../state/session_controller.dart';
import '../widgets/big_cell_board.dart';
import '../widgets/composed_text_bar.dart';
import '../widgets/dwell_keyboard.dart';
import '../widgets/suggestion_bar.dart';

/// Tablero de comunicación: texto compuesto, sugerencias de la RNN y teclado
/// dwell. Es la pantalla principal tras iniciar sesión.
///
/// Atajos del investigador para los ensayos de E2 (el ratón lo mueve la
/// mirada, así que todo se maneja con el teclado):
///   F2 = ensayo nuevo CON predicción · F3 = ensayo nuevo SIN predicción
///   F4 = abandonar el ensayo en curso · F8 = volver al uso libre
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _frases = FrasesE2();

  Future<void> _nuevoEnsayo(Condicion condicion) async {
    final session = context.read<SessionController>();
    final objetivo = await showDialog<String>(
      context: context,
      builder: (_) => _DialogoEnsayo(
        numero: (session.ensayo?.numero ?? 0) + 1,
        condicion: condicion,
        propuesta: _frases.proponer(condicion) ?? '',
      ),
    );
    if (objetivo == null || objetivo.trim().isEmpty) return;
    _frases.consumir(condicion);
    await session.iniciarEnsayo(condicion, objetivo);
  }

  @override
  Widget build(BuildContext context) {
    final session = context.watch<SessionController>();
    final auth = context.read<AuthController>();
    final gaze = context.watch<GazeBridge>();

    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.f2): () =>
            _nuevoEnsayo(Condicion.conPrediccion),
        const SingleActivator(LogicalKeyboardKey.f3): () =>
            _nuevoEnsayo(Condicion.sinPrediccion),
        const SingleActivator(LogicalKeyboardKey.f4): () =>
            session.terminarEnsayo(completado: false),
        const SingleActivator(LogicalKeyboardKey.f8): session.salirDeEnsayos,
      },
      child: Focus(
        autofocus: true,
        // Con el sidecar en modo Mouse el puntero es la mirada: su posición
        // acompaña a cada selección en el registro.
        child: MouseRegion(
          onHover: (e) {
            final size = MediaQuery.sizeOf(context);
            session.puntero = {
              'x': e.position.dx / size.width,
              'y': e.position.dy / size.height,
            };
          },
          child: Scaffold(
            appBar: AppBar(
              title: _Titulo(
                ensayo: session.ensayo,
                nombre: auth.user?.displayName ?? '',
              ),
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
                PopupMenuButton<String>(
                  tooltip: 'Ensayos (F2, F3, F4, F8)',
                  icon: const Icon(Icons.science_outlined),
                  onSelected: (v) {
                    switch (v) {
                      case 'con':
                        _nuevoEnsayo(Condicion.conPrediccion);
                      case 'sin':
                        _nuevoEnsayo(Condicion.sinPrediccion);
                      case 'abandonar':
                        session.terminarEnsayo(completado: false);
                      case 'libre':
                        session.salirDeEnsayos();
                    }
                  },
                  itemBuilder: (_) => const [
                    PopupMenuItem(
                        value: 'con', child: Text('F2  Ensayo CON predicción')),
                    PopupMenuItem(
                        value: 'sin', child: Text('F3  Ensayo SIN predicción')),
                    PopupMenuItem(
                        value: 'abandonar', child: Text('F4  Abandonar ensayo')),
                    PopupMenuItem(value: 'libre', child: Text('F8  Uso libre')),
                  ],
                ),
                IconButton(
                  tooltip: 'Cerrar sesión',
                  icon: const Icon(Icons.logout),
                  onPressed: () async {
                    await session.terminar();
                    await auth.logout();
                  },
                ),
              ],
            ),
            body: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  ComposedTextBar(text: session.text),
                  const SizedBox(height: 12),
                  // Sin predicción la barra queda vacía pero ocupa su sitio: el
                  // tablero no se mueve y sigue dentro de la zona calibrada.
                  session.prediccionActiva
                      ? SuggestionBar(
                          suggestions: session.suggestions,
                          loading: session.loadingSuggestions,
                          dwellSeconds: session.dwellSeconds,
                          dwellEnabled: session.dwellEnabled,
                          onPick: session.applySuggestion,
                        )
                      : const SizedBox(height: 72),
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
                            onKey: session.type,
                            onSpace: session.space,
                            onBackspace: session.backspace,
                            onClear: session.clear,
                            onWords: session.toggleBoardMode,
                          ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Título de la barra: durante un ensayo muestra la frase que hay que escribir
/// (en la barra y no en el cuerpo, para que el tablero no cambie de sitio).
class _Titulo extends StatelessWidget {
  const _Titulo({required this.ensayo, required this.nombre});

  final Ensayo? ensayo;
  final String nombre;

  @override
  Widget build(BuildContext context) {
    final e = ensayo;
    if (e == null) return Text('InteractorGate — $nombre');
    if (e.completado) {
      return Text('✓ Ensayo ${e.numero} terminado',
          style: const TextStyle(color: Colors.greenAccent));
    }
    return Text.rich(
      TextSpan(children: [
        TextSpan(
          text: 'Escribe:  ',
          style: TextStyle(color: Colors.white.withValues(alpha: 0.6)),
        ),
        TextSpan(
          text: e.objetivo,
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 24),
        ),
      ]),
      overflow: TextOverflow.ellipsis,
    );
  }
}

/// Diálogo del investigador: confirma (o escribe) la frase del ensayo. Enter
/// lo inicia y Esc lo cancela.
class _DialogoEnsayo extends StatefulWidget {
  const _DialogoEnsayo({
    required this.numero,
    required this.condicion,
    required this.propuesta,
  });

  final int numero;
  final Condicion condicion;
  final String propuesta;

  @override
  State<_DialogoEnsayo> createState() => _DialogoEnsayoState();
}

class _DialogoEnsayoState extends State<_DialogoEnsayo> {
  late final _frase = TextEditingController(text: widget.propuesta);

  @override
  void dispose() {
    _frase.dispose();
    super.dispose();
  }

  void _iniciar() => Navigator.of(context).pop(_frase.text);

  @override
  Widget build(BuildContext context) {
    final con = widget.condicion == Condicion.conPrediccion;
    return AlertDialog(
      title: Text(
          'Ensayo ${widget.numero} · ${con ? 'CON' : 'SIN'} predicción'),
      content: SizedBox(
        width: 520,
        child: TextField(
          controller: _frase,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: 'Frase objetivo',
            helperText: 'Enter para empezar · Esc para cancelar',
          ),
          onSubmitted: (_) => _iniciar(),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancelar'),
        ),
        FilledButton(onPressed: _iniciar, child: const Text('Empezar')),
      ],
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
