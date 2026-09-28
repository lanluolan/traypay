import 'dart:convert';

import 'package:checkout_common/checkout_common.dart';
import 'package:flutter/material.dart';

import '../models/admin.dart';

/// 食堂端首页：月/日销售额与售出份数明细。
class HomePage extends StatefulWidget {
  final Admin user;
  final String password;

  const HomePage(this.user, this.password, {super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  /// 查询年份。日期选择器与查询共用它，闰年天数自动跟着正确。
  /// 原先钉死在 2023，见 ISSUES.md B5。
  static final int queryYear = DateTime.now().year;

  String _subtitle = "";
  String _monthPrice = "0";
  String _dayPrice = "0";

  /// 售出明细，每项含 c_name / count。
  List _cuisines = [];

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _subtitle = "${now.month}月";
    _loadMonth(now.month);
    _loadDay(now.month, now.day);
  }

  Future<void> _loadMonth(int month) async {
    final request = apiRequest(
      'GET',
      '$apiBase/admin/query/data/month/${widget.user.a_id}'
          '/$queryYear-$month-1/1',
    );
    final response = await sendApi(request);
    if (response.statusCode != 200) return;
    final body = json.decode(
      await response.stream.transform(utf8.decoder).join(),
    );
    if (!mounted) return;

    setState(() {
      _subtitle = "$month月";
      if (body["code"] == 0) {
        _cuisines = body["cuisine"];
        _monthPrice = body["total_price"].toString();
      } else {
        _cuisines = [];
        _monthPrice = "0";
      }
    });
  }

  Future<void> _loadDay(int month, int day) async {
    final request = apiRequest(
      'GET',
      '$apiBase/admin/query/data/day/${widget.user.a_id}'
          '/$queryYear-$month-$day/1',
    );
    final response = await sendApi(request);
    if (response.statusCode != 200) return;
    final body = json.decode(
      await response.stream.transform(utf8.decoder).join(),
    );
    if (!mounted) return;

    setState(() {
      _subtitle = "$month月$day日";
      if (body["code"] == 0) {
        _cuisines = body["cuisine"];
        _dayPrice = body["total_price"].toString();
      } else {
        _cuisines = [];
        _dayPrice = "0";
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0x6FF3F3F4),
      body: Column(
        children: [
          _buildHeader(),
          const SizedBox(height: 5.0),
          MonthDayPicker(
            year: queryYear,
            onMonthChanged: _loadMonth,
            onDayChanged: _loadDay,
          ),
          Expanded(child: _buildCard()),
        ],
      ),
    );
  }

  Widget _buildHeader() {
    return Stack(
      children: [
        Container(
          color: Colors.lightBlueAccent,
          width: double.infinity,
          height: 150,
        ),
        Positioned(
          top: 26,
          left: 10,
          child: Text(
            "hi,${widget.user.a_store_name}",
            style: const TextStyle(
              color: Colors.white,
              decoration: TextDecoration.none,
              fontSize: 22,
            ),
          ),
        ),
        Positioned(
          top: 57,
          left: 0,
          right: 0,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _buildFigure("月销售额:", _monthPrice),
              _buildFigure("日销售额:", _dayPrice),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildFigure(String label, String value) {
    return Column(
      children: [
        Text(
          label,
          style: const TextStyle(
            color: Colors.white,
            decoration: TextDecoration.none,
            fontSize: 18,
          ),
        ),
        Text(
          "￥$value",
          style: const TextStyle(
            color: Colors.white,
            decoration: TextDecoration.none,
            fontSize: 35,
          ),
        ),
      ],
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
              const Text('销售记录', style: TextStyle(fontSize: 20)),
              Expanded(
                child: Container(
                  margin: const EdgeInsets.fromLTRB(0, 0, 10, 0),
                  alignment: Alignment.centerRight,
                  child: Text(
                    _subtitle,
                    style: const TextStyle(color: Color(0xff999999)),
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
                      '该时段没有销售记录',
                      style: TextStyle(color: Colors.grey),
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.all(10.0),
                    itemExtent: 40.0,
                    itemCount: _cuisines.length,
                    itemBuilder: (context, i) => Column(
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              _cuisines[i]["c_name"],
                              style: const TextStyle(fontSize: 18),
                            ),
                            Text(
                              "${_cuisines[i]["count"]}份",
                              style: const TextStyle(fontSize: 18),
                            ),
                          ],
                        ),
                        Divider(
                          color: Colors.grey.shade200,
                          thickness: 1,
                          height: 1,
                        ),
                      ],
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}
