/// Resultado de una predicción de texto (RNN) del backend.
///
/// El backend devuelve las sugerencias en `result.output_text` unidas por
/// `" | "`; aquí las separamos en una lista lista para la UI.
class Prediction {
  const Prediction({required this.suggestions, required this.confidence});

  final List<String> suggestions;
  final double confidence;

  factory Prediction.fromJson(Map<String, dynamic> json) {
    final result = json['result'] as Map<String, dynamic>?;
    final text = (result?['output_text'] as String?) ?? '';
    final conf = (result?['confidence_score'] as num?)?.toDouble() ?? 0.0;

    final parts = text
        .split(' | ')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();

    return Prediction(suggestions: parts, confidence: conf);
  }
}
