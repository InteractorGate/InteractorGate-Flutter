import 'dart:ui' show AppExitResponse;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'services/api_client.dart';
import 'services/auth_service.dart';
import 'services/gaze_bridge.dart';
import 'services/prediction_service.dart';
import 'services/sidecar_launcher.dart';
import 'services/speech_service.dart';
import 'services/telemetry_service.dart';
import 'services/token_store.dart';
import 'services/wav_player.dart';
import 'state/auth_controller.dart';
import 'state/session_controller.dart';
import 'state/speech_controller.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // --- Capa de servicios (sin estado de UI) ---
  final tokens = TokenStore();
  final api = ApiClient(tokens);
  final authService = AuthService(api, tokens);
  final predictionService = PredictionService(api);
  final telemetryService = TelemetryService(api);

  // La cámara se solicita después del login, desde la preparación del tablero.
  final sidecar = SidecarLauncher();

  // --- Controladores de estado ---
  final sessionController = SessionController(
    predictionService,
    telemetryService,
  );
  final authController = AuthController(authService, sessionController)
    ..bootstrap();
  final gazeBridge = GazeBridge()..connect();
  // Modo discurso con Azure AI Speech (token emitido por el backend).
  final speechController = SpeechController(
    AzureSpeechSynthesizer(api),
    WindowsWavPlayer(),
  );
  // Al cerrar sesión se corta la voz y se olvida el último mensaje.
  authController.addListener(() {
    if (authController.status != AuthStatus.authenticated) {
      speechController.reset();
    }
  });

  runApp(
    MultiProvider(
      providers: [
        Provider<SidecarLauncher>.value(value: sidecar),
        ChangeNotifierProvider.value(value: authController),
        ChangeNotifierProvider.value(value: sessionController),
        ChangeNotifierProvider.value(value: gazeBridge),
        ChangeNotifierProvider<SpeechController?>.value(value: speechController),
      ],
      child: _SidecarLifecycle(
        sidecar: sidecar,
        auth: authController,
        child: const InteractorGateApp(),
      ),
    ),
  );
}

/// Mata el sidecar cuando la app se cierra (en Windows los procesos hijo no se
/// terminan automáticamente al cerrar el padre).
class _SidecarLifecycle extends StatefulWidget {
  const _SidecarLifecycle({
    required this.sidecar,
    required this.auth,
    required this.child,
  });

  final SidecarLauncher sidecar;
  final AuthController auth;
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
    widget.auth.addListener(_onAuthChanged);
  }

  void _onAuthChanged() {
    if (widget.auth.status != AuthStatus.authenticated) widget.sidecar.stop();
  }

  @override
  Future<AppExitResponse> didRequestAppExit() async {
    if (!await widget.auth.logout()) return AppExitResponse.cancel;
    widget.sidecar.stop();
    return AppExitResponse.exit;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.detached) widget.sidecar.stop();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    widget.auth.removeListener(_onAuthChanged);
    widget.sidecar.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
