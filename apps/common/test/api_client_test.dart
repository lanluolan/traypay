import 'package:checkout_common/checkout_common.dart';
import 'package:flutter_test/flutter_test.dart';

/// The auth header is attached in one place ([apiRequest] / [apiMultipart])
/// precisely so it cannot be forgotten at one of the seventeen call sites.
/// These tests pin that down: a missing header does not fail to compile, it
/// fails at runtime as a 401 against a live server.
void main() {
  tearDown(() {
    AuthSession.end();
    AuthSession.onSessionExpired = null;
  });

  test('no header before login', () {
    expect(AuthSession.isAuthenticated, isFalse);
    expect(AuthSession.headers, isEmpty);
    final request = apiRequest('GET', 'http://example.test/user/query');
    expect(request.headers.containsKey('Authorization'), isFalse);
  });

  test('apiRequest carries the bearer token after login', () {
    AuthSession.begin('tok-123');
    final request = apiRequest('GET', 'http://example.test/user/query');
    expect(request.headers['Authorization'], 'Bearer tok-123');
    expect(request.method, 'GET');
    expect(request.url.path, '/user/query');
  });

  test('apiMultipart carries the bearer token too', () {
    // Image uploads hit admin-only endpoints; a bare http.MultipartRequest
    // reaches /admin/detect and /cuisine/add without a token and 401s.
    AuthSession.begin('tok-123');
    final request = apiMultipart('http://example.test/cuisine/add');
    expect(request.headers['Authorization'], 'Bearer tok-123');
    expect(request.method, 'POST');
  });

  test('call sites adding their own headers do not drop the token', () {
    // Every call site still does `request.headers.addAll({...})` after
    // construction. addAll merges, so this must survive.
    AuthSession.begin('tok-123');
    final request = apiRequest('GET', 'http://example.test/x')
      ..headers.addAll({'User-Agent': 'whatever'});
    expect(request.headers['Authorization'], 'Bearer tok-123');
    expect(request.headers['User-Agent'], 'whatever');
  });

  test('an empty or null token counts as logged out', () {
    // /user/login on an older backend returns no `token` field at all;
    // treating "" or null as authenticated would send `Bearer ` and get a
    // confusing 401 instead of an obvious "you are not logged in".
    AuthSession.begin(null);
    expect(AuthSession.isAuthenticated, isFalse);
    AuthSession.begin('');
    expect(AuthSession.isAuthenticated, isFalse);
  });

  test('end() clears the token', () {
    AuthSession.begin('tok-123');
    AuthSession.end();
    expect(AuthSession.isAuthenticated, isFalse);
    expect(apiRequest('GET', 'http://example.test/x').headers, isEmpty);
  });

  test('a 401 clears the session and fires the expiry hook', () {
    // Without the hook the user is stranded on a screen that can never load
    // data again and has to kill the app.
    var fired = 0;
    AuthSession.onSessionExpired = () => fired++;
    AuthSession.begin('tok-123');

    AuthSession.handleRejection(401);

    expect(AuthSession.isAuthenticated, isFalse);
    expect(fired, 1);
  });

  test('a 403 keeps the session and does not fire the hook', () {
    // 403 is "this account may not do that" — logging in again changes
    // nothing, so bouncing to the login screen would be wrong.
    var fired = 0;
    AuthSession.onSessionExpired = () => fired++;
    AuthSession.begin('tok-123');

    AuthSession.handleRejection(403);

    expect(AuthSession.isAuthenticated, isTrue);
    expect(fired, 0);
  });
}
