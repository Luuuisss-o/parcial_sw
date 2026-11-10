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
