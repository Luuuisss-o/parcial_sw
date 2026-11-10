// lib/screens/brand.dart
//
// Paleta "bosque y ámbar" (la misma del login web) y piezas visuales
// compartidas entre pantallas: el fondo de encabezado con cuadrícula y el
// logo. Colores sólidos, sin degradés.
import 'package:flutter/material.dart';

class BrandColors {
  static const brand = Color(0xFF0E3B36);
  static const brandText = Color(0xFFEEF6F2);
  static const brandMuted = Color(0xFFA8C9BF);
  static const mint = Color(0xFF6FE0C4);
  static const amber = Color(0xFFF4A940);
  static const amberInk = Color(0xFF1D1405);
  static const teal = Color(0xFF1F9C85);
  static const coral = Color(0xFFEF7A5A);
  static const cream = Color(0xFFF6F1E7);
  static const line = Color(0xFFE4DAC6);
  static const ink = Color(0xFF1C2A27);
  static const muted = Color(0xFF5B6B66);
}

/// Logo: cuadrado ámbar con sombra menta desplazada.
class BrandLogo extends StatelessWidget {
  const BrandLogo({super.key, this.size = 40});
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: BrandColors.amber,
        borderRadius: BorderRadius.circular(size * 0.28),
        boxShadow: const [BoxShadow(color: BrandColors.mint, offset: Offset(4, 4))],
      ),
      child: Icon(Icons.account_tree_outlined, color: BrandColors.amberInk, size: size * 0.55),
    );
  }
}

/// Fondo de encabezado: verde petróleo sólido con una cuadrícula tenue,
/// como el lienzo del editor.
class BrandGridPainter extends CustomPainter {
  const BrandGridPainter();

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = BrandColors.brand);
    final line = Paint()
      ..color = BrandColors.mint.withValues(alpha: 0.07)
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

/// Botón principal ámbar (el "Ingresar" del login).
ButtonStyle brandPrimaryButton() => FilledButton.styleFrom(
      backgroundColor: BrandColors.amber,
      foregroundColor: BrandColors.amberInk,
      disabledBackgroundColor: BrandColors.amber.withValues(alpha: 0.6),
      disabledForegroundColor: BrandColors.amberInk.withValues(alpha: 0.7),
      minimumSize: const Size.fromHeight(50),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
    );

/// Tarjeta blanca con franja de color arriba (formulario del login y
/// tarjetas de "¿Qué querés hacer?").
BoxDecoration brandCardDecoration() => BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(18),
      boxShadow: const [
        BoxShadow(color: Color(0x1A0E3B36), blurRadius: 20, offset: Offset(0, 8)),
      ],
    );

/// Encabezado de las pantallas internas: verde petróleo con cuadrícula,
/// botón de volver, título grande, subtítulo y acciones a la derecha.
class BrandPageHeader extends StatelessWidget {
  const BrandPageHeader({
    super.key,
    required this.title,
    this.subtitle,
    this.actions = const [],
  });

  final String title;
  final String? subtitle;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final top = MediaQuery.of(context).padding.top;
    final canPop = Navigator.of(context).canPop();
    return CustomPaint(
      painter: const BrandGridPainter(),
      child: Padding(
        padding: EdgeInsets.fromLTRB(14, top + 10, 14, 22),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              height: 44,
              child: Row(
                children: [
                  if (canPop)
                    BrandHeaderButton(
                      icon: Icons.arrow_back_rounded,
                      tooltip: 'Volver',
                      onPressed: () => Navigator.of(context).maybePop(),
                    ),
                  const Spacer(),
                  ...actions,
                ],
              ),
            ),
            const SizedBox(height: 10),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      color: BrandColors.brandText,
                      fontSize: 26,
                      height: 1.15,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.4,
                    ),
                  ),
                  if (subtitle != null) ...[
                    const SizedBox(height: 6),
                    Text(
                      subtitle!,
                      style: const TextStyle(color: BrandColors.brandMuted, fontSize: 14, height: 1.35),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Botón redondeado translúcido para el encabezado (volver, cerrar sesión).
class BrandHeaderButton extends StatelessWidget {
  const BrandHeaderButton({super.key, required this.icon, required this.tooltip, required this.onPressed});

  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      tooltip: tooltip,
      onPressed: onPressed,
      icon: Icon(icon, size: 22),
      style: IconButton.styleFrom(
        foregroundColor: BrandColors.brandText,
        backgroundColor: BrandColors.mint.withValues(alpha: 0.10),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: BrandColors.mint.withValues(alpha: 0.30)),
        ),
      ),
    );
  }
}

/// Aviso de error con el mismo estilo del login.
class BrandErrorBox extends StatelessWidget {
  const BrandErrorBox(this.message, {super.key});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFFDE8E6),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.warning_amber_rounded, size: 18, color: Color(0xFFD64545)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(message, style: const TextStyle(color: Color(0xFFB43636), fontSize: 13)),
          ),
        ],
      ),
    );
  }
}
