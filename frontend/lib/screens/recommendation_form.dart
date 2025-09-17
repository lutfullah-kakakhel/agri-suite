import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api.dart';


class RecommendationFormScreen extends StatefulWidget {
  final String? farmId;   // <-- add this line

  const RecommendationFormScreen({super.key, this.farmId});  // <-- update constructor

  @override
  State<RecommendationFormScreen> createState() =>
      _RecommendationFormScreenState();
}

class _RecommendationFormScreenState extends State<RecommendationFormScreen> {
  final _formKey = GlobalKey<FormState>();

  // Pre-fill with realistic values (farmer doesn’t need to type all)
  String _selectedCrop = "wheat";
  final _moistureCtrl = TextEditingController(text: "25");
  final _rainCtrl = TextEditingController(text: "5");
  final _tempCtrl = TextEditingController(text: "32");
  final _et0Ctrl = TextEditingController();

  bool _checking = true;
  bool _backendOk = false;
  bool _wakingUp = false;
  bool _submitting = false;
  Map<String, dynamic>? _result;
  String? _error;

  final List<Map<String, String>> _crops = [
    {"en": "wheat", "ur": "گندم"},
    {"en": "maize", "ur": "مکئی"},
    {"en": "rice", "ur": "چاول"},
    {"en": "cotton", "ur": "کپاس"},
    {"en": "sugarcane", "ur": "گنا"},
  ];

  @override
  void initState() {
    super.initState();
    _checkHealth();
  }

  Future<void> _checkHealth() async {
    try {
      final ok = await ApiService.healthz();
      setState(() {
        _backendOk = ok;
        _checking = false;
      });
    } catch (_) {
      // Assume cold start
      setState(() {
        _wakingUp = true;
        _checking = false;
      });
      Future.delayed(const Duration(seconds: 20), () async {
        try {
          final ok2 = await ApiService.healthz();
          setState(() {
            _backendOk = ok2;
            _wakingUp = false;
          });
        } catch (_) {
          setState(() {
            _backendOk = false;
            _wakingUp = false;
          });
        }
      });
    }
  }

  @override
  void dispose() {
    _moistureCtrl.dispose();
    _rainCtrl.dispose();
    _tempCtrl.dispose();
    _et0Ctrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _submitting = true;
      _error = null;
      _result = null;
    });
    try {
      final res = await ApiService.irrigationRecommendation(
        crop: _selectedCrop,
        soilMoisturePct: double.parse(_moistureCtrl.text.trim()),
        rainfallForecastMm: double.parse(_rainCtrl.text.trim()),
        tempC: double.parse(_tempCtrl.text.trim()),
        et0Mm: _et0Ctrl.text.trim().isEmpty
            ? null
            : double.parse(_et0Ctrl.text.trim()),
      );
      setState(() {
        _result = res;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
      });
    } finally {
      setState(() {
        _submitting = false;
      });
    }
  }

  InputDecoration _dec(String label) => InputDecoration(
        labelText: label,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      );

  @override
  Widget build(BuildContext context) {
    final green = const Color(0xFF2E7D32);

    return Scaffold(
      appBar: AppBar(title: const Text('Irrigation Recommendation')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: ListView(
          children: [
            if (_checking)
              Row(
                children: [
                  const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2)),
                  const SizedBox(width: 10),
                  Text("Checking backend…", style: GoogleFonts.nunito()),
                ],
              )
            else if (_wakingUp)
              Row(
                children: [
                  const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2)),
                  const SizedBox(width: 10),
                  Text("Waking up server… please wait",
                      style: GoogleFonts.nunito(color: Colors.orange[800])),
                ],
              )
            else
              Row(
                children: [
                  Icon(_backendOk ? Icons.check_circle : Icons.error,
                      color: _backendOk ? Colors.green : Colors.red),
                  const SizedBox(width: 8),
                  Text(
                    _backendOk ? "Connected to backend" : "Backend unreachable",
                    style: GoogleFonts.nunito(fontWeight: FontWeight.w700),
                  ),
                ],
              ),
            const SizedBox(height: 16),
            Form(
              key: _formKey,
              autovalidateMode: AutovalidateMode.disabled,
              child: Column(
                children: [
                  // Crop dropdown
                  DropdownButtonFormField<String>(
                    value: _selectedCrop,
                    decoration: _dec("Crop / فصل"),
                    items: _crops
                        .map((c) => DropdownMenuItem(
                              value: c["en"],
                              child: Text("${c["en"]} — ${c["ur"]}"),
                            ))
                        .toList(),
                    onChanged: (val) =>
                        setState(() => _selectedCrop = val ?? "wheat"),
                  ),
                  const SizedBox(height: 12),
                  // Soil moisture
                  TextFormField(
                    controller: _moistureCtrl,
                    decoration: _dec("Soil moisture % (0–100)"),
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return "Required";
                      final d = double.tryParse(v);
                      if (d == null || d < 0 || d > 100) return "Enter 0–100";
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  // Rain forecast
                  TextFormField(
                    controller: _rainCtrl,
                    decoration: _dec("Rainfall forecast (mm)"),
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return "Required";
                      final d = double.tryParse(v);
                      if (d == null || d < 0) return "Enter ≥ 0";
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  // Temperature
                  TextFormField(
                    controller: _tempCtrl,
                    decoration: _dec("Temperature (°C)"),
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return "Required";
                      if (double.tryParse(v) == null) return "Enter a number";
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  // ET0 optional
                  TextFormField(
                    controller: _et0Ctrl,
                    decoration: _dec("ET₀ (mm) — optional"),
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    validator: (_) => null,
                  ),
                  const SizedBox(height: 18),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      icon: _submitting
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white))
                          : const Icon(Icons.water_drop),
                      label: Text(
                          _submitting ? "Calculating…" : "Get Recommendation"),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: green,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14)),
                      ),
                      onPressed: _submitting ? null : _submit,
                    ),
                  ),
                ],
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 14),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.red.shade50,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.red.shade200),
                ),
                child: Text(_error!,
                    style: GoogleFonts.nunito(color: Colors.red.shade800)),
              ),
            ],
            if (_result != null) ...[
              const SizedBox(height: 16),
              _RecommendationCard(data: _result!),
            ],
          ],
        ),
      ),
    );
  }
}

class _RecommendationCard extends StatelessWidget {
  final Map<String, dynamic> data;
  const _RecommendationCard({required this.data});

  @override
  Widget build(BuildContext context) {
    final ok = data["need_irrigation"] == true;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ok ? const Color(0xFFE8F5E9) : const Color(0xFFFFFDE7),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.black12),
      ),
      child: DefaultTextStyle.merge(
        style: const TextStyle(fontSize: 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              ok ? "Irrigation Needed" : "No Immediate Irrigation",
              style: GoogleFonts.nunito(
                  fontSize: 18, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            Text("Crop: ${data["crop"]}"),
            Text("Adjusted moisture score: ${data["adjusted_moisture_score"]}"),
            Text("Threshold: ${data["threshold"]}"),
            if (data["recommended_irrigation_mm"] != null)
              Text("Recommended irrigation: ${data["recommended_irrigation_mm"]} mm"),
          ],
        ),
      ),
    );
  }
}
