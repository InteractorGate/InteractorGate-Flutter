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
}
