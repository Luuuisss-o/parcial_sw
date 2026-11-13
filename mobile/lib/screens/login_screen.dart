// lib/screens/login_screen.dart
//
// Login con la paleta "bosque y ámbar" (la misma del login web): encabezado
// verde petróleo con cuadrícula tenue y formulario en tarjeta. Sin degradés.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../app_state.dart';
import 'brand.dart';
import 'mode_selector_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _nameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _password2Ctrl = TextEditingController();
  // false: iniciar sesión; true: crear una cuenta nueva.
  bool _signup = false;
  bool _loading = false;
  bool _showPwd = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (context.read<AppState>().auth.sessionExpired) {
      _error = 'Tu sesión venció. Iniciá sesión de nuevo.';
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    _password2Ctrl.dispose();
    super.dispose();
  }

  void _switchMode() {
    setState(() {
      _signup = !_signup;
      _error = null;
      _passwordCtrl.clear();
      _password2Ctrl.clear();
    });
  }

  Future<void> _submit() async {
    if (_signup) {
      if (_passwordCtrl.text.length < 8) {
        setState(() => _error = 'La contraseña tiene que tener al menos 8 caracteres.');
        return;
      }
      if (_passwordCtrl.text != _password2Ctrl.text) {
        setState(() => _error = 'Las contraseñas no coinciden.');
        return;
      }
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    final app = context.read<AppState>();
    try {
      if (_signup) {
        // Registrarse deja la sesión iniciada (el backend devuelve el token).
        await app.auth.signUp(_nameCtrl.text.trim(), _emailCtrl.text.trim(), _passwordCtrl.text);
      } else {
        await app.auth.signIn(_emailCtrl.text.trim(), _passwordCtrl.text);
      }
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const ModeSelectorScreen()),
      );
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    // Encabezado oscuro: íconos de la barra de estado en claro.
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light,
      child: Scaffold(
        backgroundColor: BrandColors.cream,
        body: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const _BrandHeader(),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 420),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          _signup ? 'Creá tu cuenta' : '¡Hola de nuevo!',
                          style: const TextStyle(
                            fontSize: 26,
                            fontWeight: FontWeight.w800,
                            color: BrandColors.ink,
                            letterSpacing: -0.3,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          _signup
                              ? 'Registrate para diseñar diagramas con tu equipo.'
                              : 'Iniciá sesión para seguir con tus diagramas.',
                          style: const TextStyle(fontSize: 14, color: BrandColors.muted),
                        ),
                        const SizedBox(height: 20),
                        _formCard(),
                        const SizedBox(height: 14),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(
                              _signup ? '¿Ya tenés una cuenta?' : '¿No tenés una cuenta?',
                              style: const TextStyle(color: BrandColors.muted),
                            ),
                            TextButton(
                              onPressed: _loading ? null : _switchMode,
                              style: TextButton.styleFrom(foregroundColor: BrandColors.teal),
                              child: Text(
                                _signup ? 'Iniciá sesión' : 'Creá una',
                                style: const TextStyle(fontWeight: FontWeight.w700),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  InputDecoration _decoration(String label, IconData icon, {Widget? suffix, String? hint}) {
    OutlineInputBorder border(Color c, [double w = 1]) => OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: c, width: w),
        );
    return InputDecoration(
      labelText: label,
      hintText: hint,
      prefixIcon: Icon(icon, size: 20),
      suffixIcon: suffix,
      filled: true,
      fillColor: BrandColors.cream,
      floatingLabelStyle: const TextStyle(color: BrandColors.teal, fontWeight: FontWeight.w600),
      prefixIconColor: BrandColors.muted,
      enabledBorder: border(BrandColors.line),
      focusedBorder: border(BrandColors.teal, 2),
      border: border(BrandColors.line),
    );
  }

  Widget _formCard() {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        boxShadow: const [
          BoxShadow(color: Color(0x1F0E3B36), blurRadius: 24, offset: Offset(0, 10)),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(height: 4, color: BrandColors.amber),
          Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_signup) ...[
                  TextField(
                    controller: _nameCtrl,
                    textCapitalization: TextCapitalization.words,
                    autofillHints: const [AutofillHints.name],
                    decoration: _decoration('Nombre', Icons.badge_outlined, hint: 'Tu nombre y apellido'),
                  ),
                  const SizedBox(height: 14),
                ],
                TextField(
                  controller: _emailCtrl,
                  keyboardType: TextInputType.emailAddress,
                  autofillHints: const [AutofillHints.email],
                  decoration: _decoration('Email', Icons.person_outline, hint: 'usuario@ejemplo.com'),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: _passwordCtrl,
                  obscureText: !_showPwd,
                  autofillHints: const [AutofillHints.password],
                  decoration: _decoration(
                    'Contraseña',
                    Icons.lock_outline,
                    suffix: IconButton(
                      tooltip: _showPwd ? 'Ocultar contraseña' : 'Mostrar contraseña',
                      icon: Icon(_showPwd ? Icons.visibility_off_outlined : Icons.visibility_outlined),
                      color: BrandColors.muted,
                      onPressed: () => setState(() => _showPwd = !_showPwd),
                    ),
                  ),
                  onSubmitted: (_) => _loading || _signup ? null : _submit(),
                ),
                if (_signup) ...[
                  const SizedBox(height: 14),
                  TextField(
                    controller: _password2Ctrl,
                    obscureText: !_showPwd,
                    decoration: _decoration('Repetí la contraseña', Icons.lock_outline),
                    onSubmitted: (_) => _loading ? null : _submit(),
                  ),
                ],
                const SizedBox(height: 18),
                if (_error != null) ...[
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFDE8E6),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.warning_amber_rounded, size: 18, color: Color(0xFFD64545)),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _error!,
                            style: const TextStyle(color: Color(0xFFB43636), fontSize: 13),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                ],
                SizedBox(
                  height: 50,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: BrandColors.amber,
                      foregroundColor: BrandColors.amberInk,
                      disabledBackgroundColor: BrandColors.amber.withValues(alpha: 0.6),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                    ),
                    onPressed: _loading ? null : _submit,
                    child: _loading
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2, color: BrandColors.amberInk),
                          )
                        : Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(_signup ? 'Crear cuenta' : 'Ingresar'),
                              const SizedBox(width: 6),
                              const Icon(Icons.arrow_forward_rounded, size: 20),
                            ],
                          ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _BrandHeader extends StatelessWidget {
  const _BrandHeader();

  @override
  Widget build(BuildContext context) {
    final top = MediaQuery.of(context).padding.top;
    return CustomPaint(
      painter: const BrandGridPainter(),
      child: Padding(
        padding: EdgeInsets.fromLTRB(22, top + 22, 22, 26),
        child: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                BrandLogo(),
                SizedBox(width: 12),
                Text(
                  'UML Collab',
                  style: TextStyle(
                    color: BrandColors.brandText,
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
            SizedBox(height: 22),
            Text.rich(
              TextSpan(
                children: [
                  TextSpan(text: 'Diseñá diagramas '),
                  TextSpan(text: 'en equipo', style: TextStyle(color: BrandColors.amber)),
                  TextSpan(text: ', en tiempo real.'),
                ],
              ),
              style: TextStyle(
                color: BrandColors.brandText,
                fontSize: 26,
                height: 1.15,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.4,
              ),
            ),
            SizedBox(height: 10),
            Text(
              'Editor colaborativo de diagramas de clases con un asesor de IA '
              'que revisa tu modelo y propone mejoras.',
              style: TextStyle(color: BrandColors.brandMuted, fontSize: 14, height: 1.4),
            ),
            SizedBox(height: 16),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _Chip(Icons.groups_outlined, 'Colaboración en vivo'),
                _Chip(Icons.auto_awesome_outlined, 'Asesor de IA'),
                _Chip(Icons.phone_android_outlined, 'IA en el celular'),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip(this.icon, this.label);
  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: BrandColors.mint.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: BrandColors.mint.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 15, color: BrandColors.mint),
          const SizedBox(width: 6),
          Text(
            label,
            style: const TextStyle(
              color: BrandColors.brandText,
              fontSize: 12.5,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}
