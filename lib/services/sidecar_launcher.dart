import 'dart:io';

/// Ejecuta la calibración y el seguimiento como procesos separados.
/// El seguimiento solo se solicita después de mostrar el tablero.
///
/// Resolución del ejecutable, en orden:
///   1. Variable de entorno `IG_SIDECAR_CMD` (ruta a un .exe) — para pruebas.
///   2. Build empaquetado: `<dir del .exe>\gaze\gaze_service.exe` (PyInstaller).
///   3. Desarrollo: `sidecar\.venv\Scripts\python.exe main.py <modo>`
///      relativo al directorio de trabajo actual.
class SidecarLauncher {
  SidecarLauncher({Future<Process?> Function(List<String>)? launchProcess})
    : _launchProcess = launchProcess ?? _spawn;

  final Future<Process?> Function(List<String>) _launchProcess;
  Process? _proc;
  bool _starting = false;
  int _generation = 0;

  bool get running => _proc != null;

  Future<bool> calibrate() => _launch(['--calibrate'], waitForExit: true);

  Future<bool> start() => _launch(['--track']);

  Future<bool> _launch(List<String> args, {bool waitForExit = false}) async {
    if (_starting || _proc != null) return false;
    _starting = true;
    final generation = _generation;
    try {
      final process = await _launchProcess(args);
      if (process == null) return false;
      if (generation != _generation) {
        process.kill(ProcessSignal.sigterm);
        return false;
      }
      _proc = process;
      // Drenar salida para que el proceso no se bloquee por buffers llenos.
      process.stdout.drain<void>();
      process.stderr.drain<void>();
      process.exitCode.then((_) {
        if (identical(_proc, process)) _proc = null;
      });
      if (!waitForExit) return true;
      final code = await process.exitCode;
      return generation == _generation && code == 0;
    } catch (e) {
      stderr.writeln('[sidecar] no se pudo lanzar: $e');
      return false;
    } finally {
      if (generation == _generation) _starting = false;
    }
  }

  void stop() {
    _generation++;
    _starting = false;
    _proc?.kill(ProcessSignal.sigterm);
    _proc = null;
  }

  static Future<Process?> _spawn(List<String> args) async {
    if (!Platform.isWindows) return null;
    final spec = _resolve(args);
    if (spec == null) {
      stderr.writeln('[sidecar] no se encontró el ejecutable del tracker.');
      return null;
    }
    return Process.start(
      spec.executable,
      spec.args,
      workingDirectory: spec.workingDir,
    );
  }

  static _SidecarSpec? _resolve(List<String> args) {
    // 1) Override explícito por variable de entorno.
    final env = Platform.environment['IG_SIDECAR_CMD'];
    if (env != null && env.trim().isNotEmpty && File(env).existsSync()) {
      return _SidecarSpec(env, args, File(env).parent.path);
    }

    // 2) Build empaquetado: sidecar junto al ejecutable de la app.
    final exeDir = File(Platform.resolvedExecutable).parent.path;
    final bundled = File('$exeDir\\gaze\\gaze_service.exe');
    if (bundled.existsSync()) {
      return _SidecarSpec(bundled.path, args, bundled.parent.path);
    }

    // 3) Desarrollo: venv del sidecar relativo al cwd del proyecto.
    final cwd = Directory.current.path;
    final devPy = File('$cwd\\sidecar\\.venv\\Scripts\\python.exe');
    final devMain = File('$cwd\\sidecar\\main.py');
    if (devPy.existsSync() && devMain.existsSync()) {
      return _SidecarSpec(devPy.path, [
        devMain.path,
        ...args,
      ], devMain.parent.path);
    }
    return null;
  }
}

class _SidecarSpec {
  const _SidecarSpec(this.executable, this.args, this.workingDir);
  final String executable;
  final List<String> args;
  final String workingDir;
}
