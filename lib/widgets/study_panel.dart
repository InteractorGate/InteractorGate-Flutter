import 'package:flutter/material.dart';

import '../models/study_protocol.dart';
import '../state/session_controller.dart';

/// Controles del investigador, separados del tablero de composición.
class StudyPanel extends StatelessWidget {
  const StudyPanel({
    super.key,
    required this.session,
    required this.participantCode,
  });

  final SessionController session;
  final String participantCode;

  Future<void> _configure(BuildContext context) async {
    final setup = await showDialog<(int, StudyPhase)>(
      context: context,
      builder: (_) =>
          _StudySetupDialog(session: session, participantCode: participantCode),
    );
    if (setup != null) {
      await session.configureStudy(
        participantNumber: setup.$1,
        phase: setup.$2,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final plan = session.studyPlan;
    final entry = session.studyEntry;
    final busy = !session.active || session.studyBusy;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (session.studyError != null)
            Text(
              session.studyError!,
              style: const TextStyle(color: Colors.amber),
            ),
          if (plan == null)
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: busy ? null : () => _configure(context),
                icon: const Icon(Icons.science_outlined),
                label: const Text('Preparar estudio E2'),
              ),
            )
          else ...[
            const Text(
              'PILOTO · Frases provisionales',
              style: TextStyle(color: Colors.amber),
            ),
            Wrap(
              spacing: 16,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(plan.phase.label),
                Text(
                  entry == null
                      ? 'Sesión completada'
                      : 'Ensayo ${entry.order}/${plan.entries.length} · Bloque ${entry.block} · ${entry.condition.label}',
                ),
                TextButton(
                  onPressed: busy || session.trialActive
                      ? null
                      : () => _configure(context),
                  child: const Text('Cambiar sesión'),
                ),
                TextButton(
                  onPressed: busy || session.trialActive
                      ? null
                      : session.leaveStudy,
                  child: const Text('Volver al tablero libre'),
                ),
              ],
            ),
            if (entry != null) ...[
              Text(
                'Frase objetivo: ${entry.target.toUpperCase()}',
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 6),
              Wrap(
                spacing: 12,
                children: [
                  if (!session.trialActive)
                    FilledButton(
                      onPressed: busy ? null : () => session.startTrial(),
                      child: const Text('Iniciar ensayo'),
                    )
                  else ...[
                    FilledButton(
                      onPressed: busy ? null : () => session.finishTrial(),
                      child: const Text('Terminar mensaje'),
                    ),
                    OutlinedButton(
                      onPressed: busy
                          ? null
                          : () => session.finishTrial(interrupted: true),
                      child: const Text('Interrumpir ensayo'),
                    ),
                  ],
                ],
              ),
            ],
            if (session.studyBusy) const LinearProgressIndicator(),
          ],
        ],
      ),
    );
  }
}

class _StudySetupDialog extends StatefulWidget {
  const _StudySetupDialog({
    required this.session,
    required this.participantCode,
  });
  final SessionController session;
  final String participantCode;

  @override
  State<_StudySetupDialog> createState() => _StudySetupDialogState();
}

class _StudySetupDialogState extends State<_StudySetupDialog> {
  late final TextEditingController _number;
  StudyPhase _phase = StudyPhase.practice;
  String? _error;

  @override
  void initState() {
    super.initState();
    final suffix = RegExp(
      r'(\d+)$',
    ).firstMatch(widget.participantCode)?.group(1);
    final inferred = int.tryParse(suffix ?? '') ?? 1;
    final saved = widget.session.studyProgress;
    _number = TextEditingController(
      text:
          '${saved?.participantNumber ?? (inferred > 0 && inferred <= 999 ? inferred : 1)}',
    );
    _phase =
        widget.session.studyPlan?.phase ??
        (saved?.s2Completed == 20
            ? StudyPhase.s3
            : saved?.readyToMeasure == true
            ? StudyPhase.s2
            : StudyPhase.practice);
  }

  @override
  void dispose() {
    _number.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final progress = widget.session.studyProgress;
    return AlertDialog(
      title: const Text('Preparar estudio E2 · Piloto'),
      content: SizedBox(
        width: 440,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Banco provisional: revisar las listas antes del estudio real. Los números impares usan la lista A con predicción; los pares, la lista B.',
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _number,
                readOnly: progress != null,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Orden de inclusión del participante (1–999)',
                  helperText:
                      'Confirmar con el registro de reclutamiento. Se conserva en este equipo.',
                ),
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<StudyPhase>(
                initialValue: _phase,
                decoration: const InputDecoration(
                  labelText: 'Sesión del protocolo',
                ),
                items: StudyPhase.values
                    .map(
                      (phase) => DropdownMenuItem(
                        value: phase,
                        child: Text(phase.label),
                      ),
                    )
                    .toList(),
                onChanged: (phase) => setState(() => _phase = phase!),
              ),
              const SizedBox(height: 12),
              Text(
                'Práctica completada: ${progress?.practiceCompleted ?? 0}/10 mensajes. S2 y S3: 20 frases por sesión, en bloques alternados de cinco.',
              ),
              const SizedBox(height: 8),
              const Text(
                'Interrumpir ante fatiga o malestar. Hacer pausas cada 10 minutos y separar las sesiones de medición al menos un día.',
              ),
              if (_error != null)
                Text(_error!, style: const TextStyle(color: Colors.amber)),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        FilledButton(
          onPressed: () {
            final number = int.tryParse(_number.text.trim());
            if (number == null || number < 1 || number > 999) {
              setState(() => _error = 'Usa un número entre 1 y 999.');
              return;
            }
            Navigator.pop(context, (number, _phase));
          },
          child: const Text('Preparar'),
        ),
      ],
    );
  }
}
