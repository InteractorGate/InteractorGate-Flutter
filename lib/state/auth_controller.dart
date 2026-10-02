import 'package:flutter/foundation.dart';

import '../models/user.dart';
import '../services/api_client.dart';
import '../services/auth_service.dart';

enum AuthStatus { unknown, authenticated, unauthenticated }

/// Estado global de autenticación.
class AuthController extends ChangeNotifier {
  AuthController(this._auth);

  final AuthService _auth;

  AuthStatus status = AuthStatus.unknown;
  User? user;
  String? error;

  /// Al arrancar: intenta usar los tokens guardados para recuperar el perfil.
  /// Si no hay sesión válida, muestra la pantalla de acceso, donde el
  /// investigador introduce el código de participante la primera vez; después
  /// los tokens guardados mantienen la sesión.
  Future<void> bootstrap() async {
    try {
      user = await _auth.me();
      status = AuthStatus.authenticated;
    } catch (_) {
      status = AuthStatus.unauthenticated;
    }
    notifyListeners();
  }

  Future<bool> login(String username, String password) async {
    error = null;
    try {
      await _auth.login(username, password);
      user = await _auth.me();
      status = AuthStatus.authenticated;
      notifyListeners();
      return true;
    } on ApiException catch (e) {
      error = e.statusCode == 401
          ? 'Código de participante o clave incorrectos.'
          : e.message;
      notifyListeners();
      return false;
    } catch (_) {
      error = 'No se pudo conectar con el servidor.';
      notifyListeners();
      return false;
    }
  }

  Future<bool> register({
    required String username,
    required String email,
    required String password,
    required String password2,
    String firstName = '',
    String lastName = '',
  }) async {
    error = null;
    try {
      await _auth.register(
        username: username,
        email: email,
        password: password,
        password2: password2,
        firstName: firstName,
        lastName: lastName,
      );
      // Registro exitoso → login automático.
      return login(username, password);
    } on ApiException catch (e) {
      error = e.message;
      notifyListeners();
      return false;
    } catch (_) {
      error = 'No se pudo conectar con el servidor.';
      notifyListeners();
      return false;
    }
  }

  Future<void> logout() async {
    await _auth.logout();
    user = null;
    status = AuthStatus.unauthenticated;
    notifyListeners();
  }
}
