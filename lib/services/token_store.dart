import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Persiste los tokens JWT de forma segura (en Windows usa el Credential
/// Manager del sistema operativo).
class TokenStore {
  static const _accessKey = 'ig_access';
  static const _refreshKey = 'ig_refresh';

  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  Future<void> save({required String access, required String refresh}) async {
    await _storage.write(key: _accessKey, value: access);
    await _storage.write(key: _refreshKey, value: refresh);
  }

  Future<String?> get access => _storage.read(key: _accessKey);
  Future<String?> get refresh => _storage.read(key: _refreshKey);

  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}
