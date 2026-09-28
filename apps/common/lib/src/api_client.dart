import 'package:http/http.dart' as http;

import 'auth_session.dart';

/// Request builders that carry the auth token, plus a send() that notices
/// rejections.
///
/// These exist so the token is attached in exactly one place. Both apps build
/// requests by hand (`http.Request` / `http.MultipartRequest` then `.send()`)
/// at seventeen call sites; without a shared constructor, adding auth would
/// mean seventeen chances to forget the header, and forgetting it fails as a
/// 401 at runtime rather than at compile time.
///
/// Call sites keep adding their own headers afterwards — `addAll` does not
/// drop the Authorization entry already placed here.

/// A GET/POST request to [url] with the auth header already applied.
http.Request apiRequest(String method, String url) {
  return http.Request(method, Uri.parse(url))
    ..headers.addAll(AuthSession.headers);
}

/// A multipart POST to [url] (form fields and file uploads) with the auth
/// header already applied.
///
/// Image uploads must go through this too. `/admin/detect` and `/cuisine/add`
/// are admin-only endpoints; a bare `http.MultipartRequest` reaches them
/// without a token and comes back 401, which the upload call sites report as
/// a generic failure.
http.MultipartRequest apiMultipart(String url) {
  return http.MultipartRequest('POST', Uri.parse(url))
    ..headers.addAll(AuthSession.headers);
}

/// Send a request built by [apiRequest] / [apiMultipart].
///
/// Use this instead of `request.send()`. The call sites all branch on
/// `statusCode == 200` with no else, so an expired token would otherwise be
/// indistinguishable from "nothing happened" — the screen just stays empty
/// and the user has no idea why. This surfaces it.
Future<http.StreamedResponse> sendApi(http.BaseRequest request) async {
  final response = await request.send();
  if (response.statusCode == 401 || response.statusCode == 403) {
    AuthSession.handleRejection(response.statusCode);
  }
  return response;
}
