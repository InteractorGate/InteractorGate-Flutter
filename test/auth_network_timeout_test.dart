import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:interactor_gate/services/api_client.dart';
import 'package:interactor_gate/services/auth_service.dart';
import 'package:interactor_gate/services/token_store.dart';

class _Tokens extends TokenStore {
  String? accessValue;
  @override
  Future<String?> get access async => accessValue;
  @override
  Future<void> save({required String access, required String refresh}) async {
    accessValue = access;
  }
}

void main() {
  testWidgets(
    'authentication survives SQL connection latency above 15 seconds',
    (tester) async {
      final tokens = _Tokens();
      String? authorization;
      final client = MockClient((request) async {
        await Future<void>.delayed(const Duration(seconds: 20));
        if (request.url.path.endsWith('login/')) {
          return http.Response(
            jsonEncode({'access': 'test-access', 'refresh': 'test-refresh'}),
            200,
          );
        }
        authorization = request.headers['Authorization'];
        return http.Response(
          jsonEncode({
            'id': 1,
            'username': 'P01',
            'email': 'study@example.com',
          }),
          200,
        );
      });
      final auth = AuthService(ApiClient(tokens, client: client), tokens);
      var completed = false;
      final login = auth
          .login('P01', 'test-only')
          .then((_) => completed = true);
      await tester.pump();
      await tester.pump(const Duration(seconds: 16));
      expect(completed, isFalse);
      await tester.pump(const Duration(seconds: 5));
      await login;
      expect(tokens.accessValue, 'test-access');
      final profile = auth.me();
      await tester.pump();
      await tester.pump(const Duration(seconds: 21));
      expect((await profile).username, 'P01');
      expect(authorization, 'Bearer test-access');
      client.close();
    },
  );

  testWidgets('telemetry keeps its original 15-second timeout', (tester) async {
    final client = MockClient((_) async {
      await Future<void>.delayed(const Duration(seconds: 20));
      return http.Response('{}', 200);
    });
    final api = ApiClient(_Tokens(), client: client);
    Object? failure;
    final request = api
        .postJson('/api/logs/', {}, auth: false)
        .then<void>(
          (_) {},
          onError: (Object e) {
            failure = e;
          },
        );
    await tester.pump();
    await tester.pump(const Duration(seconds: 16));
    await request;
    expect(failure, isA<TimeoutException>());
    await tester.pump(const Duration(seconds: 5));
    client.close();
  });

  testWidgets('authentication still fails after its bounded 75-second wait', (
    tester,
  ) async {
    final response = Completer<http.Response>();
    final client = MockClient((_) => response.future);
    final tokens = _Tokens();
    final auth = AuthService(ApiClient(tokens, client: client), tokens);
    Object? failure;
    final request = auth
        .login('P01', 'test-only')
        .then<void>(
          (_) {},
          onError: (Object e) {
            failure = e;
          },
        );
    await tester.pump();
    await tester.pump(const Duration(seconds: 76));
    await request;
    expect(failure, isA<TimeoutException>());
    expect(tokens.accessValue, isNull);
    response.complete(http.Response('{}', 503));
    await tester.pump();
    client.close();
  });
}
