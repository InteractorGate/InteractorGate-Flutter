import 'dart:io';

/// Lanza el sidecar de rastreo ocular (proceso Python) cuando un participante
/// inicia sesión y lo mata al cerrar sesión o la app. El sidecar corre en
/// "modo servicio": si ese participante no tiene calibración la ejecuta
/// primero, y luego entra en modo Mouse (el cursor del SO sigue la mirada, con
/// clic por parpadeo), lo que hace funcionar el tablero dwell.
///
/// La calibración es por participante: el código (P01...) va al sidecar en la
/// variable IG_USUARIO y cada uno tiene su propio archivo de calibración.
///
/// Resolución del ejecutable, en orden:
///   1. Variable de entorno `IG_SIDECAR_CMD` (ruta a un .exe) — para pruebas.
///   2. Build empaquetado: `<dir del .exe>\gaze\gaze_service.exe` (PyInstaller).
///   3. Desarrollo: `sidecar\.venv\Scripts\python.exe main.py --service`
///      relativo al directorio de trabajo actual.
class SidecarLauncher {
  Process? _proc;
  String? _usuario;
  Future<void> _cola = Future.value();

  bool get running => _proc != null;

  /// Alinea el sidecar con la sesión: lo arranca para [usuario], lo reinicia
  /// si cambia de participante y lo apaga con `null` (sin sesión). Antes del
  /// login el ratón queda normal para que el investigador escriba el código.
  void seguirA(String? usuario) {
    if (usuario == _usuario) return;
    _usuario = usuario;
    // En cola, para que dos cambios seguidos no lancen dos sidecars a la vez.
    _cola = _cola.then((_) async {
      stop();
      if (usuario != null) await start(usuario: usuario);
    });
  }

  Future<void> start({String? usuario}) async {
    if (!Platform.isWindows || _proc != null) return;
    final spec = _resolve();
    if (spec == null) {
      stderr.writeln('[sidecar] no se encontró el ejecutable del tracker.');
      return;
    }
    try {
      // --parent-pid: el sidecar se apaga solo si esta app muere sin avisar.
      _proc = await Process.start(
        spec.executable,
        [...spec.args, '--parent-pid', '$pid'],
        workingDirectory: spec.workingDir,
        environment: {if (usuario != null) 'IG_USUARIO': usuario},
      );
      // Drenar salida para que el proceso no se bloquee por buffers llenos.
      final proc = _proc!;
      proc.stdout.drain<void>();
      proc.stderr.drain<void>();
      // Solo si sigue siendo el actual: al cambiar de participante el viejo
      // termina después de lanzado el nuevo.
      proc.exitCode.then((_) {
        if (identical(_proc, proc)) _proc = null;
      });
    } catch (e) {
      stderr.writeln('[sidecar] no se pudo lanzar: $e');
      _proc = null;
    }
  }

  /// Mata el sidecar y sus hijos. En desarrollo el python.exe del venv es un
  /// lanzador que crea otro python.exe: matar solo al primero dejaba vivo al
  /// que mueve el cursor. `taskkill /T` recorre el árbol.
  void stop() {
    final proc = _proc;
    _proc = null;
    if (proc == null) return;
    try {
      Process.runSync('taskkill', ['/PID', '${proc.pid}', '/T', '/F']);
    } catch (_) {}
    proc.kill(ProcessSignal.sigkill);
  }

  _SidecarSpec? _resolve() {
    // 1) Override explícito por variable de entorno.
    final env = Platform.environment['IG_SIDECAR_CMD'];
    if (env != null && env.trim().isNotEmpty && File(env).existsSync()) {
      return _SidecarSpec(env, const ['--service'], File(env).parent.path);
    }

    // 2) Build empaquetado: sidecar junto al ejecutable de la app.
    final exeDir = File(Platform.resolvedExecutable).parent.path;
    final bundled = File('$exeDir\\gaze\\gaze_service.exe');
    if (bundled.existsSync()) {
      return _SidecarSpec(bundled.path, const ['--service'], bundled.parent.path);
    }

    // 3) Desarrollo: venv del sidecar relativo al cwd del proyecto.
    final cwd = Directory.current.path;
    final devPy = File('$cwd\\sidecar\\.venv\\Scripts\\python.exe');
    final devMain = File('$cwd\\sidecar\\main.py');
    if (devPy.existsSync() && devMain.existsSync()) {
      return _SidecarSpec(
        devPy.path,
        [devMain.path, '--service'],
        devMain.parent.path,
      );
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
