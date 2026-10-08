import 'dart:ui' show AppExitResponse;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'config/app_version.dart';
import 'services/api_client.dart';
import 'services/auth_service.dart';
import 'services/gaze_bridge.dart';
import 'services/prediction_service.dart';
import 'services/sidecar_launcher.dart';
import 'services/telemetry_service.dart';
import 'services/token_store.dart';
import 'state/auth_controller.dart';
import 'state/session_controller.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // --- Capa de servicios (sin estado de UI) ---
  final tokens = TokenStore();
  final api = ApiClient(tokens);
  final authService = AuthService(api, tokens);
  final predictionService = PredictionService(api);
  final telemetryService = TelemetryService(api);

  // --- Sidecar de rastreo ocular (proceso Python): arranca tras el login ---
  final sidecar = SidecarLauncher();

  // --- Controladores de estado ---
  final authController = AuthController(authService);
  final sessionController = SessionController(
      predictionService, telemetryService,
      appVersion: appVersion);
  // Un sidecar por participante (cada uno con su calibración): se lanza al
  // iniciar sesión, se reinicia al cambiar de código y se apaga al salir.
  // La sesión del registro sigue el mismo ciclo.
  authController.addListener(() {
    final usuario = authController.status == AuthStatus.authenticated
        ? authController.user?.username
        : null;
    sidecar.seguirA(usuario);
    if (usuario != null) {
      sessionController.comenzar(usuario);
    } else {
      sessionController.terminar();
    }
  });
  authController.bootstrap();
  final gazeBridge = GazeBridge()..connect();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: authController),
        ChangeNotifierProvider.value(value: sessionController),
        ChangeNotifierProvider.value(value: gazeBridge),
      ],
      child: _SidecarLifecycle(
        sidecar: sidecar,
        session: sessionController,
        child: const InteractorGateApp(),
      ),
    ),
  );
}

/// Mata el sidecar cuando la app se cierra (en Windows los procesos hijo no se
/// terminan automáticamente al cerrar el padre). Cubre el cierre normal; los
/// cierres bruscos los cubren el Job Object de `windows/runner/main.cpp` y el
/// `--parent-pid` que vigila el propio sidecar.
class _SidecarLifecycle extends StatefulWidget {
  const _SidecarLifecycle({
    required this.sidecar,
    required this.session,
    required this.child,
  });

  final SidecarLauncher sidecar;
  final SessionController session;
  final Widget child;

  @override
  State<_SidecarLifecycle> createState() => _SidecarLifecycleState();
}

class _SidecarLifecycleState extends State<_SidecarLifecycle>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  // Al pulsar la X de la ventana: apagar el tracker antes de salir. En Windows
  // `detached` no siempre llega; esta es la vía fiable para un cierre normal.
  @override
  Future<AppExitResponse> didRequestAppExit() async {
    widget.sidecar.stop();
    // Cerrar la sesión del registro (session_end) sin retener la salida.
    await widget.session
        .terminar()
        .timeout(const Duration(seconds: 2), onTimeout: () {});
    return AppExitResponse.exit;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.detached) widget.sidecar.stop();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    widget.sidecar.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
