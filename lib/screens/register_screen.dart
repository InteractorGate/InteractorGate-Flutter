import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/auth_controller.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _form = GlobalKey<FormState>();
  final _user = TextEditingController();
  final _email = TextEditingController();
  final _pass = TextEditingController();
  final _pass2 = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _user.dispose();
    _email.dispose();
    _pass.dispose();
    _pass2.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy) return;
    if (!_form.currentState!.validate()) return;
    setState(() => _busy = true);
    final ok = await context.read<AuthController>().register(
      username: _user.text.trim(),
      email: _email.text.trim(),
      password: _pass.text,
      password2: _pass2.text,
    );
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) {
      Navigator.of(context).pop();
    } else {
      final msg =
          context.read<AuthController>().error ?? 'No se pudo registrar';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Crear cuenta')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Form(
              key: _form,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextFormField(
                    controller: _user,
                    validator: (value) => value == null || value.trim().isEmpty
                        ? 'Ingresa el código de participante.'
                        : null,
                    decoration: const InputDecoration(
                      labelText: 'Código de participante',
                      hintText: 'P01',
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _email,
                    validator: (value) => value == null || value.trim().isEmpty
                        ? 'Ingresa el correo de estudio.'
                        : null,
                    decoration: const InputDecoration(
                      labelText: 'Correo de estudio',
                      hintText: 'p01@example.com',
                      helperText:
                          'Usa un correo de estudio, sin datos personales.',
                    ),
                    keyboardType: TextInputType.emailAddress,
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _pass,
                    validator: (value) => value == null || value.isEmpty
                        ? 'Ingresa la contraseña.'
                        : null,
                    decoration: const InputDecoration(labelText: 'Contraseña'),
                    obscureText: true,
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _pass2,
                    validator: (value) => value == null || value.isEmpty
                        ? 'Repite la contraseña.'
                        : value != _pass.text
                        ? 'Las contraseñas no coinciden.'
                        : null,
                    decoration: const InputDecoration(
                      labelText: 'Repetir contraseña',
                    ),
                    obscureText: true,
                    onFieldSubmitted: (_) => _submit(),
                  ),
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: _busy ? null : _submit,
                    child: _busy
                        ? const SizedBox(
                            height: 22,
                            width: 22,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Registrarme'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
