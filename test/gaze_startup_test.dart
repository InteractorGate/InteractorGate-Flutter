import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:interactor_gate/app.dart';
import 'package:interactor_gate/models/user.dart';
import 'package:interactor_gate/screens/home_screen.dart';
import 'package:interactor_gate/services/api_client.dart';
import 'package:interactor_gate/services/auth_service.dart';
import 'package:interactor_gate/services/gaze_bridge.dart';
import 'package:interactor_gate/services/prediction_service.dart';
import 'package:interactor_gate/services/sidecar_launcher.dart';
import 'package:interactor_gate/services/telemetry_service.dart';
import 'package:interactor_gate/services/token_store.dart';
import 'package:interactor_gate/state/auth_controller.dart';
import 'package:interactor_gate/state/session_controller.dart';

class _Process extends Fake implements Process {
  final done = Completer<int>();
  bool killed = false;
  bool finishOnKill = true;
  @override
  Stream<List<int>> get stdout => const Stream.empty();
  @override
  Stream<List<int>> get stderr => const Stream.empty();
  @override
  Future<int> get exitCode => done.future;
  @override
  bool kill([ProcessSignal signal = ProcessSignal.sigterm]) {
    killed = true;
    if (finishOnKill && !done.isCompleted) done.complete(-1);
    return true;
  }
}

class _Auth extends AuthController {
  _Auth(SessionController session)
    : super(AuthService(ApiClient(TokenStore()), TokenStore()), session);
  void change(AuthStatus value) {
    status = value;
    user = value == AuthStatus.authenticated
        ? const User(id: 1, username: 'P01', email: 'p01@example.com')
        : null;
    notifyListeners();
  }
}

Future<_Auth> _openApp(WidgetTester tester, SidecarLauncher launcher) async {
  tester.view.physicalSize = const Size(1280, 900);
  tester.view.devicePixelRatio = 1;
  final api = ApiClient(TokenStore());
  final telemetry = TelemetryService(api, autoRetry: false);
  final session = SessionController(PredictionService(api), telemetry);
  final auth = _Auth(session)..change(AuthStatus.unauthenticated);
  final gaze = GazeBridge();
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        Provider<SidecarLauncher>.value(value: launcher),
        ChangeNotifierProvider<AuthController>.value(value: auth),
        ChangeNotifierProvider<SessionController>.value(value: session),
        ChangeNotifierProvider<GazeBridge>.value(value: gaze),
      ],
      child: const InteractorGateApp(),
    ),
  );
  addTearDown(() async {
    await tester.pumpWidget(const SizedBox.shrink());
    auth.dispose();
    session.dispose();
    telemetry.dispose();
    gaze.dispose();
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  return auth;
}

void main() {
  test(
    'calibration waits for its result and tracking uses a separate command',
    () async {
      final process = _Process();
      final commands = <List<String>>[];
      final launcher = SidecarLauncher(
        launchProcess: (args) async {
          commands.add(args);
          return process;
        },
      );
      var completed = false;
      final result = launcher.calibrate().then((ok) {
        completed = true;
        return ok;
      });
      await Future<void>.delayed(Duration.zero);
      expect(completed, isFalse);
      expect(commands, [
        ['--calibrate'],
      ]);
      expect(await launcher.start(), isFalse);
      process.done.complete(1);
      expect(await result, isFalse);
      expect(launcher.running, isFalse);
    },
  );

  test('logout during process creation kills the late child', () async {
    final pending = Completer<Process?>();
    final process = _Process();
    final launcher = SidecarLauncher(launchProcess: (_) => pending.future);
    final result = launcher.start();
    launcher.stop();
    pending.complete(process);
    expect(await result, isFalse);
    expect(process.killed, isTrue);
    expect(launcher.running, isFalse);
  });

  test(
    'an old process exiting cannot clear the new tracking process',
    () async {
      final old = _Process()..finishOnKill = false;
      final current = _Process();
      var calls = 0;
      final launcher = SidecarLauncher(
        launchProcess: (_) async => calls++ == 0 ? old : current,
      );
      expect(await launcher.start(), isTrue);
      launcher.stop();
      expect(await launcher.start(), isTrue);
      old.done.complete(0);
      await Future<void>.delayed(Duration.zero);
      expect(launcher.running, isTrue);
      launcher.stop();
      expect(current.killed, isTrue);
    },
  );

  testWidgets(
    'login has no camera; tracking starts after calibration and board frame',
    (tester) async {
      final calibration = _Process();
      final tracking = _Process();
      final commands = <List<String>>[];
      final launcher = SidecarLauncher(
        launchProcess: (args) async {
          commands.add(args);
          if (args.single == '--track') {
            expect(find.byType(HomeScreen), findsOneWidget);
            return tracking;
          }
          return calibration;
        },
      );
      final auth = await _openApp(tester, launcher);
      expect(find.text('Iniciar sesión'), findsOneWidget);
      expect(commands, isEmpty);
      auth.change(AuthStatus.authenticated);
      await tester.pumpAndSettle();
      expect(commands, isEmpty);
      await tester.tap(find.text('Calibrar y abrir tablero'));
      await tester.pumpAndSettle();
      expect(commands, isEmpty);
      await tester.tap(find.text('Permitir cámara y calibrar'));
      await tester.pump();
      expect(commands, [
        ['--calibrate'],
      ]);
      expect(find.byType(HomeScreen), findsNothing);
      calibration.done.complete(0);
      await tester.pumpAndSettle();
      expect(commands, [
        ['--calibrate'],
        ['--track'],
      ]);
      await tester.tap(find.byTooltip('Desactivar cámara'));
      await tester.pumpAndSettle();
      expect(tracking.killed, isTrue);
      expect(find.text('Calibrar y abrir tablero'), findsOneWidget);
      auth.change(AuthStatus.unauthenticated);
      await tester.pumpAndSettle();
      expect(tracking.killed, isTrue);
      expect(find.text('Iniciar sesión'), findsOneWidget);
    },
  );

  testWidgets('cancelled calibration keeps tracking off and allows mouse', (
    tester,
  ) async {
    final process = _Process();
    var calls = 0;
    final launcher = SidecarLauncher(
      launchProcess: (_) async {
        calls++;
        return process;
      },
    );
    final auth = await _openApp(tester, launcher);
    auth.change(AuthStatus.authenticated);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Calibrar y abrir tablero'));
    await tester.pumpAndSettle();
    expect(calls, 0);
    await tester.tap(find.text('Permitir cámara y calibrar'));
    await tester.pump();
    process.done.complete(1);
    await tester.pumpAndSettle();
    expect(
      find.text('No se completó la calibración. Reintenta o usa el mouse.'),
      findsOneWidget,
    );
    expect(find.byType(HomeScreen), findsNothing);
    await tester.tap(find.text('Usar solo mouse'));
    await tester.pumpAndSettle();
    expect(find.byType(HomeScreen), findsOneWidget);
    expect(calls, 1);
  });

  testWidgets('rejecting camera permission never starts the sidecar', (
    tester,
  ) async {
    var calls = 0;
    final launcher = SidecarLauncher(
      launchProcess: (_) async {
        calls++;
        return _Process();
      },
    );
    final auth = await _openApp(tester, launcher);
    auth.change(AuthStatus.authenticated);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Calibrar y abrir tablero'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ahora no'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Usar solo mouse'));
    await tester.pumpAndSettle();
    expect(find.byType(HomeScreen), findsOneWidget);
    expect(calls, 0);
  });
}
