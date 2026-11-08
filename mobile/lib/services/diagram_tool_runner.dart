// lib/services/diagram_tool_runner.dart
//
// Ejecuta sobre el diagrama las acciones que propone el modelo LOCAL del
// celular. Cada acción se aplica con la API REST normal (ApiClient), así que
// el backend la valida y la difunde por WebSocket a todo el equipo igual
// que una edición manual -- el modelo nunca toca la base directamente.
//
// Lo usan el asistente offline (assistant_screen.dart) y el chat del equipo
// (team_chat_screen.dart). Entre acción y acción se vuelve a leer el
// diagrama, para que "creá Pago y agregale monto" funcione en una sola
// respuesta (la segunda acción necesita el id de la clase recién creada).

import 'package:collection/collection.dart';
import '../models/diagram.dart';
import 'api_client.dart';
import 'assistant_prompt.dart';

class ActionOutcome {
  final AssistantAction action;
  final bool ok;
  final String message;
  const ActionOutcome(this.action, this.ok, this.message);

  /// Mismo formato que guarda el backend en chat_message.actions.
  Map<String, dynamic> toJson() => {
        'tool': action.tool,
        'input': action.args,
        'result': {'ok': ok, 'message': message},
      };
}

/// "1" -> (1, 1); "0..*" -> (0, null); "1..*" -> (1, null); "*" -> (0, null).
/// null en el máximo significa "*" (muchos), igual que en el backend.
(int, int?) parseMultiplicity(String? raw) {
  final v = (raw ?? '1').trim();
  if (v == '*' || v.toLowerCase() == 'n') return (0, null);
  if (v.contains('..')) {
    final parts = v.split('..');
    final lo = int.tryParse(parts[0].trim()) ?? 0;
    final hiRaw = parts[1].trim();
    return (lo, (hiRaw == '*' || hiRaw.toLowerCase() == 'n') ? null : int.tryParse(hiRaw));
  }
  final n = int.tryParse(v) ?? 1;
  return (n, n);
}

class DiagramToolRunner {
  final ApiClient api;
  final String diagramId;
  DiagramToolRunner(this.api, this.diagramId);

  Future<List<ActionOutcome>> runAll(List<AssistantAction> actions) async {
    final out = <ActionOutcome>[];
    for (final a in actions) {
      try {
        final classes = await api.listClasses(diagramId);
        out.add(ActionOutcome(a, true, await _run(a, classes)));
      } on _NotFound catch (e) {
        out.add(ActionOutcome(a, false, e.message));
      } catch (e) {
        out.add(ActionOutcome(a, false, '$e'));
      }
    }
    return out;
  }

  UmlClass _cls(List<UmlClass> classes, Object? name) {
    final n = '${name ?? ''}'.trim().toLowerCase();
    final c = classes.firstWhereOrNull((c) => c.name.toLowerCase() == n);
    if (c == null) throw _NotFound('No existe la clase "$name".');
    return c;
  }

  Future<String> _run(AssistantAction a, List<UmlClass> classes) async {
    final args = a.args;
    switch (a.tool) {
      case 'create_class':
        final name = '${args['name']}'.trim();
        if (classes.any((c) => c.name.toLowerCase() == name.toLowerCase())) {
          return 'La clase "$name" ya existía.';
        }
        await api.createClass(diagramId, name);
        return 'Creé la clase "$name".';

      case 'rename_class':
        final cls = _cls(classes, args['class_name']);
        await api.updateClass(cls.id, {'name': '${args['new_name']}'});
        return 'Renombré "${cls.name}" a "${args['new_name']}".';

      case 'delete_class':
        final cls = _cls(classes, args['class_name']);
        await api.deleteClass(cls.id);
        return 'Eliminé la clase "${cls.name}".';

      case 'add_attribute':
        final cls = _cls(classes, args['class_name']);
        final name = '${args['name']}';
        final type = (args['type'] as String?) ?? 'String';
        await api.createAttribute(cls.id, name, type, required: args['required'] == true);
        return 'Agregué "$name: $type" a "${cls.name}".';

      case 'delete_attribute':
        final cls = _cls(classes, args['class_name']);
        final target = '${args['attribute_name'] ?? args['name']}'.toLowerCase();
        final attr = cls.attributes.firstWhereOrNull((x) => x.name.toLowerCase() == target);
        if (attr == null) throw _NotFound('"${cls.name}" no tiene el atributo "$target".');
        await api.deleteAttribute(attr.id);
        return 'Eliminé el atributo "${attr.name}" de "${cls.name}".';

      case 'add_method':
        final cls = _cls(classes, args['class_name']);
        final name = '${args['name']}';
        await api.createMethod(cls.id, name, returnType: (args['return_type'] as String?) ?? 'void');
        return 'Agregué el método "$name()" a "${cls.name}".';

      case 'delete_method':
        final cls = _cls(classes, args['class_name']);
        final target = '${args['method_name'] ?? args['name']}'.toLowerCase();
        final m = cls.methods.firstWhereOrNull((x) => x.name.toLowerCase() == target);
        if (m == null) throw _NotFound('"${cls.name}" no tiene el método "$target".');
        await api.deleteMethod(m.id);
        return 'Eliminé el método "${m.name}" de "${cls.name}".';

      case 'create_relation':
        final from = _cls(classes, args['from_class']);
        final to = _cls(classes, args['to_class']);
        final (srcMin, srcMax) = parseMultiplicity(args['src_multiplicity'] as String?);
        final (dstMin, dstMax) = parseMultiplicity(args['dst_multiplicity'] as String?);
        await api.createRelation(
          diagramId: diagramId,
          fromClass: from.id,
          toClass: to.id,
          type: relationTypeFromString((args['type'] as String?) ?? 'ASSOCIATION'),
          srcMultMin: srcMin,
          srcMultMax: srcMax,
          dstMultMin: dstMin,
          dstMultMax: dstMax,
        );
        return 'Relacioné "${from.name}" con "${to.name}".';

      case 'delete_relation':
        final from = _cls(classes, args['from_class']);
        final to = _cls(classes, args['to_class']);
        final rels = await api.listRelations(diagramId);
        final rel = rels.firstWhereOrNull((r) =>
            (r.fromClassId == from.id && r.toClassId == to.id) || (r.fromClassId == to.id && r.toClassId == from.id));
        if (rel == null) throw _NotFound('No hay relación entre "${from.name}" y "${to.name}".');
        await api.deleteRelation(rel.id);
        return 'Eliminé la relación entre "${from.name}" y "${to.name}".';

      default:
        throw _NotFound('No reconozco la acción "${a.tool}".');
    }
  }
}

class _NotFound implements Exception {
  final String message;
  _NotFound(this.message);
}
