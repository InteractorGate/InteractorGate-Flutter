import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import '../services/calibration_info.dart';
import '../services/prediction_service.dart';
import '../services/telemetry_service.dart';

/// Modo del tablero: celdas grandes de palabras (amigable con la mirada) o
/// teclado de letras (escritura libre).
enum BoardMode { words, keyboard }

/// Condición experimental de E2 (diseño intra-sujeto, sección 4.5 del informe).
enum Condicion { conPrediccion, sinPrediccion }

extension CondicionNombre on Condicion {
  /// Nombre estable con el que la condición queda en los registros.
  String get clave =>
      this == Condicion.conPrediccion ? 'con_prediccion' : 'sin_prediccion';
}

/// Un ensayo de E2: escribir [objetivo] en una [condicion] dada. Los
/// contadores son un resumen para revisar en el momento; el análisis se hace
/// con los eventos uno a uno.
class Ensayo {
  Ensayo(this.numero, this.condicion, this.objetivo) : inicio = DateTime.now();

  final int numero;
  final Condicion condicion;
  final String objetivo;
  final DateTime inicio;
  bool completado = false;

  int selecciones = 0;
  int teclas = 0;
  int palabras = 0;
  int sugerenciasAceptadas = 0;
  int borrados = 0;
  int limpiezas = 0;
  int cambiosTablero = 0;
}

/// Estado de una sesión de comunicación: texto compuesto, sugerencias de la
/// RNN y configuración de dwell. Coordina predicción y telemetría.
///
/// Una sesión dura lo que dura el inicio de sesión de un participante:
/// [comenzar] al entrar y [terminar] al salir o cerrar la app. Dentro de ella
/// el investigador puede abrir ensayos de E2 ([iniciarEnsayo]).
class SessionController extends ChangeNotifier {
  SessionController(this._predictions, this._telemetry, {this.appVersion = ''});

  final PredictionService _predictions;
  final TelemetryService _telemetry;
  final String appVersion;

  String sessionId = '';
  String? _usuario;
  bool get activa => _usuario != null;

  String text = '';
  List<String> suggestions = [];
  bool loadingSuggestions = false;

  // Configuración de dwell (permanencia).
  double dwellSeconds = 1.2;
  bool dwellEnabled = true;

  // Tablero por defecto: celdas grandes de palabras (amigable con la mirada).
  BoardMode boardMode = BoardMode.words;

  /// Fuera de un ensayo la predicción está activa (uso normal de la app).
  Condicion condicion = Condicion.conPrediccion;
  bool get prediccionActiva => condicion == Condicion.conPrediccion;

  Ensayo? ensayo;
  int _ensayosAbiertos = 0;

  /// Posición del puntero en la ventana, en fracción [0..1]. Con el sidecar en
  /// modo Mouse el puntero ES la mirada (suavizada).
  Map<String, double>? puntero;

  // Para descartar respuestas de predicción que llegan tarde.
  int _consulta = 0;

  Future<void> comenzar(String usuario) async {
    if (_usuario == usuario) return;
    if (activa) await terminar();
    _usuario = usuario;
    sessionId = const Uuid().v4();
    text = '';
    suggestions = [];
    ensayo = null;
    _ensayosAbiertos = 0;
    condicion = Condicion.conPrediccion;
    _telemetry.abrirSesion(usuario, sessionId);
    notifyListeners();
    await _log('session_start', data: {
      'app_version': appVersion,
      ..._ajustes(),
      'calibracion': await leerCalibracion(usuario),
    });
  }

  Future<void> terminar() async {
    if (!activa) return;
    if (ensayo != null && !ensayo!.completado) {
      await terminarEnsayo(completado: false);
    }
    await _log('session_end', data: {'ensayos': _ensayosAbiertos});
    await _telemetry.vaciar();
    _telemetry.cerrarSesion();
    _usuario = null;
  }

  /// Cambiar de tablero es una celda más del tablero: dentro de un ensayo
  /// cuenta como selección (cuesta una permanencia como cualquier otra).
  void toggleBoardMode() {
    boardMode =
        boardMode == BoardMode.words ? BoardMode.keyboard : BoardMode.words;
    ensayo?.selecciones++;
    ensayo?.cambiosTablero++;
    notifyListeners();
    _log('settings', gaze: puntero, data: {
      ..._ajustes(),
      'cambio': 'tablero',
      ..._ensayoData(),
    });
  }

  void setDwellEnabled(bool value) {
    dwellEnabled = value;
    notifyListeners();
    _log('settings', data: _ajustes());
  }

  void setDwellSeconds(double value) {
    dwellSeconds = value;
    notifyListeners();
    _log('settings', data: _ajustes());
  }

  // --- Ensayos de E2 (los abre el investigador desde el teclado) -----------

  Future<void> iniciarEnsayo(Condicion cond, String objetivo) async {
    if (ensayo != null && !ensayo!.completado) {
      await terminarEnsayo(completado: false);
    }
    _ensayosAbiertos++;
    condicion = cond;
    ensayo = Ensayo(_ensayosAbiertos, cond, objetivo.trim());
    text = '';
    suggestions = [];
    notifyListeners();
    await _log('trial_start', data: {
      ..._ensayoData(),
      ..._ajustes(),
      'calibracion': await leerCalibracion(_usuario),
    });
  }

  /// Cierra el ensayo en curso: [completado] si el texto llegó al objetivo,
  /// o abandonado si el investigador lo corta.
  Future<void> terminarEnsayo({required bool completado}) async {
    final e = ensayo;
    if (e == null || e.completado) return;
    e.completado = true;
    notifyListeners();
    await _log('trial_end', data: {
      ..._ensayoData(),
      'completado': completado,
      'texto_final': text,
      'duracion_ms': DateTime.now().difference(e.inicio).inMilliseconds,
      'selecciones': e.selecciones,
      'teclas': e.teclas,
      'palabras': e.palabras,
      'sugerencias_aceptadas': e.sugerenciasAceptadas,
      'borrados': e.borrados,
      'limpiezas': e.limpiezas,
      'cambios_tablero': e.cambiosTablero,
    });
  }

  /// Vuelve al uso libre: sin ensayo y con predicción.
  void salirDeEnsayos() {
    ensayo = null;
    condicion = Condicion.conPrediccion;
    notifyListeners();
  }

  // --- Entrada de texto -----------------------------------------------------

  Future<void> type(String char) async {
    text += char;
    ensayo?.selecciones++;
    ensayo?.teclas++;
    notifyListeners();
    _logSeleccion(char == ' ' ? 'espacio' : 'tecla', char);
    await _despuesDeEditar();
  }

  Future<void> space() => type(' ');

  Future<void> backspace() async {
    if (text.isEmpty) return;
    final borrado = text.substring(text.length - 1);
    text = text.substring(0, text.length - 1);
    ensayo?.selecciones++;
    ensayo?.borrados++;
    notifyListeners();
    _log('delete', gaze: puntero, data: {
      'borrado': borrado,
      'largo': text.length,
      ..._ensayoData(),
      if (ensayo != null) 'texto': text,
    });
    await _despuesDeEditar();
  }

  void clear() {
    final largoPrevio = text.length;
    text = '';
    suggestions = [];
    ensayo?.selecciones++;
    ensayo?.limpiezas++;
    notifyListeners();
    _log('clear', gaze: puntero, data: {
      'largo_previo': largoPrevio,
      ..._ensayoData(),
    });
  }

  /// Inserta una palabra completa (celda AAC) al texto, con espacio, y refresca
  /// las sugerencias de la RNN para seguir prediciendo.
  Future<void> insertWord(String word) async {
    text = text.isEmpty ? word : '${text.trimRight()} $word';
    ensayo?.selecciones++;
    ensayo?.palabras++;
    notifyListeners();
    _logSeleccion('celda', word);
    await _despuesDeEditar();
  }

  Future<void> applySuggestion(String phrase) async {
    final rango = suggestions.indexOf(phrase);
    text = text.isEmpty ? phrase : '${text.trimRight()} $phrase';
    suggestions = [];
    ensayo?.selecciones++;
    ensayo?.sugerenciasAceptadas++;
    notifyListeners();
    _logSeleccion('sugerencia', phrase, extra: {'rango': rango});
    _comprobarObjetivo();
  }

  void _logSeleccion(String origen, String valor,
      {Map<String, Object?>? extra}) {
    _log('selection', selectedWord: valor, gaze: puntero, data: {
      'origen': origen,
      'largo': text.length,
      ..._ensayoData(),
      if (ensayo != null) 'texto': text,
      ...?extra,
    });
  }

  Future<void> _despuesDeEditar() async {
    if (_comprobarObjetivo()) return;
    await _refreshSuggestions();
  }

  /// Cierra el ensayo solo cuando el texto coincide con la frase objetivo
  /// (sin distinguir mayúsculas, tildes ni espacios sobrantes: el teclado no
  /// tiene tildes y escribe en mayúsculas).
  bool _comprobarObjetivo() {
    final e = ensayo;
    if (e == null || e.completado) return false;
    if (normalizar(text) != normalizar(e.objetivo)) return false;
    suggestions = [];
    terminarEnsayo(completado: true);
    return true;
  }

  Future<void> _refreshSuggestions() async {
    final context = text.trim();
    if (context.isEmpty || !prediccionActiva) {
      suggestions = [];
      notifyListeners();
      return;
    }
    final consulta = ++_consulta;
    loadingSuggestions = true;
    notifyListeners();
    final t0 = DateTime.now();
    try {
      final prediction = await _predictions.predictText(context, sessionId);
      if (consulta != _consulta) return;
      suggestions = prediction.suggestions;
      _log('suggestions', data: {
        'sugerencias': suggestions,
        'largo_contexto': context.length,
        // Latencia de extremo a extremo: red + modelo + respuesta.
        'latencia_ms': DateTime.now().difference(t0).inMilliseconds,
        ..._ensayoData(),
      });
    } catch (_) {
      if (consulta != _consulta) return;
      suggestions = [];
      _log('suggestions', data: {
        'error': true,
        'latencia_ms': DateTime.now().difference(t0).inMilliseconds,
        ..._ensayoData(),
      });
    } finally {
      if (consulta == _consulta) {
        loadingSuggestions = false;
        notifyListeners();
      }
    }
  }

  Map<String, Object?> _ensayoData() {
    final e = ensayo;
    if (e == null) return {'condicion': condicion.clave};
    return {
      'ensayo': e.numero,
      'condicion': e.condicion.clave,
      'objetivo': e.objetivo,
    };
  }

  Map<String, Object?> _ajustes() => {
        'dwell_s': dwellSeconds,
        'dwell': dwellEnabled,
        'tablero': boardMode.name,
        'condicion': condicion.clave,
      };

  Future<void> _log(
    String eventType, {
    String? selectedWord,
    Map<String, double>? gaze,
    Map<String, Object?>? data,
  }) {
    if (!activa) return Future.value();
    return _telemetry.log(
      sessionId: sessionId,
      eventType: eventType,
      selectedWord: selectedWord,
      gaze: gaze,
      data: data,
    );
  }
}

/// Forma canónica para comparar el texto escrito con la frase objetivo.
String normalizar(String s) {
  const conTilde = 'áéíóúüÁÉÍÓÚÜ';
  const sinTilde = 'aeiouuAEIOUU';
  final b = StringBuffer();
  for (final r in s.runes) {
    final ch = String.fromCharCode(r);
    final i = conTilde.indexOf(ch);
    b.write(i >= 0 ? sinTilde[i] : ch);
  }
  return b.toString().toLowerCase().trim().replaceAll(RegExp(r'\s+'), ' ');
}
