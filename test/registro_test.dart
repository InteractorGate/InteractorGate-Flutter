import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:interactor_gate/models/prediction.dart';
import 'package:interactor_gate/services/api_client.dart';
import 'package:interactor_gate/services/prediction_service.dart';
import 'package:interactor_gate/services/telemetry_service.dart';
import 'package:interactor_gate/services/token_store.dart';
import 'package:interactor_gate/state/session_controller.dart';

/// Guarda los eventos en memoria en vez de enviarlos.
class _Telemetria extends TelemetryService {
  _Telemetria() : super(ApiClient(TokenStore()));

  final eventos = <Map<String, Object?>>[];

  @override
  void abrirSesion(String usuario, String sessionId) {}

  @override
  Future<void> log({
    required String sessionId,
    required String eventType,
    Map<String, double>? gaze,
    String? selectedWord,
    Map<String, Object?>? data,
  }) async {
    eventos.add({
      'event_type': eventType,
      'selected_word': selectedWord,
      'data': data,
    });
  }

  Iterable<Map<String, Object?>> de(String tipo) =>
      eventos.where((e) => e['event_type'] == tipo);
}

class _Prediccion extends PredictionService {
  _Prediccion() : super(ApiClient(TokenStore()));

  int consultas = 0;

  @override
  Future<Prediction> predictText(String context, String sessionId) async {
    consultas++;
    return const Prediction(suggestions: ['agua', 'ayuda'], confidence: 0.5);
  }
}

void main() {
  late _Telemetria tel;
  late _Prediccion pred;
  late SessionController s;

  setUp(() async {
    tel = _Telemetria();
    pred = _Prediccion();
    s = SessionController(pred, tel, appVersion: 'test');
    await s.comenzar('P00');
  });

  test('normalizar ignora mayúsculas, tildes y espacios sobrantes', () {
    expect(normalizar('  Sí   QUIERO agua '), 'si quiero agua');
  });

  test('la sesión empieza con el login y termina con session_end', () async {
    expect(tel.de('session_start').single['data'],
        containsPair('app_version', 'test'));
    await s.terminar();
    expect(tel.eventos.last['event_type'], 'session_end');
    // Sin sesión no se registra nada.
    await s.type('A');
    expect(tel.eventos.last['event_type'], 'session_end');
  });

  test('un ensayo se cierra solo al llegar a la frase objetivo', () async {
    await s.iniciarEnsayo(Condicion.conPrediccion, 'sí agua');
    await s.insertWord('Sí');
    expect(s.ensayo!.completado, isFalse);
    await s.applySuggestion('agua');

    final fin = tel.de('trial_end').single['data'] as Map;
    expect(fin['completado'], isTrue);
    expect(fin['condicion'], 'con_prediccion');
    expect(fin['texto_final'], 'Sí agua');
    expect(fin['palabras'], 1);
    expect(fin['sugerencias_aceptadas'], 1);
    final sel = tel.de('selection').last['data'] as Map;
    expect(sel['origen'], 'sugerencia');
    expect(sel['rango'], 0);
  });

  test('sin predicción no se consulta la RNN y se registran los borrados',
      () async {
    await s.iniciarEnsayo(Condicion.sinPrediccion, 'no');
    s.toggleBoardMode(); // a teclado: también es una selección
    await s.type('N');
    await s.type('X');
    await s.backspace();
    await s.type('O');

    expect(pred.consultas, 0);
    expect(s.suggestions, isEmpty);
    expect(tel.de('delete').single['data'], containsPair('borrado', 'X'));
    final fin = tel.de('trial_end').single['data'] as Map;
    expect(fin['completado'], isTrue);
    expect(fin['teclas'], 3);
    expect(fin['borrados'], 1);
    expect(fin['cambios_tablero'], 1);
    expect(fin['selecciones'], 5);
  });

  test('con predicción se registran las sugerencias y su latencia', () async {
    await s.iniciarEnsayo(Condicion.conPrediccion, 'quiero agua');
    await s.type('Q');
    final sug = tel.de('suggestions').single['data'] as Map;
    expect(sug['sugerencias'], ['agua', 'ayuda']);
    expect(sug['latencia_ms'], isA<int>());
    expect(sug['ensayo'], 1);
  });

  test('abrir un ensayo nuevo abandona el que estaba en curso', () async {
    await s.iniciarEnsayo(Condicion.conPrediccion, 'agua');
    await s.iniciarEnsayo(Condicion.sinPrediccion, 'comida');
    final fines = tel.de('trial_end').toList();
    expect(fines, hasLength(1));
    expect((fines.single['data'] as Map)['completado'], isFalse);
    expect(s.ensayo!.numero, 2);
    expect(s.prediccionActiva, isFalse);
  });

  test('el archivo local tiene un evento JSON por línea, en orden', () async {
    final dir = await Directory.systemTemp.createTemp('ig_registro');
    addTearDown(() => dir.delete(recursive: true));
    final real = TelemetryService(ApiClient(TokenStore()));
    // Sin LOCALAPPDATA controlable desde el test, se escribe en la carpeta
    // real; se borra al final.
    real.abrirSesion('ZZTEST', 'abcdef0123456789');
    final carpeta = real.carpeta!;
    addTearDown(() => Directory(carpeta).delete(recursive: true));
    for (final t in ['session_start', 'selection', 'session_end']) {
      // El envío al servidor falla sin red ni token: no debe importar.
      await real.log(sessionId: 's', eventType: t, data: {'k': 1});
    }
    final archivos = Directory(carpeta).listSync().whereType<File>().toList();
    final lineas = archivos.single.readAsLinesSync();
    expect(lineas.map((l) => jsonDecode(l)['event_type']),
        ['session_start', 'selection', 'session_end']);
    expect(jsonDecode(lineas.first)['usuario'], 'ZZTEST');
    expect(jsonDecode(lineas.first)['timestamp'], endsWith('Z'));
  });
}
