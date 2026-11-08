// lib/services/speech_service.dart
//
// Reconocimiento de voz offline con Vosk (modelo español chico, ~50MB).
// SpeechService de vosk_flutter_2 ya maneja el micrófono y el streaming de
// audio: acá solo se expone como Stream de texto reconocido para que la
// pantalla del asistente lo consuma con un StreamBuilder.

import 'dart:async';
import 'package:flutter/services.dart';
import 'package:vosk_flutter_2/vosk_flutter_2.dart';

class SpeechRecognitionService {
  final _vosk = VoskFlutterPlugin.instance();
  Model? _model;
  Recognizer? _recognizer;
  SpeechService? _speechService;
  bool _ready = false;
  // vosk_flutter_2 1.0.5 no expone un getter de estado en SpeechService
  // (no existe "recognitionStarted" ni equivalente) -- se lleva el estado
  // acá mismo, en base a las llamadas a start()/stop() que ya hacemos.
  bool _listening = false;
  StreamSubscription<String>? _partialSub;
  StreamSubscription<String>? _resultSub;

  bool get isReady => _ready;
  bool get isListening => _listening;

  /// Carga el modelo Vosk español desde una carpeta ya descargada en el
  /// dispositivo (ver ModelDownloader). Se llama una vez al abrir el
  /// asistente por primera vez en la sesión.
  Future<void> load(String modelPath) async {
    if (_ready) return;
    _model = await _vosk.createModel(modelPath);
    _recognizer = await _vosk.createRecognizer(model: _model!, sampleRate: 16000);
    try {
      _speechService = await _vosk.initSpeechService(_recognizer!);
    } on PlatformException catch (e) {
      // El plugin nativo guarda UNA instancia estática que sobrevive si
      // Android conserva el proceso pero recrea la parte Flutter (ej. salir
      // con "atrás" y volver a entrar): ahí Dart cree que no hay servicio y
      // el nativo responde "SpeechService instance already exist". Se
      // destruye la instancia vieja y se crea una nueva con este reconocedor.
      if (e.code != 'INITIALIZE_FAIL' || !(e.message ?? '').contains('already exist')) rethrow;
      await const MethodChannel('vosk_flutter').invokeMethod<void>('speechService.destroy');
      _speechService = await _vosk.initSpeechService(_recognizer!);
    }
    _ready = true;
  }

  /// Empieza a escuchar el micrófono. `onPartial` recibe texto parcial
  /// mientras la persona sigue hablando (para feedback visual en vivo);
  /// `onFinal` recibe la frase completa cuando detecta una pausa.
  Future<void> startListening({
    required void Function(String partialText) onPartial,
    required void Function(String finalText) onFinal,
  }) async {
    if (!_ready || _speechService == null) {
      throw StateError('El reconocimiento de voz todavía no está cargado.');
    }
    // Cancelar los oyentes del start() anterior: si no, cada vez que se
    // toca el micrófono se suma otro y una misma frase se procesa repetida.
    await _partialSub?.cancel();
    await _resultSub?.cancel();
    _partialSub = _speechService!.onPartial().listen((jsonStr) {
      final text = _extractText(jsonStr, key: 'partial');
      if (text.isNotEmpty) onPartial(text);
    });
    _resultSub = _speechService!.onResult().listen((jsonStr) {
      final text = _extractText(jsonStr, key: 'text');
      if (text.isNotEmpty) onFinal(text);
    });
    await _speechService!.start();
    _listening = true;
  }

  Future<void> stopListening() async {
    await _speechService?.stop();
    _listening = false;
  }

  Future<void> dispose() async {
    await _speechService?.stop();
    _listening = false;
    await _partialSub?.cancel();
    await _resultSub?.cancel();
    await _speechService?.dispose(); // destruye la instancia nativa
    _speechService = null;
    await _recognizer?.dispose();
    _model?.dispose(); // Model.dispose() es sincrono en vosk_flutter_2 1.0.5
    _ready = false;
  }

  /// Vosk devuelve JSON crudo tipo {"partial": "..."} o {"text": "..."}.
  /// A veces el valor es "nun" cuando no reconoció nada: se descarta.
  String _extractText(String jsonStr, {required String key}) {
    final match = RegExp('"$key"\\s*:\\s*"([^"]*)"').firstMatch(jsonStr);
    final text = match?.group(1)?.trim() ?? '';
    if (text.isEmpty || text == 'nun') return '';
    return text;
  }
}
