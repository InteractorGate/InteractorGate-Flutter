/// Configuración de endpoints del backend y del sidecar de rastreo ocular.
class ApiConfig {
  ApiConfig._();

  /// `true` = backend desplegado en Azure (build de escritorio distribuible).
  /// Cambia a `false` para desarrollar contra un backend local.
  static const bool useProd = true;

  static const String devBaseUrl = 'http://localhost:8000';
  static const String prodBaseUrl = 'https://ig-backend-tesis.azurewebsites.net';

  static String get baseUrl => useProd ? prodBaseUrl : devBaseUrl;

  /// Cuenta demo embebida: la app entra directo al tablero sin pantalla de
  /// login (auto-login al arrancar). Si no existe en el backend, se registra
  /// sola en el primer arranque. Cambia estas credenciales si querés otra
  /// cuenta de demostración.
  static const String demoUsername = 'demo_ig';
  static const String demoPassword = 'Interactor2026!';
  static const String demoEmail = 'demo@interactorgate.app';

  /// Sidecar de rastreo ocular (proceso Python) — socket TCP local.
  static const String gazeHost = '127.0.0.1';
  static const int gazePort = 8765;
}
