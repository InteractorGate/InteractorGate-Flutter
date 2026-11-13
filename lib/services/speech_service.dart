import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'api_client.dart';

/// Error de la síntesis o reproducción de voz, con un mensaje para la interfaz.
class SpeechException implements Exception {
  SpeechException(this.message);
  final String message;

  @override
  String toString() => 'SpeechException: $message';
}

/// Convierte texto en audio WAV.
abstract class SpeechSynthesizer {
  Future<Uint8List> synthesize(String text);
}

class _AzureToken {
  _AzureToken(this.token, this.region, this.voice, this.expiresAt);
  final String token;
  final String region;
  final String voice;
  final DateTime expiresAt;
}

/// Síntesis neural con **Azure AI Speech** (API REST).
///
/// La clave de Azure vive solo en el backend: `/api/speech/token/` entrega un
/// token de 10 minutos, la región y la voz. El texto viaja directo a Azure y no
/// pasa por el backend.
class AzureSpeechSynthesizer implements SpeechSynthesizer {
  AzureSpeechSynthesizer(
    this._api, {
    http.Client? client,
    DateTime Function()? now,
  }) : _http = client ?? http.Client(),
       _now = now ?? DateTime.now;

  final ApiClient _api;
  final http.Client _http;
  final DateTime Function() _now;
  _AzureToken? _cached;

  static const _timeout = Duration(seconds: 15);
  static const outputFormat = 'riff-24khz-16bit-mono-pcm';
  static final _region = RegExp(r'^[a-z0-9]+$');

  /// Descarta el token (p. ej. al cerrar sesión).
  void clear() => _cached = null;

  Future<_AzureToken> _token({bool force = false}) async {
    final cached = _cached;
    if (!force && cached != null && _now().isBefore(cached.expiresAt)) {
      return cached;
    }
    _cached = null;
    final data = await _api.getJson('/api/speech/token/');
    final token = data['token'];
    final region = data['region'];
    final voice = data['voice'];
    if (token is! String ||
        token.isEmpty ||
        region is! String ||
        !_region.hasMatch(region) ||
        voice is! String ||
        voice.isEmpty) {
      throw SpeechException('El servidor devolvió una configuración de voz inválida.');
    }
    final seconds = (data['expires_in'] as num?)?.toInt() ?? 540;
    return _cached = _AzureToken(
      token,
      region,
      voice,
      _now().add(Duration(seconds: seconds)),
    );
  }

  @override
  Future<Uint8List> synthesize(String text) async {
    var token = await _token();
    var res = await _post(token, text);
    if (res.statusCode == 401) {
      token = await _token(force: true);
      res = await _post(token, text);
    }
    if (res.statusCode != 200) {
      throw SpeechException(
        'Azure AI Speech respondió con el código ${res.statusCode}.',
      );
    }
    return res.bodyBytes;
  }

  Future<http.Response> _post(_AzureToken token, String text) => _http
      .post(
        Uri.parse(
          'https://${token.region}.tts.speech.microsoft.com/cognitiveservices/v1',
        ),
        headers: {
          'Authorization': 'Bearer ${token.token}',
          'Content-Type': 'application/ssml+xml',
          'X-Microsoft-OutputFormat': outputFormat,
          'User-Agent': 'InteractorGate',
        },
        body: utf8.encode(ssml(text, token.voice)),
      )
      .timeout(_timeout);

  /// Documento SSML con el texto escapado. El idioma sale del nombre de la voz
  /// (`es-PE-CamilaNeural` → `es-PE`).
  static String ssml(String text, String voice) {
    final parts = voice.split('-');
    final lang = parts.length >= 2 ? '${parts[0]}-${parts[1]}' : 'es-PE';
    return "<speak version='1.0' xml:lang='${_escape(lang)}'>"
        "<voice name='${_escape(voice)}'>${_escape(text)}</voice></speak>";
  }

  static String _escape(String value) => value
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&apos;');
}
