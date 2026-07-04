import '../models/prediction.dart';
import 'api_client.dart';

/// Predicción de texto (RNN real) vía `/api/predictions/`.
class PredictionService {
  PredictionService(this._api);

  final ApiClient _api;

  Future<Prediction> predictText(String context, String sessionId) async {
    final data = await _api.postJson('/api/predictions/', {
      'input_type': 'text',
      'raw_input': {'context': context},
      'session_id': sessionId,
    });
    return Prediction.fromJson(data);
  }
}
