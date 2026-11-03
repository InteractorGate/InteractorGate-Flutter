import 'api_client.dart';

/// Envía eventos de interacción a `/api/logs/` (Cosmos DB).
///
/// Las acciones son best-effort; los límites de sesión y ensayo exigen confirmación.
class TelemetryService {
  TelemetryService(this._api);

  final ApiClient _api;

  Future<void> log({
    required String sessionId,
    required String eventType,
    Map<String, double>? gaze,
    String? selectedWord,
    Map<String, dynamic>? data,
    DateTime? timestamp,
    bool requireDelivery = false,
  }) async {
    try {
      await _api.postJson('/api/logs/', {
        'session_id': sessionId,
        'event_type': eventType,
        if (gaze != null) 'gaze_coordinates': gaze,
        if (selectedWord != null) 'selected_word': selectedWord,
        if (data != null) 'data': data,
        if (timestamp != null) 'timestamp': timestamp.toUtc().toIso8601String(),
      });
    } catch (_) {
      if (requireDelivery) rethrow;
    }
  }
}
