import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import '../models/study_protocol.dart';
import '../services/prediction_service.dart';
import '../services/study_store.dart';
import '../services/telemetry_service.dart';

enum BoardMode { words, keyboard }

/// Una sesión por apertura autenticada, sin estado compartido entre participantes.
class SessionController extends ChangeNotifier {
  SessionController(
    this._predictions,
    this._telemetry, {
    StudyStore? studyStore,
  }) : _studyStore = studyStore ?? StudyStore();

  final PredictionService _predictions;
  final TelemetryService _telemetry;
  final StudyStore _studyStore;
  final _pending = <Future<void>>{};
  String? _sessionId;
  Future<void>? _ending;
  bool _closing = false;
  int? _participantId;
  int _predictionRevision = 0;
  StudyProgress? _studyProgress;
  StudyPlan? _studyPlan;
  String? _trialId;
  final _trialClock = Stopwatch();
  bool studyBusy = false;
  String? studyError;

  StudyProgress? get studyProgress => _studyProgress;
  StudyPlan? get studyPlan => _studyPlan;
  String? get trialId => _trialId;
  bool get trialActive => _trialId != null;
  bool get canCompose =>
      active && !studyBusy && (_studyPlan == null || trialActive);
  bool get predictionEnabled =>
      canCompose &&
      (_studyPlan == null ||
          studyEntry?.condition == StudyCondition.withPrediction);
  StudyEntry? get studyEntry {
    final plan = _studyPlan;
    if (plan == null) return null;
    final index = _studyProgress!.completed(plan.phase);
    return index < plan.entries.length ? plan.entries[index] : null;
  }

  String? get sessionId => _sessionId;
  bool get active => _sessionId != null && !_closing;

  String text = '';
  List<String> suggestions = [];
  bool loadingSuggestions = false;
  double dwellSeconds = 1.2;
  bool dwellEnabled = true;
  BoardMode boardMode = BoardMode.words;

  Future<void> start({int? participantId}) async {
    if (_sessionId != null) {
      throw StateError('La sesión anterior sigue abierta.');
    }
    final progress = participantId == null
        ? null
        : await _studyStore.load(participantId);
    final id = const Uuid().v4();
    await _telemetry.log(
      sessionId: id,
      eventType: 'session_start',
      requireDelivery: true,
    );
    _reset();
    _sessionId = id;
    _participantId = participantId;
    _studyProgress = progress;
    notifyListeners();
  }

  Future<void> end() {
    final id = _sessionId;
    if (id == null) return Future<void>.value();
    return _ending ??= _finish(id);
  }

  Future<void> _finish(String id) async {
    _closing = true;
    if (trialActive) _trialClock.stop();
    notifyListeners();
    try {
      await Future.wait(_pending.toList());
      if (trialActive) await _recordTrialEnd(id, interrupted: true);
      await _telemetry.log(
        sessionId: id,
        eventType: 'session_end',
        requireDelivery: true,
      );
      _sessionId = null;
      _reset();
    } finally {
      _closing = false;
      if (trialActive) _trialClock.start();
      _ending = null;
      notifyListeners();
    }
  }

  void _reset() {
    _clearComposition();
    _participantId = null;
    _studyProgress = null;
    _studyPlan = null;
    _trialId = null;
    _trialClock.reset();
    _trialClock.stop();
    studyBusy = false;
    studyError = null;
    dwellSeconds = 1.2;
    dwellEnabled = true;
    boardMode = BoardMode.words;
  }

  void _clearComposition() {
    _predictionRevision++;
    text = '';
    suggestions = [];
    loadingSuggestions = false;
  }

  Future<void> _run(Future<void> Function(String) action) async {
    if (!canCompose) return;
    await _track(action);
  }

  Future<void> _track(Future<void> Function(String) action) async {
    final id = _sessionId;
    if (id == null || _closing) return;
    final work = action(id);
    _pending.add(work);
    try {
      await work;
    } finally {
      _pending.remove(work);
    }
  }

  void toggleBoardMode() {
    if (!canCompose) return;
    boardMode = boardMode == BoardMode.words
        ? BoardMode.keyboard
        : BoardMode.words;
    notifyListeners();
  }

  void setDwellEnabled(bool value) {
    if (!active || _studyPlan != null || studyBusy) return;
    dwellEnabled = value;
    notifyListeners();
  }

  void setDwellSeconds(double value) {
    if (!active || _studyPlan != null || studyBusy) return;
    dwellSeconds = value;
    notifyListeners();
  }

  Future<void> type(String char) => _run((id) async {
    text += char;
    notifyListeners();
    await _refreshSuggestions(id);
  });

  Future<void> space() => type(' ');

  Future<void> backspace() => _run((id) async {
    if (text.isEmpty) return;
    text = text.substring(0, text.length - 1);
    notifyListeners();
    await _refreshSuggestions(id);
  });

  void clear() {
    if (!canCompose) return;
    _clearComposition();
    notifyListeners();
  }

  Future<void> insertWord(String word) => _run((id) async {
    text = text.isEmpty ? word : '${text.trimRight()} $word';
    notifyListeners();
    await _telemetry.log(
      sessionId: id,
      eventType: 'selection',
      selectedWord: word,
    );
    await _refreshSuggestions(id);
  });

  Future<void> applySuggestion(String phrase) => _run((id) async {
    if (!predictionEnabled || !suggestions.contains(phrase)) return;
    _predictionRevision++;
    text = text.isEmpty ? phrase : '${text.trimRight()} $phrase';
    suggestions = [];
    notifyListeners();
    await _telemetry.log(
      sessionId: id,
      eventType: 'selection',
      selectedWord: phrase,
    );
  });

  Future<void> _refreshSuggestions(String id) async {
    if (!predictionEnabled || _sessionId != id) return;
    final revision = ++_predictionRevision;
    final context = text.trim();
    if (context.isEmpty) {
      suggestions = [];
      notifyListeners();
      return;
    }
    loadingSuggestions = true;
    notifyListeners();
    try {
      final prediction = await _predictions.predictText(context, id);
      if (predictionEnabled &&
          _sessionId == id &&
          revision == _predictionRevision &&
          text.trim() == context) {
        suggestions = prediction.suggestions;
      }
    } catch (_) {
      if (predictionEnabled &&
          _sessionId == id &&
          revision == _predictionRevision &&
          text.trim() == context) {
        suggestions = [];
      }
    } finally {
      if (_sessionId == id && revision == _predictionRevision) {
        loadingSuggestions = false;
        notifyListeners();
      }
    }
  }

  Future<void> logKeySelection(String key, {Map<String, double>? gaze}) => _run(
    (id) => _telemetry.log(
      sessionId: id,
      eventType: 'selection',
      selectedWord: key,
      gaze: gaze,
    ),
  );

  Future<bool> _studyOperation(Future<void> Function(String) action) async {
    if (!active || studyBusy) return false;
    studyBusy = true;
    studyError = null;
    final pending = _pending.toList();
    notifyListeners();
    try {
      await _track((id) async {
        await Future.wait(pending);
        await action(id);
      });
      return true;
    } catch (error) {
      if (trialActive) _trialClock.start();
      studyError = error is StateError
          ? error.message
          : error is ArgumentError
          ? error.message.toString()
          : 'No se pudo confirmar el cambio del ensayo. Revisa la conexión y reintenta.';
      return false;
    } finally {
      studyBusy = false;
      notifyListeners();
    }
  }

  Future<bool> configureStudy({
    required int participantNumber,
    required StudyPhase phase,
  }) => _studyOperation((id) async {
    if (trialActive) throw StateError('Termina o interrumpe el ensayo actual.');
    final participantId = _participantId;
    if (participantId == null) {
      throw StateError('Falta identificar al participante.');
    }
    final plan = StudyPlan(participantNumber: participantNumber, phase: phase);
    final progress =
        _studyProgress ?? StudyProgress(participantNumber: participantNumber);
    if (progress.participantNumber != participantNumber) {
      throw StateError(
        'Conserva el orden de inclusión guardado para este participante.',
      );
    }
    if (!plan.practice && !progress.readyToMeasure) {
      throw StateError(
        'Completa primero los diez mensajes de práctica en ambas condiciones.',
      );
    }
    if (phase == StudyPhase.s3 && progress.s2Completed < 20) {
      throw StateError('Completa S2 antes de comenzar S3.');
    }
    await _studyStore.save(participantId, progress);
    _studyProgress = progress;
    await _telemetry.log(
      sessionId: id,
      eventType: 'settings',
      requireDelivery: true,
      data: {
        'study': 'E2',
        'bank_version': studyBankVersion,
        'provisional': true,
        'protocol_session': phase.name,
        'participant_number': participantNumber,
        'list_with_prediction': participantNumber.isOdd ? 'A' : 'B',
        'seed': plan.seed,
        'dwell_enabled': dwellEnabled,
        'dwell_seconds': dwellSeconds,
        'phrase_order': plan.entries.map((e) => e.phraseId).toList(),
        'first_condition': plan.entries.first.condition.code,
      },
    );
    _studyPlan = plan;
    _clearComposition();
    boardMode = BoardMode.keyboard;
  });

  Future<bool> startTrial() => _studyOperation((id) async {
    final entry = studyEntry;
    if (entry == null || trialActive) {
      throw StateError('No hay un ensayo disponible.');
    }
    final trialId = const Uuid().v4();
    await _telemetry.log(
      sessionId: id,
      eventType: 'trial_start',
      requireDelivery: true,
      timestamp: DateTime.now(),
      data: {..._trialData(entry), 'trial_id': trialId},
    );
    _clearComposition();
    _trialId = trialId;
    _trialClock.reset();
    _trialClock.start();
  });

  Map<String, dynamic> _trialData(StudyEntry entry) => {
    'study': 'E2',
    'bank_version': studyBankVersion,
    'provisional': true,
    'protocol_session': _studyPlan!.phase.name,
    'practice': _studyPlan!.practice,
    'participant_number': _studyProgress!.participantNumber,
    ...entry.toJson(),
  };

  Future<bool> finishTrial({bool interrupted = false}) {
    if (active && !studyBusy && trialActive) _trialClock.stop();
    return _studyOperation((id) async {
      if (!trialActive) throw StateError('No hay un ensayo en curso.');
      if (!interrupted && text.trim().isEmpty) {
        throw StateError('Compón un mensaje antes de terminar el ensayo.');
      }
      await _recordTrialEnd(id, interrupted: interrupted);
    });
  }

  Future<void> _recordTrialEnd(String id, {required bool interrupted}) async {
    _predictionRevision++;
    loadingSuggestions = false;
    _trialClock.stop();
    try {
      // shortcut: un ACK perdido puede duplicar límites; deduplicar en el bloque 3.
      await _telemetry.log(
        sessionId: id,
        eventType: 'trial_end',
        requireDelivery: true,
        timestamp: DateTime.now(),
        data: {
          ..._trialData(studyEntry!),
          'trial_id': _trialId,
          'status': interrupted ? 'interrupted' : 'completed',
          'final_text': text,
          'duration_ms': _trialClock.elapsedMilliseconds,
        },
      );
      if (!interrupted) {
        final progress = _studyProgress!.advance(_studyPlan!.phase);
        await _studyStore.save(_participantId!, progress);
        _studyProgress = progress;
      }
      _trialId = null;
      _clearComposition();
    } catch (_) {
      _trialClock.start();
      rethrow;
    }
  }

  void leaveStudy() {
    if (!active || studyBusy || trialActive) return;
    _studyPlan = null;
    _clearComposition();
    studyError = null;
    notifyListeners();
  }
}
