import 'dart:async';
import 'dart:ui' show PointerDeviceKind;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:interactor_gate/models/prediction.dart';
import 'package:interactor_gate/models/study_protocol.dart';
import 'package:interactor_gate/services/api_client.dart';
import 'package:interactor_gate/services/prediction_service.dart';
import 'package:interactor_gate/services/study_store.dart';
import 'package:interactor_gate/services/telemetry_service.dart';
import 'package:interactor_gate/services/token_store.dart';
import 'package:interactor_gate/state/session_controller.dart';
import 'package:interactor_gate/widgets/suggestion_bar.dart';

import 'telemetry_queue_test.dart' show MemoryOutbox, DeliveryApi;

class _Study extends StudyStore {
  @override
  Future<StudyProgress?> load(int owner) async => null;
  @override
  Future<void> save(int owner, StudyProgress value) async {}
}

class _Predictions extends PredictionService {
  _Predictions() : super(ApiClient(TokenStore()));
  bool hold = false;
  final calls = <({String context, Completer<Prediction> response})>[];
  Completer<void> _changed = Completer<void>();

  Future<void> waitForCalls(int count) async {
    while (calls.length < count) {
      await _changed.future;
    }
  }

  @override
  Future<Prediction> predictText(String context, String sessionId) {
    final response = Completer<Prediction>();
    calls.add((context: context, response: response));
    _changed.complete();
    _changed = Completer<void>();
    if (!hold) response.complete(result('agua'));
    return response.future;
  }
}

Prediction result(String phrase) =>
    Prediction(suggestions: [phrase], confidence: .5);

void main() {
  late _Predictions predictions;
  late TelemetryService telemetry;
  late SessionController session;

  setUp(() async {
    predictions = _Predictions();
    telemetry = TelemetryService(
      DeliveryApi()..owner = 7,
      store: MemoryOutbox(),
      autoRetry: false,
    );
    session = SessionController(predictions, telemetry, studyStore: _Study());
    await session.start(participantId: 7);
  });
  tearDown(() async {
    await telemetry.flush();
    session.dispose();
    telemetry.dispose();
  });

  test(
    'keyboard continuations require a completed word and an explicit space',
    () async {
      await session.type('QUI');
      expect(predictions.calls, isEmpty);
      await session.applySuggestion('agua', requestId: 'obsolete');
      expect(session.text, 'QUI');
      await session.type('ERO');
      await session.space();
      expect(predictions.calls.single.context, 'QUIERO');
      expect(session.suggestions, ['agua']);
      final request = session.suggestionPresentationId!;
      await session.suggestionsPresented(request);
      await session.applySuggestion('agua', requestId: request);
      expect(session.text, 'QUIERO agua');
      expect(predictions.calls.last.context, 'QUIERO agua');
      await session.clear();
      await session.insertWord('AGUA');
      expect(predictions.calls.last.context, 'AGUA');
    },
  );

  test('reversed responses only show the latest committed context', () async {
    predictions.hold = true;
    final first = session.type('HOLA ');
    await predictions.waitForCalls(1);
    final second = session.type('A ');
    await predictions.waitForCalls(2);
    expect(predictions.calls.map((c) => c.context), ['HOLA', 'HOLA A']);
    predictions.calls[1].response.complete(result('nueva'));
    await second;
    final request = session.suggestionPresentationId;
    predictions.calls[0].response.complete(result('vieja'));
    await first;
    expect(session.suggestions, ['nueva']);
    expect(session.suggestionPresentationId, request);
    expect(session.loadingSuggestions, isFalse);
  });

  test(
    'deleting while waiting invalidates a response even if text returns',
    () async {
      predictions.hold = true;
      final first = session.type('HOLA ');
      await predictions.waitForCalls(1);
      await session.backspace();
      expect(session.loadingSuggestions, isFalse);
      final second = session.space();
      await predictions.waitForCalls(2);
      predictions.calls[0].response.complete(result('vieja'));
      await first;
      expect(session.suggestions, isEmpty);
      expect(session.loadingSuggestions, isTrue);
      predictions.calls[1].response.complete(result('nueva'));
      await second;
      expect(session.suggestions, ['nueva']);
    },
  );

  test(
    'clear and typing the same context cannot restore an old response or error',
    () async {
      predictions.hold = true;
      final first = session.type('HOLA ');
      await predictions.waitForCalls(1);
      await session.clear();
      final second = session.type('HOLA ');
      await predictions.waitForCalls(2);
      predictions.calls[1].response.complete(result('actual'));
      await second;
      predictions.calls[0].response.completeError(StateError('old timeout'));
      await first;
      expect(session.suggestions, ['actual']);
      expect(session.loadingSuggestions, isFalse);
    },
  );

  test(
    'editing removes presented suggestions and rejects an old pick with the same label',
    () async {
      await session.insertWord('QUIERO');
      final old = session.suggestionPresentationId!;
      await session.type('X');
      expect(session.suggestions, isEmpty);
      expect(session.suggestionPresentationId, isNull);
      await session.applySuggestion('agua', requestId: old);
      expect(session.text, 'QUIEROX');
      await session.backspace();
      await session.space();
      expect(session.suggestions, ['agua']);
      await session.applySuggestion('agua', requestId: old);
      expect(session.text, 'QUIERO ');
      await session.applySuggestion(
        'agua',
        requestId: session.suggestionPresentationId!,
      );
      expect(session.text, 'QUIERO agua');
    },
  );

  test(
    'finishing a trial rejects pending results and the following condition makes no request',
    () async {
      await session.configureStudy(
        participantNumber: 2,
        phase: StudyPhase.practice,
      );
      for (var i = 0; i < 4; i++) {
        await session.startTrial();
        await session.type('MENSAJE');
        await session.finishTrial();
      }
      expect(session.studyEntry!.condition, StudyCondition.withPrediction);
      await session.startTrial();
      predictions.hold = true;
      final pending = session.type('HOLA ');
      await predictions.waitForCalls(1);
      final finishing = session.finishTrial();
      predictions.calls.single.response.complete(result('antigua'));
      await pending;
      expect(await finishing, isTrue);
      expect(session.suggestions, isEmpty);
      expect(session.studyEntry!.condition, StudyCondition.withoutPrediction);
      await session.startTrial();
      await session.type('HOLA ');
      expect(predictions.calls.length, 1);
      expect(session.suggestions, isEmpty);
    },
  );

  testWidgets(
    'a replacement response resets dwell even for an identical label',
    (tester) async {
      final picked = <String>[];
      Widget bar(String id) => MaterialApp(
        home: Scaffold(
          body: SuggestionBar(
            suggestions: const ['agua'],
            presentationId: id,
            dwellSeconds: 1,
            onPick: picked.add,
          ),
        ),
      );
      await tester.pumpWidget(bar('first'));
      final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
      await mouse.addPointer(location: Offset.zero);
      await mouse.moveTo(tester.getCenter(find.text('agua')));
      await tester.pump(const Duration(milliseconds: 600));
      await tester.pumpWidget(bar('replacement'));
      await tester.pump(const Duration(milliseconds: 500));
      expect(picked, isEmpty);
      await mouse.removePointer();
      await tester.pumpWidget(const SizedBox());
    },
  );
}
