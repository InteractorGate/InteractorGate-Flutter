import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../config/api_config.dart';

class PendingEvent {
  const PendingEvent({
    required this.owner,
    required this.order,
    required this.body,
    this.retain = false,
  });

  final int owner;
  final int order;
  final Map<String, dynamic> body;
  final bool retain;
  String get id => body['event_id'] as String;

  Map<String, dynamic> toJson() => {
    'owner': owner,
    'order': order,
    'body': body,
    'retain': retain,
  };

  factory PendingEvent.fromJson(Map<String, dynamic> json) => PendingEvent(
    owner: json['owner'] as int,
    order: json['order'] as int,
    body: Map<String, dynamic>.from(json['body'] as Map),
    retain: json['retain'] as bool,
  );
}

/// Un archivo cifrado por evento en Windows; sin índice separado que pueda perderse.
class OutboxStore {
  final FlutterSecureStorage _storage = const FlutterSecureStorage();
  String _prefix(int owner) =>
      'ig_outbox_${base64Url.encode(utf8.encode(ApiConfig.baseUrl)).replaceAll('=', '')}_${owner}_';

  Future<List<PendingEvent>> load(int owner) async {
    final values = await _storage.readAll();
    final events =
        values.entries
            .where((e) => e.key.startsWith(_prefix(owner)))
            .map(
              (e) => PendingEvent.fromJson(
                jsonDecode(e.value) as Map<String, dynamic>,
              ),
            )
            .toList()
          ..sort((a, b) => a.order.compareTo(b.order));
    if (events.any((e) => e.owner != owner)) {
      throw const FormatException(
        'La cola contiene un propietario incorrecto.',
      );
    }
    return events;
  }

  Future<void> put(PendingEvent event) => _storage.write(
    key: '${_prefix(event.owner)}${event.id}',
    value: jsonEncode(event.toJson()),
  );

  Future<void> remove(PendingEvent event) =>
      _storage.delete(key: '${_prefix(event.owner)}${event.id}');
}
