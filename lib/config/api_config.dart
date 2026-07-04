/// Configuración de endpoints del backend y del sidecar de rastreo ocular.
class ApiConfig {
  ApiConfig._();

  /// Cambia a `true` para apuntar al backend desplegado en Azure.
  static const bool useProd = false;

  static const String devBaseUrl = 'http://localhost:8000';
  static const String prodBaseUrl = 'https://ig-backend-tesis.azurewebsites.net';

  static String get baseUrl => useProd ? prodBaseUrl : devBaseUrl;

  /// Sidecar de rastreo ocular (proceso Python) — socket TCP local.
  static const String gazeHost = '127.0.0.1';
  static const int gazePort = 8765;
}
