import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:interactor_gate/config/app_theme.dart';
import 'package:interactor_gate/services/update_service.dart';
import 'package:interactor_gate/widgets/update_banner.dart';

const _url =
    'https://github.com/InteractorGate/descargas/releases/download/v1.2.9/InteractorGate-Setup.exe';

Map<String, dynamic> manifest({
  String version = '1.2.9+14',
  String url = _url,
  int bytes = 4,
  String? sha,
}) => {
  'version': version,
  'installer': {
    'url': url,
    'bytes': bytes,
    'sha256': sha ?? sha256.convert([1, 2, 3, 4]).toString(),
  },
};

void main() {
  test('compareVersions ordena por x.y.z y número de compilación', () {
    expect(compareVersions('1.2.9+14', '1.2.8+13'), greaterThan(0));
    expect(compareVersions('1.2.8+13', '1.2.8+13'), 0);
    expect(compareVersions('1.10.0+1', '1.9.9+99'), greaterThan(0));
    expect(compareVersions('1.2.8+14', '1.2.8+13'), greaterThan(0));
    expect(compareVersions('1.2.8', '1.2.8+13'), isNull);
  });

  test('parseManifest acepta solo versiones nuevas publicadas en descargas', () {
    expect(parseManifest(manifest(), '1.2.8+13')!.displayVersion, '1.2.9');
    expect(parseManifest(manifest(), '1.2.9+14'), isNull);
    expect(parseManifest(manifest(), '1.3.0+15'), isNull);
    expect(
      parseManifest(manifest(url: 'https://evil.example/x.exe'), '1.2.8+13'),
      isNull,
    );
    expect(parseManifest(manifest(sha: 'abc'), '1.2.8+13'), isNull);
    expect(parseManifest(manifest(bytes: 0), '1.2.8+13'), isNull);
  });

  test('sin versión inyectada (desarrollo) no consulta nada', () async {
    var calls = 0;
    final service = UpdateService(
      client: MockClient((_) async {
        calls++;
        return http.Response('{}', 200);
      }),
      currentVersion: '',
    );
    expect(await service.check(), isNull);
    expect(calls, 0);
  });

  test('check devuelve null ante errores de red o manifiesto inválido', () async {
    for (final client in [
      MockClient((_) async => throw const SocketException('sin red')),
      MockClient((_) async => http.Response('no json', 200)),
      MockClient((_) async => http.Response('', 404)),
    ]) {
      final service = UpdateService(client: client, currentVersion: '1.2.8+13');
      expect(await service.check(), isNull);
    }
  });

  test('check encuentra la versión nueva', () async {
    final service = UpdateService(
      client: MockClient(
        (_) async => http.Response(jsonEncode(manifest()), 200),
      ),
      currentVersion: '1.2.8+13',
    );
    expect((await service.check())!.version, '1.2.9+14');
  }, testOn: 'windows');

  group('download', () {
    late Directory dir;
    setUp(() => dir = Directory.systemTemp.createTempSync('ig_update_test'));
    tearDown(() => dir.deleteSync(recursive: true));

    UpdateService serving(List<int> body) => UpdateService(
      client: MockClient.streaming(
        (_, _) async => http.StreamedResponse(Stream.value(body), 200),
      ),
      currentVersion: '1.2.8+13',
    );

    test('guarda el instalador si tamaño y SHA-256 coinciden', () async {
      final info = parseManifest(manifest(), '1.2.8+13')!;
      final progress = <double>[];
      final file = await serving([1, 2, 3, 4]).download(
        info,
        into: dir,
        onProgress: progress.add,
      );
      expect(file.readAsBytesSync(), [1, 2, 3, 4]);
      expect(progress.last, 1.0);
    });

    test('borra la descarga si el SHA-256 no coincide', () async {
      final info = parseManifest(manifest(), '1.2.8+13')!;
      await expectLater(
        serving([9, 9, 9, 9]).download(info, into: dir),
        throwsA(isA<UpdateException>()),
      );
      expect(dir.listSync(), isEmpty);
    });

    test('corta la descarga si es más grande de lo anunciado', () async {
      final info = parseManifest(manifest(), '1.2.8+13')!;
      await expectLater(
        serving([1, 2, 3, 4, 5]).download(info, into: dir),
        throwsA(isA<UpdateException>()),
      );
      expect(dir.listSync(), isEmpty);
    });
  });

  testWidgets('el aviso aparece solo con versión nueva y se puede posponer', (
    tester,
  ) async {
    final service = UpdateService(
      client: MockClient(
        (_) async => http.Response(jsonEncode(manifest()), 200),
      ),
      currentVersion: '1.2.8+13',
    );
    await tester.pumpWidget(
      // Con el tema real: sus botones de ancho completo rompían la fila.
      MaterialApp(
        theme: AppTheme.dark,
        home: Scaffold(body: UpdateBanner(service: service)),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('Hay una versión nueva (1.2.9)'), findsOneWidget);
    await tester.tap(find.text('Ahora no'));
    await tester.pump();
    expect(find.text('Hay una versión nueva (1.2.9)'), findsNothing);
  }, skip: !Platform.isWindows);
}
