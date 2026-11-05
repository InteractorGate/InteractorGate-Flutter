import '../models/user.dart';
import 'api_client.dart';
import 'token_store.dart';

/// Operaciones de identidad contra `/api/users/` y `/api/token/`.
class AuthService {
  AuthService(this._api, this._tokens);

  final ApiClient _api;
  final TokenStore _tokens;
  // Azure SQL permite hasta 60 s para abrir la conexión; dejar margen HTTP.
  static const _authenticationTimeout = Duration(seconds: 75);

  Future<void> login(String username, String password) async {
    final data = await _api.postJson(
      '/api/users/login/',
      {'username': username, 'password': password},
      auth: false,
      timeout: _authenticationTimeout,
    );
    await _tokens.save(
      access: data['access'] as String,
      refresh: data['refresh'] as String,
    );
  }

  Future<void> register({
    required String username,
    required String email,
    required String password,
    required String password2,
    String firstName = '',
    String lastName = '',
  }) async {
    await _api.postJson(
      '/api/users/register/',
      {
        'username': username,
        'email': email,
        'password': password,
        'password2': password2,
        if (firstName.isNotEmpty) 'first_name': firstName,
        if (lastName.isNotEmpty) 'last_name': lastName,
      },
      auth: false,
      timeout: _authenticationTimeout,
    );
  }

  Future<User> me() async {
    final data = await _api.getJson(
      '/api/users/me/',
      timeout: _authenticationTimeout,
    );
    return User.fromJson(data);
  }

  Future<void> clearLocalSession() => _tokens.clear();

  Future<void> logout() async {
    final refresh = await _tokens.refresh;
    if (refresh != null) {
      try {
        await _api.postJson('/api/users/logout/', {'refresh': refresh});
      } catch (_) {
        // aunque falle el blacklist, limpiamos los tokens locales.
      }
    }
    await clearLocalSession();
  }
}
