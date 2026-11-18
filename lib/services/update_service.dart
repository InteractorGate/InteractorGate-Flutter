import 'dart:convert';
import 'dart:ffi';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:ffi/ffi.dart';
import 'package:http/http.dart' as http;
import 'package:win32/win32.dart';

/// Versión de esta compilación (`x.y.z+n`), inyectada por el CI con
/// `--dart-define=IG_APP_VERSION=...`. En compilaciones de desarrollo está
/// vacía y la búsqueda de actualizaciones se desactiva.
const appVersion = String.fromEnvironment('IG_APP_VERSION');

/// Manifiesto público de la página de descarga.
const updateManifestUrl =
    'https://interactorgate.github.io/descargas/release-manifest.json';

/// Solo se aceptan instaladores publicados en las releases de `descargas`.
const _allowedInstallerPrefix =
    'https://github.com/InteractorGate/descargas/releases/download/';

class UpdateInfo {
  const UpdateInfo({
    required this.version,
    required this.url,
    required this.bytes,
    required this.sha256,
  });

  final String version;
  final Uri url;
  final int bytes;
  final String sha256;

  /// Versión sin el número de compilación, para mostrar al usuario.
  String get displayVersion => version.split('+').first;
}

class UpdateException implements Exception {
  const UpdateException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// Compara `x.y.z+n`. Devuelve null si alguna no tiene ese formato.
int? compareVersions(String a, String b) {
  List<int>? parse(String v) {
    final m = RegExp(r'^(\d+)\.(\d+)\.(\d+)\+(\d+)$').firstMatch(v.trim());
    if (m == null) return null;
    return [for (var i = 1; i <= 4; i++) int.parse(m.group(i)!)];
  }

  final x = parse(a), y = parse(b);
  if (x == null || y == null) return null;
  for (var i = 0; i < 4; i++) {
    if (x[i] != y[i]) return x[i].compareTo(y[i]);
  }
  return 0;
}

/// Lee el manifiesto. Devuelve null si no es una versión más nueva válida.
UpdateInfo? parseManifest(Map<String, dynamic> json, String current) {
  final version = json['version'];
  final installer = json['installer'];
  if (version is! String || installer is! Map) return null;
  final url = installer['url'], bytes = installer['bytes'];
  final sha = installer['sha256'];
  if (url is! String ||
      !url.startsWith(_allowedInstallerPrefix) ||
      bytes is! int ||
      bytes <= 0 ||
      sha is! String ||
      !RegExp(r'^[0-9a-f]{64}$').hasMatch(sha)) {
    return null;
  }
  final order = compareVersions(version, current);
  if (order == null || order <= 0) return null;
  return UpdateInfo(
    version: version,
    url: Uri.parse(url),
    bytes: bytes,
    sha256: sha,
  );
}

class UpdateService {
  UpdateService({http.Client? client, this.currentVersion = appVersion})
    : _client = client ?? http.Client();

  final http.Client _client;
  final String currentVersion;

  bool get enabled => currentVersion.isNotEmpty && Platform.isWindows;

  /// Busca una versión más nueva. Cualquier fallo (sin red, manifiesto
  /// inválido) devuelve null para no molestar al usuario.
  Future<UpdateInfo?> check() async {
    if (!enabled) return null;
    try {
      final res = await _client
          .get(Uri.parse(updateManifestUrl))
          .timeout(const Duration(seconds: 15));
      if (res.statusCode != 200) return null;
      final json = jsonDecode(utf8.decode(res.bodyBytes));
      if (json is! Map<String, dynamic>) return null;
      return parseManifest(json, currentVersion);
    } catch (_) {
      return null;
    }
  }

  /// Descarga el instalador y comprueba tamaño y SHA-256 antes de devolverlo.
  Future<File> download(
    UpdateInfo info, {
    void Function(double progress)? onProgress,
    Directory? into,
  }) async {
    final dir = into ?? Directory('${Directory.systemTemp.path}\\InteractorGate-update');
    await dir.create(recursive: true);
    // Instaladores de actualizaciones anteriores ya no sirven.
    await for (final old in dir.list()) {
      if (old is File && old.path.endsWith('.exe')) {
        try {
          await old.delete();
        } catch (_) {
          /* En uso o bloqueado: se intentará la próxima vez. */
        }
      }
    }
    final file = File('${dir.path}\\InteractorGate-Setup-${info.displayVersion}.exe');
    final res = await _client.send(http.Request('GET', info.url));
    if (res.statusCode != 200) {
      throw UpdateException('No se pudo descargar la actualización (${res.statusCode}).');
    }
    final sink = file.openWrite();
    final hashSink = _DigestSink();
    final hasher = sha256.startChunkedConversion(hashSink);
    var received = 0;
    try {
      await for (final chunk in res.stream) {
        received += chunk.length;
        if (received > info.bytes) {
          throw const UpdateException('La descarga es más grande de lo esperado.');
        }
        sink.add(chunk);
        hasher.add(chunk);
        onProgress?.call(received / info.bytes);
      }
      await sink.close();
      hasher.close();
    } catch (_) {
      await sink.close();
      if (await file.exists()) await file.delete();
      rethrow;
    }
    if (received != info.bytes || hashSink.value.toString() != info.sha256) {
      await file.delete();
      throw const UpdateException(
        'La descarga no coincide con la versión publicada; no se instaló nada.',
      );
    }
    return file;
  }

  /// Ejecuta el instalador en modo silencioso con permisos de administrador
  /// (Windows muestra su aviso). Devuelve false si el usuario lo cancela.
  bool launchInstaller(File installer) {
    final verb = 'runas'.toNativeUtf16();
    final path = installer.path.toNativeUtf16();
    final params = '/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS'
        .toNativeUtf16();
    try {
      final result = ShellExecute(
        NULL,
        verb,
        path,
        params,
        nullptr,
        SW_SHOWNORMAL,
      );
      return result > 32;
    } finally {
      calloc.free(verb);
      calloc.free(path);
      calloc.free(params);
    }
  }
}

class _DigestSink implements Sink<Digest> {
  late Digest value;
  @override
  void add(Digest data) => value = data;
  @override
  void close() {}
}
