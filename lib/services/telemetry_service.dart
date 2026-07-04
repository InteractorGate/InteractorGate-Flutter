import 'api_client.dart';

/// Envía eventos de interacción a `/api/logs/` (Cosmos DB).
///
/// Es best-effort: si falla, NO interrumpe la experiencia del usuario.
class TelemetryService {
  TelemetryService(this._api);

  final ApiClient _api;

  Future<void> log({
    required String sessionId,
    required String eventType,
    Map<String, double>? gaze,
    String? selectedWord,
  }) async {
    try {
      await _api.postJson('/api/logs/', {
        'session_id': sessionId,
        'event_type': eventType,
        if (gaze != null) 'gaze_coordinates': gaze,
        if (selectedWord != null) 'selected_word': selectedWord,
      });
    } catch (_) {
      // telemetría no crítica.
    }
  }
}
