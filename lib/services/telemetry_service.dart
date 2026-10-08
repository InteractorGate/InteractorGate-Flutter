import 'dart:convert';
import 'dart:io';

import 'api_client.dart';

/// Registro de eventos de interacción: cada evento va a dos sitios.
///
/// 1. **Archivo local** (`%LOCALAPPDATA%\InteractorGate\registros\<código>\`),
///    un JSON por línea y un archivo por sesión. Es el registro de referencia
///    de las pruebas con usuarios: no depende de la red, y en una sesión a
///    domicilio el investigador se lo lleva copiando la carpeta.
/// 2. **Servidor** (`/api/logs/` → Cosmos DB), como copia. Es best-effort: si
///    falla, NO interrumpe la experiencia del usuario.
///
/// La hora es la del equipo en el momento del evento (`timestamp`, UTC con
/// milisegundos); el servidor guarda aparte la de llegada. Ningún evento lleva
/// imágenes: el backend rechaza un `data` de más de 4 KB.
class TelemetryService {
  TelemetryService(this._api);

  final ApiClient _api;

  File? _archivo;
  String? _usuario;

  /// Carpeta de registros del participante, o null si no hay sesión.
  String? get carpeta => _archivo?.parent.path;

  /// Abre el archivo de una sesión nueva de [usuario]. Si no se puede crear
  /// (disco, permisos), el registro sigue solo hacia el servidor.
  void abrirSesion(String usuario, String sessionId) {
    _usuario = usuario;
    try {
      final base = Platform.environment['LOCALAPPDATA'] ??
          Directory.systemTemp.path;
      final codigo = usuario.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '');
      final dir = Directory('$base\\InteractorGate\\registros\\$codigo');
      dir.createSync(recursive: true);
      final ahora = DateTime.now();
      String dos(int n) => n.toString().padLeft(2, '0');
      final sello = '${ahora.year}${dos(ahora.month)}${dos(ahora.day)}'
          '-${dos(ahora.hour)}${dos(ahora.minute)}${dos(ahora.second)}';
      _archivo = File(
          '${dir.path}\\sesion_${sello}_${sessionId.substring(0, 8)}.jsonl');
    } catch (_) {
      _archivo = null;
    }
  }

  void cerrarSesion() {
    _archivo = null;
    _usuario = null;
  }

  Future<void> log({
    required String sessionId,
    required String eventType,
    Map<String, double>? gaze,
    String? selectedWord,
    Map<String, Object?>? data,
  }) async {
    final evento = <String, Object?>{
      'session_id': sessionId,
      'event_type': eventType,
      'timestamp': DateTime.now().toUtc().toIso8601String(),
      if (gaze != null) 'gaze_coordinates': gaze,
      if (selectedWord != null) 'selected_word': selectedWord,
      if (data != null) 'data': data,
    };
    _escribirLocal(evento);
    try {
      await _api.postJson('/api/logs/', evento);
    } catch (_) {
      // telemetría no crítica: el archivo local ya la tiene.
    }
  }

  /// Escritura síncrona: una línea de unos cientos de bytes cada pocos
  /// segundos no se nota, las líneas quedan en orden y, si la app se cierra a
  /// la fuerza, no se pierde ninguna que estuviera en cola.
  void _escribirLocal(Map<String, Object?> evento) {
    final archivo = _archivo;
    if (archivo == null) return;
    final linea = '${jsonEncode({'usuario': _usuario, ...evento})}\n';
    try {
      archivo.writeAsStringSync(linea, mode: FileMode.append, flush: true);
    } catch (_) {
      // sin disco no hay registro local; el servidor puede tenerlo.
    }
  }
}
