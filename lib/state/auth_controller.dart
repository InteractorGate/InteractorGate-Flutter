import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../models/user.dart';
import '../services/api_client.dart';
import '../services/auth_service.dart';
import 'session_controller.dart';

enum AuthStatus { unknown, authenticated, unauthenticated }

/// Identifica al participante antes de abrir su sesión de comunicación.
class AuthController extends ChangeNotifier {
  AuthController(this._auth, this._session);

  final AuthService _auth;
  final SessionController _session;

  AuthStatus status = AuthStatus.unknown;
  User? user;
  String? error;
  bool busy = false;

  Future<void> bootstrap() async {
    if (busy || status != AuthStatus.unknown) return;
    busy = true;
    error = null;
    // Cada apertura requiere identificar al participante, incluso con tokens previos.
    try {
      await _auth.clearLocalSession();
      status = AuthStatus.unauthenticated;
    } catch (_) {
      error =
          'No se pudo limpiar la autenticación anterior. '
          'Reintenta antes de identificar al participante.';
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<bool> login(String username, String password) =>
      _signIn(() => _auth.login(username, password));

  Future<bool> register({
    required String username,
    required String email,
    required String password,
    required String password2,
    String firstName = '',
    String lastName = '',
  }) async {
    var created = false;
    final ok = await _signIn(() async {
      await _auth.register(
        username: username,
        email: email,
        password: password,
        password2: password2,
        firstName: firstName,
        lastName: lastName,
      );
      created = true;
      await _auth.login(username, password);
    });
    if (!ok && created) {
      error =
          'La cuenta se creó, pero no se pudo abrir la sesión. '
          'Vuelve a Iniciar sesión con el mismo código; no la registres otra vez. '
          '${error ?? ''}';
      notifyListeners();
    }
    return ok;
  }

  Future<bool> _signIn(Future<void> Function() authenticate) async {
    if (busy || status != AuthStatus.unauthenticated) return false;
    busy = true;
    error = null;
    notifyListeners();
    var step = 'autenticación';
    try {
      await authenticate();
      step = 'consulta del perfil';
      final participant = await _auth.me();
      step = 'confirmación de la sesión';
      await _session.start(participantId: participant.id);
      user = participant;
      status = AuthStatus.authenticated;
      return true;
    } on ApiException catch (e) {
      error = e.statusCode == 401 && step == 'autenticación'
          ? 'Usuario o contraseña incorrectos.'
          : 'Error en $step: ${e.message}';
    } on TimeoutException {
      error =
          'El servidor no respondió a tiempo durante $step. '
          'Espera unos segundos e intenta iniciar sesión de nuevo.';
    } on PlatformException {
      error =
          'No se pudo acceder al almacenamiento seguro de Windows durante '
          '$step. Cierra otras ventanas de InteractorGate y reintenta.';
    } catch (e) {
      error =
          'No se pudo completar $step (${e.runtimeType}). '
          'Comunica este mensaje al equipo para revisar el fallo.';
    } finally {
      try {
        if (status != AuthStatus.authenticated) {
          _session.pauseTelemetry();
          await _auth.clearLocalSession();
        }
      } catch (_) {
        status = AuthStatus.unknown;
        error = 'No se pudo limpiar la autenticación anterior. Reintenta.';
      }
      busy = false;
      notifyListeners();
    }
    return false;
  }

  Future<bool> logout() async {
    if (busy) return false;
    if (status != AuthStatus.authenticated) return true;
    busy = true;
    error = null;
    notifyListeners();
    try {
      // El cierre y los eventos pendientes necesitan todavía el token del participante.
      await _session.end();
      await _auth.logout();
      user = null;
      status = AuthStatus.unauthenticated;
      return true;
    } catch (_) {
      error =
          'No se pudo confirmar el cierre de la sesión. '
          'Revisa la conexión y vuelve a cerrar sesión.';
      return false;
    } finally {
      busy = false;
      notifyListeners();
    }
  }
}
