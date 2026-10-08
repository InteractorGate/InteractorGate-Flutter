import 'dart:convert';
import 'dart:io';

/// Resumen de la calibración del participante, para dejarla en el registro.
///
/// El sidecar guarda la calibración en `calibration_<código>.json`: empaquetado
/// en `%LOCALAPPDATA%\InteractorGate`, y en desarrollo en `sidecar\` (ver
/// `sidecar/config.py`). Del archivo solo se copian la fecha, la versión y el
/// error de verificación; las muestras crudas se quedan en el equipo.
///
/// Devuelve null si el participante todavía no tiene calibración (el sidecar la
/// hace al entrar por primera vez, después de abrirse la sesión).
Future<Map<String, Object?>?> leerCalibracion(String? usuario) async {
  if (usuario == null) return null;
  final codigo = usuario.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '');
  final nombre = 'calibration_$codigo.json';
  final candidatos = [
    if (Platform.environment['LOCALAPPDATA'] != null)
      '${Platform.environment['LOCALAPPDATA']}\\InteractorGate\\$nombre',
    '${Directory.current.path}\\sidecar\\$nombre',
  ];
  // Lectura síncrona: el archivo pesa pocos KB y se lee solo al abrir una
  // sesión o un ensayo.
  for (final ruta in candidatos) {
    final archivo = File(ruta);
    if (!archivo.existsSync()) continue;
    try {
      final json = jsonDecode(archivo.readAsStringSync()) as Map;
      return {
        'creada': json['creada'],
        'features_version': json['features_version'],
        if (json['verificacion'] != null) 'verificacion': json['verificacion'],
      };
    } catch (_) {
      return {'ilegible': true};
    }
  }
  return null;
}
