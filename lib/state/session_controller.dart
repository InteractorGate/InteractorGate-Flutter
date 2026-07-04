import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import '../services/prediction_service.dart';
import '../services/telemetry_service.dart';

/// Estado de una sesión de comunicación: texto compuesto, sugerencias de la
/// RNN y configuración de dwell. Coordina predicción y telemetría.
class SessionController extends ChangeNotifier {
  SessionController(this._predictions, this._telemetry)
      : sessionId = const Uuid().v4();

  final PredictionService _predictions;
  final TelemetryService _telemetry;

  final String sessionId;

  String text = '';
  List<String> suggestions = [];
  bool loadingSuggestions = false;

  // Configuración de dwell (permanencia).
  double dwellSeconds = 1.2;
  bool dwellEnabled = true;

  Future<void> start() =>
      _telemetry.log(sessionId: sessionId, eventType: 'session_start');

  Future<void> end() =>
      _telemetry.log(sessionId: sessionId, eventType: 'session_end');

  void setDwellEnabled(bool value) {
    dwellEnabled = value;
    notifyListeners();
  }

  void setDwellSeconds(double value) {
    dwellSeconds = value;
    notifyListeners();
  }

  Future<void> type(String char) async {
    text += char;
    notifyListeners();
    await _refreshSuggestions();
  }

  Future<void> space() => type(' ');

  Future<void> backspace() async {
    if (text.isEmpty) return;
    text = text.substring(0, text.length - 1);
    notifyListeners();
    await _refreshSuggestions();
  }

  void clear() {
    text = '';
    suggestions = [];
    notifyListeners();
  }

  Future<void> applySuggestion(String phrase) async {
    text = text.isEmpty ? phrase : '${text.trimRight()} $phrase';
    suggestions = [];
    notifyListeners();
    await _telemetry.log(
      sessionId: sessionId,
      eventType: 'selection',
      selectedWord: phrase,
    );
  }

  Future<void> _refreshSuggestions() async {
    final context = text.trim();
    if (context.isEmpty) {
      suggestions = [];
      notifyListeners();
      return;
    }
    loadingSuggestions = true;
    notifyListeners();
    try {
      final prediction = await _predictions.predictText(context, sessionId);
      suggestions = prediction.suggestions;
    } catch (_) {
      suggestions = [];
    } finally {
      loadingSuggestions = false;
      notifyListeners();
    }
  }

  /// Registra un evento de selección de tecla (opcionalmente con coords de mirada).
  Future<void> logKeySelection(String key, {Map<String, double>? gaze}) =>
      _telemetry.log(
        sessionId: sessionId,
        eventType: 'selection',
        selectedWord: key,
        gaze: gaze,
      );
}
