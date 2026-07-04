import 'package:flutter/material.dart';

import 'dwell_button.dart';

/// Teclado en pantalla de teclas grandes, operado por dwell/clic.
class DwellKeyboard extends StatelessWidget {
  const DwellKeyboard({
    super.key,
    required this.onKey,
    required this.onSpace,
    required this.onBackspace,
    required this.onClear,
    this.dwellSeconds = 1.2,
    this.dwellEnabled = true,
  });

  final ValueChanged<String> onKey;
  final VoidCallback onSpace;
  final VoidCallback onBackspace;
  final VoidCallback onClear;
  final double dwellSeconds;
  final bool dwellEnabled;

  static const List<String> _rows = ['QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM'];

  DwellButton _key(String label, VoidCallback onSel, {Color? color, double fontSize = 26}) {
    return DwellButton(
      dwellSeconds: dwellSeconds,
      dwellEnabled: dwellEnabled,
      color: color,
      onSelected: onSel,
      child: Text(
        label,
        style: TextStyle(fontSize: fontSize, fontWeight: FontWeight.bold),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (final row in _rows)
          Expanded(
            child: Row(
              children: [
                for (final ch in row.split(''))
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.all(4),
                      child: _key(ch, () => onKey(ch)),
                    ),
                  ),
              ],
            ),
          ),
        Expanded(
          child: Row(
            children: [
              Expanded(
                flex: 2,
                child: Padding(
                  padding: const EdgeInsets.all(4),
                  child: _key('LIMPIAR', onClear,
                      color: const Color(0xFF4D2626), fontSize: 16),
                ),
              ),
              Expanded(
                flex: 5,
                child: Padding(
                  padding: const EdgeInsets.all(4),
                  child: _key('ESPACIO', onSpace, fontSize: 18),
                ),
              ),
              Expanded(
                flex: 2,
                child: Padding(
                  padding: const EdgeInsets.all(4),
                  child: DwellButton(
                    dwellSeconds: dwellSeconds,
                    dwellEnabled: dwellEnabled,
                    onSelected: onBackspace,
                    child: const Icon(Icons.backspace_outlined, size: 26),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
