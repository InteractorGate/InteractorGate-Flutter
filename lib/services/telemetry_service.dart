import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import 'api_client.dart';
import 'outbox_store.dart';

/// Persiste antes de enviar; solo retira eventos tras un ACK de su ID y cuenta.
class TelemetryService extends ChangeNotifier {
  TelemetryService(this._api, {OutboxStore? store, this.autoRetry = true})
    : _store = store ?? OutboxStore();

  final ApiClient _api;
  final OutboxStore _store;
  final bool autoRetry;
  final _events = <PendingEvent>[];
  final _acknowledged = <String>{};
  final _sequences = <String, int>{};
  final _manifest = <String, Set<String>>{};
  Future<void> _writes = Future.value();
  Future<void>? _flushing;
  Timer? _retry;
  int? _owner;
  int _order = 0;
  String? error;
  bool blocked = false;

  int get pendingCount => _events.length;
  List<PendingEvent> get retainedEvents =>
      List.unmodifiable(_events.where((e) => e.retain));
  String _ackKey(int owner, String id) => '$owner:$id';

  Future<T> _write<T>(Future<T> Function() action) {
    final result = _writes.then((_) => action());
    _writes = result.then<void>((_) {}, onError: (Object _, StackTrace _) {});
    return result;
  }

  Future<void> bindParticipant(int owner) async {
    pause();
    try {
      await _flushing;
    } catch (_) {
      /* Pendientes conservados. */
    }
    await _writes;
    final events = await _store.load(owner);
    _owner = owner;
    _events
      ..clear()
      ..addAll(events);
    _order = events.isEmpty ? 0 : events.last.order;
    for (final event in events) {
      final session = event.body['session_id'] as String;
      final sequence = event.body['sequence'] as int;
      if (sequence > (_sequences[session] ?? 0)) _sequences[session] = sequence;
      (_manifest[session] ??= {}).add(event.id);
    }
    error = null;
    blocked = false;
    if (autoRetry) {
      _retry = Timer.periodic(
        const Duration(seconds: 5),
        (_) => _sendInBackground(),
      );
    }
    notifyListeners();
  }

  void pause() {
    _retry?.cancel();
    _retry = null;
  }

  void _sendInBackground() {
    if (_owner == null || blocked || _events.isEmpty) return;
    unawaited(flush().catchError((Object _) {}));
  }

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
    final owner = _owner;
    if (owner == null) {
      throw StateError('Falta identificar al propietario de los eventos.');
    }
    final id = eventId ?? const Uuid().v4();
    try {
      await _write(() async {
        if (_owner != owner) {
          throw StateError('La cuenta cambió durante el registro.');
        }
        if (_acknowledged.contains(_ackKey(owner, id)) ||
            _events.any((e) => e.id == id)) {
          return;
        }
        if (_events.length >= 10000) {
          throw StateError('La cola está llena; confirma su entrega.');
        }
        final sequence = (_sequences[sessionId] ?? 0) + 1;
        final body =
            jsonDecode(
                  jsonEncode({
                    'event_id': id,
                    'participant_id': owner,
                    'sequence': sequence,
                    'session_id': sessionId,
                    'event_type': eventType,
                    'timestamp': (timestamp ?? DateTime.now())
                        .toUtc()
                        .toIso8601String(),
                    if (gaze != null) 'gaze_coordinates': gaze,
                    if (selectedWord != null) 'selected_word': selectedWord,
                    if (data != null) 'data': data,
                  }),
                )
                as Map<String, dynamic>;
        final event = PendingEvent(
          owner: owner,
          order: _order + 1,
          body: body,
          retain: retainUntilCommitted,
        );
        await _store.put(event);
        _events.add(event);
        _order = event.order;
        _sequences[sessionId] = sequence;
        (_manifest[sessionId] ??= {}).add(id);
        notifyListeners();
      });
    } catch (_) {
      error =
          'No se pudo guardar un evento. Revisa el almacenamiento antes de continuar.';
      notifyListeners();
      rethrow;
    }
    if (requireDelivery) {
      while (!_acknowledged.contains(_ackKey(owner, id))) {
        await flush();
      }
    } else {
      _sendInBackground();
    }
  }

  Future<void> flush() =>
      _flushing ??= _flush().whenComplete(() => _flushing = null);

  Future<void> _flush() async {
    await _writes;
    try {
      while (true) {
        final todo = _events.where(
          (e) => !_acknowledged.contains(_ackKey(e.owner, e.id)),
        );
        if (todo.isEmpty) break;
        final event = todo.first;
        if (_owner != event.owner) {
          throw StateError('Propietario de cola incorrecto.');
        }
        final ack = await _api.postJson('/api/logs/', event.body);
        if (ack['event_id'] != event.id ||
            ack['user_id'] != event.owner ||
            ack['schema_version'] != 2) {
          blocked = true;
          throw StateError(
            'El servidor no confirmó el identificador y propietario del evento.',
          );
        }
        await _write(() async {
          if (!event.retain) {
            await _store.remove(event);
            _events.remove(event);
          }
          _acknowledged.add(_ackKey(event.owner, event.id));
          notifyListeners();
        });
      }
      error = null;
      blocked = false;
    } catch (failure) {
      if (failure is ApiException &&
          failure.statusCode >= 400 &&
          failure.statusCode < 500 &&
          failure.statusCode != 429) {
        blocked = true;
      }
      error = blocked
          ? 'El servidor no aceptó un evento. Los pendientes se conservan para revisión.'
          : 'Sin confirmar entrega. Los eventos se conservan y se reintentarán.';
      rethrow;
    } finally {
      notifyListeners();
    }
  }

  Future<void> commit(String eventId) => _write(() async {
    final found = _events.where((e) => e.id == eventId).toList();
    if (found.isEmpty) return;
    final event = found.single;
    if (!_acknowledged.contains(_ackKey(event.owner, event.id))) {
      throw StateError('No se puede retirar un evento sin confirmar.');
    }
    await _store.remove(event);
    _events.remove(event);
    notifyListeners();
  });

  Future<Map<String, dynamic>> sessionReport(String sessionId) async {
    await flush();
    final report = await _api.getJson('/api/logs/session/$sessionId/');
    final logs = (report['logs'] as List).cast<Map<String, dynamic>>();
    final received = logs.map((e) => e['event_id']).toSet();
    final missing = (_manifest[sessionId] ?? {}).difference(received);
    if (missing.isNotEmpty) {
      throw StateError('Hay eventos confirmados ausentes en la consulta.');
    }
    return report;
  }

  @override
  void dispose() {
    pause();
    super.dispose();
  }
}
