// Regresiones de accesibilidad; no certifican conformidad global.
import 'dart:ui' show PointerDeviceKind;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:interactor_gate/config/app_theme.dart';
import 'package:interactor_gate/widgets/dwell_button.dart';
import 'package:interactor_gate/widgets/dwell_keyboard.dart';
import 'package:interactor_gate/widgets/suggestion_bar.dart';
import 'package:interactor_gate/screens/login_screen.dart';
import 'package:interactor_gate/screens/register_screen.dart';
import 'dart:ui' show SemanticsAction;

void main() {
  testWidgets('WCAG 2.1.1: DwellButton se activa con Tab/Enter/Espacio', (
    tester,
  ) async {
    var fired = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.dark,
        home: Scaffold(
          body: DwellButton(
            dwellEnabled: false,
            onSelected: () => fired++,
            child: const Text('Ayuda'),
          ),
        ),
      ),
    );
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    final button = tester.widget<TextButton>(find.byType(TextButton));
    expect(button.style!.side!.resolve({WidgetState.focused})!.width, 3);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    expect(fired, 2);
    await tester.tap(find.text('Ayuda'));
    expect(fired, 3);
  });

  testWidgets('WCAG 1.1.1/4.1.2: retroceso tiene nombre y rol de botón', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.dark,
        home: Scaffold(
          body: DwellKeyboard(
            onKey: (_) {},
            onSpace: () {},
            onBackspace: () {},
            onClear: () {},
            onWords: () {},
            dwellEnabled: false,
          ),
        ),
      ),
    );
    final data = tester
        .getSemantics(find.byIcon(Icons.backspace_outlined))
        .getSemanticsData();
    expect(data.label, 'Borrar último carácter');
    expect(data.flagsCollection.isButton, isTrue);
    expect(data.hasAction(SemanticsAction.tap), isTrue);
    semantics.dispose();
  });

  testWidgets('WCAG 1.4.3: instrucción alcanza contraste 4.5', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.dark,
        home: Scaffold(
          body: SuggestionBar(suggestions: const [], onPick: (_) {}),
        ),
      ),
    );
    final instruction = tester.widget<Text>(
      find.text('Termina una palabra y pulsa ESPACIO para ver continuaciones'),
    );
    final background = AppTheme.dark.scaffoldBackgroundColor;
    final foreground = Color.alphaBlend(instruction.style!.color!, background);
    final ratio =
        (foreground.computeLuminance() + 0.05) /
        (background.computeLuminance() + 0.05);
    expect(ratio, greaterThanOrEqualTo(4.5));
  });

  testWidgets('WCAG 3.3.1: login identifica campos vacíos', (tester) async {
    await tester.pumpWidget(
      MaterialApp(theme: AppTheme.dark, home: const LoginScreen()),
    );
    await tester.tap(find.text('Iniciar sesión'));
    await tester.pumpAndSettle();
    expect(find.text('Ingresa el código de participante.'), findsOneWidget);
    expect(find.text('Ingresa la contraseña.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'WCAG 3.3.1: registro identifica vacíos y contraseñas diferentes',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(theme: AppTheme.dark, home: const RegisterScreen()),
      );
      await tester.ensureVisible(find.text('Registrarme'));
      await tester.tap(find.text('Registrarme'));
      await tester.pumpAndSettle();
      for (final message in [
        'Ingresa el código de participante.',
        'Ingresa el correo de estudio.',
        'Ingresa la contraseña.',
        'Repite la contraseña.',
      ]) {
        expect(find.text(message), findsOneWidget);
      }
      await tester.enterText(find.byType(TextFormField).at(0), 'P01');
      await tester.enterText(
        find.byType(TextFormField).at(1),
        'p01@example.com',
      );
      await tester.enterText(find.byType(TextFormField).at(2), 'first');
      await tester.enterText(find.byType(TextFormField).at(3), 'different');
      await tester.ensureVisible(find.text('Registrarme'));
      await tester.tap(find.text('Registrarme'));
      await tester.pumpAndSettle();
      expect(find.text('Las contraseñas no coinciden.'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'Dwell: salir del objetivo antes del plazo cancela la selección',
    (tester) async {
      var fired = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 200,
                height: 100,
                child: DwellButton(
                  onSelected: () => fired++,
                  child: const Text('Ayuda'),
                ),
              ),
            ),
          ),
        ),
      );
      final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
      await mouse.addPointer(location: Offset.zero);
      await mouse.moveTo(tester.getCenter(find.text('Ayuda')));
      await tester.pump(const Duration(milliseconds: 600));
      await mouse.moveTo(Offset.zero);
      await tester.pump(const Duration(seconds: 2));
      expect(fired, 0);
      await mouse.moveTo(tester.getCenter(find.text('Ayuda')));
      await tester.pump(const Duration(milliseconds: 1200));
      expect(fired, 1);
      await tester.pump(const Duration(seconds: 2));
      expect(fired, 1);
      await mouse.removePointer();
    },
  );
}
