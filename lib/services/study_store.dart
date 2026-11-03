import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/study_protocol.dart';

/// Solo guarda asignación y avance; los resultados de ensayo van a Azure.
class StudyStore {
  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  Future<StudyProgress?> load(int participantId) async {
    final value = await _storage.read(key: 'ig_e2_$participantId');
    return value == null
        ? null
        : StudyProgress.fromJson(jsonDecode(value) as Map<String, dynamic>);
  }

  Future<void> save(int participantId, StudyProgress progress) => _storage
      .write(key: 'ig_e2_$participantId', value: jsonEncode(progress.toJson()));
}
