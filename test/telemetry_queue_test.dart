import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:interactor_gate/services/api_client.dart';
import 'package:interactor_gate/services/outbox_store.dart';
import 'package:interactor_gate/services/telemetry_service.dart';
import 'package:interactor_gate/services/token_store.dart';

class MemoryOutbox extends OutboxStore {
  final entries = <String, PendingEvent>{};
  bool failWrite = false;

  @override
  Future<List<PendingEvent>> load(int owner) async =>
      entries.values.where((e) => e.owner == owner).toList()
        ..sort((a, b) => a.order.compareTo(b.order));

  @override
  Future<void> put(PendingEvent event) async {
    await Future<void>.delayed(Duration.zero);
    if (failWrite) throw StateError('Disk full');
    entries['${event.owner}:${event.id}'] = PendingEvent.fromJson(
      jsonDecode(jsonEncode(event.toJson())) as Map<String, dynamic>,
    );
  }

  @override
  Future<void> remove(PendingEvent event) async {
    entries.remove('${event.owner}:${event.id}');
  }
}

class DeliveryApi extends ApiClient {
  DeliveryApi() : super(TokenStore());
  int owner = 1;
  bool offline = false;
  bool loseNextAck = false;
  bool wrongOwnerAck = false;
  int? rejectStatus;
  final requests = <Map<String, dynamic>>[];
  final accepted = <String, Map<String, dynamic>>{};

  @override
  Future<Json> postJson(String path, Object body, {bool auth = true}) async {
    final payload = Map<String, dynamic>.from(body as Map);
    requests.add(payload);
    if (rejectStatus != null) throw ApiException(rejectStatus!, 'retry later');
    if (offline) throw ApiException(503, 'offline');
    if (payload['participant_id'] != owner) {
      throw ApiException(403, 'wrong account');
    }
    final key = '$owner:${payload['event_id']}';
    final existing = accepted[key];
    if (existing != null) expect(payload, existing);
    accepted[key] ??= payload;
    if (loseNextAck) {
      loseNextAck = false;
      throw TimeoutException('ACK lost');
    }
    return {
      ...payload,
      'user_id': wrongOwnerAck ? owner + 1 : owner,
      'schema_version': 2,
    };
  }
}

void main() {
  late MemoryOutbox store;
  late DeliveryApi api;
  final services = <TelemetryService>[];
  TelemetryService make() {
    final service = TelemetryService(api, store: store, autoRetry: false);
    services.add(service);
    return service;
  }

  setUp(() {
    store = MemoryOutbox();
    api = DeliveryApi();
  });
  tearDown(() {
    for (final service in services) {
      service.dispose();
    }
    services.clear();
  });

  test(
    'offline events survive restart and preserve exact IDs, clocks and causal order',
    () async {
      api.offline = true;
      final first = make();
      await first.bindParticipant(1);
      await first.log(
        sessionId: 's',
        eventType: 'selection',
        data: {'action': 'letter'},
      );
      await first.log(
        sessionId: 's',
        eventType: 'delete',
        data: {'action': 'backspace'},
      );
      await expectLater(first.flush(), throwsA(isA<ApiException>()));
      expect(first.pendingCount, 2);
      final saved = (await store.load(1)).map((e) => e.body).toList();
      final resumed = make();
      api.offline = false;
      await resumed.bindParticipant(1);
      await resumed.flush();
      expect(resumed.pendingCount, 0);
      expect(store.entries, isEmpty);
      expect(api.accepted.values.toList(), saved);
      expect(saved.map((e) => e['sequence']).toList(), [1, 2]);
    },
  );

  test(
    'lost ACK resends the same immutable event and is counted once',
    () async {
      final service = make();
      await service.bindParticipant(1);
      api.loseNextAck = true;
      await expectLater(
        service.log(
          sessionId: 's',
          eventType: 'session_end',
          requireDelivery: true,
        ),
        throwsA(isA<TimeoutException>()),
      );
      expect(service.pendingCount, 1);
      await service.flush();
      expect(api.requests.length, 2);
      expect(api.requests.first, api.requests.last);
      expect(api.accepted.length, 1);
      expect(store.entries, isEmpty);
    },
  );

  test('ACK from another account never removes the pending event', () async {
    final service = make();
    await service.bindParticipant(1);
    api.wrongOwnerAck = true;
    await expectLater(
      service.log(
        sessionId: 's',
        eventType: 'session_start',
        requireDelivery: true,
      ),
      throwsStateError,
    );
    expect(service.blocked, isTrue);
    expect(store.entries.length, 1);
    api.wrongOwnerAck = false;
    await service.flush();
    expect(store.entries, isEmpty);
  });

  test(
    'trial completion stays durable until local progress commits, including restart',
    () async {
      final service = make();
      await service.bindParticipant(1);
      await service.log(
        sessionId: 's',
        eventType: 'trial_end',
        data: {'status': 'completed'},
        requireDelivery: true,
        retainUntilCommitted: true,
      );
      expect(service.retainedEvents.length, 1);
      final id = service.retainedEvents.single.id;
      final recovered = make();
      await recovered.bindParticipant(1);
      await recovered.flush();
      expect(api.accepted.length, 1);
      expect(recovered.pendingCount, 1);
      await recovered.commit(id);
      expect(store.entries, isEmpty);
    },
  );

  test('changing accounts cannot deliver another participants queue', () async {
    final service = make();
    await service.bindParticipant(1);
    api.offline = true;
    await expectLater(
      service.log(
        sessionId: 'one',
        eventType: 'session_end',
        requireDelivery: true,
      ),
      throwsA(isA<ApiException>()),
    );
    await service.bindParticipant(2);
    api.owner = 2;
    api.offline = false;
    await service.log(
      sessionId: 'two',
      eventType: 'session_start',
      requireDelivery: true,
    );
    expect((await store.load(1)).length, 1);
    expect(api.accepted.values.single['session_id'], 'two');
    api.owner = 1;
    await service.bindParticipant(1);
    await service.flush();
    expect(api.accepted.length, 2);
    expect(store.entries, isEmpty);
  });

  test(
    'concurrent inputs receive consecutive sequences without dropped events',
    () async {
      final service = make();
      await service.bindParticipant(1);
      await Future.wait(
        List.generate(
          20,
          (i) => service.log(
            sessionId: 's',
            eventType: 'selection',
            requireDelivery: true,
          ),
        ),
      );
      expect(api.accepted.length, 20);
      expect(
        api.accepted.values.map((e) => e['sequence']).toList(),
        List.generate(20, (i) => i + 1),
      );
      expect(service.pendingCount, 0);
    },
  );

  test(
    'storage failure cannot masquerade as a persisted or delivered action',
    () async {
      final service = make();
      await service.bindParticipant(1);
      store.failWrite = true;
      await expectLater(
        service.log(sessionId: 's', eventType: 'selection'),
        throwsStateError,
      );
      expect(api.requests, isEmpty);
      expect(store.entries, isEmpty);
      expect(service.error, isNotNull);
    },
  );

  test('rate limits retain events and remain retryable', () async {
    final service = make();
    await service.bindParticipant(1);
    api.rejectStatus = 429;
    await expectLater(
      service.log(
        sessionId: 's',
        eventType: 'selection',
        requireDelivery: true,
      ),
      throwsA(isA<ApiException>()),
    );
    expect(service.blocked, isFalse);
    expect(service.pendingCount, 1);
    api.rejectStatus = null;
    await service.flush();
    expect(service.pendingCount, 0);
  });

  test(
    'a token replaced by another account cannot misattribute queued data',
    () async {
      final service = make();
      await service.bindParticipant(1);
      api.offline = true;
      await expectLater(
        service.log(
          sessionId: 's',
          eventType: 'selection',
          requireDelivery: true,
        ),
        throwsA(isA<ApiException>()),
      );
      api.offline = false;
      api.owner = 2;
      await expectLater(service.flush(), throwsA(isA<ApiException>()));
      expect(api.accepted, isEmpty);
      expect(service.pendingCount, 1);
      api.owner = 1;
      await service.flush();
      expect(api.accepted.length, 1);
      expect(service.pendingCount, 0);
    },
  );
}
