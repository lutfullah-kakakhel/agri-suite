import 'dart:async';
import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../services/irrigation_repository.dart';

class FieldIrrigationPanel extends StatefulWidget {
  final String fieldId;
  final String fieldName;
  const FieldIrrigationPanel({super.key, required this.fieldId, required this.fieldName});

  @override
  State<FieldIrrigationPanel> createState() => _FieldIrrigationPanelState();
}

class _FieldIrrigationPanelState extends State<FieldIrrigationPanel> {
  late final IrrigationRepository repo;
  bool loading = true;
  String? error;
  Map<String, dynamic>? data;
  Timer? _retryTimer;

  @override
  void initState() {
    super.initState();
    repo = IrrigationRepository(ApiClient());
    _load();
  }

  @override
  void dispose() {
    _retryTimer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    _retryTimer?.cancel();
    setState(() { loading = true; error = null; });
    try {
      final res = await repo.getRecommendation(fieldId: widget.fieldId);
      if (!mounted) return;
      setState(() => data = res);

      if (res['status'] == 'processing') {
        final etaMin = (res['eta_minutes'] is num) ? (res['eta_minutes'] as num).toInt() : 2;
        _retryTimer = Timer(Duration(minutes: etaMin.clamp(1, 10)), () {
          if (mounted) _load();
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => error = e.toString());
      await _showCopyableDialog('Error', e.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _confirm() async {
    final rec = data;
    if (rec == null || rec['recommendation_mm'] == null) return;
    try {
      final mm = (rec['recommendation_mm'] as num).toDouble();
      final inputs = Map<String, dynamic>.from(rec['inputs'] ?? {});
      final id = await repo.confirmRecommendation(
        fieldId: widget.fieldId, recommendationMm: mm, inputs: inputs,
      );
      if (!mounted) return;
      await _showCopyableDialog('Saved', 'Schedule ID: $id');
    } catch (e) {
      await _showCopyableDialog('Error', 'Failed to save:\n$e');
    }
  }

  Future<void> _openHistory() async {
    try {
      final items = await repo.listSchedules(widget.fieldId);
      if (!mounted) return;
      await showModalBottomSheet(
        context: context,
        builder: (_) => ListView.separated(
          padding: const EdgeInsets.all(12),
          itemCount: items.length,
          separatorBuilder: (_, __) => const Divider(height: 1),
          itemBuilder: (_, i) {
            final row = items[i];
            final mm = row['recommendation_mm'];
            final created = (row['created_at'] ?? '').toString();
            final inputs = Map<String, dynamic>.from(row['inputs'] ?? {});
            final ok = row['confirmed'] == true ? '✓' : '—';
            return ListTile(
              title: Text('💧 $mm mm ($ok)'),
              subtitle: Text(
                [
                  if (inputs['et0_mm'] != null) 'ET₀: ${inputs['et0_mm']}',
                  if (inputs['temp_c'] != null) 'Temp: ${inputs['temp_c']} °C',
                  if (inputs['rainfall_forecast_mm'] != null) 'Rain: ${inputs['rainfall_forecast_mm']} mm',
                  if (inputs['soil_moisture_pct'] != null) 'Soil: ${inputs['soil_moisture_pct']} %',
                  created,
                ].join(' • '),
              ),
              isThreeLine: true,
            );
          },
        ),
      );
    } catch (e) {
      await _showCopyableDialog('Error', 'Failed to load history:\n$e');
    }
  }

  Future<void> _showCopyableDialog(String title, String body) {
    return showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(title),
        content: SelectableText(body),
        actions: [ TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK')) ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final body = () {
      if (loading && data == null && error == null) {
        return _Section(
          title: 'Preparing your recommendation…',
          child: Column(children: const [
            SizedBox(height: 8),
            CircularProgressIndicator(),
            SizedBox(height: 8),
            Text('Fetching weather & satellite soil moisture.'),
          ]),
        );
      }
      if (error != null) {
        return _Section(
          title: 'Could not fetch recommendation',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SelectableText(error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              const SizedBox(height: 8),
              OutlinedButton.icon(onPressed: _load, icon: const Icon(Icons.refresh), label: const Text('Retry')),
            ],
          ),
        );
      }
      if (data?['status'] == 'processing') {
        final eta = (data?['eta_minutes'] ?? 2).toString();
        final note = (data?['note'] ?? 'Data is being prepared…').toString();
        return _Section(
          title: 'We’re processing your field',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(note),
              const SizedBox(height: 8),
              Row(
                children: [
                  const Icon(Icons.hourglass_bottom, size: 18),
                  const SizedBox(width: 6),
                  Text('Check back in about $eta minute(s).'),
                ],
              ),
              const SizedBox(height: 8),
              OutlinedButton.icon(onPressed: _load, icon: const Icon(Icons.refresh), label: const Text('Refresh now')),
              const SizedBox(height: 8),
              _InfoBanner(
                text:
                  'Heads up: satellite updates can change over the next ~5 days. '
                  'If conditions shift, tap Refresh to fetch the latest.',
              ),
            ],
          ),
        );
      }

      // Ready
      final mm = (data?['recommendation_mm'] as num?)?.toDouble();
      final inputs = Map<String, dynamic>.from(data?['inputs'] ?? {});
      return Column(
        children: [
          _Section(
            title: 'Irrigation recommendation',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('💧 Apply: ${mm?.toStringAsFixed(1) ?? '--'} mm',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 12,
                  runSpacing: 8,
                  children: [
                    _Chip('Temp', '${inputs['temp_c'] ?? '--'} °C'),
                    _Chip('ET₀', '${inputs['et0_mm'] ?? '--'} mm'),
                    _Chip('Rain 24h', '${inputs['rainfall_forecast_mm'] ?? '--'} mm'),
                    _Chip('Soil', inputs['soil_moisture_pct'] == null ? 'satellite' : '${inputs['soil_moisture_pct']} %'),
                  ],
                ),
                const SizedBox(height: 8),
                _InfoBanner(
                  text:
                    'This recommendation uses recent weather and satellite soil moisture. '
                    'If conditions change (e.g. rain), tap Refresh to update.',
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          ElevatedButton.icon(onPressed: _confirm, icon: const Icon(Icons.check_circle), label: const Text('Confirm & Save')),
          const SizedBox(height: 8),
          OutlinedButton.icon(onPressed: _load, icon: const Icon(Icons.refresh), label: const Text('Refresh')),
          const SizedBox(height: 8),
          OutlinedButton(onPressed: _openHistory, child: const Text('History')),
        ],
      );
    }();

    return Scaffold(
      appBar: AppBar(title: Text(widget.fieldName.isEmpty ? 'Irrigation' : widget.fieldName)),
      body: ListView(padding: const EdgeInsets.all(12), children: [body]),
    );
  }
}

class _Section extends StatelessWidget {
  final String title;
  final Widget child;
  const _Section({required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          child,
        ]),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  final String label;
  final String value;
  const _Chip(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Chip(
      label: Text('$label: $value'),
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      side: BorderSide(color: Theme.of(context).dividerColor),
    );
  }
}

class _InfoBanner extends StatelessWidget {
  final String text;
  const _InfoBanner({required this.text});
  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity, padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.secondary.withOpacity(0.16),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(text),
    );
  }
}
