import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../services/api_client.dart';
import '../services/speech_service.dart';
import '../services/wav_player.dart';

enum SpeechStatus { idle, loading, speaking }

/// Modo discurso: pronuncia el mensaje compuesto cuando el usuario lo pide.
///
/// Repetir la misma frase reutiliza el audio ya sintetizado. Pulsar durante la
/// carga o la reproducción detiene la voz.
class SpeechController extends ChangeNotifier {
  SpeechController(this._synthesizer, this._player);

  final SpeechSynthesizer _synthesizer;
  final AudioPlayback _player;

  SpeechStatus status = SpeechStatus.idle;
  String? error;
  String? _cachedText;
  Uint8List? _cachedAudio;
  int _generation = 0;

  bool get busy => status != SpeechStatus.idle;

  /// Acción del botón: pronuncia o, si ya está hablando, detiene.
  Future<void> toggle(String text) async {
    if (busy) {
      stop();
    } else {
      await speak(text);
    }
  }

  Future<void> speak(String text) async {
    final phrase = text.trim();
    if (phrase.isEmpty) return;
    final generation = ++_generation;
    _player.stop();
    error = null;
    status = SpeechStatus.loading;
    notifyListeners();
    try {
      final audio = phrase == _cachedText && _cachedAudio != null
          ? _cachedAudio!
          : await _synthesizer.synthesize(phrase);
      if (generation != _generation) return;
      _cachedText = phrase;
      _cachedAudio = audio;
      status = SpeechStatus.speaking;
      notifyListeners();
      await _player.play(audio);
    } catch (e) {
      if (generation == _generation) error = _message(e);
    } finally {
      if (generation == _generation) {
        status = SpeechStatus.idle;
        notifyListeners();
      }
    }
  }

  void stop() {
    _generation++;
    _player.stop();
    if (status != SpeechStatus.idle) {
      status = SpeechStatus.idle;
      notifyListeners();
    }
  }

  /// Detiene la voz y olvida el último audio (al cambiar de participante).
  void reset() {
    stop();
    _cachedText = null;
    _cachedAudio = null;
    final synthesizer = _synthesizer;
    if (synthesizer is AzureSpeechSynthesizer) synthesizer.clear();
    if (error != null) {
      error = null;
      notifyListeners();
    }
  }

  static String _message(Object e) {
    if (e is SpeechException) return e.message;
    if (e is ApiException) {
      return e.statusCode == 503
          ? 'La voz no está configurada en el servidor.'
          : 'No se pudo obtener la voz: ${e.message}';
    }
    if (e is SessionExpired) return 'La sesión expiró. Vuelve a iniciar sesión.';
    if (e is SocketException || e is TimeoutException) {
      return 'Sin conexión con el servicio de voz.';
    }
    return 'No se pudo pronunciar el mensaje.';
  }

  @override
  void dispose() {
    stop();
    super.dispose();
  }
}
