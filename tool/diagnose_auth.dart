import 'dart:io';
import 'package:flutter/widgets.dart';
import 'package:interactor_gate/services/api_client.dart';
import 'package:interactor_gate/services/auth_service.dart';
import 'package:interactor_gate/services/token_store.dart';
import 'package:interactor_gate/services/study_store.dart';
import 'package:interactor_gate/services/outbox_store.dart';
import 'package:interactor_gate/services/telemetry_service.dart';
import 'package:interactor_gate/services/prediction_service.dart';
import 'package:interactor_gate/state/session_controller.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final tokens = TokenStore();
  final api = ApiClient(tokens);
  final auth = AuthService(api, tokens);
  final session = SessionController(
    PredictionService(api),
    TelemetryService(api),
  );
  var stage = 'login';
  try {
    await auth.login(
      'EVALUADOR01',
      const String.fromEnvironment('DIAGNOSTIC_PASSWORD'),
    );
    print('DIAGNOSTIC login OK');
    stage = 'profile';
    final user = await auth.me();
    print('DIAGNOSTIC profile OK');
    stage = 'study storage';
    await StudyStore().load(user.id);
    print('DIAGNOSTIC study storage OK');
    stage = 'outbox storage';
    await OutboxStore().load(user.id);
    print('DIAGNOSTIC outbox storage OK');
    stage = 'session start';
    await session.start(participantId: user.id);
    print('DIAGNOSTIC session start OK');
    stage = 'session end';
    await session.end();
    print('DIAGNOSTIC session end OK');
  } catch (e, stack) {
    print('DIAGNOSTIC FAILED at $stage: ${e.runtimeType}: $e');
    print(stack);
  } finally {
    await auth.logout();
    session.dispose();
    exit(0);
  }
}
