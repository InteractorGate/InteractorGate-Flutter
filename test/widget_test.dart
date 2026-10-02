import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:interactor_gate/models/prediction.dart';
import 'package:interactor_gate/widgets/composed_text_bar.dart';
import 'package:interactor_gate/widgets/dwell_button.dart';

void main() {
  test('Prediction.fromJson divide output_text por " | "', () {
    final p = Prediction.fromJson({
      'result': {
        'output_text': 'la cabeza | el estómago | mucho aquí',
        'confidence_score': 0.47,
      },
    });
    expect(p.suggestions, ['la cabeza', 'el estómago', 'mucho aquí']);
    expect(p.confidence, closeTo(0.47, 1e-6));
  });

  testWidgets('ComposedTextBar muestra el texto compuesto', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: ComposedTextBar(text: 'hola')),
    ));
    expect(find.text('hola'), findsOneWidget);
  });

  testWidgets('DwellButton dispara onSelected al hacer tap', (tester) async {
    var fired = false;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: DwellButton(
          dwellEnabled: false,
          onSelected: () => fired = true,
          child: const Text('A'),
        ),
      ),
    ));
    await tester.tap(find.text('A'));
    expect(fired, isTrue);
  });

  group('DwellButton: tolerancia de salida', () {
    // Nota de mecanica del test: tras mover el raton hace falta un `pump()`
    // sin duracion para que se despache el evento de entrada/salida. Si se
    // pasa directamente a `pump(700)`, esos 700 ms se consumen ANTES de que
    // onEnter arranque la animacion y la permanencia se queda en cero.
    late TestGesture g;
    final boton = find.text('A');

    Future<void> montar(WidgetTester tester, VoidCallback onSelected,
        {double tolerancia = 0.5}) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Center(
            child: SizedBox(
              width: 200,
              height: 100,
              child: DwellButton(
                dwellSeconds: 1.0,
                toleranceSeconds: tolerancia,
                onSelected: onSelected,
                child: const Text('A'),
              ),
            ),
          ),
        ),
      ));
      g = await tester.createGesture(kind: PointerDeviceKind.mouse);
      await g.addPointer(location: Offset.zero);
      addTearDown(g.removePointer);
    }

    Future<void> entrar(WidgetTester tester) async {
      await g.moveTo(tester.getCenter(boton));
      await tester.pump();
    }

    Future<void> salir(WidgetTester tester) async {
      await g.moveTo(Offset.zero);
      await tester.pump();
    }

    testWidgets('una salida breve NO reinicia la cuenta', (tester) async {
      var fired = false;
      await montar(tester, () => fired = true);

      await entrar(tester);
      await tester.pump(const Duration(milliseconds: 700)); // 0.7 de 1.0
      await salir(tester);                                  // se PAUSA en 0.7
      await tester.pump(const Duration(milliseconds: 300)); // dentro de 0.5 s
      await entrar(tester);                                 // reanuda en 0.7

      // Solo deben faltar los 300 ms que quedaban, no 1000 desde cero.
      await tester.pump(const Duration(milliseconds: 250));
      expect(fired, isFalse, reason: 'aun faltan ~50 ms');
      await tester.pump(const Duration(milliseconds: 100));
      expect(fired, isTrue, reason: 'reanudo en vez de reiniciar');
    });

    testWidgets('nunca dispara con el puntero fuera', (tester) async {
      var fired = false;
      await montar(tester, () => fired = true);

      await entrar(tester);
      await tester.pump(const Duration(milliseconds: 900)); // 0.9 de 1.0
      await salir(tester);
      // Le faltaban 100 ms y la tolerancia es de 500: si la cuenta siguiera
      // corriendo, aqui se confirmaria una seleccion sin mirar el boton.
      await tester.pump(const Duration(milliseconds: 400));
      expect(fired, isFalse);
    });

    testWidgets('una salida larga SI cancela', (tester) async {
      var fired = false;
      await montar(tester, () => fired = true);

      await entrar(tester);
      await tester.pump(const Duration(milliseconds: 700));
      await salir(tester);
      await tester.pump(const Duration(milliseconds: 600)); // pasa de 0.5 s
      await entrar(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(fired, isFalse, reason: 'la cuenta se reinicio al volver');

      await tester.pump(const Duration(milliseconds: 700));
      expect(fired, isTrue);
    });

    testWidgets('toleranceSeconds: 0 recupera el comportamiento anterior',
        (tester) async {
      var fired = false;
      await montar(tester, () => fired = true, tolerancia: 0);

      await entrar(tester);
      await tester.pump(const Duration(milliseconds: 900));
      await salir(tester);
      await tester.pump(const Duration(milliseconds: 50));
      await entrar(tester);
      await tester.pump(const Duration(milliseconds: 200));
      expect(fired, isFalse);
    });
  });
}
