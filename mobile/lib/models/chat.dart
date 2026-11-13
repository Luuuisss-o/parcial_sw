// lib/models/chat.dart
//
// Espejo de backend/app/schemas/chat.py y backend/app/schemas/models.py
// (Fase 2: chat del equipo y modelo personalizado que corre en el celular).

class ChatMessage {
  final String id;
  final String diagramId;
  final String role; // USER | ASSISTANT | ERROR
  final int? authorId;
  final String authorName;
  final String? authorEmail;
  final String content;
  final bool asksAi;
  final String? replyToId;
  final String? addressedToName;
  final String? aiMode; // MENTOR | AUTO
  final String? aiModelLabel;
  final int actionsCount;
  final DateTime createdAt;
  final int seq;

  ChatMessage({
    required this.id,
    required this.diagramId,
    required this.role,
    required this.authorId,
    required this.authorName,
    required this.authorEmail,
    required this.content,
    required this.asksAi,
    required this.replyToId,
    required this.addressedToName,
    required this.aiMode,
    required this.aiModelLabel,
    required this.actionsCount,
    required this.createdAt,
    required this.seq,
  });

  bool get isAi => role != 'USER';

  factory ChatMessage.fromJson(Map<String, dynamic> j) => ChatMessage(
        id: j['id'] as String,
        diagramId: j['diagram_id'] as String,
        role: j['role'] as String,
        authorId: j['author_id'] as int?,
        authorName: j['author_name'] as String,
        authorEmail: j['author_email'] as String?,
        content: j['content'] as String,
        asksAi: j['asks_ai'] as bool? ?? false,
        replyToId: j['reply_to_id'] as String?,
        addressedToName: j['addressed_to_name'] as String?,
        aiMode: j['ai_mode'] as String?,
        aiModelLabel: j['ai_model_label'] as String?,
        actionsCount: (j['actions'] as List?)?.length ?? 0,
        createdAt: DateTime.parse(j['created_at'] as String).toLocal(),
        seq: j['seq'] as int,
      );
}

class ModelManifest {
  final bool available;
  final String? version;
  final String? sha256;
  final int? sizeBytes;
  final String? baseModel;
  final String? downloadPath;

  ModelManifest({
    required this.available,
    this.version,
    this.sha256,
    this.sizeBytes,
    this.baseModel,
    this.downloadPath,
  });

  factory ModelManifest.fromJson(Map<String, dynamic> j) => ModelManifest(
        available: j['available'] as bool? ?? false,
        version: j['version'] as String?,
        sha256: j['sha256'] as String?,
        sizeBytes: j['size_bytes'] as int?,
        baseModel: j['base_model'] as String?,
        downloadPath: j['download_path'] as String?,
      );
}
