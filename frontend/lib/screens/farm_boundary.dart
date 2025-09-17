import 'dart:convert';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;

import '../config.dart';

/// --- Area thresholds (adjust as needed) ---
const double kMinAcres = 1.0;
const double kMaxAcres = 5.0;

/// Earth radius in meters
const double _earthR = 6378137.0;

/// Compute polygon area on a sphere (m²), expects LatLng WGS84
double polygonAreaSqMeters(List<LatLng> pts) {
  if (pts.length < 3) return 0.0;

  // close ring
  final ring = <LatLng>[...pts];
  if (ring.first.latitude != ring.last.latitude ||
      ring.first.longitude != ring.last.longitude) {
    ring.add(ring.first);
  }

  // Spherical excess approximation (good for field sizes)
  double sum = 0.0;
  for (int i = 0; i < ring.length - 1; i++) {
    final p1 = ring[i];
    final p2 = ring[i + 1];
    final lon1 = p1.longitude * (math.pi / 180.0);
    final lon2 = p2.longitude * (math.pi / 180.0);
    final lat1 = p1.latitude * (math.pi / 180.0);
    final lat2 = p2.latitude * (math.pi / 180.0);
    sum += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2));
  }
  final area = (sum * _earthR * _earthR / 2.0).abs();
  return area.isFinite ? area : 0.0;
}

double sqmToHectares(double sqm) => sqm / 10000.0;
double sqmToAcres(double sqm) => sqm / 4046.8564224;

/// Minimal API client for this screen (uses AppConfig base URL)
class _ApiClient {
  final String base = AppConfig.apiBaseUrl;
  Future<Map<String, dynamic>> postJson(String path, Map<String, dynamic> body) async {
    final uri = Uri.parse('$base$path');
    final r = await http.post(uri, headers: {'Content-Type': 'application/json'}, body: json.encode(body));
    if (r.statusCode >= 400) {
      throw Exception('POST $path failed: ${r.statusCode} ${r.body}');
    }
    return json.decode(r.body) as Map<String, dynamic>;
  }
}

/// Repo to save field polygon (optional crop)
class _FieldRepository {
  final _ApiClient api;
  _FieldRepository(this.api);

  Future<String> saveField({
    required Map<String, dynamic> geometry,
    String? crop,
  }) async {
    final payload = <String, dynamic>{
      'geometry': geometry,
      if (crop != null && crop.isNotEmpty) 'crop': crop,
    };
    final res = await api.postJson('/fields', payload);
    return (res['id'] ?? '').toString();
  }
}

/// Simple crop option model (icon + key + label)
class _CropOption {
  final String key;    // value sent to backend, e.g. "wheat"
  final String label;  // localized label to show
  final String icon;   // emoji or one-char icon
  const _CropOption(this.key, this.label, this.icon);
}

/// Configure the crops you care about (keys should match backend Kc presets)
const List<_CropOption> _cropOptions = [
  _CropOption('wheat',     'Wheat',      '🌾'),
  _CropOption('rice',      'Rice',       '🌴'),
  _CropOption('maize',     'Maize',      '🌽'),
  _CropOption('cotton',    'Cotton',     '🧵'),
  _CropOption('sugarcane', 'Sugarcane',  '🟩'),
  _CropOption('vegetable', 'Vegetables', '🥬'),
  _CropOption('orchard',   'Orchard',    '🌳'),
  _CropOption('fallow',    'Fallow',     '🟫'),
];

class FarmBoundaryScreen extends StatefulWidget {
  const FarmBoundaryScreen({super.key});
  @override
  State<FarmBoundaryScreen> createState() => _FarmBoundaryScreenState();
}

class _FarmBoundaryScreenState extends State<FarmBoundaryScreen> {
  final _mapController = MapController();
  final _repo = _FieldRepository(_ApiClient());

  final List<LatLng> _points = [];
  double _areaSqm = 0.0;
  bool _saving = false;
  LatLng _center = const LatLng(33.705, 72.905); // fallback

  @override
  void initState() {
    super.initState();
    _initLocation();
  }

  Future<void> _initLocation() async {
    try {
      final enabled = await Geolocator.isLocationServiceEnabled();
      if (!enabled) return;
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
      }
      if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) return;
      final pos = await Geolocator.getCurrentPosition(desiredAccuracy: LocationAccuracy.medium);
      setState(() => _center = LatLng(pos.latitude, pos.longitude));
    } catch (_) {}
  }

  bool get _hasPolygon => _points.length >= 3;

  void _recalcArea() {
    _areaSqm = polygonAreaSqMeters(_points);
    setState(() {});
  }

  void _addPoint(LatLng p) {
    _points.add(p);
    _recalcArea();
  }

  void _undo() {
    if (_points.isNotEmpty) {
      _points.removeLast();
      _recalcArea();
    }
  }

  void _clear() {
    _points.clear();
    _recalcArea();
  }

  Map<String, dynamic> _toGeoJsonPolygon(List<LatLng> pts) {
    final coords = pts.map((p) => [p.longitude, p.latitude]).toList();
    if (coords.isEmpty || coords.first[0] != coords.last[0] || coords.first[1] != coords.last[1]) {
      if (coords.isNotEmpty) coords.add([coords.first[0], coords.first[1]]);
    }
    return {"type": "Polygon", "coordinates": [coords]};
  }

  Future<void> _savePolygon() async {
    if (!_hasPolygon) {
      await _showDialog('Validation', 'Add at least 3 points to make a boundary.');
      return;
    }
    final acres = sqmToAcres(_areaSqm);
    if (acres < kMinAcres || acres > kMaxAcres) {
      await _showDialog(
        'Area out of range',
        'Current: ${acres.toStringAsFixed(2)} acres\n'
        'Allowed: ${kMinAcres.toStringAsFixed(1)}–${kMaxAcres.toStringAsFixed(1)} acres',
      );
      return;
    }

    // 🔽 NEW: optional crop picker (icons + names). Farmer may Skip.
    final selectedCrop = await _pickCrop();
    // selectedCrop is null if skipped.

    setState(() => _saving = true);
    try {
      final gj = _toGeoJsonPolygon(_points);
      final fieldId = await _repo.saveField(
        geometry: gj,
        crop: selectedCrop, // null if skipped
      );
      if (!mounted) return;

      await showDialog(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Field Saved'),
          content: SelectableText(
            'ID: $fieldId\n'
            'Area: ${sqmToHectares(_areaSqm).toStringAsFixed(3)} ha '
            '(${acres.toStringAsFixed(2)} acres)\n'
            'Crop: ${selectedCrop ?? "(not set)"}',
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(context);           // close dialog
                Navigator.pop(context, fieldId);  // return fieldId to caller
              },
              child: const Text('Continue'),
            ),
          ],
        ),
      );
    } catch (e) {
      await _showDialog('Error', e.toString(), copyable: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  /// Crop picker bottom sheet. Returns the crop key (e.g., "wheat") or null if skipped.
  Future<String?> _pickCrop() async {
    return await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: false,
      builder: (_) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(height: 10),
              Text('Select Crop (optional)', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 10),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Wrap(
                  spacing: 10, runSpacing: 10,
                  children: _cropOptions.map((c) {
                    return SizedBox(
                      width: 100,
                      child: OutlinedButton(
                        onPressed: () => Navigator.pop(context, c.key),
                        style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 10)),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(c.icon, style: const TextStyle(fontSize: 28)),
                            const SizedBox(height: 4),
                            Text(c.label, textAlign: TextAlign.center),
                          ],
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: () => Navigator.pop(context, null),
                child: const Text('Skip'),
              ),
              const SizedBox(height: 8),
            ],
          ),
        );
      },
    );
  }

  Future<void> _showDialog(String title, String body, {bool copyable = false}) async {
    return showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(title),
        content: copyable ? SelectableText(body) : Text(body),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final poly = _hasPolygon
        ? Polygon(
            points: _points,
            color: Colors.green.withOpacity(0.2),
            borderColor: Colors.green.shade800,
            borderStrokeWidth: 3,
          )
        : null;

    return Scaffold(
      appBar: AppBar(title: const Text('Draw Field Boundary')),
      body: Stack(
        children: [
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: _center,
              initialZoom: 15,
              onTap: (tapPos, latLng) => _addPoint(latLng),
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.doordars.agro_assist',
              ),
              if (poly != null) PolygonLayer(polygons: [poly]),
              MarkerLayer(
                markers: _points
                    .map((p) => Marker(
                          point: p,
                          width: 16,
                          height: 16,
                          child: Container(
                            decoration: BoxDecoration(
                              color: Colors.green,
                              border: Border.all(color: Colors.white, width: 2),
                              shape: BoxShape.circle,
                            ),
                          ),
                        ))
                    .toList(),
              ),
            ],
          ),

          // Live area chip
          Positioned(
            left: 12, top: 12,
            child: Card(
              color: Colors.white, elevation: 2,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                child: Text(
                  () {
                    final ha = sqmToHectares(_areaSqm);
                    final ac = sqmToAcres(_areaSqm);
                    return 'Area: ${ha.toStringAsFixed(3)} ha • ${ac.toStringAsFixed(2)} ac';
                  }(),
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              ),
            ),
          ),

          // Controls
          Positioned(
            left: 12, right: 12, bottom: 12,
            child: Card(
              elevation: 2,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                child: Row(
                  children: [
                    IconButton(
                      tooltip: 'Undo last point',
                      onPressed: _points.isEmpty ? null : _undo,
                      icon: const Icon(Icons.undo),
                    ),
                    IconButton(
                      tooltip: 'Clear',
                      onPressed: _points.isEmpty ? null : _clear,
                      icon: const Icon(Icons.delete_outline),
                    ),
                    const Spacer(),
                    ElevatedButton.icon(
                      onPressed: _saving ? null : _savePolygon,
                      icon: const Icon(Icons.save),
                      label: Text(_saving ? 'Saving…' : 'Save'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
