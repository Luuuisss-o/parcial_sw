// lib/voice/tts_service.dart
//
// Texto a voz nativo de Android (flutter_tts) para el modo Alexa. Usa las
// voces ya instaladas en el sistema operativo -- sin ningún servicio en la
// nube. Si el teléfono no tiene una voz en español instalada, se informa
// en vez de fallar en silencio (ver isSpanishVoiceAvailable): el modo
// Alexa sin voz sería inútil sin que el usuario entienda por qué no
// escucha nada.
//
// Solo lee en voz alta las respuestas del modo Alexa (ver
// AlexaScreen) -- el modo Historial siempre queda con el texto visible en
// pantalla independientemente de si TTS está disponible.

import 'package:flutter_tts/flutter_tts.dart';

class TtsService {
  final FlutterTts _tts = FlutterTts();
  bool? _spanishAvailable;

  /// Configura el motor una sola vez (idioma, velocidad) y detecta si hay
  /// una voz en español instalada. Se puede llamar varias veces sin
  /// problema -- flutter_tts no falla por reconfigurar.
  Future<void> init() async {
    await _tts.setLanguage('es-ES');
    await _tts.setSpeechRate(0.5);
    await _tts.setVolume(1.0);
    await _tts.setPitch(1.0);
    await _detectSpanishVoice();
  }

  /// true si el sistema tiene alguna voz cuyo locale empieza con "es"
  /// (España, Latinoamérica, cualquier variante) instalada. Si es false,
  /// la UI del modo Alexa debe avisarlo en vez de quedarse en silencio sin
  /// explicación.
  Future<bool> isSpanishVoiceAvailable() async {
    return _spanishAvailable ??= await _detectSpanishVoice();
  }

  Future<bool> _detectSpanishVoice() async {
    try {
      final languages = await _tts.getLanguages;
      final available = (languages as List?)?.any((l) => l.toString().toLowerCase().startsWith('es')) ?? false;
      _spanishAvailable = available;
      return available;
    } catch (_) {
      // Si el plugin no puede listar idiomas en este dispositivo, no se
      // asume que SÍ hay voz -- mejor avisar que no se pudo confirmar.
      _spanishAvailable = false;
      return false;
    }
  }

  Future<void> speak(String text) async {
    if (text.trim().isEmpty) return;
    await _tts.speak(text);
  }

  Future<void> stop() async {
    await _tts.stop();
  }

  Future<void> dispose() async {
    await _tts.stop();
  }
}
