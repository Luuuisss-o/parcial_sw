// lib/services/auth_service.dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';

/// Sesión del usuario: guarda el JWT en SharedPreferences (persiste entre
/// aperturas de la app, igual que localStorage en la versión web) y lo
/// expone para que ApiClient lo adjunte en cada pedido.
class AuthService {
  static const _tokenKey = 'uml_access_token';
  static const _emailKey = 'uml_email';

  String? _token;
  String? _email;

  String? get token => _token;
  String? get email => _email;
  bool get isAuthenticated => _token != null && _token!.isNotEmpty;

  Future<void> loadFromDisk() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString(_tokenKey);
    _email = prefs.getString(_emailKey);
  }

  Future<void> signIn(String email, String password) async {
    final resp = await http.post(
      Uri.parse('${AppConfig.apiBaseUrl}/auth/sign-in'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (resp.statusCode != 200) {
      final detail = _tryExtractDetail(resp.body);
      throw AuthException(detail ?? 'No se pudo iniciar sesión');
    }
    final data = jsonDecode(resp.body) as Map<String, dynamic>;
    _token = data['access_token'] as String;
    _email = email;

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, _token!);
    await prefs.setString(_emailKey, _email!);
  }

  Future<void> signOut() async {
    _token = null;
    _email = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
    await prefs.remove(_emailKey);
  }

  String? _tryExtractDetail(String body) {
    try {
      final data = jsonDecode(body);
      if (data is Map && data['detail'] is String) return data['detail'] as String;
    } catch (_) {}
    return null;
  }
}

class AuthException implements Exception {
  final String message;
  AuthException(this.message);
  @override
  String toString() => message;
}
