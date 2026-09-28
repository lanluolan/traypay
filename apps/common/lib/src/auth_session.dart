import 'package:fluttertoast/fluttertoast.dart';

/// The bearer token for whoever is logged in, for the life of the process.
///
/// Deliberately not persisted. Both apps open on their login screen, so a
/// token that outlived the process would never be read — adding
/// shared_preferences would buy an async startup path and a credential
/// sitting on disk, for nothing. Add persistence together with auto-login,
/// not before.
///
/// The backend issues one token per account kind: the customer app holds a
/// `user` token, the canteen app an `admin` one. Which endpoints each may
/// reach is decided server-side (see backend/README.md), so there is nothing
/// to branch on here.
class AuthSession {
  AuthSession._();

  static String? _token;

  static String? get token => _token;

  static bool get isAuthenticated => _token != null;

  /// Called when a 401 clears the session, so the app can navigate back to
  /// its login screen. Set once at startup by each app's `main()`.
  ///
  /// Navigation needs a `BuildContext` and [sendApi] is a context-free
  /// helper, so the hook is the seam between them. Without it the user is
  /// left on a screen that will never load data again and can only fix it
  /// by killing the app (ISSUES.md A2).
  static void Function()? onSessionExpired;

  /// Store the `token` field returned by /user/login, /user/register or
  /// /admin/login. Every later request carries it.
  static void begin(String? token) {
    _token = (token != null && token.isNotEmpty) ? token : null;
  }

  static void end() {
    _token = null;
  }

  /// The header protected endpoints require. Empty before login, which makes
  /// the request fail with 401 rather than silently look like a valid
  /// anonymous call.
  static Map<String, String> get headers =>
      _token == null ? const {} : {'Authorization': 'Bearer $_token'};

  /// Called by [sendApi] when the backend rejects a request.
  ///
  /// 401 and 403 mean different things and must not be merged: 401 is "your
  /// token is missing or no longer valid", which the user fixes by logging in
  /// again; 403 is "this account is not allowed to do that", which logging in
  /// again will not change.
  static void handleRejection(int statusCode) {
    if (statusCode == 401) {
      end();
      _toast('登录已失效，请重新登录');
      onSessionExpired?.call();
    } else if (statusCode == 403) {
      _toast('没有权限执行该操作');
    }
  }

  static void _toast(String message) {
    Fluttertoast.showToast(
      msg: message,
      toastLength: Toast.LENGTH_SHORT,
      gravity: ToastGravity.BOTTOM,
    );
  }
}
