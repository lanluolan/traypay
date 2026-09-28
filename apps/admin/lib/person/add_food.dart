import 'dart:convert';
import 'dart:typed_data';
import 'package:checkout_common/checkout_common.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:image_picker/image_picker.dart';
import '../services/admin_api.dart';

/// New-dish enrollment and existing-dish sample maintenance share the same
/// preview/confirmation flow. Only confirmed PNG crops are uploaded.
class add_Food extends StatefulWidget {
  final Map<String, dynamic>? cuisine;
  const add_Food({super.key, this.cuisine});
  @override
  State<add_Food> createState() => _AddFoodState();
}

class _AddFoodState extends State<add_Food> {
  final _images = <Uint8List>[];
  final _name = TextEditingController();
  final _price = TextEditingController();
  List<Map<String, dynamic>> _samples = [];
  bool _busy = false;
  String _message = '';
  int? get _id => widget.cuisine?['c_id'] as int?;

  @override
  void initState() {
    super.initState();
    if (_id != null) _refresh();
  }

  @override
  void dispose() {
    _name.dispose();
    _price.dispose();
    super.dispose();
  }

  Future<void> _loadSamples() async {
    final body =
        await adminJson(apiRequest('GET', '$apiBase/cuisine/$_id/samples'));
    if (mounted) {
      setState(() =>
          _samples = (body['samples'] as List).cast<Map<String, dynamic>>());
    }
  }

  Future<void> _refresh() async {
    setState(() => _busy = true);
    try {
      await _loadSamples();
    } catch (e) {
      if (mounted) setState(() => _message = '样本加载失败，请刷新重试。');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pick(bool camera) async {
    setState(() {
      _busy = true;
      _message = '正在准备照片，请逐张确认菜品区域。';
    });
    try {
      final picker = ImagePicker();
      final List<XFile> picked;
      if (camera) {
        final photo = await picker.pickImage(source: ImageSource.camera);
        picked = photo == null ? [] : [photo];
      } else {
        picked = await picker.pickMultiImage();
      }
      for (final photo in picked) {
        if (!mounted) return;
        if (_images.length >= 20) {
          setState(() => _message = '每次最多提交 20 张照片。');
          break;
        }
        final request = apiMultipart('$apiBase/cuisine/samples/preview');
        request.files.add(await http.MultipartFile.fromPath('img', photo.path));
        final body = await adminJson(request);
        if (!mounted) return;
        final original = base64Decode(body['original'] as String);
        final crop = base64Decode(body['crop'] as String);
        final selected = await showDialog<Uint8List>(
          context: context,
          barrierDismissible: false,
          builder: (_) => _CropConfirmation(original: original, crop: crop),
        );
        if (!mounted) return;
        if (selected != null) setState(() => _images.add(selected));
      }
      if (mounted && _images.length < 20) {
        setState(() => _message = '已确认 ${_images.length} 张照片，点击下方按钮保存。');
      }
    } catch (e) {
      if (mounted) {
        setState(() =>
            _message = e is AdminApiException ? e.message : '照片处理失败，请检查网络后重试。');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    if (_images.isEmpty) {
      setState(() => _message = '请先选择照片并确认裁剪区域。');
      return;
    }
    final price = double.tryParse(_price.text.trim());
    if (_id == null &&
        (_name.text.trim().isEmpty ||
            _name.text.trim().length > 20 ||
            price == null ||
            !price.isFinite ||
            price < 0 ||
            price > 9999.99)) {
      setState(() => _message = '请输入 1–20 字的菜名和 0–9999.99 的价格。');
      return;
    }
    setState(() => _busy = true);
    try {
      final request = apiMultipart(_id == null
          ? '$apiBase/cuisine/add'
          : '$apiBase/cuisine/$_id/samples');
      request.fields['crops_confirmed'] = 'true';
      if (_id == null) {
        request.fields['c_name'] = _name.text.trim();
        request.fields['c_price'] = _price.text.trim();
      }
      for (var i = 0; i < _images.length; i++) {
        request.files.add(http.MultipartFile.fromBytes('img', _images[i],
            filename: 'sample_$i.png', contentType: MediaType('image', 'png')));
      }
      final body = await adminJson(request);
      if (!mounted) return;
      setState(() {
        _images.clear();
        _message = '样本已保存，识别特征已更新。';
      });
      final conflicts = body['conflicts'] as List? ?? [];
      if (conflicts.isNotEmpty) {
        await showDialog<void>(
            context: context,
            builder: (dialogContext) => AlertDialog(
                  title: const Text('样本已保存，请关注相似菜品'),
                  content: SingleChildScrollView(
                      child: Text(conflicts
                          .map((c) =>
                              '${c['c_name'] ?? c['dish_id']} · 相似度 ${(c['similarity'] as num).toStringAsFixed(3)}')
                          .join('\n'))),
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.of(dialogContext).pop(),
                        child: const Text('知道了'))
                  ],
                ));
      }
      if (!mounted) return;
      if (_id == null) {
        Navigator.of(context).pop(true);
      } else {
        await _loadSamples();
      }
    } catch (e) {
      if (mounted) {
        setState(() => _message =
            e is AdminApiException ? e.message : '未能确认保存结果，请刷新样本列表后再操作。');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete(Map<String, dynamic> sample) async {
    final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
              title: const Text('删除这张样本？'),
              content: const Text('识别特征将根据剩余照片重新生成。至少保留一张样本。'),
              actions: [
                TextButton(
                    onPressed: () => Navigator.of(dialogContext).pop(false),
                    child: const Text('取消')),
                TextButton(
                    onPressed: () => Navigator.of(dialogContext).pop(true),
                    child: const Text('删除')),
              ],
            ));
    if (confirmed != true || !mounted) return;
    setState(() => _busy = true);
    try {
      await adminJson(apiRequest(
          'DELETE', '$apiBase/cuisine/$_id/samples/${sample['id']}'));
      if (!mounted) return;
      setState(() => _message = '样本已删除，识别特征已更新。');
      await _loadSamples();
    } catch (e) {
      if (mounted) {
        setState(() =>
            _message = e is AdminApiException ? e.message : '未能确认删除结果，请刷新后检查。');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
            title: Text(
                _id == null ? '添加菜品' : '${widget.cuisine!['c_name']} · 样本管理')),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          if (_busy) const LinearProgressIndicator(),
          if (_id == null) ...[
            TextField(
                controller: _name,
                enabled: !_busy,
                maxLength: 20,
                decoration: const InputDecoration(labelText: '菜品名称')),
            TextField(
                controller: _price,
                enabled: !_busy,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: '价格')),
          ],
          if (_id != null) ...[
            Row(children: [
              Expanded(child: Text('已保存样本（${_samples.length}）')),
              IconButton(
                  onPressed: _busy ? null : _refresh,
                  icon: const Icon(Icons.refresh),
                  tooltip: '刷新样本')
            ]),
            Wrap(spacing: 12, runSpacing: 12, children: [
              for (final sample in _samples)
                SizedBox(
                    width: 140,
                    child: Column(children: [
                      Image.network('$apiBase${sample['url']}',
                          headers: AuthSession.headers,
                          width: 140,
                          height: 120,
                          fit: BoxFit.contain,
                          errorBuilder: (_, __, ___) => const SizedBox(
                              height: 120,
                              child: Center(child: Text('图片加载失败')))),
                      Text(sample['confirmed_crop'] == true ? '已确认裁剪' : '历史照片'),
                      TextButton(
                          onPressed: _busy ? null : () => _delete(sample),
                          child: const Text('删除样本')),
                    ])),
            ]),
          ],
          const SizedBox(height: 16),
          const Text('补充不同角度、份量和现场光照的照片。每张照片只保留目标菜品；确认后才会保存。'),
          Wrap(spacing: 12, children: [
            OutlinedButton.icon(
                onPressed: _busy ? null : () => _pick(true),
                icon: const Icon(Icons.camera_alt),
                label: const Text('拍照')),
            OutlinedButton.icon(
                onPressed: _busy ? null : () => _pick(false),
                icon: const Icon(Icons.photo_library),
                label: const Text('从相册选择')),
          ]),
          Text('待保存照片（${_images.length}）'),
          Wrap(spacing: 12, runSpacing: 12, children: [
            for (var i = 0; i < _images.length; i++)
              SizedBox(
                  width: 140,
                  child: Column(children: [
                    Image.memory(_images[i],
                        width: 140, height: 120, fit: BoxFit.contain),
                    TextButton(
                        onPressed: _busy
                            ? null
                            : () => setState(() => _images.removeAt(i)),
                        child: const Text('移除')),
                  ])),
          ]),
          Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text(_message)),
          ElevatedButton(
              onPressed: _busy || _images.isEmpty ? null : _save,
              child: Text(_id == null ? '确认照片并添加菜品' : '保存补拍照片并更新识别')),
        ]),
      );
}

class _CropConfirmation extends StatefulWidget {
  final Uint8List original, crop;
  const _CropConfirmation({required this.original, required this.crop});
  @override
  State<_CropConfirmation> createState() => _CropConfirmationState();
}

class _CropConfirmationState extends State<_CropConfirmation> {
  bool _whole = false;
  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('确认用于识别的菜品区域'),
        content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text('请确认图片完整包含目标菜品，没有其他菜。区域不合适时，可使用仅含一道菜的整图，或跳过重拍。'),
          const SizedBox(height: 12),
          Image.memory(_whole ? widget.original : widget.crop,
              height: 240, fit: BoxFit.contain),
          SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('使用整张照片'),
              value: _whole,
              onChanged: (v) => setState(() => _whole = v)),
        ])),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('跳过 / 重拍')),
          ElevatedButton(
              onPressed: () => Navigator.of(context)
                  .pop(_whole ? widget.original : widget.crop),
              child: const Text('确认这张照片')),
        ],
      );
}
