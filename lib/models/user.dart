/// Perfil de usuario devuelto por `/api/users/me/`.
class User {
  const User({
    required this.id,
    required this.username,
    required this.email,
    this.firstName = '',
    this.lastName = '',
  });

  final int id;
  final String username;
  final String email;
  final String firstName;
  final String lastName;

  String get displayName =>
      firstName.isNotEmpty ? firstName : username;

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] as int,
      username: (json['username'] as String?) ?? '',
      email: (json['email'] as String?) ?? '',
      firstName: (json['first_name'] as String?) ?? '',
      lastName: (json['last_name'] as String?) ?? '',
    );
  }
}
