import 'dart:math';

enum StudyPhase {
  practice('S1 · Práctica'),
  s2('S2 · Primera mitad'),
  s3('S3 · Segunda mitad');

  const StudyPhase(this.label);
  final String label;
}

enum StudyCondition {
  withoutPrediction('without_prediction', 'Sin predicción'),
  withPrediction('with_prediction', 'Con predicción');

  const StudyCondition(this.code, this.label);
  final String code;
  final String label;
}

// Banco provisional de piloto: revisar equivalencia antes del estudio real.
const studyBankVersion = 'pilot-v1';
const studyListA = [
  'quiero tomar agua',
  'necesito agua tibia',
  'quiero comer arroz',
  'necesito comer algo',
  'quiero descansar ahora',
  'necesito una manta',
  'puedes acercar la mesa',
  'puedes abrir la puerta',
  'quiero mirar el patio',
  'quiero escuchar la radio',
  'necesito hablar con alguien',
  'quiero ver a mi hermano',
  'por favor trae mi vaso',
  'por favor mueve la silla',
  'me siento mejor hoy',
  'me duele el brazo',
  'quiero cambiar de canal',
  'necesito lavar mis manos',
  'quiero cenar con todos',
  'puedes dejar la luz',
];
const studyListB = [
  'quiero tomar leche',
  'necesito leche tibia',
  'quiero comer fruta',
  'necesito beber algo',
  'quiero acostarme ahora',
  'necesito una almohada',
  'puedes acercar la silla',
  'puedes cerrar la ventana',
  'quiero mirar la calle',
  'quiero escuchar un cuento',
  'necesito estar con alguien',
  'quiero ver a mi hermana',
  'por favor trae mi plato',
  'por favor mueve la mesa',
  'me siento tranquilo hoy',
  'me duele la pierna',
  'quiero cambiar de ropa',
  'necesito secar mis manos',
  'quiero comer con todos',
  'puedes dejar la puerta',
];
const studyPracticePhrases = [
  'hola me puedes escuchar',
  'quiero probar el teclado',
  'puedo escribir un mensaje',
  'vamos a practicar juntos',
  'necesito ajustar mi silla',
  'hoy vamos a escribir',
  'puedo borrar una letra',
  'vamos a probar otra vez',
  'este mensaje es de prueba',
  'quiero terminar la prueba',
];

class StudyEntry {
  const StudyEntry({
    required this.phraseId,
    required this.target,
    required this.list,
    required this.condition,
    required this.block,
    required this.order,
  });

  final String phraseId;
  final String target;
  final String list;
  final StudyCondition condition;
  final int block;
  final int order;

  Map<String, dynamic> toJson() => {
    'phrase_id': phraseId,
    'target_phrase': target,
    'list': list,
    'condition': condition.code,
    'block': block,
    'order': order,
  };
}

class StudyPlan {
  StudyPlan({required this.participantNumber, required this.phase}) {
    if (participantNumber < 1 || participantNumber > 999) {
      throw ArgumentError('El orden de inclusión debe estar entre 1 y 999.');
    }
    final firstWithPrediction = Random(seed).nextBool();
    final listWithPrediction = participantNumber.isOdd ? 'A' : 'B';
    final lists = <String, List<int>>{};
    for (final list in ['A', 'B']) {
      // La misma permutación en S2 y S3, dividida en mitades sin repetir frases.
      lists[list] = List.generate(20, (i) => i)
        ..shuffle(Random(participantNumber * 1009 + (list == 'A' ? 17 : 31)));
    }
    final result = <StudyEntry>[];
    final blockCount = phase == StudyPhase.practice ? 2 : 4;
    for (var block = 0; block < blockCount; block++) {
      final withPrediction = block.isEven == firstWithPrediction;
      final condition = withPrediction
          ? StudyCondition.withPrediction
          : StudyCondition.withoutPrediction;
      final list = withPrediction == (listWithPrediction == 'A') ? 'A' : 'B';
      for (var position = 0; position < 5; position++) {
        final practice = phase == StudyPhase.practice;
        final index = practice
            ? (withPrediction ? 5 : 0) + position
            : lists[list]![(phase == StudyPhase.s3 ? 10 : 0) +
                  (block ~/ 2) * 5 +
                  position];
        result.add(
          StudyEntry(
            phraseId: practice ? 'P${index + 1}' : '$list${index + 1}',
            target: practice
                ? studyPracticePhrases[index]
                : (list == 'A' ? studyListA : studyListB)[index],
            list: practice ? 'practice' : list,
            condition: condition,
            block: block + 1,
            order: result.length + 1,
          ),
        );
      }
    }
    entries = List.unmodifiable(result);
  }

  final int participantNumber;
  final StudyPhase phase;
  late final List<StudyEntry> entries;
  int get seed => participantNumber * 1009 + phase.index * 97;
  bool get practice => phase == StudyPhase.practice;
}

class StudyProgress {
  const StudyProgress({
    required this.participantNumber,
    this.practiceCompleted = 0,
    this.s2Completed = 0,
    this.s3Completed = 0,
  });

  final int participantNumber;
  final int practiceCompleted;
  final int s2Completed;
  final int s3Completed;
  bool get readyToMeasure => practiceCompleted >= 10;

  int completed(StudyPhase phase) => switch (phase) {
    StudyPhase.practice => practiceCompleted,
    StudyPhase.s2 => s2Completed,
    StudyPhase.s3 => s3Completed,
  };

  StudyProgress advance(StudyPhase phase) => StudyProgress(
    participantNumber: participantNumber,
    practiceCompleted:
        practiceCompleted + (phase == StudyPhase.practice ? 1 : 0),
    s2Completed: s2Completed + (phase == StudyPhase.s2 ? 1 : 0),
    s3Completed: s3Completed + (phase == StudyPhase.s3 ? 1 : 0),
  );

  Map<String, dynamic> toJson() => {
    'bank_version': studyBankVersion,
    'participant_number': participantNumber,
    'practice_completed': practiceCompleted,
    's2_completed': s2Completed,
    's3_completed': s3Completed,
  };

  factory StudyProgress.fromJson(Map<String, dynamic> json) {
    final number = json['participant_number'];
    final practice = json['practice_completed'];
    final s2 = json['s2_completed'];
    final s3 = json['s3_completed'];
    if (json['bank_version'] != studyBankVersion ||
        number is! int ||
        number < 1 ||
        number > 999 ||
        practice is! int ||
        practice < 0 ||
        practice > 10 ||
        s2 is! int ||
        s2 < 0 ||
        s2 > 20 ||
        s3 is! int ||
        s3 < 0 ||
        s3 > 20 ||
        (practice < 10 && (s2 > 0 || s3 > 0)) ||
        (s2 < 20 && s3 > 0)) {
      throw const FormatException('El progreso de E2 no es válido.');
    }
    return StudyProgress(
      participantNumber: number,
      practiceCompleted: practice,
      s2Completed: s2,
      s3Completed: s3,
    );
  }
}
