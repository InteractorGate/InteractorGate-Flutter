import 'package:flutter_test/flutter_test.dart';
import 'package:interactor_gate/models/prediction.dart';
import 'package:interactor_gate/models/study_protocol.dart';
import 'package:interactor_gate/services/api_client.dart';
import 'package:interactor_gate/services/prediction_service.dart';
import 'package:interactor_gate/services/study_store.dart';
import 'package:interactor_gate/services/telemetry_service.dart';
import 'package:interactor_gate/services/token_store.dart';
import 'package:interactor_gate/state/session_controller.dart';

import 'telemetry_queue_test.dart' show MemoryOutbox, DeliveryApi;

class _Study extends StudyStore {
  StudyProgress? progress = const StudyProgress(
    participantNumber: 1,
    practiceCompleted: 5,
  );
  bool failSave = false;
  @override
  Future<StudyProgress?> load(int owner) async => progress;
  @override
  Future<void> save(int owner, StudyProgress value) async {
    if (failSave) throw StateError('Disk unavailable');
    progress = value;
  }
}

class _Predict extends PredictionService {
  _Predict() : super(ApiClient(TokenStore()));
  @override
  Future<Prediction> predictText(String text, String session) async =>
      const Prediction(suggestions: ['por favor'], confidence: .5);
}

void main() {
  late MemoryOutbox outbox;
  late DeliveryApi api;
  late _Study study;
  final sessions = <SessionController>[];
  final services = <TelemetryService>[];
  SessionController make() {
    final service = TelemetryService(api, store: outbox, autoRetry: false);
    services.add(service);
    final session = SessionController(_Predict(), service, studyStore: study);
    sessions.add(session);
    return session;
  }

  setUp(() {
    outbox = MemoryOutbox();
    api = DeliveryApi()..owner = 7;
    study = _Study();
  });
  tearDown(() {
    for (final session in sessions) {
      session.dispose();
    }
    sessions.clear();
    for (final service in services) {
      service.dispose();
    }
    services.clear();
  });

  test(
    'edits, corrections, rendered suggestions and acceptance reconstruct the final text',
    () async {
      final session = make();
      await session.start(participantId: 7);
      await session.configureStudy(
        participantNumber: 1,
        phase: StudyPhase.practice,
      );
      await session.startTrial();
      await session.type('A');
      await session.space();
      await session.type('X');
      await session.backspace();
      await session.clear();
      await session.insertWord('AGUA');
      await session.suggestionsPresented(session.suggestionPresentationId!);
      await session.suggestionsPresented(session.suggestionPresentationId!);
      await session.applySuggestion('por favor');
      expect(session.text, 'AGUA por favor');
      expect(await session.finishTrial(), isTrue);
      await services.single.flush();
      final events = api.accepted.values.toList();
      final shown = events.where(
        (e) => (e['data'] as Map?)?['action'] == 'shown',
      );
      expect(shown.length, 1);
      expect((shown.single['data'] as Map)['latency_ms'], isNonNegative);
      var reconstructed = '';
      for (final event in events) {
        if (!['selection', 'delete', 'clear'].contains(event['event_type'])) {
          continue;
        }
        final data = event['data'] as Map;
        final removed = data['removed_characters'] as int;
        reconstructed =
            reconstructed.substring(0, reconstructed.length - removed) +
            (data['inserted_text'] as String);
      }
      expect(reconstructed, 'AGUA por favor');
      expect((events.last['data'] as Map)['final_text'], reconstructed);
      expect(study.progress!.practiceCompleted, 6);
      expect(outbox.entries, isEmpty);
    },
  );

  test(
    'failed local progress save recovers after restart without duplicating completion',
    () async {
      final first = make();
      await first.start(participantId: 7);
      await first.configureStudy(
        participantNumber: 1,
        phase: StudyPhase.practice,
      );
      await first.startTrial();
      await first.type('TEST');
      study.failSave = true;
      expect(await first.finishTrial(), isFalse);
      expect(first.finalizingTrial, isTrue);
      expect(first.canCompose, isFalse);
      final terminal = api.accepted.values
          .where((e) => e['event_type'] == 'trial_end')
          .single;
      await first.type('IGNORED');
      expect(first.text, 'TEST');
      study.failSave = false;
      final resumed = make();
      await resumed.start(participantId: 7);
      expect(study.progress!.practiceCompleted, 6);
      expect(
        api.accepted.values.where((e) => e['event_type'] == 'trial_end').length,
        1,
      );
      expect(
        api.accepted.values.where((e) => e['event_type'] == 'trial_end').single,
        terminal,
      );
      expect(outbox.entries, isEmpty);
    },
  );

  test(
    'rapid inputs and a disk error never silently change unaudited text',
    () async {
      final session = make();
      await session.start(participantId: 7);
      await Future.wait(['A', 'B', 'C'].map(session.type));
      expect(session.text, 'ABC');
      await services.single.flush();
      final edits = api.accepted.values.where(
        (e) => (e['data'] as Map?)?['action'] == 'letter',
      );
      expect(edits.length, 3);
      expect(
        edits.every((e) => !(e['data'] as Map).containsKey('inserted_text')),
        isTrue,
      );
      outbox.failWrite = true;
      await session.type('D');
      expect(session.text, 'ABC');
      expect(session.actionError, isNotNull);
    },
  );
}
