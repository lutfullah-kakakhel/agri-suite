import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:google_fonts/google_fonts.dart';

import 'screens/farm_boundary.dart';
import 'screens/field_irrigation_panel.dart';




// Your existing screens
import 'screens/farm_boundary.dart';
// If you still use the old form, keep the import (but we now prefer the panel):
// import 'screens/recommendation_form.dart';

// Optional: if you created this file from my earlier message
import 'screens/field_irrigation_panel.dart';

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

    final textTheme = GoogleFonts.nunitoTextTheme(ThemeData.light().textTheme);

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Agro Assist',
      locale: _locale,
      supportedLocales: const [Locale('en'), Locale('ur')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      builder: (context, child) => Directionality(
        textDirection:
            _locale.languageCode == 'ur' ? TextDirection.rtl : TextDirection.ltr,
        child: child!,
      ),
      theme: ThemeData(
        colorScheme: colorScheme,
        useMaterial3: true,
        textTheme: textTheme,
        appBarTheme: AppBarTheme(
          backgroundColor: colorScheme.primary,
          foregroundColor: Colors.white,
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: colorScheme.primary,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
        ),
      ),
      home: LandingPage(
        locale: _locale,
        onChangeLang: (loc) => setState(() => _locale = loc),
      ),
    );
  }
}

class LandingPage extends StatelessWidget {
  final Locale locale;
  final void Function(Locale) onChangeLang;

  const LandingPage({
    super.key,
    required this.locale,
    required this.onChangeLang,
  });

  @override
  Widget build(BuildContext context) {
    final isUrdu = locale.languageCode == 'ur';
    final titleStyle = Theme.of(context).textTheme.headlineSmall?.copyWith(
          color: Colors.black87,
          fontWeight: FontWeight.w800,
        );

    // Urdu paragraph style (smaller, more line height for readability)
    final urduBody = GoogleFonts.notoNastaliqUrdu(
      fontSize: 14,
      color: Colors.black87,
      height: 1.8,
    );

    return Scaffold(
      backgroundColor: const Color(0xFFEAFCD7),
      appBar: AppBar(
        title: Text(isUrdu ? 'ایگری اسسٹ' : 'Agro Assist'),
        actions: [
          PopupMenuButton<String>(
            icon: const Icon(Icons.language),
            onSelected: (v) {
              if (v == 'en') onChangeLang(const Locale('en'));
              if (v == 'ur') onChangeLang(const Locale('ur'));
            },
            itemBuilder: (context) => const [
              PopupMenuItem(value: 'en', child: Text('English')),
              PopupMenuItem(value: 'ur', child: Text('اردو')),
            ],
          ),
        ],
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          final maxW = constraints.maxWidth;
          final logoSize = (maxW * 0.20).clamp(64.0, 110.0);
          const targetWidth = 520.0;
          final horizPad =
              (maxW > targetWidth) ? (maxW - targetWidth) / 2 : 12.0;

          return SingleChildScrollView(
            padding: EdgeInsets.fromLTRB(horizPad, 10, horizPad, 8),
            child: Container(
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(18),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.04),
                    blurRadius: 10,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(18, 18, 18, 14),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Align(
                      alignment: Alignment.center,
                      child: Container(
                        width: logoSize,
                        height: logoSize,
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(24),
                          color: const Color(0xFFF9F871),
                        ),
                        clipBehavior: Clip.antiAlias,
                        child: Image.asset('assets/logo.png', fit: BoxFit.cover),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      isUrdu ? 'ایگری اسسٹ' : 'Agro Assist',
                      style: titleStyle,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      isUrdu
                          ? 'فصل اور موسم کے مطابق، سمارٹ آبپاشی کی رہنمائی۔'
                          : 'Smart irrigation guidance tailored to your crop and weather.',
                      style: Theme.of(context).textTheme.bodyLarge,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'سمارٹ آبپاشی اور کھیت کے مشورے — آپ کی فصل اور موسم کے مطابق۔',
                      style: urduBody,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 16),

                    // FLOW: Draw polygon → get fieldId → open irrigation panel
                    ElevatedButton.icon(
                      icon: const Icon(Icons.arrow_forward),
                      label: Text(isUrdu ? 'شروع کریں' : 'Get Started'),
                      onPressed: () async {
                        // 1) Let farmer draw & save polygon.
                        //    Expect FarmBoundaryScreen to return a String fieldId (UUID).
                        final result = await Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => const FarmBoundaryScreen(),
                          ),
                        );

                        if (!context.mounted) return;

                        // 2) If saved successfully, go to irrigation panel for that field.
                        if (result is String && result.isNotEmpty) {
                          // Prefer the lightweight panel (confirm + history)
                          await Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => FieldIrrigationPanel(
                                fieldId: result,
                                fieldName: isUrdu ? 'میرا کھیت' : 'My Field',
                              ),
                            ),
                          );

                          // If you still want to use your RecommendationFormScreen instead,
                          // comment the panel above and uncomment below (make sure it expects fieldId):
                          /*
                          await Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => RecommendationFormScreen(fieldId: result),
                            ),
                          );
                          */
                        } else {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(isUrdu
                                  ? 'کھیت محفوظ نہیں ہوا۔ دوبارہ کوشش کریں۔'
                                  : 'Field was not saved. Please try again.'),
                            ),
                          );
                        }
                      },
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
