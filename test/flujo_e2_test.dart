// Prueba de punta a punta del registro de E2: maneja la pantalla real
// (HomeScreen) con los atajos del investigador, toques y permanencia del
// puntero, y comprueba el archivo JSONL que queda en disco.
//
// Si se define IG_VALIDACION_OUT, copia ahí el archivo antes de borrarlo, para
// pasarle herramientas/validar_registro.py y herramientas/analisis_e2.py.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:interactor_gate/models/prediction.dart';
import 'package:interactor_gate/screens/home_screen.dart';
import 'package:interactor_gate/services/api_client.dart';
import 'package:interactor_gate/services/auth_service.dart';
import 'package:interactor_gate/services/gaze_bridge.dart';
import 'package:interactor_gate/services/prediction_service.dart';
import 'package:interactor_gate/services/telemetry_service.dart';
import 'package:interactor_gate/services/token_store.dart';
import 'package:interactor_gate/state/auth_controller.dart';
import 'package:interactor_gate/state/session_controller.dart';
import 'package:interactor_gate/widgets/big_cell_board.dart';
import 'package:interactor_gate/widgets/dwell_keyboard.dart';
import 'package:interactor_gate/widgets/suggestion_bar.dart';

/// Sin red: el envío al servidor falla y solo queda el archivo local.
class _SinRed extends ApiClient {
  _SinRed() : super(TokenStore());

  @override
  Future<Json> postJson(String path, Object body, {bool auth = true}) async =>
      throw const SocketException('sin red en la prueba');
}

class _Prediccion extends PredictionService {
  _Prediccion() : super(_SinRed());

  @override
  Future<Prediction> predictText(String context, String sessionId) async =>
      const Prediction(
        suggestions: ['por favor', 'gracias', 'ayuda'],
        confidence: 0.4,
      );
}

const _usuario = 'ZZVALIDA';

void main() {
  testWidgets('una sesión de E2 deja en disco todos los eventos del catálogo', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final telemetria = TelemetryService(_SinRed());
    final session = SessionController(
      _Prediccion(),
      telemetria,
      appVersion: 'prueba',
    );
    final auth = AuthController(AuthService(_SinRed(), TokenStore()));
    await session.comenzar(_usuario);
    final carpeta = telemetria.carpeta!;

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: auth),
          ChangeNotifierProvider.value(value: session),
          ChangeNotifierProvider(create: (_) => GazeBridge()),
        ],
        child: const MaterialApp(home: HomeScreen()),
      ),
    );
    await tester.pump();

    Finder en(Type tablero, String texto) =>
        find.descendant(of: find.byType(tablero), matching: find.text(texto));
    Future<void> toca(Finder f) async {
      await tester.tap(f);
      await tester.pump();
    }

    // Permanencia de verdad: el puntero entra en el botón y se queda 1,2 s.
    final raton = await tester.createGesture(kind: PointerDeviceKind.mouse);
    await raton.addPointer(location: Offset.zero);
    addTearDown(raton.removePointer);
    Future<void> mira(Finder f) async {
      await raton.moveTo(tester.getCenter(f));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 1300));
      await raton.moveTo(const Offset(5, 5));
      await tester.pump();
    }

    Future<void> ensayo(
      LogicalKeyboardKey tecla,
      String frase, {
      bool ctrl = false,
    }) async {
      if (ctrl) await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
      await tester.sendKeyEvent(tecla);
      if (ctrl) await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), frase);
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pumpAndSettle();
    }

    // Ensayo 1, CON predicción: celda por permanencia + sugerencia (rango 0).
    await ensayo(LogicalKeyboardKey.f2, 'agua por favor');
    expect(session.ensayo?.objetivo, 'agua por favor');
    expect(
      find.textContaining('agua por favor', findRichText: true),
      findsOneWidget,
    ); // la frase se ve en la barra de título
    await mira(en(BigCellBoard, 'Agua'));
    await toca(en(SuggestionBar, 'por favor'));
    expect(session.ensayo!.completado, isTrue);

    // Ensayo 2, SIN predicción: celda, cambio a teclado, espacio, un error
    // corregido con borrar y el resto de letras.
    // Con Ctrl+2 en vez de F3: en muchas laptops la fila de F no llega a la
    // app. Antes, un clic en el interruptor Dwell para quitarle el foco.
    await toca(find.byType(Switch));
    await toca(find.byType(Switch));
    await ensayo(LogicalKeyboardKey.digit2, 'no quiero', ctrl: true);
    expect(session.ensayo?.condicion, Condicion.sinPrediccion);
    expect(find.byType(SuggestionBar), findsNothing);
    await toca(en(BigCellBoard, 'No'));
    await toca(en(BigCellBoard, '⌨ Teclado'));
    await toca(en(DwellKeyboard, 'ESPACIO'));
    for (final ch in 'QUX'.split('')) {
      await toca(en(DwellKeyboard, ch));
    }
    await mira(
      find.descendant(
        of: find.byType(DwellKeyboard),
        matching: find.byIcon(Icons.backspace_outlined),
      ),
    );
    for (final ch in 'IERO'.split('')) {
      await toca(en(DwellKeyboard, ch));
    }
    expect(session.ensayo!.completado, isTrue);

    // Ensayo 3, CON predicción, abandonado: una letra, LIMPIAR y F4.
    await ensayo(LogicalKeyboardKey.f2, 'hola');
    await toca(en(DwellKeyboard, 'H'));
    await toca(en(DwellKeyboard, 'LIMPIAR'));
    await tester.sendKeyEvent(LogicalKeyboardKey.f4);
    await tester.pump();

    // F8: uso libre, y una letra fuera de ensayo.
    await tester.sendKeyEvent(LogicalKeyboardKey.f8);
    await tester.pump();
    await toca(en(DwellKeyboard, 'A'));

    await session.terminar();
    await tester.pumpAndSettle();

    // --- El archivo ---------------------------------------------------------
    final archivos = Directory(carpeta)
        .listSync()
        .whereType<File>()
        .where((f) => f.path.contains('sesion_'))
        .toList();
    expect(archivos, hasLength(1));
    final salida = Platform.environment['IG_VALIDACION_OUT'];
    if (salida != null) {
      final destino = Directory('$salida\\registros\\$_usuario')
        ..createSync(recursive: true);
      archivos.single.copySync(
        '${destino.path}\\${archivos.single.uri.pathSegments.last}',
      );
    }
    final ev = archivos.single
        .readAsLinesSync()
        .map((l) => jsonDecode(l) as Map<String, dynamic>)
        .toList();
    Directory(carpeta).deleteSync(recursive: true);

    final tipos = ev.map((e) => e['event_type']).toSet();
    expect(
      tipos,
      containsAll(<String>[
        'session_start',
        'trial_start',
        'selection',
        'suggestions',
        'settings',
        'delete',
        'clear',
        'trial_end',
        'session_end',
      ]),
    );
    expect(ev.first['event_type'], 'session_start');
    expect(ev.last['event_type'], 'session_end');
    for (final e in ev) {
      expect(e['usuario'], _usuario);
      expect(e['session_id'], session.sessionId);
      expect(e['timestamp'], endsWith('Z'));
    }

    final fines = ev.where((e) => e['event_type'] == 'trial_end').toList();
    expect(fines.map((e) => e['data']['completado']), [true, true, false]);
    final f2 = fines[1]['data'];
    expect(f2['condicion'], 'sin_prediccion');
    // No, teclado, espacio, Q, U, X, borrar, I, E, R, O
    expect(f2['selecciones'], 11);
    expect(f2['cambios_tablero'], 1);
    expect(f2['borrados'], 1);
    expect(fines[2]['data']['limpiezas'], 1);

    final sug = ev.firstWhere(
      (e) =>
          e['event_type'] == 'selection' && e['data']['origen'] == 'sugerencia',
    );
    expect(sug['data']['rango'], 0);
    // La selección por permanencia lleva la posición del puntero (= mirada).
    final porMirada = ev.firstWhere((e) => e['selected_word'] == 'Agua');
    expect(porMirada['gaze_coordinates'], isNotNull);
    expect(
      ev.firstWhere((e) => e['event_type'] == 'delete')['gaze_coordinates'],
      isNotNull,
    );
    // Fuera de ensayo no se registra el texto completo.
    final libre = ev.lastWhere((e) => e['event_type'] == 'selection');
    expect(libre['data'].containsKey('texto'), isFalse);
    expect(libre['data'].containsKey('ensayo'), isFalse);
  });
}
