import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'token_store.dart';

typedef Json = Map<String, dynamic>;

/// Error de la API con el código HTTP y el mensaje del backend.
class ApiException implements Exception {
  ApiException(this.statusCode, this.message, [this.body]);
  final int statusCode;
  final String message;
  final dynamic body;

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// Se lanza cuando el refresh token también expiró: hay que volver a loguear.
class SessionExpired implements Exception {}

/// Cliente HTTP con Bearer JWT y renovación automática ante 401
/// (rotación de refresh token incluida, según el contrato del backend).
class ApiClient {
  ApiClient(this._tokens, {http.Client? client})
    : _http = client ?? http.Client();

  final TokenStore _tokens;
  final http.Client _http;
  static const _timeout = Duration(seconds: 15);

  Uri _uri(String path) => Uri.parse('${ApiConfig.baseUrl}$path');

  Future<http.Response> _send(
    String method,
    String path, {
    Object? body,
    bool auth = true,
    Duration? timeout,
  }) async {
    Future<http.Response> once() async {
      final headers = <String, String>{'Content-Type': 'application/json'};
      if (auth) {
        final token = await _tokens.access;
        if (token != null) headers['Authorization'] = 'Bearer $token';
      }
      final uri = _uri(path);
      final payload = body == null ? null : jsonEncode(body);
      switch (method) {
        case 'GET':
          return _http.get(uri, headers: headers);
        case 'POST':
          return _http.post(uri, headers: headers, body: payload);
        case 'PATCH':
          return _http.patch(uri, headers: headers, body: payload);
        default:
          throw ArgumentError('Método no soportado: $method');
      }
    }

    final limit = timeout ?? _timeout;
    var res = await once().timeout(limit);
    if (res.statusCode == 401 && auth) {
      final refreshed = await _refresh();
      if (!refreshed) throw SessionExpired();
      res = await once().timeout(limit);
    }
    return res;
  }

  Future<bool> _refresh() async {
    final refresh = await _tokens.refresh;
    if (refresh == null) return false;

    final res = await _http
        .post(
          _uri('/api/token/refresh/'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'refresh': refresh}),
        )
        .timeout(_timeout);
    if (res.statusCode != 200) return false;

    final data = jsonDecode(res.body) as Json;
    // Rotación: guardar SIEMPRE el nuevo refresh token.
    await _tokens.save(
      access: data['access'] as String,
      refresh: (data['refresh'] as String?) ?? refresh,
    );
    return true;
  }

  Json _decode(http.Response res) {
    if (res.body.isEmpty) return <String, dynamic>{};
    return jsonDecode(res.body) as Json;
  }

  Never _fail(http.Response res) {
    dynamic decoded;
    try {
      decoded = res.body.isNotEmpty ? jsonDecode(res.body) : null;
    } catch (_) {
      decoded = null;
    }
    String message = 'Error ${res.statusCode}';
    if (decoded is Map && decoded['detail'] != null) {
      message = decoded['detail'].toString();
    } else if (decoded is Map && decoded.isNotEmpty) {
      // errores de validación: { campo: [mensajes] }
      final first = decoded.values.first;
      if (first is List && first.isNotEmpty) message = first.first.toString();
    }
    throw ApiException(res.statusCode, message, decoded);
  }

  Future<Json> getJson(
    String path, {
    bool auth = true,
    Duration? timeout,
  }) async {
    final res = await _send('GET', path, auth: auth, timeout: timeout);
    if (res.statusCode >= 200 && res.statusCode < 300) return _decode(res);
    _fail(res);
  }

  Future<Json> postJson(
    String path,
    Object body, {
    bool auth = true,
    Duration? timeout,
  }) async {
    final res = await _send(
      'POST',
      path,
      body: body,
      auth: auth,
      timeout: timeout,
    );
    if (res.statusCode >= 200 && res.statusCode < 300) return _decode(res);
    _fail(res);
  }
}
