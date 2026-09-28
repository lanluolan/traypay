import 'dart:convert';

import 'package:checkout_common/checkout_common.dart';
import 'package:flutter/material.dart';
import 'package:fluttertoast/fluttertoast.dart';

import '../models/admin.dart';
import 'add_food.dart';
import '../services/admin_api.dart';

/// 菜品库：列出、改价改名、下架、上新。
class Mine extends StatefulWidget {
  final Admin user;

  const Mine(this.user, {Key? key}) : super(key: key);

  @override
  State<Mine> createState() => _MineState();
}

class _MineState extends State<Mine> {
  List _cuisines = [];
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _priceController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadCuisines();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _priceController.dispose();
    super.dispose();
  }

  Future<void> _loadCuisines() async {
    try {
      final rows = await loadMenu();
      if (mounted) setState(() => _cuisines = rows);
    } catch (e) {
      if (mounted) _toast('菜品列表加载失败，请重试');
    }
  }

  Future<void> _modify(int cId, String name, String price) async {
    final request = apiMultipart('$apiBase/cuisine/modify');
    request.fields.addAll({
      'c_id': cId.toString(),
      'c_name': name,
      'c_price': price,
    });
    final response = await sendApi(request);
    if (response.statusCode != 200 || !mounted) return;
    final body = json.decode(
      await response.stream.transform(utf8.decoder).join(),
    );
    if (!mounted) return;
    if (body["code"] == 0) {
      _toast("修改成功");
    } else {
      _toast(body["message"]?.toString() ?? "修改失败");
    }
    await _loadCuisines();
  }

  Future<void> _delete(int cId) async {
    final request = apiMultipart('$apiBase/cuisine/delete');
    request.fields.addAll({'c_id': cId.toString()});
    final response = await sendApi(request);
    if (response.statusCode != 200 || !mounted) return;
    final body = json.decode(
      await response.stream.transform(utf8.decoder).join(),
    );
    if (!mounted) return;

    // code 2 = 这道菜有消费记录，后端拒绝删除以保住财务历史（ISSUES.md B6）。
    // 一定要把这条原因说出来，否则收银员只看到"删了没反应"。
    if (body["code"] == 0) {
      _toast("已下架");
    } else if (body["code"] == 2) {
      _toast("该菜品已有消费记录，无法删除");
    } else {
      _toast("菜品不存在");
    }
    await _loadCuisines();
  }

  void _toast(String message) {
    Fluttertoast.showToast(
      msg: message,
      toastLength: Toast.LENGTH_SHORT,
      gravity: ToastGravity.BOTTOM,
      timeInSecForIosWeb: 1,
      textColor: Colors.black54,
      fontSize: 16.0,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0x6FF3F3F4),
      body: Column(
        children: [
          const SizedBox(height: 25.0),
          Expanded(child: _buildCard()),
        ],
      ),
    );
  }

  Widget _buildCard() {
    return Card(
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(10.0)),
      ),
      elevation: 5,
      margin: const EdgeInsets.only(left: 20, right: 20, top: 7, bottom: 7),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                margin: const EdgeInsets.only(
                  left: 10,
                  bottom: 10,
                  top: 10,
                  right: 10,
                ),
                height: 20,
                width: 6,
                color: Colors.lightBlueAccent,
              ),
              const Text('菜品库', style: TextStyle(fontSize: 20)),
              Expanded(
                child: Container(
                  margin: const EdgeInsets.fromLTRB(0, 0, 10, 0),
                  alignment: Alignment.centerRight,
                  child: IconButton(
                    onPressed: () async {
                      final added = await Navigator.of(context).push<bool>(
                        MaterialPageRoute(builder: (_) => const add_Food()),
                      );
                      if (added == true) await _loadCuisines();
                    },
                    color: Colors.blue,
                    icon: const Icon(Icons.add),
                    tooltip: '上新',
                  ),
                ),
              ),
            ],
          ),
          Divider(color: Colors.grey.shade200, thickness: 1, height: 1),
          Expanded(
            child: _cuisines.isEmpty
                ? const Center(
                    child: Text(
                      '菜品库是空的，点右上角 + 上新',
                      style: TextStyle(color: Colors.grey),
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.all(10.0),
                    itemCount: _cuisines.length,
                    itemBuilder: (context, i) => _buildRow(_cuisines[i]),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildRow(dynamic cuisine) {
    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(cuisine["c_name"], style: const TextStyle(fontSize: 18)),
            Text(
              "￥${cuisine["c_price"]}",
              style: const TextStyle(fontSize: 18),
            ),
          ],
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            TextButton(
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) =>
                    add_Food(cuisine: Map<String, dynamic>.from(cuisine)),
              )),
              child: const Text('补拍 / 样本管理'),
            ),
            SizedBox(
              height: 33,
              child: TextButton(
                onPressed: () => _showEditDialog(cuisine),
                child: Text(
                  "修改 >",
                  style: TextStyle(color: Colors.grey.shade400),
                ),
              ),
            ),
          ],
        ),
        Divider(color: Colors.grey.shade200, thickness: 1, height: 1),
      ],
    );
  }

  Future<void> _showEditDialog(dynamic cuisine) async {
    _nameController.text = cuisine["c_name"];
    _priceController.text = cuisine["c_price"].toString();

    await showDialog<void>(
      barrierDismissible: true,
      context: context,
      builder: (dialogContext) => AlertDialog(
        elevation: 10,
        backgroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        icon: const Icon(Icons.fastfood_rounded, size: 40, color: Colors.blue),
        content: Padding(
          padding: const EdgeInsets.all(8.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: _nameController,
                decoration: const InputDecoration(
                  labelText: '菜品名称',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 20),
              TextField(
                controller: _priceController,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: const InputDecoration(
                  labelText: '价格',
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
        ),
        contentTextStyle: const TextStyle(color: Colors.black),
        actions: [
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                // 下架不可逆，先确认一次。
                final confirmed = await _confirmDelete(cuisine["c_name"]);
                if (confirmed) await _delete(cuisine["c_id"]);
              },
              child: const Text('删除'),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: ElevatedButton(
              onPressed: () {
                final price = _priceController.text.trim();
                if (double.tryParse(price) == null) {
                  _toast("请输入正确的价格");
                  return;
                }
                Navigator.of(dialogContext).pop();
                _modify(cuisine["c_id"], _nameController.text.trim(), price);
              },
              child: const Text('确定'),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: ElevatedButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('取消'),
            ),
          ),
        ],
      ),
    );
  }

  Future<bool> _confirmDelete(String name) async {
    final result = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('确认下架'),
        content: Text('下架「$name」后菜品库里就没有它了，确定吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('确定下架'),
          ),
        ],
      ),
    );
    return result ?? false;
  }
}
