import 'dart:io';

import '../state/session_controller.dart';

/// Listas de frases de E2, una por condición, para no teclearlas en cada ensayo.
///
/// Archivos de texto (una frase por línea) en `%LOCALAPPDATA%\InteractorGate\`:
/// `frases_con_prediccion.txt` y `frases_sin_prediccion.txt`. Con dos listas
/// equivalentes, para contrabalancear basta con intercambiar los archivos entre
/// participantes. Si no existen, el diálogo del ensayo arranca vacío y el
/// investigador escribe la frase.
///
/// Cada ensayo propone la frase siguiente de su lista. Un ensayo abandonado
/// también la consume: para repetirla se escribe a mano.
class FrasesE2 {
  final Map<Condicion, int> _siguiente = {};

  String? proponer(Condicion condicion) {
    final frases = _leer(condicion);
    final i = _siguiente[condicion] ?? 0;
    return i < frases.length ? frases[i] : null;
  }

  void consumir(Condicion condicion) =>
      _siguiente[condicion] = (_siguiente[condicion] ?? 0) + 1;

  List<String> _leer(Condicion condicion) {
    final base = Platform.environment['LOCALAPPDATA'];
    if (base == null) return const [];
    final archivo =
        File('$base\\InteractorGate\\frases_${condicion.clave}.txt');
    try {
      return archivo
          .readAsLinesSync()
          .map((l) => l.trim())
          .where((l) => l.isNotEmpty && !l.startsWith('#'))
          .toList();
    } catch (_) {
      return const [];
    }
  }
}
