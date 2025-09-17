import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config.dart';

class ApiClient {
  final String base = AppConfig.apiBaseUrl;

  Future<dynamic> getAny(String path, {Map<String, String>? query}) async {
    final uri = Uri.parse('$base$path').replace(queryParameters: query);
    final r = await http.get(uri);
    if (r.statusCode >= 400) {
      throw Exception('GET $path failed: ${r.statusCode} ${r.body}');
    }
    return json.decode(r.body);
  }

  Future<Map<String, dynamic>> postJson(String path, Map<String, dynamic> body) async {
    final uri = Uri.parse('$base$path');
    final r = await http.post(uri, headers: {'Content-Type': 'application/json'}, body: json.encode(body));
    if (r.statusCode >= 400) {
      throw Exception('POST $path failed: ${r.statusCode} ${r.body}');
    }
    return json.decode(r.body) as Map<String, dynamic>;
  }
}
