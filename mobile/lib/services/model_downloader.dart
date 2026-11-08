// lib/services/model_downloader.dart
//
// El modelo Vosk español (~50MB) se descarga en runtime (no justifica
// inflar el APK). El modelo del LLM (Gemma 3 1B, GGUF Q4_K_M, ~1GB) es
// distinto: va EMPAQUETADO dentro del APK como asset
// (assets/models/assistant.gguf, ver pubspec.yaml), porque es la pieza
// fija del sistema y no depende de qué backend UAP se use después --
// ensureLlmModel() lo copia de ahí al almacenamiento privado de la app en
// el primer arranque (llamadart necesita una ruta de archivo real en
// disco, no puede leer directo desde el bundle de assets de Flutter).

import 'dart:async';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:archive/archive_io.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/chat.dart';
import 'api_client.dart';

class ModelDownloader {
  static const llmModelFileName = 'assistant.gguf';
  static const _llmAssetPath = 'assets/models/assistant.gguf';

  // Modelo Vosk español chico (~50MB), del catálogo oficial alphacephei.
  static const voskModelUrl = 'https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip';
  static const voskModelDirName = 'vosk-model-small-es-0.42';

  Future<Directory> _modelsDir() async {
    final base = await getApplicationSupportDirectory();
    final dir = Directory('${base.path}/models');
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  Future<String> llmModelPath() async => '${(await _modelsDir()).path}/$llmModelFileName';
  Future<String> voskModelPath() async => '${(await _modelsDir()).path}/$voskModelDirName';

  Future<bool> isLlmDownloaded() async => File(await llmModelPath()).exists();
  Future<bool> isVoskDownloaded() async => Directory(await voskModelPath()).exists();

  /// Copia el .gguf embebido en el APK al almacenamiento privado de la
  /// app, si todavía no está ahí. `onProgress` recibe 0.0..1.0 -- se
  /// reporta en pasos gruesos (no hay progreso real byte a byte al leer
  /// un asset, a diferencia de una descarga HTTP) porque rootBundle no
  /// expone un stream de progreso.
  Future<void> ensureLlmModel({required void Function(double progress) onProgress}) async {
    if (await isLlmDownloaded()) {
      onProgress(1.0);
      return;
    }
    final path = await llmModelPath();
    final tmpFile = File('$path.part');
    onProgress(0.05);
    try {
      // ByteData completo en memoria: el asset ya vive comprimido dentro
      // del APK, así que esto no es peor que lo que Android ya hace al
      // instalar la app -- pero es un pico real de RAM (~1GB) a vigilar
      // en dispositivos con poca memoria (ver README, limitación conocida).
      final data = await rootBundle.load(_llmAssetPath);
      onProgress(0.5);
      await tmpFile.writeAsBytes(data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes));
      await tmpFile.rename(path);
      onProgress(1.0);
    } catch (e) {
      if (await tmpFile.exists()) await tmpFile.delete();
      throw Exception(
        'No encontré el modelo del asistente ($_llmAssetPath). '
        'Hace falta descargarlo y compilar el APK con él incluido -- ver mobile/README.md.',
      );
    }
  }

  /// Descarga y descomprime el modelo Vosk (viene como .zip).
  Future<void> downloadVosk({required void Function(double progress) onProgress}) async {
    final modelsDir = await _modelsDir();
    final zipPath = '${modelsDir.path}/$voskModelDirName.zip';

    final request = http.Request('GET', Uri.parse(voskModelUrl));
    final response = await http.Client().send(request);
    if (response.statusCode != 200) {
      throw Exception('No se pudo descargar el modelo de voz (HTTP ${response.statusCode})');
    }

    final total = response.contentLength ?? 0;
    var received = 0;
    final sink = File(zipPath).openWrite();
    await for (final chunk in response.stream) {
      sink.add(chunk);
      received += chunk.length;
      if (total > 0) onProgress(received / total * 0.8); // 80% descarga, 20% descompresión
    }
    await sink.close();

    final bytes = await File(zipPath).readAsBytes();
    final archive = ZipDecoder().decodeBytes(bytes);
    for (final entry in archive) {
      final outPath = '${modelsDir.path}/${entry.name}';
      if (entry.isFile) {
        final outFile = File(outPath);
        await outFile.create(recursive: true);
        await outFile.writeAsBytes(entry.content as List<int>);
      } else {
        await Directory(outPath).create(recursive: true);
      }
    }
    onProgress(1.0);
    await File(zipPath).delete();
  }

  // ---------------------------------------------------------------
  // Modelo PERSONALIZADO alojado en el servidor (Fase 2)
  // ---------------------------------------------------------------
  // El modelo se entrena en Colab (training/finetune_colab.ipynb) y se
  // publica en el backend (PUT /models/assistant). El servidor solo lo
  // aloja: acá se descarga y después corre 100% en el teléfono. Si el
  // servidor no tiene ninguno, se usa el modelo base empaquetado en el APK.

  static const customModelFileName = 'assistant-custom.gguf';
  static const _prefVersion = 'custom_model_version';
  static const _prefSha = 'custom_model_sha256';

  Future<String> customModelPath() async => '${(await _modelsDir()).path}/$customModelFileName';

  /// Versión del modelo personalizado ya descargada y verificada (o null).
  Future<String?> installedCustomVersion() async {
    final prefs = await SharedPreferences.getInstance();
    final v = prefs.getString(_prefVersion);
    if (v == null || !await File(await customModelPath()).exists()) return null;
    return v;
  }

  /// Si el servidor tiene una versión distinta a la instalada, la descarga.
  /// Devuelve el manifiesto del servidor (o null si no hay modelo
  /// personalizado o no hay conexión: en ese caso se sigue con lo que haya).
  Future<ModelManifest?> syncCustomModel(
    ApiClient api, {
    required void Function(double progress) onProgress,
  }) async {
    final ModelManifest manifest;
    try {
      manifest = await api.assistantModelManifest();
    } catch (_) {
      return null; // sin red: offline-first, se usa el modelo ya instalado
    }
    if (!manifest.available || manifest.sha256 == null || manifest.downloadPath == null) return null;

    final prefs = await SharedPreferences.getInstance();
    final path = await customModelPath();
    if (prefs.getString(_prefSha) == manifest.sha256 && await File(path).exists()) {
      onProgress(1.0);
      return manifest;
    }

    final part = File('$path.part');
    var have = await part.exists() ? await part.length() : 0;
    final req = http.Request('GET', api.assistantModelUri(manifest.downloadPath!))
      ..headers.addAll(api.authHeaders);
    // Reanudación: si quedó una descarga cortada, se pide solo lo que falta.
    if (have > 0) req.headers['Range'] = 'bytes=$have-';
    final client = http.Client();
    try {
      final resp = await client.send(req);
      if (resp.statusCode == 200) {
        have = 0; // el servidor ignoró el Range: se empieza de cero
      } else if (resp.statusCode != 206) {
        throw Exception('No se pudo descargar el modelo personalizado (HTTP ${resp.statusCode})');
      }
      final total = manifest.sizeBytes ?? (have + (resp.contentLength ?? 0));
      final sink = part.openWrite(mode: have > 0 ? FileMode.append : FileMode.write);
      var received = have;
      await for (final chunk in resp.stream) {
        sink.add(chunk);
        received += chunk.length;
        if (total > 0) onProgress((received / total).clamp(0, 0.98).toDouble());
      }
      await sink.close();
    } finally {
      client.close();
    }

    // Integridad: el archivo tiene que coincidir con el SHA-256 publicado.
    final digest = await sha256.bind(part.openRead()).first;
    if (digest.toString() != manifest.sha256) {
      await part.delete();
      throw Exception('El modelo descargado está corrupto (SHA-256 no coincide). Reintentá.');
    }
    await part.rename(path);
    await prefs.setString(_prefVersion, manifest.version ?? '?');
    await prefs.setString(_prefSha, manifest.sha256!);
    onProgress(1.0);
    return manifest;
  }
}
