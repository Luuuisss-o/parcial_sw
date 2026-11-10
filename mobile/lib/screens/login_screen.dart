// lib/screens/login_screen.dart
//
// Login con la paleta "bosque y ámbar" (la misma del login web): encabezado
// verde petróleo con cuadrícula tenue y formulario en tarjeta. Sin degradés.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../app_state.dart';
import 'mode_selector_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
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
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final app = context.read<AppState>();
    try {
      await app.auth.signIn(_emailCtrl.text.trim(), _passwordCtrl.text);
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
    return Scaffold(
      backgroundColor: _LoginColors.cream,
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
                      const Text(
                        '¡Hola de nuevo!',
                        style: TextStyle(
                          fontSize: 26,
                          fontWeight: FontWeight.w800,
                          color: _LoginColors.ink,
                          letterSpacing: -0.3,
                        ),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'Iniciá sesión para seguir con tus diagramas.',
                        style: TextStyle(fontSize: 14, color: _LoginColors.muted),
                      ),
                      const SizedBox(height: 20),
                      _formCard(),
                    ],
                  ),
                ),
              ),
            ),
          ],
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
      fillColor: _LoginColors.cream,
      floatingLabelStyle: const TextStyle(color: _LoginColors.teal, fontWeight: FontWeight.w600),
      prefixIconColor: _LoginColors.muted,
      enabledBorder: border(_LoginColors.line),
      focusedBorder: border(_LoginColors.teal, 2),
      border: border(_LoginColors.line),
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
          Container(height: 4, color: _LoginColors.amber),
          Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
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
                      color: _LoginColors.muted,
                      onPressed: () => setState(() => _showPwd = !_showPwd),
                    ),
                  ),
                  onSubmitted: (_) => _loading ? null : _submit(),
                ),
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
                      backgroundColor: _LoginColors.amber,
                      foregroundColor: _LoginColors.amberInk,
                      disabledBackgroundColor: _LoginColors.amber.withValues(alpha: 0.6),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                    ),
                    onPressed: _loading ? null : _submit,
                    child: _loading
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2, color: _LoginColors.amberInk),
                          )
                        : const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text('Ingresar'),
                              SizedBox(width: 6),
                              Icon(Icons.arrow_forward_rounded, size: 20),
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

/// Paleta "bosque y ámbar", la misma del login web.
class _LoginColors {
  static const brand = Color(0xFF0E3B36);
  static const brandText = Color(0xFFEEF6F2);
  static const brandMuted = Color(0xFFA8C9BF);
  static const mint = Color(0xFF6FE0C4);
  static const amber = Color(0xFFF4A940);
  static const amberInk = Color(0xFF1D1405);
  static const teal = Color(0xFF1F9C85);
  static const cream = Color(0xFFF6F1E7);
  static const line = Color(0xFFE4DAC6);
  static const ink = Color(0xFF1C2A27);
  static const muted = Color(0xFF5B6B66);
}

class _BrandHeader extends StatelessWidget {
  const _BrandHeader();

  @override
  Widget build(BuildContext context) {
    final top = MediaQuery.of(context).padding.top;
    return CustomPaint(
      painter: _GridPainter(),
      child: Padding(
        padding: EdgeInsets.fromLTRB(22, top + 22, 22, 26),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: _LoginColors.amber,
                    borderRadius: BorderRadius.circular(11),
                    boxShadow: const [BoxShadow(color: _LoginColors.mint, offset: Offset(4, 4))],
                  ),
                  child: const Icon(Icons.account_tree_outlined, color: _LoginColors.amberInk, size: 22),
                ),
                const SizedBox(width: 12),
                const Text(
                  'UML Collab',
                  style: TextStyle(
                    color: _LoginColors.brandText,
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 22),
            const Text.rich(
              TextSpan(
                children: [
                  TextSpan(text: 'Diseñá diagramas '),
                  TextSpan(text: 'en equipo', style: TextStyle(color: _LoginColors.amber)),
                  TextSpan(text: ', en tiempo real.'),
                ],
              ),
              style: TextStyle(
                color: _LoginColors.brandText,
                fontSize: 26,
                height: 1.15,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.4,
              ),
            ),
            const SizedBox(height: 10),
            const Text(
              'Editor colaborativo de diagramas de clases con un asesor de IA '
              'que revisa tu modelo y propone mejoras.',
              style: TextStyle(color: _LoginColors.brandMuted, fontSize: 14, height: 1.4),
            ),
            const SizedBox(height: 16),
            const Wrap(
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
        color: _LoginColors.mint.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: _LoginColors.mint.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 15, color: _LoginColors.mint),
          const SizedBox(width: 6),
          Text(
            label,
            style: const TextStyle(
              color: _LoginColors.brandText,
              fontSize: 12.5,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}

/// Fondo del encabezado: color sólido con una cuadrícula tenue, como el
/// lienzo del editor.
class _GridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = _LoginColors.brand);
    final line = Paint()
      ..color = _LoginColors.mint.withValues(alpha: 0.07)
      ..strokeWidth = 1;
    const step = 26.0;
    for (double x = 0; x < size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), line);
    }
    for (double y = 0; y < size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), line);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
