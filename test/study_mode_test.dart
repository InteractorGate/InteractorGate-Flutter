import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:interactor_gate/models/prediction.dart';
import 'package:interactor_gate/models/study_protocol.dart';
import 'package:interactor_gate/models/user.dart';
import 'package:interactor_gate/screens/home_screen.dart';
import 'package:interactor_gate/services/api_client.dart';
import 'package:interactor_gate/services/auth_service.dart';
import 'package:interactor_gate/services/gaze_bridge.dart';
import 'package:interactor_gate/services/prediction_service.dart';
import 'package:interactor_gate/services/study_store.dart';
import 'package:interactor_gate/services/telemetry_service.dart';
import 'package:interactor_gate/services/token_store.dart';
import 'package:interactor_gate/state/session_controller.dart';
import 'package:interactor_gate/state/auth_controller.dart';
import 'package:interactor_gate/widgets/study_panel.dart';
import 'package:interactor_gate/widgets/suggestion_bar.dart';

class _Store extends StudyStore {
  final saved = <int, StudyProgress>{};

  @override
  Future<StudyProgress?> load(int participantId) async => saved[participantId];

  @override
  Future<void> save(int participantId, StudyProgress progress) async {
    saved[participantId] = progress;
  }
}

class _Telemetry extends TelemetryService {
  @override
  Future<void> bindParticipant(int owner) async {}
  @override
  Future<void> flush() async {}
  _Telemetry() : super(ApiClient(TokenStore()));
  final events =
      <({String type, String sessionId, Map<String, dynamic> data})>[];
  String? reject;

  @override
  Future<void> log({
    required String sessionId,
    required String eventType,
    Map<String, double>? gaze,
    String? selectedWord,
    Map<String, dynamic>? data,
    DateTime? timestamp,
    bool requireDelivery = false,
    String? eventId,
    bool retainUntilCommitted = false,
  }) async {
    if (eventType == reject) throw StateError('offline');
    if (data != null) expect(jsonEncode(data).length, lessThanOrEqualTo(4096));
    events.add((type: eventType, sessionId: sessionId, data: data ?? {}));
  }
}

class _Predictions extends PredictionService {
  _Predictions() : super(ApiClient(TokenStore()));
  int calls = 0;
  Completer<Prediction>? pending;

  @override
  Future<Prediction> predictText(String context, String sessionId) async {
    calls++;
    return pending == null
        ? const Prediction(suggestions: ['una respuesta'], confidence: .5)
        : await pending!.future;
  }
}

void main() {
  test(
    'pilot bank has 40 unique targets of 15–30 characters and separate practice',
    () {
      final targets = [...studyListA, ...studyListB];
      expect(studyListA.length, 20);
      expect(studyListB.length, 20);
      expect(targets.toSet().length, 40);
      for (final phrase in targets) {
        expect(phrase.length, inInclusiveRange(15, 30));
      }
      expect(studyPracticePhrases.length, 10);
      expect(
        studyPracticePhrases.toSet().intersection(targets.toSet()),
        isEmpty,
      );
    },
  );

  test(
    'S2/S3 use 20 distinct phrases, alternating 3-2-2-3 blocks and counterbalancing lists',
    () {
      for (var number = 1; number <= 20; number++) {
        final s2 = StudyPlan(participantNumber: number, phase: StudyPhase.s2);
        final s3 = StudyPlan(participantNumber: number, phase: StudyPhase.s3);
        final entries = [...s2.entries, ...s3.entries];
        expect(s2.entries.length, studySessionTrials);
        expect(s3.entries.length, studySessionTrials);
        expect(entries.map((e) => e.phraseId).toSet().length, 20);
        for (final plan in [s2, s3]) {
          expect(
            plan.entries
                .where((e) => e.condition == StudyCondition.withPrediction)
                .length,
            5,
          );
          StudyCondition? previous;
          for (var block = 1; block <= 4; block++) {
            final group = plan.entries.where((e) => e.block == block);
            expect(group.length, studySessionBlocks[block - 1]);
            expect(group.map((e) => e.condition).toSet().length, 1);
            expect(group.first.condition, isNot(previous));
            previous = group.first.condition;
          }
          expect(
            plan.entries.map((e) => e.order),
            List.generate(studySessionTrials, (i) => i + 1),
          );
        }
        expect(
          entries
              .where((e) => e.condition == StudyCondition.withPrediction)
              .every((e) => e.list == (number.isOdd ? 'A' : 'B')),
          isTrue,
        );
        expect(
          StudyPlan(
            participantNumber: number,
            phase: StudyPhase.s2,
          ).entries.map((e) => e.phraseId),
          s2.entries.map((e) => e.phraseId),
        );
      }
    },
  );

  test('corrupted or incompatible local progress is rejected', () {
    final json = const StudyProgress(participantNumber: 1).toJson();
    expect(
      () => StudyProgress.fromJson({
        ...json,
        'practice_completed': studyPracticeTrials + 1,
      }),
      throwsFormatException,
    );
    expect(
      () => StudyProgress.fromJson({...json, 'bank_version': 'other'}),
      throwsFormatException,
    );
    expect(
      () => StudyProgress.fromJson({...json, 's2_completed': 1}),
      throwsFormatException,
    );
    expect(StudyProgress.fromJson(json).participantNumber, 1);
  });

  late _Store store;
  late _Telemetry telemetry;
  late _Predictions predictions;
  late SessionController session;

  setUp(() async {
    store = _Store();
    telemetry = _Telemetry();
    predictions = _Predictions();
    session = SessionController(predictions, telemetry, studyStore: store);
    await session.start(participantId: 7);
  });

  tearDown(() => session.dispose());

  Future<void> completeMessage([String message = 'MENSAJE']) async {
    expect(await session.startTrial(), isTrue);
    await session.type(message);
    expect(await session.finishTrial(), isTrue);
  }

  Future<void> completePractice() async {
    expect(
      await session.configureStudy(
        participantNumber: 1,
        phase: StudyPhase.practice,
      ),
      isTrue,
    );
    for (var i = 0; i < studyPracticeTrials; i++) {
      await completeMessage();
    }
  }

  test('practice has five messages in 3-2 blocks of both conditions', () {
    for (var number = 1; number <= 20; number++) {
      final plan = StudyPlan(
        participantNumber: number,
        phase: StudyPhase.practice,
      );
      expect(plan.entries.length, studyPracticeTrials);
      expect(plan.entries.where((e) => e.block == 1).length, 3);
      expect(plan.entries.where((e) => e.block == 2).length, 2);
      expect(plan.entries.map((e) => e.condition).toSet().length, 2);
      expect(plan.entries.map((e) => e.phraseId).toSet().length, 5);
    }
  });

  test(
    'measurement is gated by five completed practice messages, including both conditions',
    () async {
      expect(
        await session.configureStudy(
          participantNumber: 1,
          phase: StudyPhase.s2,
        ),
        isFalse,
      );
      await completePractice();
      expect(store.saved[7]!.practiceCompleted, studyPracticeTrials);
      final practice = telemetry.events
          .where((e) => e.type == 'trial_end')
          .toList();
      expect(practice.length, studyPracticeTrials);
      expect(practice.every((e) => e.data['practice'] == true), isTrue);
      expect(
        practice.where((e) => e.data['condition'] == 'with_prediction').length,
        isIn([2, 3]),
      );
      expect(
        await session.configureStudy(
          participantNumber: 1,
          phase: StudyPhase.s3,
        ),
        isFalse,
      );
      expect(
        await session.configureStudy(
          participantNumber: 1,
          phase: StudyPhase.s2,
        ),
        isTrue,
      );
    },
  );

  test(
    'without prediction makes no requests through any composition path',
    () async {
      await completePractice();
      await session.configureStudy(participantNumber: 1, phase: StudyPhase.s2);
      for (var i = 0; i < 10; i++) {
        final entry = session.studyEntry!;
        final before = predictions.calls;
        await session.startTrial();
        expect(session.text, isEmpty);
        await session.type('H');
        await session.space();
        await session.insertWord('hola');
        await session.backspace();
        if (entry.condition == StudyCondition.withoutPrediction) {
          expect(predictions.calls, before);
          expect(session.suggestions, isEmpty);
          final text = session.text;
          await session.applySuggestion('una respuesta', requestId: 'obsolete');
          expect(session.text, text);
        } else {
          expect(predictions.calls, greaterThan(before));
        }
        final trialId = session.trialId;
        await session.finishTrial();
        final end = telemetry.events.last;
        expect(end.data['trial_id'], trialId);
        expect(end.data['phrase_id'], entry.phraseId);
        expect(end.data['condition'], entry.condition.code);
        expect(end.data['order'], entry.order);
        expect(end.data['practice'], isFalse);
        expect(end.data['duration_ms'], isNonNegative);
        expect(session.suggestions, isEmpty);
      }
    },
  );

  test(
    'interruption retains the scheduled phrase and a retry uses a new UUID',
    () async {
      await session.configureStudy(
        participantNumber: 1,
        phase: StudyPhase.practice,
      );
      await session.startTrial();
      final firstId = session.trialId;
      final phraseId = session.studyEntry!.phraseId;
      await session.type('AB');
      expect(await session.finishTrial(interrupted: true), isTrue);
      expect(telemetry.events.last.data['status'], 'interrupted');
      expect(store.saved[7]!.practiceCompleted, 0);
      expect(session.studyEntry!.phraseId, phraseId);
      await session.startTrial();
      expect(session.trialId, isNot(firstId));
      expect(session.text, isEmpty);
    },
  );

  test(
    'complete S2 and S3 retain twenty distinct measured trials across logins',
    () async {
      await completePractice();
      for (final phase in [StudyPhase.s2, StudyPhase.s3]) {
        expect(
          await session.configureStudy(participantNumber: 1, phase: phase),
          isTrue,
        );
        final dwell = session.dwellEnabled;
        session.setDwellEnabled(!dwell);
        expect(session.dwellEnabled, dwell);
        for (var i = 0; i < studySessionTrials; i++) {
          await completeMessage();
        }
        expect(session.studyEntry, isNull);
        expect(await session.startTrial(), isFalse);
        await session.end();
        await session.start(participantId: 7);
      }
      final measured = telemetry.events
          .where((e) => e.type == 'trial_end' && e.data['practice'] == false)
          .toList();
      expect(measured.length, 20);
      expect(measured.map((e) => e.data['phrase_id']).toSet().length, 20);
      expect(measured.map((e) => e.data['trial_id']).toSet().length, 20);
      expect(session.studyProgress!.s2Completed, studySessionTrials);
      expect(session.studyProgress!.s3Completed, studySessionTrials);
    },
  );

  test(
    'unconfirmed start/end retains the scheduled trial for a retry',
    () async {
      await session.configureStudy(
        participantNumber: 1,
        phase: StudyPhase.practice,
      );
      telemetry.reject = 'trial_start';
      expect(await session.startTrial(), isFalse);
      expect(session.canCompose, isFalse);
      telemetry.reject = null;
      await session.startTrial();
      await session.type('HOLA');
      final id = session.trialId;
      telemetry.reject = 'trial_end';
      expect(await session.finishTrial(), isFalse);
      expect(session.trialId, id);
      expect(session.text, 'HOLA');
      expect(store.saved[7]!.practiceCompleted, 0);
      telemetry.reject = null;
      expect(await session.finishTrial(), isTrue);
      expect(store.saved[7]!.practiceCompleted, 1);
    },
  );

  test(
    'progress and fixed enrollment survive logout, while another participant starts clean',
    () async {
      await session.configureStudy(
        participantNumber: 1,
        phase: StudyPhase.practice,
      );
      await completeMessage();
      await session.startTrial();
      await session.type('INCOMPLETO');
      await session.end();
      expect(
        telemetry.events[telemetry.events.length - 2].data['status'],
        'interrupted',
      );
      expect(telemetry.events.last.type, 'session_end');
      await session.start(participantId: 7);
      expect(session.studyPlan, isNull);
      expect(session.studyProgress!.practiceCompleted, 1);
      expect(
        await session.configureStudy(
          participantNumber: 2,
          phase: StudyPhase.practice,
        ),
        isFalse,
      );
      expect(
        await session.configureStudy(
          participantNumber: 1,
          phase: StudyPhase.practice,
        ),
        isTrue,
      );
      expect(session.studyEntry!.order, 2);
      await session.end();
      await session.start(participantId: 8);
      expect(session.studyProgress, isNull);
    },
  );

  test(
    'trial transition drains old requests and blocks edits until confirmation',
    () async {
      await session.configureStudy(
        participantNumber: 1,
        phase: StudyPhase.practice,
      );
      while (session.studyEntry!.condition != StudyCondition.withPrediction) {
        await completeMessage();
      }
      await session.startTrial();
      predictions.pending = Completer<Prediction>();
      final typing = session.type('HOLA ');
      await Future<void>.delayed(Duration.zero);
      final finishing = session.finishTrial();
      await Future<void>.delayed(Duration.zero);
      expect(session.studyBusy, isTrue);
      expect(session.canCompose, isFalse);
      await session.type('NO');
      expect(session.text, 'HOLA ');
      predictions.pending!.complete(
        const Prediction(suggestions: ['old'], confidence: .5),
      );
      await typing;
      expect(await finishing, isTrue);
      expect(session.suggestions, isEmpty);
    },
  );

  testWidgets(
    'disabled suggestion area keeps its height and hides actionable suggestions',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SuggestionBar(
              enabled: false,
              suggestions: const ['oculta'],
              onPick: (_) => fail('Disabled suggestion was picked'),
            ),
          ),
        ),
      );
      expect(find.text('oculta'), findsNothing);
      expect(tester.getSize(find.byType(SuggestionBar)).height, 72);
    },
  );

  testWidgets(
    'study panel shows target and changes from start to finish controls',
    (tester) async {
      await session.configureStudy(
        participantNumber: 1,
        phase: StudyPhase.practice,
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ListenableBuilder(
              listenable: session,
              builder: (_, _) =>
                  StudyPanel(session: session, participantCode: 'P01'),
            ),
          ),
        ),
      );
      expect(find.textContaining('Frase objetivo:'), findsOneWidget);
      await tester.tap(find.text('Iniciar ensayo'));
      await tester.pumpAndSettle();
      expect(find.text('Terminar mensaje'), findsOneWidget);
      expect(find.text('Interrumpir ensayo'), findsOneWidget);
    },
  );

  testWidgets(
    'study board fits desktop windows with an active target and keyboard',
    (tester) async {
      final auth =
          AuthController(
              AuthService(ApiClient(TokenStore()), TokenStore()),
              session,
            )
            ..status = AuthStatus.authenticated
            ..user = const User(
              id: 7,
              username: 'P01',
              email: 'study@example.com',
            );
      final gaze = GazeBridge();
      addTearDown(auth.dispose);
      addTearDown(gaze.dispose);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      tester.view.devicePixelRatio = 1;
      await session.configureStudy(
        participantNumber: 1,
        phase: StudyPhase.practice,
      );
      await session.startTrial();
      for (final size in [const Size(1280, 720), const Size(800, 600)]) {
        tester.view.physicalSize = size;
        await tester.pumpWidget(
          MultiProvider(
            providers: [
              ChangeNotifierProvider.value(value: session),
              ChangeNotifierProvider.value(value: auth),
              ChangeNotifierProvider.value(value: gaze),
            ],
            child: const MaterialApp(home: HomeScreen()),
          ),
        );
        await tester.pump();
        expect(tester.takeException(), isNull);
        expect(find.text('Terminar mensaje'), findsOneWidget);
        expect(find.text('ESPACIO'), findsOneWidget);
      }
    },
  );
}
