// lib/screens/historial_screen.dart
//
// Modo "Historial": chat con entrada de texto, historial conversacional y
// resultados en frases legibles -- sin micrófono (eso es el modo Alexa,
// ver alexa_screen.dart). Toda respuesta pasa por response_phrasing.dart:
// nunca se muestra JSON crudo como respuesta principal.

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import '../app_state.dart';
import '../services/local_llm_service.dart';
import '../uap/connection_manager.dart';
import '../uap/intent_parser.dart';
import '../uap/response_phrasing.dart';
import 'alexa_screen.dart';

const _uuid = Uuid();

enum _Role { user, assistant, error }

class _Message {
  final _Role role;
  final String text;
  _Message(this.role, this.text);
}

class HistorialScreen extends StatefulWidget {
  const HistorialScreen({super.key});

  @override
  State<HistorialScreen> createState() => _HistorialScreenState();
}

class _HistorialScreenState extends State<HistorialScreen> {
  final _controller = TextEditingController();
  final _messages = <_Message>[];
  final _scrollController = ScrollController();
  bool _busy = false;
  bool _llmReady = false;
  String _llmStatus = 'Cargando el modelo de lenguaje...';
  // Qué entidad/verbo/campos quedaron "a mitad de camino" tras la última
  // pregunta de aclaración -- así "crear" solo, como respuesta a "¿qué
  // querés hacer con bank?", no pierde el contexto de que se venía
  // hablando de bank. Se reinicia cada vez que se completa una operación
  // o se rechaza el pedido (ver ConversationContext en intent_parser.dart).
  ConversationContext _pendingContext = const ConversationContext();

  @override
  void initState() {
    super.initState();
    _prepareLlm();
  }

  /// Carga el LLM local antes de permitir mandar mensajes -- sin esto,
  /// cada resolveUapCommand() tira StateError (atrapado en el catch de
  /// _send, así que no crashea, pero el LLM nunca participa: el parser
  /// queda resolviendo TODO solo con reglas de texto sobre lo escrito,
  /// sin la ayuda real del modelo para pedidos más naturales o ambiguos).
  Future<void> _prepareLlm() async {
    final app = context.read<AppState>();
    if (app.llm.isLoaded) {
      setState(() => _llmReady = true);
      return;
    }
    try {
      setState(() => _llmStatus = 'Preparando el modelo de lenguaje (puede tardar un momento)...');
      await app.downloader.ensureLlmModel(onProgress: (_) {});
      await app.llm.load(await app.downloader.llmModelPath());
      if (mounted) setState(() => _llmReady = true);
    } catch (e) {
      if (mounted) {
        setState(() {
          _llmStatus = 'No pude cargar el modelo de lenguaje ($e). Puedo seguir ayudando con pedidos simples.';
          _llmReady = true; // no bloquea el chat: el parser sigue funcionando sin el LLM
        });
      }
    }
  }

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _busy) return;
    _controller.clear();

    setState(() {
      _messages.add(_Message(_Role.user, text));
      _busy = true;
    });
    _scrollToEnd();

    final app = context.read<AppState>();
    final contract = app.contract;
    if (contract == null) {
      setState(() {
        _messages.add(_Message(_Role.error, 'Todavía no hay un contrato UAP descubierto. Conectate a un backend primero.'));
        _busy = false;
      });
      return;
    }

    try {
      LlmDraft? draft;
      try {
        final llmResponse = await app.llm.resolveUapCommand(
          userText: text,
          tools: contract.tools
              .map((t) => UapToolSummary(toolId: t.toolId, description: t.description, fieldNames: t.properties.keys.toList()))
              .toList(),
        );
        switch (llmResponse) {
          case ChatReply(:final text):
            // El LLM ya determinó que esto es charla, no una operación:
            // se muestra tal cual, sin pasar por el parser determinista
            // (que es solo para validar OPERACIONES contra el contrato).
            setState(() => _messages.add(_Message(_Role.assistant, text)));
            return;
          case ToolProposal(:final call):
            draft = LlmDraft(fields: call.arguments);
        }
      } catch (_) {
        // El LLM local puede fallar (modelo no cargado, respuesta no
        // parseable, etc): el parser determinista igual intenta resolver
        // la intención solo con el texto, sin depender del LLM.
        draft = null;
      }

      final parser = IntentParser(contract);
      final result = parser.parse(text, draft: draft, previous: _pendingContext);

      switch (result) {
        case ParsedInvocation(:final toolId, :final input):
          final tool = contract.toolsById[toolId]!;
          final entity = contract.manifest.entities.firstWhere((e) => e.key == tool.entityKey);
          final response = await app.uapClient!.invoke(toolId, input, clientRecordId: _uuid.v4());
          final phrase = phraseForResult(verb: tool.verb, entity: entity, result: response);
          setState(() {
            _messages.add(_Message(_Role.assistant, phrase));
            _pendingContext = const ConversationContext(); // operación completa: se limpia
          });
        case NeedsClarification(:final questionEs, :final context):
          setState(() {
            _messages.add(_Message(_Role.assistant, questionEs));
            _pendingContext = context; // se recuerda para el próximo mensaje
          });
        case Conversational(:final replyEs):
          setState(() => _messages.add(_Message(_Role.assistant, replyEs)));
        case Rejected(:final reasonEs):
          setState(() {
            _messages.add(_Message(_Role.error, 'No pude determinar una única acción: $reasonEs'));
            _pendingContext = const ConversationContext(); // se descarta, hubo un error real
          });
      }
    } catch (e) {
      setState(() => _messages.add(_Message(_Role.error, phraseForBackendRejected(e.toString()))));
    } finally {
      setState(() => _busy = false);
      _scrollToEnd();
    }
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final connection = context.watch<AppState>().connection;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Asistente'),
        actions: [
          IconButton(
            icon: const Icon(Icons.mic),
            tooltip: 'Modo Alexa (solo voz)',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const AlexaScreen())),
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(28),
          child: _ConnectionBanner(connection: connection),
        ),
      ),
      body: Column(
        children: [
          if (!_llmReady)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                  const SizedBox(width: 12),
                  Expanded(child: Text(_llmStatus, style: Theme.of(context).textTheme.bodySmall)),
                ],
              ),
            ),
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.all(12),
              itemCount: _messages.length,
              itemBuilder: (context, i) => _MessageBubble(message: _messages[i]),
            ),
          ),
          if (_busy) const LinearProgressIndicator(),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      decoration: const InputDecoration(hintText: 'Escribí un pedido...', border: OutlineInputBorder()),
                      onSubmitted: (_) => _send(),
                    ),
                  ),
                  IconButton(icon: const Icon(Icons.send), onPressed: _busy ? null : _send),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  final _Message message;
  const _MessageBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == _Role.user;
    final isError = message.role == _Role.error;
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.all(12),
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
        decoration: BoxDecoration(
          color: isError
              ? Theme.of(context).colorScheme.errorContainer
              : (isUser ? Theme.of(context).colorScheme.primaryContainer : Theme.of(context).colorScheme.surfaceContainerHighest),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Text(message.text),
      ),
    );
  }
}

class _ConnectionBanner extends StatelessWidget {
  final ConnectionManager? connection;
  const _ConnectionBanner({required this.connection});

  @override
  Widget build(BuildContext context) {
    // ListenableBuilder escucha al ConnectionManager DIRECTAMENTE, no vía
    // context.watch<AppState>(): el ConnectionManager es su propio
    // ChangeNotifier (necesita notificar cambios de estado seguido,
    // mientras sincroniza), y notifyListeners() ahí adentro no dispara un
    // rebuild de nada que solo esté escuchando AppState -- sin esto, el
    // banner quedaba "pegado" en el estado inicial hasta que algo MÁS
    // (como enviar un mensaje) forzaba un rebuild por otro motivo.
    if (connection == null) {
      return const _ConnectionBannerLabel(state: null);
    }
    return ListenableBuilder(
      listenable: connection!,
      builder: (context, _) => _ConnectionBannerLabel(state: connection!.state),
    );
  }
}

class _ConnectionBannerLabel extends StatelessWidget {
  final UapConnectionState? state;
  const _ConnectionBannerLabel({required this.state});

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (state) {
      UapConnectionState.conectado => ('Conectado', Colors.green),
      UapConnectionState.sincronizando => ('Sincronizando...', Colors.blue),
      UapConnectionState.pendiente => ('Pendiente de sincronización', Colors.orange),
      UapConnectionState.desconectado => ('Sin conexión — usando datos locales', Colors.grey),
      UapConnectionState.conflicto => ('Conflicto con el servidor', Colors.red),
      UapConnectionState.fallido => ('No se pudo sincronizar', Colors.red),
      UapConnectionState.usandoDatosLocales => ('Usando datos locales', Colors.grey),
      null => ('Sin conexión configurada', Colors.grey),
    };
    return Container(
      width: double.infinity,
      color: color.withValues(alpha: 0.15),
      padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 12),
      child: Text(label, style: TextStyle(color: color, fontSize: 12)),
    );
  }
}
