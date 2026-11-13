import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:interactor_gate/services/api_client.dart';
import 'package:interactor_gate/services/speech_service.dart';
import 'package:interactor_gate/services/token_store.dart';
import 'package:interactor_gate/services/wav_player.dart';
import 'package:interactor_gate/state/speech_controller.dart';
import 'package:interactor_gate/widgets/speak_button.dart';

class _Tokens extends TokenStore {
  @override
  Future<String?> get access async => 'jwt';
  @override
  Future<String?> get refresh async => null;
}

/// WAV PCM mínimo: [seconds] de silencio a 24 kHz, 16 bits, mono.
Uint8List _wav(double seconds) {
  const byteRate = 24000 * 2;
  final dataSize = (byteRate * seconds).round();
  final b = ByteData(44 + dataSize);
  void tag(int at, String s) {
    for (var i = 0; i < 4; i++) {
      b.setUint8(at + i, s.codeUnitAt(i));
    }
  }

  tag(0, 'RIFF');
  b.setUint32(4, 36 + dataSize, Endian.little);
  tag(8, 'WAVE');
  tag(12, 'fmt ');
  b.setUint32(16, 16, Endian.little);
  b.setUint16(20, 1, Endian.little);
  b.setUint16(22, 1, Endian.little);
  b.setUint32(24, 24000, Endian.little);
  b.setUint32(28, byteRate, Endian.little);
  b.setUint16(32, 2, Endian.little);
  b.setUint16(34, 16, Endian.little);
  tag(36, 'data');
  b.setUint32(40, dataSize, Endian.little);
  return b.buffer.asUint8List();
}

class _Synth implements SpeechSynthesizer {
  final calls = <String>[];
  Completer<Uint8List>? pending;
  Object? failure;

  @override
  Future<Uint8List> synthesize(String text) async {
    calls.add(text);
    if (failure != null) throw failure!;
    if (pending != null) return pending!.future;
    return _wav(0.1);
  }
}

class _Player implements AudioPlayback {
  int plays = 0;
  int stops = 0;
  Completer<void>? _done;

  @override
  Future<void> play(Uint8List wav) {
    plays++;
    return (_done = Completer<void>()).future;
  }

  void finish() => _done?.complete();

  @override
  void stop() {
    stops++;
    final done = _done;
    _done = null;
    if (done != null && !done.isCompleted) done.complete();
  }
}

void main() {
  group('Azure AI Speech', () {
    test('SSML escapa el texto y toma el idioma de la voz', () {
      final ssml = AzureSpeechSynthesizer.ssml(
        "Tom & Ana <dicen> 'hola'",
        'es-PE-CamilaNeural',
      );
      expect(ssml, contains("xml:lang='es-PE'"));
      expect(ssml, contains("<voice name='es-PE-CamilaNeural'>"));
      expect(
        ssml,
        contains('Tom &amp; Ana &lt;dicen&gt; &apos;hola&apos;'),
      );
    });

    test('pide un token al backend, lo reutiliza y sintetiza en WAV', () async {
      var tokenRequests = 0;
      final api = ApiClient(
        _Tokens(),
        client: MockClient((request) async {
          expect(request.url.path, '/api/speech/token/');
          expect(request.headers['Authorization'], 'Bearer jwt');
          tokenRequests++;
          return http.Response(
            jsonEncode({
              'token': 'azure-token',
              'region': 'eastus',
              'voice': 'es-PE-AlexNeural',
              'expires_in': 540,
            }),
            200,
          );
        }),
      );
      final azure = <http.Request>[];
      final synth = AzureSpeechSynthesizer(
        api,
        client: MockClient((request) async {
          azure.add(request);
          return http.Response.bytes(_wav(0.1), 200);
        }),
      );

      await synth.synthesize('hola');
      final audio = await synth.synthesize('gracias');

      expect(tokenRequests, 1);
      expect(azure, hasLength(2));
      final req = azure.first;
      expect(
        req.url.toString(),
        'https://eastus.tts.speech.microsoft.com/cognitiveservices/v1',
      );
      expect(req.headers['Authorization'], 'Bearer azure-token');
      expect(
        req.headers['X-Microsoft-OutputFormat'],
        'riff-24khz-16bit-mono-pcm',
      );
      expect(req.body, contains('es-PE-AlexNeural'));
      expect(req.body, contains('hola'));
      expect(wavDuration(audio), const Duration(milliseconds: 100));
    });

    test('renueva el token una vez si Azure responde 401', () async {
      var tokenRequests = 0;
      final api = ApiClient(
        _Tokens(),
        client: MockClient((_) async {
          tokenRequests++;
          return http.Response(
            jsonEncode({
              'token': 't$tokenRequests',
              'region': 'eastus',
              'voice': 'es-PE-CamilaNeural',
            }),
            200,
          );
        }),
      );
      final synth = AzureSpeechSynthesizer(
        api,
        client: MockClient((request) async {
          return request.headers['Authorization'] == 'Bearer t1'
              ? http.Response('', 401)
              : http.Response.bytes(_wav(0.1), 200);
        }),
      );
      await synth.synthesize('hola');
      expect(tokenRequests, 2);
    });

    test('rechaza una región con caracteres no válidos', () async {
      final api = ApiClient(
        _Tokens(),
        client: MockClient(
          (_) async => http.Response(
            jsonEncode({
              'token': 't',
              'region': 'evil.com/x',
              'voice': 'es-PE-CamilaNeural',
            }),
            200,
          ),
        ),
      );
      final synth = AzureSpeechSynthesizer(
        api,
        client: MockClient((_) async => fail('No debe llamar a Azure')),
      );
      expect(synth.synthesize('hola'), throwsA(isA<SpeechException>()));
    });
  });

  test('wavDuration rechaza datos que no son WAV', () {
    expect(
      () => wavDuration(Uint8List.fromList(utf8.encode('no es audio'))),
      throwsA(isA<SpeechException>()),
    );
  });

  group('SpeechController', () {
    test('pronuncia, vuelve a reposo y reutiliza el audio repetido', () async {
      final synth = _Synth();
      final player = _Player();
      final speech = SpeechController(synth, player);

      final first = speech.speak('  hola mundo ');
      await Future<void>.delayed(Duration.zero);
      expect(speech.status, SpeechStatus.speaking);
      player.finish();
      await first;
      expect(speech.status, SpeechStatus.idle);

      final again = speech.speak('hola mundo');
      await Future<void>.delayed(Duration.zero);
      player.finish();
      await again;

      expect(synth.calls, ['hola mundo']);
      expect(player.plays, 2);
    });

    test('ignora texto vacío', () async {
      final synth = _Synth();
      final speech = SpeechController(synth, _Player());
      await speech.speak('   ');
      expect(synth.calls, isEmpty);
      expect(speech.status, SpeechStatus.idle);
    });

    test('toggle durante la reproducción detiene la voz', () async {
      final player = _Player();
      final speech = SpeechController(_Synth(), player);
      final speaking = speech.toggle('hola');
      await Future<void>.delayed(Duration.zero);
      expect(speech.status, SpeechStatus.speaking);
      await speech.toggle('hola');
      await speaking;
      expect(speech.status, SpeechStatus.idle);
      expect(player.stops, greaterThan(0));
    });

    test('detener durante la síntesis no reproduce el audio tardío', () async {
      final synth = _Synth()..pending = Completer<Uint8List>();
      final player = _Player();
      final speech = SpeechController(synth, player);
      final speaking = speech.speak('hola');
      expect(speech.status, SpeechStatus.loading);
      speech.stop();
      synth.pending!.complete(_wav(0.1));
      await speaking;
      expect(player.plays, 0);
      expect(speech.status, SpeechStatus.idle);
    });

    test('muestra un mensaje si el backend no tiene la voz configurada',
        () async {
      final synth = _Synth()..failure = ApiException(503, 'no');
      final speech = SpeechController(synth, _Player());
      await speech.speak('hola');
      expect(speech.error, 'La voz no está configurada en el servidor.');
      expect(speech.status, SpeechStatus.idle);
    });

    test('reset olvida el audio del participante anterior', () async {
      final synth = _Synth();
      final player = _Player();
      final speech = SpeechController(synth, player);
      final first = speech.speak('hola');
      await Future<void>.delayed(Duration.zero);
      player.finish();
      await first;
      speech.reset();
      final second = speech.speak('hola');
      await Future<void>.delayed(Duration.zero);
      player.finish();
      await second;
      expect(synth.calls, ['hola', 'hola']);
    });
  });

  testWidgets('SpeakButton muestra HABLAR/DETENER y respeta el estado',
      (tester) async {
    var pressed = 0;
    Future<void> pump(SpeechStatus status, {required bool enabled}) =>
        tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: SizedBox(
                width: 230,
                height: 90,
                child: SpeakButton(
                  status: status,
                  enabled: enabled,
                  dwellEnabled: false,
                  onPressed: () => pressed++,
                ),
              ),
            ),
          ),
        );

    await pump(SpeechStatus.idle, enabled: false);
    await tester.tap(find.text('HABLAR'), warnIfMissed: false);
    expect(pressed, 0);

    await pump(SpeechStatus.idle, enabled: true);
    await tester.tap(find.text('HABLAR'));
    expect(pressed, 1);

    await pump(SpeechStatus.speaking, enabled: false);
    expect(find.text('DETENER'), findsOneWidget);
    await tester.tap(find.text('DETENER'));
    expect(pressed, 2);
  });
}
