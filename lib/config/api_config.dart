/// Configuración de endpoints del backend y del sidecar de rastreo ocular.
class ApiConfig {
  ApiConfig._();

  /// `true` = backend desplegado en Azure (build de escritorio distribuible).
  /// Cambia a `false` para desarrollar contra un backend local.
  static const bool useProd = true;

  static const String devBaseUrl = 'http://localhost:8000';
  static const String prodBaseUrl = 'https://ig-backend-tesis.azurewebsites.net';

  static String get baseUrl => useProd ? prodBaseUrl : devBaseUrl;

  /// No hay cuenta embebida: cada participante entra con el código y la clave
  /// que le asignan los investigadores (P01, P02…), de modo que sus datos
  /// quedan separados y seudonimizados. Ningún secreto viaja dentro del .exe.

  /// Sidecar de rastreo ocular (proceso Python) — socket TCP local.
  static const String gazeHost = '127.0.0.1';
  static const int gazePort = 8765;
}
