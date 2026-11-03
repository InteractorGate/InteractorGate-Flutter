import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import '../services/prediction_service.dart';
import '../services/telemetry_service.dart';

enum BoardMode { words, keyboard }

/// Una sesión por apertura autenticada, sin estado compartido entre participantes.
class SessionController extends ChangeNotifier {
  SessionController(this._predictions, this._telemetry);

  final PredictionService _predictions;
  final TelemetryService _telemetry;
  final _pending = <Future<void>>{};
  String? _sessionId;
  Future<void>? _ending;
  bool _closing = false;

  String? get sessionId => _sessionId;
  bool get active => _sessionId != null && !_closing;

  String text = '';
  List<String> suggestions = [];
  bool loadingSuggestions = false;
  double dwellSeconds = 1.2;
  bool dwellEnabled = true;
  BoardMode boardMode = BoardMode.words;

  Future<void> start() async {
    if (_sessionId != null) {
      throw StateError('La sesión anterior sigue abierta.');
    }
    final id = const Uuid().v4();
    await _telemetry.log(
      sessionId: id,
      eventType: 'session_start',
      requireDelivery: true,
    );
    _reset();
    _sessionId = id;
    notifyListeners();
  }

  Future<void> end() {
    final id = _sessionId;
    if (id == null) return Future<void>.value();
    return _ending ??= _finish(id);
  }

  Future<void> _finish(String id) async {
    _closing = true;
    notifyListeners();
    try {
      await Future.wait(_pending.toList());
      await _telemetry.log(
        sessionId: id,
        eventType: 'session_end',
        requireDelivery: true,
      );
      _sessionId = null;
      _reset();
    } finally {
      _closing = false;
      _ending = null;
      notifyListeners();
    }
  }

  void _reset() {
    text = '';
    suggestions = [];
    loadingSuggestions = false;
    dwellSeconds = 1.2;
    dwellEnabled = true;
    boardMode = BoardMode.words;
  }

  Future<void> _run(Future<void> Function(String) action) async {
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
    if (!active) return;
    boardMode = boardMode == BoardMode.words
        ? BoardMode.keyboard
        : BoardMode.words;
    notifyListeners();
  }

  void setDwellEnabled(bool value) {
    if (!active) return;
    dwellEnabled = value;
    notifyListeners();
  }

  void setDwellSeconds(double value) {
    if (!active) return;
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
    if (!active) return;
    text = '';
    suggestions = [];
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
    if (!active || _sessionId != id) return;
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
      if (active && _sessionId == id && text.trim() == context) {
        suggestions = prediction.suggestions;
      }
    } catch (_) {
      if (active && _sessionId == id && text.trim() == context) {
        suggestions = [];
      }
    } finally {
      if (_sessionId == id) {
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
}
