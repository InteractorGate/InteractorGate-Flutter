import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../config/api_config.dart';

/// Una muestra de mirada del sidecar: posición normalizada [0..1] en pantalla
/// y si hubo parpadeo en ese frame.
class GazeSample {
  const GazeSample(this.x, this.y, this.blink);
  final double x;
  final double y;
  final bool blink;
}

/// Cliente del sidecar de rastreo ocular (proceso Python) por TCP.
///
/// El sidecar publica líneas JSON: `{"x":0.42,"y":0.71,"blink":false}`.
/// Es OPCIONAL: si no conecta, la app sigue funcionando con el mouse
/// (que el tracker Python ya controla con la mirada).
class GazeBridge extends ChangeNotifier {
  Socket? _socket;
  bool connected = false;
  GazeSample? last;

  final StreamController<GazeSample> _controller =
      StreamController<GazeSample>.broadcast();

  Stream<GazeSample> get stream => _controller.stream;

  Future<bool> connect() async {
    try {
      _socket = await Socket.connect(
        ApiConfig.gazeHost,
        ApiConfig.gazePort,
        timeout: const Duration(seconds: 2),
      );
      connected = true;
      notifyListeners();

      _socket!
          .cast<List<int>>()
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .listen(_onLine, onDone: _onDone, onError: (_) => _onDone());
      return true;
    } catch (_) {
      connected = false;
      notifyListeners();
      return false;
    }
  }

  void disconnect() => _onDone();

  void _onLine(String line) {
    if (line.trim().isEmpty) return;
    try {
      final json = jsonDecode(line) as Map<String, dynamic>;
      final sample = GazeSample(
        (json['x'] as num).toDouble(),
        (json['y'] as num).toDouble(),
        (json['blink'] as bool?) ?? false,
      );
      last = sample;
      _controller.add(sample);
    } catch (_) {
      // línea malformada: la ignoramos.
    }
  }

  void _onDone() {
    connected = false;
    _socket?.destroy();
    _socket = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _socket?.destroy();
    _controller.close();
    super.dispose();
  }
}
