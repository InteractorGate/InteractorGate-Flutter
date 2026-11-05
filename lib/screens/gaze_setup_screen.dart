import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/sidecar_launcher.dart';
import '../state/auth_controller.dart';
import 'home_screen.dart';

class GazeSetupScreen extends StatefulWidget {
  const GazeSetupScreen({super.key});

  @override
  State<GazeSetupScreen> createState() => _GazeSetupScreenState();
}

class _GazeSetupScreenState extends State<GazeSetupScreen> {
  late final SidecarLauncher _sidecar;
  bool _calibrating = false;
  bool _ready = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _sidecar = context.read<SidecarLauncher>();
  }

  Future<void> _calibrate() async {
    setState(() {
      _calibrating = true;
      _error = null;
    });
    final calibrated = await _sidecar.calibrate();
    if (!mounted) return;
    setState(() {
      _calibrating = false;
      _ready = calibrated;
      if (!calibrated) {
        _error = 'No se completó la calibración. Reintenta o usa el mouse.';
      }
    });
    if (!calibrated) return;
    // El cursor no se mueve hasta haber renderizado el primer frame del tablero.
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      final started = await _sidecar.start();
      if (!mounted || started) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'No se pudo iniciar el seguimiento. Puedes usar el mouse.',
          ),
        ),
      );
    });
  }

  @override
  void dispose() {
    _sidecar.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_ready) return const HomeScreen();
    final auth = context.watch<AuthController>();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Preparar seguimiento ocular'),
        actions: [
          IconButton(
            tooltip: 'Cerrar sesión',
            onPressed: auth.busy ? null : () => auth.logout(),
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Sesión de ${auth.user?.username ?? ''}',
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 16),
                const Text(
                  'Colócate frente a la cámara. Al calibrar, sigue los puntos con la mirada. '
                  'El seguimiento comenzará cuando aparezca el tablero.',
                ),
                const SizedBox(height: 16),
                if (_error != null) Text(_error!),
                if (_calibrating) ...[
                  const LinearProgressIndicator(),
                  const SizedBox(height: 12),
                  const Text('Calibración en curso. ESC permite cancelarla.'),
                ],
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: _calibrating || auth.busy ? null : _calibrate,
                  child: const Text('Calibrar y abrir tablero'),
                ),
                TextButton(
                  onPressed: _calibrating || auth.busy
                      ? null
                      : () => setState(() => _ready = true),
                  child: const Text('Usar solo mouse'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
