/// Central API endpoint configuration for both clients.
///
/// Override at build/run time without touching code:
///   flutter run --dart-define=API_BASE=http://10.0.2.2:5000
///   flutter build apk --dart-define=API_BASE=https://api.example.com
///
/// (10.0.2.2 reaches the host machine's localhost from the Android
/// emulator.)
///
/// The default points at the Android emulator's route to the host rather
/// than at a hard-coded server: a wrong-but-plausible production IP baked
/// into a release build is worse than an obviously-local default, because
/// it fails silently against someone else's machine. Set API_BASE
/// explicitly for any real build.
const String apiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'http://10.0.2.2:5000',
);
