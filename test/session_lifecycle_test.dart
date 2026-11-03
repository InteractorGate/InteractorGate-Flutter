import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:interactor_gate/models/prediction.dart';
import 'package:interactor_gate/models/user.dart';
import 'package:interactor_gate/models/study_protocol.dart';
import 'package:interactor_gate/services/api_client.dart';
import 'package:interactor_gate/services/auth_service.dart';
import 'package:interactor_gate/services/prediction_service.dart';
import 'package:interactor_gate/services/telemetry_service.dart';
import 'package:interactor_gate/services/token_store.dart';
import 'package:interactor_gate/services/study_store.dart';
import 'package:interactor_gate/state/auth_controller.dart';
import 'package:interactor_gate/state/session_controller.dart';

class _Auth extends AuthService {
  _Auth(this.events) : super(ApiClient(TokenStore()), TokenStore());
  final List<String> events;
  String participant = '';
  bool rejectLogin = false;
  bool rejectClear = false;

  @override
  Future<void> clearLocalSession() async {
    if (rejectClear) throw StateError('Storage unavailable');
    events.add('tokens.clear');
  }

  @override
  Future<void> login(String username, String password) async {
    events.add('login:$username');
    if (rejectLogin) throw ApiException(401, 'Invalid login');
    participant = username;
  }

  @override
  Future<void> register({
    required String username,
    required String email,
    required String password,
    required String password2,
    String firstName = '',
    String lastName = '',
  }) async => events.add('register:$username');

  @override
  Future<User> me() async {
    events.add('me:$participant');
    return User(
      id: participant == 'P01' ? 1 : 2,
      username: participant,
      email: 'study@example.com',
    );
  }

  @override
  Future<void> logout() async => events.add('logout:$participant');
}

class _Telemetry extends TelemetryService {
  @override
  Future<void> bindParticipant(int owner) async {}
  @override
  Future<void> flush() async {}
  _Telemetry(this.events) : super(ApiClient(TokenStore()));
  final List<String> events;
  final records = <({String id, String type, bool mustDeliver})>[];
  String? failEvent;

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
    events.add(eventType);
    if (failEvent == eventType) throw StateError('Offline');
    records.add((id: sessionId, type: eventType, mustDeliver: requireDelivery));
  }
}

class _StudyStore extends StudyStore {
  @override
  Future<StudyProgress?> load(int participantId) async => null;

  @override
  Future<void> save(int participantId, StudyProgress progress) async {}
}

class _Predictions extends PredictionService {
  _Predictions() : super(ApiClient(TokenStore()));
  Completer<Prediction>? response;

  @override
  Future<Prediction> predictText(String context, String sessionId) async {
    return response == null
        ? const Prediction(suggestions: ['agua'], confidence: .8)
        : await response!.future;
  }
}

void main() {
  late List<String> events;
  late _Auth service;
  late _Telemetry telemetry;
  late _Predictions predictions;
  late SessionController session;
  late AuthController auth;

  setUp(() {
    events = [];
    service = _Auth(events);
    telemetry = _Telemetry(events);
    predictions = _Predictions();
    session = SessionController(
      predictions,
      telemetry,
      studyStore: _StudyStore(),
    );
    auth = AuthController(service, session);
  });

  tearDown(() {
    auth.dispose();
    session.dispose();
  });

  test('startup requires identification and never logs in as a demo', () async {
    await auth.bootstrap();
    expect(auth.status, AuthStatus.unauthenticated);
    expect(auth.user, isNull);
    expect(events, ['tokens.clear']);
    await session.type('A');

    expect(session.sessionId, isNull);
    expect(session.text, isEmpty);
    expect(telemetry.records, isEmpty);
  });

  test('session starts only after login and verified profile', () async {
    await auth.bootstrap();
    expect(await auth.login('P01', 'password'), isTrue);
    expect(events, ['tokens.clear', 'login:P01', 'me:P01', 'session_start']);
    expect(auth.user!.username, 'P01');
    expect(session.active, isTrue);
    expect(telemetry.records.single.mustDeliver, isTrue);
    expect(session.sessionId, telemetry.records.single.id);
  });

  test(
    'startup storage failure blocks identification until cleanup succeeds',
    () async {
      service.rejectClear = true;
      await auth.bootstrap();
      expect(auth.status, AuthStatus.unknown);
      expect(auth.error, isNotNull);
      expect(await auth.login('P01', 'password'), isFalse);
      expect(telemetry.records, isEmpty);
      service.rejectClear = false;
      await auth.bootstrap();
      expect(auth.status, AuthStatus.unauthenticated);
      expect(auth.error, isNull);
      expect(await auth.login('P01', 'password'), isTrue);
    },
  );

  test('invalid login creates no session', () async {
    await auth.bootstrap();
    service.rejectLogin = true;
    expect(await auth.login('P01', 'wrong'), isFalse);
    expect(auth.status, AuthStatus.unauthenticated);
    expect(auth.user, isNull);
    expect(session.sessionId, isNull);
    expect(telemetry.records, isEmpty);
    expect(events.last, 'tokens.clear');
    expect(auth.busy, isFalse);
  });

  test('unconfirmed start does not open the board', () async {
    await auth.bootstrap();
    telemetry.failEvent = 'session_start';
    expect(await auth.login('P01', 'password'), isFalse);
    expect(auth.status, AuthStatus.unauthenticated);
    expect(session.sessionId, isNull);
    expect(auth.error, isNotNull);
    telemetry.failEvent = null;
    expect(await auth.login('P01', 'password'), isTrue);
  });

  test(
    'registration authenticates the named participant before starting',
    () async {
      await auth.bootstrap();
      expect(
        await auth.register(
          username: 'P02',
          email: 'p02@example.com',
          password: 'password',
          password2: 'password',
        ),
        isTrue,
      );
      expect(events, [
        'tokens.clear',
        'register:P02',
        'login:P02',
        'me:P02',
        'session_start',
      ]);
      expect(auth.user!.username, 'P02');
    },
  );

  test(
    'participant change closes the old ID and clears all composition state',
    () async {
      await auth.bootstrap();
      await auth.login('P01', 'password');
      final firstId = session.sessionId;
      await session.insertWord('quiero');
      session.setDwellSeconds(2.5);
      session.setDwellEnabled(false);
      session.toggleBoardMode();

      expect(await auth.logout(), isTrue);
      expect(
        events.indexOf('session_end'),
        lessThan(events.indexOf('logout:P01')),
      );
      expect(telemetry.records.last.mustDeliver, isTrue);
      expect(session.sessionId, isNull);
      expect(session.text, isEmpty);
      expect(session.suggestions, isEmpty);
      expect(session.dwellSeconds, 1.2);
      expect(session.dwellEnabled, isTrue);
      expect(session.boardMode, BoardMode.words);
      expect(auth.user, isNull);

      await auth.login('P02', 'password');
      expect(session.sessionId, isNot(firstId));
      expect(
        telemetry.records.where((r) => r.type == 'session_start').length,
        2,
      );
      expect(auth.user!.username, 'P02');
    },
  );

  test('failed end retains participant, ID and text for a retry', () async {
    await auth.bootstrap();
    await auth.login('P01', 'password');
    await session.insertWord('agua');
    final id = session.sessionId;
    telemetry.failEvent = 'session_end';
    expect(await auth.logout(), isFalse);
    expect(auth.status, AuthStatus.authenticated);
    expect(session.sessionId, id);
    expect(session.text, 'agua');
    expect(session.active, isFalse);
    await session.type('IGNORED');
    expect(session.text, 'agua');
    expect(events, isNot(contains('logout:P01')));
    expect(auth.error, isNotNull);
    expect(await auth.login('P02', 'password'), isFalse);
    expect(auth.user!.username, 'P01');
    telemetry.failEvent = null;
    expect(await auth.logout(), isTrue);
    expect(session.sessionId, isNull);
  });

  test(
    'logout waits for in-flight work and prevents new participant actions',
    () async {
      await auth.bootstrap();
      await auth.login('P01', 'password');
      predictions.response = Completer<Prediction>();
      final typing = session.type('A ');
      await Future<void>.delayed(Duration.zero);
      final closing = auth.logout();
      await Future<void>.delayed(Duration.zero);
      expect(auth.busy, isTrue);
      expect(session.active, isFalse);
      expect(events, isNot(contains('session_end')));
      await session.insertWord('must not be added');
      expect(session.text, 'A ');
      expect(await auth.login('P02', 'password'), isFalse);

      predictions.response!.complete(
        const Prediction(suggestions: ['old result'], confidence: .5),
      );
      await typing;
      expect(await closing, isTrue);
      expect(session.text, isEmpty);
      expect(session.suggestions, isEmpty);
      expect(events.where((e) => e == 'session_end').length, 1);
      expect(events.last, 'logout:P01');
    },
  );

  test('concurrent close requests send one end event', () async {
    await auth.bootstrap();
    await auth.login('P01', 'password');
    await Future.wait([session.end(), session.end()]);
    expect(telemetry.records.where((r) => r.type == 'session_end').length, 1);
  });
}
