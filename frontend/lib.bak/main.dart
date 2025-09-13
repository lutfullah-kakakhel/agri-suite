import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:google_fonts/google_fonts.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const AgroAssistApp());
}

class AgroAssistApp extends StatefulWidget {
  const AgroAssistApp({super.key});
  @override
  State<AgroAssistApp> createState() => _AgroAssistAppState();
}

class _AgroAssistAppState extends State<AgroAssistApp> {
  Locale _locale = const Locale('en');

  @override
  Widget build(BuildContext context) {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF2E7D32), // deep green
      primary: const Color(0xFF2E7D32),
      secondary: const Color(0xFFF9F871), // soft yellow
      brightness: Brightness.light,
    );

    final textTheme = GoogleFonts.nunitoTextTheme(
      ThemeData.light().textTheme,
    );

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Agro Assist',
      locale: _locale,
      supportedLocales: const [
        Locale('en'),
        Locale('ur'),
      ],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      // RTL support when Urdu is selected
      builder: (context, child) {
        return Directionality(
          textDirection: _locale.languageCode == 'ur'
              ? TextDirection.rtl
              : TextDirection.ltr,
          child: child!,
        );
      },
      theme: ThemeData(
        colorScheme: colorScheme,
        useMaterial3: true,
        textTheme: textTheme,
        appBarTheme: AppBarTheme(
          backgroundColor: colorScheme.primary,
          foregroundColor: Colors.white,
          elevation: 0,
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: colorScheme.primary,
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
            textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
        ),
      ),
      home: LandingPage(
        onChangeLang: (Locale loc) => setState(() => _locale = loc),
        locale: _locale,
      ),
    );
  }
}

class LandingPage extends StatelessWidget {
  final void Function(Locale) onChangeLang;
  final Locale locale;
  const LandingPage({super.key, required this.onChangeLang, required this.locale});

  @override
  Widget build(BuildContext context) {
    final isUrdu = locale.languageCode == 'ur';

    // Use Noto Nastaliq for Urdu headings, fallback to Nunito for English
    final urduStyle = GoogleFonts.notoNastaliqUrdu(
      fontSize: 20,
      color: Colors.black87,
      height: 1.4,
    );

    final titleStyle = Theme.of(context).textTheme.headlineMedium?.copyWith(
          color: Colors.black87,
          fontWeight: FontWeight.w800,
        );

    return Scaffold(
      backgroundColor: const Color(0xFFEAFCD7), // pale green background
      appBar: AppBar(
        title: Text(isUrdu ? 'ایگری اسسٹ' : 'Agro Assist'),
        actions: [
          PopupMenuButton<String>(
            icon: const Icon(Icons.language),
            onSelected: (v) {
              if (v == 'en') onChangeLang(const Locale('en'));
              if (v == 'ur') onChangeLang(const Locale('ur'));
            },
            itemBuilder: (context) => [
              const PopupMenuItem(value: 'en', child: Text('English')),
              const PopupMenuItem(value: 'ur', child: Text('اردو')),
            ],
          ),
        ],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(22.0),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: Card(
              elevation: 0,
              color: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Logo
                    Container(
                      width: 120,
                      height: 120,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(24),
                        color: const Color(0xFFF9F871), // yellow accent
                      ),
                      clipBehavior: Clip.antiAlias,
                      child: Image.asset('assets/logo.png', fit: BoxFit.cover),
                    ),
                    const SizedBox(height: 20),
                    Text(
                      isUrdu ? 'ایگری اسسٹ' : 'Agro Assist',
                      style: titleStyle,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 12),
                    // English + Urdu description
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          'Smart irrigation & field tips tailored for your crop and weather.',
                          style: Theme.of(context).textTheme.bodyLarge,
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'سمارٹ آبپاشی اور کھیت کے مشورے — آپ کی فصل اور موسم کے مطابق۔',
                          style: urduStyle,
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                    const SizedBox(height: 24),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        icon: const Icon(Icons.arrow_forward),
                        label: Text(isUrdu ? 'شروع کریں' : 'Get Started'),
                        onPressed: () {
                          Navigator.of(context).push(
                            MaterialPageRoute(builder: (_) => const PlaceholderNext()),
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// Next screen placeholder (later: hook to your FastAPI)
class PlaceholderNext extends StatelessWidget {
  const PlaceholderNext({super.key});
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Field Dashboard')),
      body: const Center(
        child: Text('Coming next: API hookup for irrigation recommendations'),
      ),
    );
  }
}
