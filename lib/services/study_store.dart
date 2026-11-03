import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/study_protocol.dart';
import '../config/api_config.dart';

/// Solo guarda asignación y avance; los resultados de ensayo van a Azure.
class StudyStore {
  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  Future<StudyProgress?> load(int participantId) async {
    var value = await _storage.read(key: _key(participantId));
    if (value == null && ApiConfig.baseUrl == ApiConfig.prodBaseUrl) {
      value = await _storage.read(key: 'ig_e2_$participantId');
      if (value != null) {
        await _storage.write(key: _key(participantId), value: value);
      }
    }
    return value == null
        ? null
        : StudyProgress.fromJson(jsonDecode(value) as Map<String, dynamic>);
  }

  Future<void> save(int participantId, StudyProgress progress) => _storage
      .write(key: _key(participantId), value: jsonEncode(progress.toJson()));

  String _key(int id) =>
      'ig_e2_${base64Url.encode(utf8.encode(ApiConfig.baseUrl))}_$id';
}
