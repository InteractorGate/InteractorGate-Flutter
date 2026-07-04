import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'services/api_client.dart';
import 'services/auth_service.dart';
import 'services/gaze_bridge.dart';
import 'services/prediction_service.dart';
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

  // --- Controladores de estado ---
  final authController = AuthController(authService)..bootstrap();
  final sessionController =
      SessionController(predictionService, telemetryService)..start();
  final gazeBridge = GazeBridge()..connect();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: authController),
        ChangeNotifierProvider.value(value: sessionController),
        ChangeNotifierProvider.value(value: gazeBridge),
      ],
      child: const InteractorGateApp(),
    ),
  );
}
