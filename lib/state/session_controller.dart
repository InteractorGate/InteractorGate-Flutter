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
  }) : _studyStore = studyStore ?? StudyStore() {
    _telemetry.addListener(notifyListeners);
  }

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
  final _candidateSessions = <int?, String>{};
  Future<void> _edits = Future.value();
  String? _endEventId;
  String? _candidateTrialId;
  Map<String, dynamic>? _trialFinish;
  DateTime? _finishRequestedAt;
  String? _suggestionRequest;
  Stopwatch? _suggestionClock;
  bool _suggestionRecorded = false;
  String? actionError;
  final _trialClock = Stopwatch();
  bool studyBusy = false;
  String? studyError;

  StudyProgress? get studyProgress => _studyProgress;
  StudyPlan? get studyPlan => _studyPlan;
  String? get trialId => _trialId;
  bool get trialActive => _trialId != null;
  bool get canCompose =>
      active &&
      !studyBusy &&
      !_telemetry.blocked &&
      _trialFinish == null &&
      (_studyPlan == null || trialActive);
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
  bool get active => _sessionId != null && !_closing && _endEventId == null;

  String text = '';
  List<String> suggestions = [];
  bool loadingSuggestions = false;
  int get pendingEvents => _telemetry.pendingCount;
  String? get telemetryError => _telemetry.error ?? actionError;
  String? get suggestionPresentationId => _suggestionRequest;
  bool get finalizingTrial => _trialFinish != null;
  double dwellSeconds = 1.2;
  bool dwellEnabled = true;
  BoardMode boardMode = BoardMode.words;

  Future<void> start({int? participantId}) async {
    if (_sessionId != null) {
      throw StateError('La sesión anterior sigue abierta.');
    }
    var progress = participantId == null
        ? null
        : await _studyStore.load(participantId);
    if (participantId != null) {
      await _telemetry.bindParticipant(participantId);
      await _telemetry.flush();
      for (final event in _telemetry.retainedEvents) {
        final data = Map<String, dynamic>.from(event.body['data'] as Map);
        progress = await _saveCompletedProgress(participantId, progress, data);
        await _telemetry.commit(event.id);
      }
    }
    final id = _candidateSessions.putIfAbsent(
      participantId,
      () => const Uuid().v4(),
    );
    await _telemetry.log(
      sessionId: id,
      eventType: 'session_start',
      requireDelivery: true,
      eventId: id,
    );
    _reset();
    _sessionId = id;
    _participantId = participantId;
    _studyProgress = progress;
    _candidateSessions.remove(participantId);
    notifyListeners();
  }

  Future<void> end() {
    final id = _sessionId;
    if (id == null) return Future<void>.value();
    return _ending ??= _finish(id);
  }

  Future<void> _finish(String id) async {
    _closing = true;
    _finishRequestedAt ??= DateTime.now();
    if (trialActive) _trialClock.stop();
    notifyListeners();
    try {
      await Future.wait(_pending.toList());
      if (_candidateTrialId != null && !trialActive) {
        _trialId = _candidateTrialId;
        _candidateTrialId = null;
        _trialClock.reset();
      }
      if (trialActive) await _recordTrialEnd(id, interrupted: true);
      await _telemetry.log(
        sessionId: id,
        eventType: 'session_end',
        requireDelivery: true,
        eventId: _endEventId ??= const Uuid().v4(),
      );
      _sessionId = null;
      _reset();
      _telemetry.pause();
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
    _candidateTrialId = null;
    _trialFinish = null;
    _finishRequestedAt = null;
    _endEventId = null;
    actionError = null;
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
    _suggestionRequest = null;
    _suggestionClock = null;
  }

  Future<void> _run(Future<void> Function(String) action) async {
    if (!canCompose) return;
    try {
      actionError = null;
      await _track(action);
    } catch (_) {
      actionError =
          'No se pudo completar el registro de la acción. Revisa los eventos antes de continuar.';
      notifyListeners();
    }
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

  Future<void> _mutate(Future<void> Function() action) {
    final result = _edits.then((_) => action());
    _edits = result.then<void>((_) {}, onError: (Object _, StackTrace _) {});
    return result;
  }

  Future<void> toggleBoardMode() => _run(
    (id) => _mutate(() async {
      final mode = boardMode == BoardMode.words
          ? BoardMode.keyboard
          : BoardMode.words;
      await _action(id, 'settings', {
        'action': 'board_mode',
        'board_mode': mode.name,
      });
      boardMode = mode;
      notifyListeners();
    }),
  );

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

  Future<void> type(String char) {
    final clock = Stopwatch()..start();
    return _run((id) async {
      await _mutate(() async {
        final next = text + char;
        await _edit(
          id,
          'selection',
          char == ' ' ? 'space' : 'letter',
          next,
          0,
          char,
        );
        text = next;
        notifyListeners();
      });
      await _refreshSuggestions(id, clock);
    });
  }

  Future<void> space() => type(' ');

  Future<void> backspace() => _run((id) async {
    final clock = Stopwatch()..start();
    await _mutate(() async {
      if (text.isEmpty) return;
      final characters = text.runes.toList()..removeLast();
      final next = String.fromCharCodes(characters);
      await _edit(id, 'delete', 'backspace', next, 1, '');
      text = next;
      notifyListeners();
    });
    await _refreshSuggestions(id, clock);
  });

  Future<void> clear() => _run(
    (id) => _mutate(() async {
      await _edit(id, 'clear', 'clear', '', text.runes.length, '');
      _clearComposition();
      notifyListeners();
    }),
  );

  Future<void> insertWord(String word) => _run((id) async {
    final clock = Stopwatch()..start();
    await _mutate(() async {
      final next = text.isEmpty ? word : '${text.trimRight()} $word';
      await _edit(
        id,
        'selection',
        'word',
        next,
        text.runes.length - text.trimRight().runes.length,
        text.isEmpty ? word : ' $word',
      );
      text = next;
      notifyListeners();
    });
    await _refreshSuggestions(id, clock);
  });

  Future<void> applySuggestion(String phrase) => _run(
    (id) => _mutate(() async {
      if (!predictionEnabled ||
          loadingSuggestions ||
          !suggestions.contains(phrase)) {
        return;
      }
      final next = text.isEmpty ? phrase : '${text.trimRight()} $phrase';
      await _edit(
        id,
        'selection',
        'suggestion',
        next,
        text.runes.length - text.trimRight().runes.length,
        text.isEmpty ? phrase : ' $phrase',
        extra: {
          'suggestion_rank': suggestions.indexOf(phrase) + 1,
          if (_suggestionRequest != null) 'request_id': _suggestionRequest,
        },
      );
      _predictionRevision++;
      text = next;
      suggestions = [];
      notifyListeners();
    }),
  );

  Map<String, dynamic> _contextData() => {
    if (trialActive) ..._trialData(studyEntry!),
    if (trialActive) 'trial_id': _trialId,
    if (trialActive) 'elapsed_ms': _trialClock.elapsedMilliseconds,
    'board_mode': boardMode.name,
  };

  Future<void> _action(String id, String type, Map<String, dynamic> data) =>
      _telemetry.log(
        sessionId: id,
        eventType: type,
        data: {..._contextData(), ...data},
      );

  Future<void> _edit(
    String id,
    String type,
    String action,
    String next,
    int removed,
    String inserted, {
    Map<String, dynamic> extra = const {},
  }) => _action(id, type, {
    'action': action,
    'text_length': next.runes.length,
    'removed_characters': removed,
    if (trialActive) 'inserted_text': inserted,
    ...extra,
  });

  Future<void> _refreshSuggestions(String id, Stopwatch clock) async {
    if (!predictionEnabled || _sessionId != id) return;
    final revision = ++_predictionRevision;
    final context = text.trim();
    if (context.isEmpty) {
      suggestions = [];
      notifyListeners();
      return;
    }
    loadingSuggestions = true;
    final request = const Uuid().v4();
    _suggestionRequest = null;
    notifyListeners();
    try {
      await _action(id, 'suggestions', {
        'action': 'requested',
        'request_id': request,
      });
      final prediction = await _predictions.predictText(context, id);
      if (predictionEnabled &&
          _sessionId == id &&
          revision == _predictionRevision &&
          text.trim() == context) {
        suggestions = prediction.suggestions;
        _suggestionRequest = request;
        _suggestionClock = clock;
        _suggestionRecorded = false;
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

  Future<void> suggestionsPresented(String request) => _run((id) async {
    if (_suggestionRequest != request ||
        _suggestionRecorded ||
        !predictionEnabled ||
        suggestions.isEmpty) {
      return;
    }
    _suggestionRecorded = true;
    final elapsed = _suggestionClock!.elapsedMilliseconds;
    await _action(id, 'suggestions', {
      'action': 'shown',
      'request_id': request,
      'suggestions': List<String>.of(suggestions),
      'latency_ms': elapsed,
    });
  });

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
      if (_trialFinish == null) _finishRequestedAt = null;
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
    if (trialActive || _candidateTrialId != null) {
      throw StateError('Confirma el inicio o termina el ensayo actual.');
    }
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
    final trialId = _candidateTrialId ??= const Uuid().v4();
    await _telemetry.log(
      sessionId: id,
      eventType: 'trial_start',
      requireDelivery: true,
      eventId: trialId,
      timestamp: DateTime.now(),
      data: {..._trialData(entry), 'trial_id': trialId},
    );
    _clearComposition();
    _trialId = trialId;
    _candidateTrialId = null;
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
    if (active && !studyBusy && trialActive) {
      _trialClock.stop();
      _finishRequestedAt ??= DateTime.now();
    }
    return _studyOperation((id) async {
      if (!trialActive) throw StateError('No hay un ensayo en curso.');
      if (_trialFinish == null && !interrupted && text.trim().isEmpty) {
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
      _trialFinish ??= {
        'event_id': const Uuid().v4(),
        'timestamp': (_finishRequestedAt ?? DateTime.now())
            .toUtc()
            .toIso8601String(),
        'data': {
          ..._trialData(studyEntry!),
          'trial_id': _trialId,
          'status': interrupted ? 'interrupted' : 'completed',
          'final_text': text,
          'duration_ms': _trialClock.elapsedMilliseconds,
        },
      };
      final finish = _trialFinish!;
      final data = Map<String, dynamic>.from(finish['data'] as Map);
      await _telemetry.log(
        sessionId: id,
        eventType: 'trial_end',
        requireDelivery: true,
        timestamp: DateTime.parse(finish['timestamp'] as String),
        eventId: finish['event_id'] as String,
        retainUntilCommitted: true,
        data: data,
      );
      _studyProgress = await _saveCompletedProgress(
        _participantId!,
        _studyProgress,
        data,
      );
      await _telemetry.commit(finish['event_id'] as String);
      _trialFinish = null;
      _finishRequestedAt = null;
      _trialId = null;
      _clearComposition();
    } catch (_) {
      _trialClock.start();
      rethrow;
    }
  }

  void leaveStudy() {
    if (!active || studyBusy || trialActive || _candidateTrialId != null) {
      return;
    }
    _studyPlan = null;
    _clearComposition();
    studyError = null;
    notifyListeners();
  }

  Future<StudyProgress?> _saveCompletedProgress(
    int owner,
    StudyProgress? progress,
    Map<String, dynamic> data,
  ) async {
    if (data['status'] != 'completed') return progress;
    if (progress == null ||
        data['bank_version'] != studyBankVersion ||
        data['participant_number'] != progress.participantNumber) {
      throw StateError(
        'El cierre pendiente no corresponde al progreso guardado.',
      );
    }
    final phase = StudyPhase.values.byName(data['protocol_session'] as String);
    final order = data['order'] as int;
    if (progress.completed(phase) >= order) return progress;
    if (progress.completed(phase) != order - 1) {
      throw StateError('Faltan ensayos antes del cierre recuperado.');
    }
    final next = progress.advance(phase);
    await _studyStore.save(owner, next);
    return next;
  }

  void pauseTelemetry() => _telemetry.pause();
  Future<void> retryTelemetry() => _telemetry.flush();
  Future<Map<String, dynamic>> sessionReport() {
    final id = sessionId;
    if (id == null) throw StateError('No hay una sesión abierta.');
    if (trialActive) {
      throw StateError('Termina o interrumpe el ensayo antes de verificar.');
    }
    return _telemetry.sessionReport(id);
  }

  @override
  void dispose() {
    _telemetry.removeListener(notifyListeners);
    super.dispose();
  }
}
