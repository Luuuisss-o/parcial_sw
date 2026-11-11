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

  /// true cuando la sesión se cerró sola porque el backend rechazó el token;
  /// el login lo usa para avisar por qué se pide la contraseña otra vez.
  bool sessionExpired = false;

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
    await _storeToken(resp, email, 'No se pudo iniciar sesión');
  }

  /// Crea una cuenta nueva y deja la sesión iniciada (el backend devuelve
  /// el token, igual que al iniciar sesión).
  Future<void> signUp(String name, String email, String password) async {
    final resp = await http.post(
      Uri.parse('${AppConfig.apiBaseUrl}/auth/sign-up'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name, 'email': email, 'password': password}),
    );
    await _storeToken(resp, email.trim().toLowerCase(), 'No se pudo crear la cuenta');
  }

  Future<void> _storeToken(http.Response resp, String email, String fallbackError) async {
    // UTF-8 explícito: la respuesta no declara charset y con resp.body los
    // mensajes con tilde ("Credenciales inválidas") llegaban rotos.
    final body = utf8.decode(resp.bodyBytes);
    if (resp.statusCode != 200 && resp.statusCode != 201) {
      throw AuthException(_tryExtractDetail(body) ?? fallbackError);
    }
    final data = jsonDecode(body) as Map<String, dynamic>;
    _token = data['access_token'] as String;
    _email = email;
    sessionExpired = false;

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
