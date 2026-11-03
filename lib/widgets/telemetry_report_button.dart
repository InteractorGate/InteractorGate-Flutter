import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

import '../state/session_controller.dart';

class TelemetryReportButton extends StatefulWidget {
  const TelemetryReportButton({
    super.key,
    required this.session,
    required this.participantCode,
  });
  final SessionController session;
  final String participantCode;

  @override
  State<TelemetryReportButton> createState() => _TelemetryReportButtonState();
}

class _TelemetryReportButtonState extends State<TelemetryReportButton> {
  bool _busy = false;

  Future<void> _export() async {
    setState(() => _busy = true);
    try {
      final report = await widget.session.sessionReport();
      final summary = report['summary'] as Map<String, dynamic>?;
      if (summary == null || summary['schema_version'] != 2) {
        throw StateError(
          'El backend todavía no ofrece la verificación del bloque 3.',
        );
      }
      final documents = await getApplicationDocumentsDirectory();
      final folder = Directory('${documents.path}/InteractorGate/E2');
      await folder.create(recursive: true);
      final stamp = DateTime.now().toUtc();
      final file = File(
        '${folder.path}/session_${report['session_id']}_${stamp.microsecondsSinceEpoch}.json',
      );
      await file.writeAsString(
        const JsonEncoder.withIndent('  ').convert({
          'export_version': 1,
          'exported_at': stamp.toIso8601String(),
          'participant_code': widget.participantCode,
          ...report,
        }),
        flush: true,
      );
      if (!mounted) return;
      final trials = summary['trials'] as List;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(
            summary['consistent'] == true
                ? 'Registros coherentes'
                : 'Registros con pendientes',
          ),
          content: SingleChildScrollView(
            child: SelectableText(
              '${report['count']} eventos recibidos y ${trials.length} ensayos.\n'
              '${trials.where((t) => t['consistent'] == true).length} ensayos con texto reconstruido coincidente.\n\n'
              'Archivo guardado:\n${file.path}\n\n'
              'Los ensayos abiertos o con huecos no se consideran completos.',
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cerrar'),
            ),
          ],
        ),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            error is StateError
                ? error.message
                : 'No se pudieron verificar o exportar los registros. Revisa la conexión y los eventos pendientes.',
          ),
        ),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => TextButton.icon(
    onPressed:
        _busy ||
            !widget.session.active ||
            widget.session.trialActive ||
            widget.session.studyBusy
        ? null
        : _export,
    icon: const Icon(Icons.fact_check_outlined),
    label: Text(_busy ? 'Verificando…' : 'Verificar y exportar sesión'),
  );
}
