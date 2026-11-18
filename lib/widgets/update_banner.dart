import 'dart:io';

import 'package:flutter/material.dart';

import '../services/update_service.dart';

/// Aviso de versión nueva. Solo se muestra antes de iniciar sesión, para no
/// interrumpir el tablero ni los ensayos del estudio. Nunca es obligatorio.
class UpdateBanner extends StatefulWidget {
  const UpdateBanner({super.key, this.service, this.onExit});

  final UpdateService? service;

  /// Cierra la app tras lanzar el instalador (en pruebas se reemplaza).
  final VoidCallback? onExit;

  @override
  State<UpdateBanner> createState() => _UpdateBannerState();
}

enum _Stage { idle, available, downloading, launching, error }

class _UpdateBannerState extends State<UpdateBanner> {
  // Se consulta una sola vez por ejecución de la app.
  static Future<UpdateInfo?>? _sharedCheck;

  late final UpdateService _service = widget.service ?? UpdateService();
  UpdateInfo? _info;
  _Stage _stage = _Stage.idle;
  double _progress = 0;
  String? _error;
  bool _dismissed = false;

  @override
  void initState() {
    super.initState();
    final check = widget.service != null
        ? _service.check()
        : (_sharedCheck ??= _service.check());
    check.then((info) {
      if (!mounted || info == null) return;
      setState(() {
        _info = info;
        _stage = _Stage.available;
      });
    });
  }

  Future<void> _update() async {
    final info = _info!;
    setState(() {
      _stage = _Stage.downloading;
      _progress = 0;
      _error = null;
    });
    try {
      final file = await _service.download(
        info,
        onProgress: (p) {
          if (mounted) setState(() => _progress = p);
        },
      );
      if (!mounted) return;
      setState(() => _stage = _Stage.launching);
      if (!_service.launchInstaller(file)) {
        setState(() {
          _stage = _Stage.error;
          _error = 'No se inició la instalación (permiso de Windows cancelado).';
        });
        return;
      }
      // El instalador cierra y vuelve a abrir la app actualizada.
      (widget.onExit ?? () => exit(0))();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _stage = _Stage.error;
        _error = e is UpdateException
            ? e.message
            : 'No se pudo descargar la actualización. Revisa la conexión.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final info = _info;
    if (info == null || _dismissed || _stage == _Stage.idle) {
      return const SizedBox.shrink();
    }
    final busy = _stage == _Stage.downloading || _stage == _Stage.launching;
    return Card(
      color: const Color(0xFF16324F),
      margin: const EdgeInsets.only(bottom: 24),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Hay una versión nueva (${info.displayVersion})',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 6),
            Text(switch (_stage) {
              _Stage.downloading =>
                'Descargando… ${(_progress * 100).clamp(0, 100).toStringAsFixed(0)} %',
              _Stage.launching =>
                'Instalando. Acepta el aviso de Windows; la app se cerrará y volverá a abrirse.',
              _Stage.error => _error ?? 'No se pudo actualizar.',
              _ => 'Se descarga, se verifica y se instala sola. '
                  'Windows pedirá un permiso de administrador.',
            }),
            if (_stage == _Stage.downloading) ...[
              const SizedBox(height: 8),
              LinearProgressIndicator(value: _progress),
            ],
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: busy ? null : () => setState(() => _dismissed = true),
                  child: const Text('Ahora no'),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: busy ? null : _update,
                  child: Text(_stage == _Stage.error ? 'Reintentar' : 'Actualizar'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
