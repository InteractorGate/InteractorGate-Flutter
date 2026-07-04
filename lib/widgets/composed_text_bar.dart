import 'package:flutter/material.dart';

/// Muestra el texto que el usuario va componiendo con la mirada.
class ComposedTextBar extends StatelessWidget {
  const ComposedTextBar({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      constraints: const BoxConstraints(minHeight: 90),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E1E),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white12),
      ),
      alignment: Alignment.centerLeft,
      child: Text(
        text.isEmpty ? '…' : text,
        style: TextStyle(
          fontSize: 32,
          color: text.isEmpty ? Colors.white24 : Colors.white,
        ),
      ),
    );
  }
}
