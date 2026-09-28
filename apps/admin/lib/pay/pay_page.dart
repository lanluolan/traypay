import 'dart:convert';
import 'dart:typed_data';
import 'package:barcode_scan2/barcode_scan2.dart';
import 'package:checkout_common/checkout_common.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import '../models/admin.dart';
import '../models/review_cart.dart';
import '../services/admin_api.dart';

class payPage extends StatefulWidget {
  final Admin user;
  const payPage(this.user, {super.key});
  @override
  State<payPage> createState() => _PayPageState();
}

class _PayPageState extends State<payPage> {
  final _cart = ReviewCart();
  Uint8List? _preview;
  double _width = 1, _height = 1;
  bool _busy = false;
  String _message = '拍摄托盘后，请核对每道菜和份数；漏识别的菜可以手动补录。';
  void _edit(VoidCallback action) => setState(() {
        action();
        _cart.trayConfirmed = false;
      });

  Future<void> _recognize() async {
    setState(() {
      _busy = true;
      _cart.clear();
      _preview = null;
      _message = '正在拍摄和识别…';
    });
    try {
      final image = await ImagePicker().pickImage(source: ImageSource.camera);
      if (!mounted) return;
      if (image == null) {
        setState(() => _message = '已取消拍摄，请重新拍摄或人工录单。');
        return;
      }
      final request = apiMultipart('$apiBase/admin/detect');
      request.files.add(await http.MultipartFile.fromPath('img', image.path));
      final body = await adminJson(request);
      if (!mounted) return;
      final items = (body['regions'] as List)
          .map((row) => ReviewItem.fromRegion(row as Map<String, dynamic>))
          .toList();
      setState(() {
        _cart.token = body['review_token'] as String;
        _cart.items.addAll(items);
        _preview = base64Decode(body['image_preview'] as String);
        _width = (body['image_width'] as num).toDouble();
        _height = (body['image_height'] as num).toDouble();
        _message = '红框需要选择菜品或明确忽略。请同时检查是否漏菜、份数是否正确。';
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _cart.clear();
          _preview = null;
          _message =
              e is AdminApiException ? e.message : '识别失败，请检查网络后重拍，或人工录单。';
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _manual() async {
    setState(() {
      _busy = true;
      _cart.clear();
      _preview = null;
    });
    try {
      final body =
          await adminJson(apiMultipart('$apiBase/admin/checkout/manual'));
      if (!mounted) return;
      setState(() {
        _cart.token = body['review_token'] as String;
        _message = '人工录单：添加托盘内的全部菜品，核对份数后确认。';
      });
    } catch (e) {
      if (mounted) setState(() => _message = '人工录单创建失败，请检查网络后重试。');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _choose([ReviewItem? item]) async {
    setState(() => _busy = true);
    try {
      final menu = await loadMenu();
      if (!mounted) return;
      final selected = await showModalBottomSheet<Map<String, dynamic>>(
        context: context,
        isScrollControlled: true,
        builder: (_) => _DishPicker(menu: menu),
      );
      if (selected == null || !mounted) return;
      _edit(() {
        if (item == null) {
          _cart.items.add(ReviewItem(dish: selected, confirmed: true));
        } else {
          item.select(selected);
        }
      });
    } catch (e) {
      if (mounted) setState(() => _message = '菜品列表加载失败，请检查网络后重试。');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _checkout() async {
    if (_busy || !_cart.canCheckout) return;
    setState(() => _busy = true);
    try {
      final scan = await BarcodeScanner.scan(
          options: const ScanOptions(
        strings: {'cancel': '取消', 'flash_on': '开启闪光灯', 'flash_off': '关闭闪光灯'},
      ));
      if (!mounted ||
          scan.type != ResultType.Barcode ||
          scan.rawContent.isEmpty) {
        return;
      }
      final request = apiMultipart('$apiBase/admin/purchase');
      request.fields.addAll({
        'u_id': scan.rawContent,
        'a_id': widget.user.a_id.toString(),
        'review_token': _cart.token!,
        'tray_confirmed': 'true',
        'review': jsonEncode(_cart.items.map((i) => i.toJson()).toList()),
        'total_price': _cart.total,
      });
      await adminJson(request);
      if (!mounted) return;
      setState(() {
        _cart.clear();
        _preview = null;
        _message = '支付成功，可以拍摄下一份托盘。';
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _cart.trayConfirmed = false;
          _message =
              e is AdminApiException ? e.message : '未能确认支付结果，请先查询消费记录，避免重复扣款。';
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: ListView(padding: const EdgeInsets.all(16), children: [
          Wrap(spacing: 12, children: [
            ElevatedButton(
                onPressed: _busy ? null : _recognize,
                child: const Text('拍照识别')),
            OutlinedButton(
                onPressed: _busy ? null : _manual, child: const Text('新建人工录单')),
          ]),
          if (_busy) const LinearProgressIndicator(),
          Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text(_message)),
          if (_preview != null)
            Center(
                child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: AspectRatio(
                  aspectRatio: _width / _height,
                  child: LayoutBuilder(
                    builder: (_, constraints) => Stack(children: [
                      Positioned.fill(
                          child: Image.memory(_preview!, fit: BoxFit.fill)),
                      for (final item
                          in _cart.items.where((i) => i.box != null))
                        Positioned(
                          left: item.box![0] / _width * constraints.maxWidth,
                          top: item.box![1] / _height * constraints.maxHeight,
                          width: (item.box![2] - item.box![0]) /
                              _width *
                              constraints.maxWidth,
                          height: (item.box![3] - item.box![1]) /
                              _height *
                              constraints.maxHeight,
                          child: Container(
                            decoration: BoxDecoration(
                                border: Border.all(
                                    color: item.ignored
                                        ? Colors.grey
                                        : item.resolved
                                            ? Colors.green
                                            : Colors.red,
                                    width: 3)),
                            alignment: Alignment.topLeft,
                            child: Container(
                                color: Colors.black87,
                                padding: const EdgeInsets.all(2),
                                child: Text('${item.regionId! + 1}',
                                    style:
                                        const TextStyle(color: Colors.white))),
                          ),
                        ),
                    ]),
                  )),
            )),
          for (final item in _cart.items) _itemCard(item),
          if (_cart.token != null) ...[
            OutlinedButton.icon(
                onPressed: _busy ? null : () => _choose(),
                icon: const Icon(Icons.add),
                label: const Text('补录菜品')),
            Text('合计 ¥${_cart.total} · ${_cart.portions} 份',
                style: const TextStyle(fontSize: 22)),
            CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('已核对整盘菜品和份数，确认没有漏菜'),
                value: _cart.trayConfirmed,
                onChanged: _busy || !_cart.resolved
                    ? null
                    : (v) => setState(() => _cart.trayConfirmed = v ?? false)),
            ElevatedButton(
                onPressed: !_busy && _cart.canCheckout ? _checkout : null,
                child: const Text('扫码收款')),
          ],
        ]),
      );

  Widget _itemCard(ReviewItem item) => Card(
          child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(
              '${item.regionId == null ? '补录' : '区域 ${item.regionId! + 1}'} · '
              '${item.ignored ? '已忽略' : item.dish?['c_name'] ?? (item.status == 'ambiguous' ? '相似菜待确认' : '未知菜待确认')}',
              style: TextStyle(
                  fontSize: 17, color: item.resolved ? null : Colors.red)),
          if (!item.resolved)
            Wrap(spacing: 8, children: [
              for (final dish in item.candidates)
                ActionChip(
                    label:
                        Text('${dish['c_name']} · 相似度 ${dish['similarity']}'),
                    onPressed:
                        _busy ? null : () => _edit(() => item.select(dish))),
            ]),
          Wrap(
              spacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                TextButton(
                    onPressed: _busy ? null : () => _choose(item),
                    child: const Text('选择 / 更换菜品')),
                if (item.dish != null) ...[
                  IconButton(
                      onPressed: _busy || item.quantity <= 1
                          ? null
                          : () => _edit(() => item.quantity--),
                      icon: const Icon(Icons.remove),
                      tooltip: '减少一份'),
                  Text('${item.quantity} 份 · ¥${item.dish!['c_price']}/份'),
                  IconButton(
                      onPressed: _busy || item.quantity >= 99
                          ? null
                          : () => _edit(() => item.quantity++),
                      icon: const Icon(Icons.add),
                      tooltip: '增加一份'),
                ],
                TextButton(
                    onPressed: _busy || item.ignored
                        ? null
                        : () => _edit(() {
                              if (item.regionId == null) {
                                _cart.items.remove(item);
                              } else {
                                item.ignore();
                              }
                            }),
                    child: Text(item.regionId == null ? '移除' : '忽略此区域')),
              ]),
        ]),
      ));
}

class _DishPicker extends StatefulWidget {
  final List<Map<String, dynamic>> menu;
  const _DishPicker({required this.menu});
  @override
  State<_DishPicker> createState() => _DishPickerState();
}

class _DishPickerState extends State<_DishPicker> {
  String _query = '';
  @override
  Widget build(BuildContext context) {
    final rows = widget.menu
        .where((c) => c['c_name'].toString().contains(_query))
        .toList();
    return SafeArea(
        child: SizedBox(
      height: MediaQuery.of(context).size.height * .75,
      child: Padding(
        padding:
            EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
        child: Column(children: [
          Padding(
              padding: const EdgeInsets.all(16),
              child: TextField(
                  decoration: const InputDecoration(labelText: '搜索菜品'),
                  onChanged: (v) => setState(() => _query = v.trim()))),
          Expanded(
              child: rows.isEmpty
                  ? const Center(child: Text('没有匹配的菜品'))
                  : ListView.builder(
                      itemCount: rows.length,
                      itemBuilder: (_, index) => ListTile(
                          title: Text(rows[index]['c_name'].toString()),
                          trailing: Text('¥${rows[index]['c_price']}'),
                          onTap: () =>
                              Navigator.of(context).pop(rows[index])))),
        ]),
      ),
    ));
  }
}
