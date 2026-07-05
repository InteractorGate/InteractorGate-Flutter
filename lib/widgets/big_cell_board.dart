import 'package:flutter/material.dart';

import 'dwell_button.dart';

/// Tablero de **celdas grandes** (2 filas x 4) amigable con la mirada: palabras
/// AAC comunes + acceso al teclado + borrar. Celdas grandes = seleccion fiable
/// aun con la precision limitada del rastreo ocular por webcam.
class BigCellBoard extends StatelessWidget {
  const BigCellBoard({
    super.key,
    required this.onWord,
    required this.onKeyboard,
    required this.onBackspace,
    this.dwellSeconds = 1.2,
    this.dwellEnabled = true,
  });

  final ValueChanged<String> onWord;
  final VoidCallback onKeyboard;
  final VoidCallback onBackspace;
  final double dwellSeconds;
  final bool dwellEnabled;

  // Palabras AAC de uso frecuente. La RNN amplia el vocabulario con sugerencias.
  static const List<String> words = [
    'Sí', 'No', 'Gracias', 'Agua', 'Comida', 'Ayuda',
  ];

  @override
  Widget build(BuildContext context) {
    final cells = <Widget>[
      for (final w in words) _cell(w, () => onWord(w)),
      _cell('⌨ Teclado', onKeyboard,
          color: const Color(0xFF264D4D), fontSize: 24),
      _cell('⌫ Borrar', onBackspace,
          color: const Color(0xFF4D2626), fontSize: 24),
    ];
    return Column(
      children: [
        for (var r = 0; r < 2; r++)
          Expanded(
            child: Row(
              children: [
                for (var c = 0; c < 4; c++)
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.all(6),
                      child: cells[r * 4 + c],
                    ),
                  ),
              ],
            ),
          ),
      ],
    );
  }

  DwellButton _cell(String label, VoidCallback onSel,
      {Color? color, double fontSize = 32}) {
    return DwellButton(
      dwellSeconds: dwellSeconds,
      dwellEnabled: dwellEnabled,
      color: color,
      onSelected: onSel,
      child: Text(
        label,
        textAlign: TextAlign.center,
        style: TextStyle(fontSize: fontSize, fontWeight: FontWeight.bold),
      ),
    );
  }
}
