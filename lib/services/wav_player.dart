import 'dart:async';
import 'dart:ffi';
import 'dart:io';
import 'dart:typed_data';

import 'package:ffi/ffi.dart';
import 'package:win32/win32.dart';

import 'speech_service.dart';

/// Reproduce audio WAV completo en memoria.
abstract class AudioPlayback {
  /// Termina cuando el audio acaba o cuando se llama a [stop].
  Future<void> play(Uint8List wav);
  void stop();
}

/// Duración de un WAV PCM a partir de su cabecera RIFF.
Duration wavDuration(Uint8List wav) {
  if (wav.length < 12 ||
      String.fromCharCodes(wav, 0, 4) != 'RIFF' ||
      String.fromCharCodes(wav, 8, 12) != 'WAVE') {
    throw SpeechException('El audio recibido no es un WAV válido.');
  }
  final bytes = ByteData.sublistView(wav);
  int? byteRate;
  var offset = 12;
  while (offset + 8 <= wav.length) {
    final id = String.fromCharCodes(wav, offset, offset + 4);
    final size = bytes.getUint32(offset + 4, Endian.little);
    final body = offset + 8;
    if (id == 'fmt ' && body + 12 <= wav.length) {
      byteRate = bytes.getUint32(body + 8, Endian.little);
    } else if (id == 'data') {
      if (byteRate == null || byteRate == 0) break;
      final available = wav.length - body;
      final dataSize = size > available ? available : size;
      return Duration(microseconds: dataSize * 1000000 ~/ byteRate);
    }
    offset = body + size + (size.isOdd ? 1 : 0);
  }
  throw SpeechException('El audio recibido no es un WAV válido.');
}

/// Reproductor nativo de Windows (`PlaySound` de winmm, asíncrono, desde
/// memoria). `PlaySound` no avisa al terminar, así que el fin se calcula con la
/// duración del WAV. El búfer se libera solo después de detener el sonido.
class WindowsWavPlayer implements AudioPlayback {
  Pointer<Uint8>? _buffer;
  Timer? _timer;
  Completer<void>? _done;

  @override
  Future<void> play(Uint8List wav) {
    stop();
    if (!Platform.isWindows) {
      throw SpeechException('La reproducción de voz solo está disponible en Windows.');
    }
    final length = wavDuration(wav);
    final buffer = calloc<Uint8>(wav.length);
    buffer.asTypedList(wav.length).setAll(0, wav);
    _buffer = buffer;
    final ok = PlaySound(
      buffer.cast<Utf16>(),
      0,
      SND_MEMORY | SND_ASYNC | SND_NODEFAULT,
    );
    if (ok == 0) {
      _release();
      throw SpeechException('Windows no pudo reproducir el audio.');
    }
    final done = _done = Completer<void>();
    _timer = Timer(length + const Duration(milliseconds: 200), stop);
    return done.future;
  }

  @override
  void stop() {
    _timer?.cancel();
    _timer = null;
    _release();
    final done = _done;
    _done = null;
    if (done != null && !done.isCompleted) done.complete();
  }

  void _release() {
    final buffer = _buffer;
    if (buffer == null) return;
    // Detiene cualquier sonido antes de liberar la memoria que lo contiene.
    PlaySound(nullptr, 0, 0);
    calloc.free(buffer);
    _buffer = null;
  }
}
