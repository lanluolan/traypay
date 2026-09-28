import 'dart:convert';
import 'package:checkout_common/checkout_common.dart';
import 'package:http/http.dart' as http;

class AdminApiException implements Exception {
  final String message;
  AdminApiException(this.message);
  @override
  String toString() => message;
}

Future<Map<String, dynamic>> adminJson(http.BaseRequest request) {
  return (() async {
    final response = await sendApi(request);
    final body = jsonDecode(await response.stream.bytesToString())
        as Map<String, dynamic>;
    if (response.statusCode != 200 || body['code'] != 0) {
      throw AdminApiException(body['message']?.toString() ?? '请求失败，请重试');
    }
    return body;
  })()
      .timeout(const Duration(seconds: 60));
}

Future<List<Map<String, dynamic>>> loadMenu() async {
  final rows = <Map<String, dynamic>>[];
  for (var page = 1;; page++) {
    final response =
        await sendApi(apiRequest('GET', '$apiBase/cuisine/query/all/$page'))
            .timeout(const Duration(seconds: 30));
    final body = jsonDecode(await response.stream
        .bytesToString()
        .timeout(const Duration(seconds: 30))) as Map<String, dynamic>;
    if (response.statusCode != 200) {
      throw AdminApiException(body['message']?.toString() ?? '菜品列表加载失败');
    }
    if (body['code'] == 1) break;
    if (body['code'] != 0) throw AdminApiException('菜品列表加载失败');
    final items = (body['cuisine'] as List).cast<Map<String, dynamic>>();
    rows.addAll(items);
    if (items.length < 10) break;
  }
  return rows;
}
