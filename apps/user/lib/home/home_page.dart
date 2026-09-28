import 'dart:convert';

import 'package:checkout_common/checkout_common.dart';
import 'package:flutter/material.dart';
import 'package:pay_system/home/home_load.dart';

import '../models/user.dart';

/// 顾客首页：余额 + 充值 + 按月/日筛选的消费记录。
class HomePage extends StatefulWidget {
  final User user;
  final String password;

  const HomePage(this.user, this.password, {Key? key}) : super(key: key);

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  /// 查询年份。日期选择器与查询共用它，改一处即可，闰年天数自动跟着正确。
  ///
  /// 原先钉死在 2023（后端演示数据都在那一年）。改成当年之后，库里没有当年
  /// 数据时界面会是空的 —— 那是正确表现，不是 bug。见 ISSUES.md B5。
  static final int queryYear = DateTime.now().year;

  int _monthShown = 0;
  double _monthTotal = 0;
  String _money = "";

  /// 消费记录列表，每项含 r_create_time / a_store_name / total_price。
  List _costs = [];

  /// r_create_time -> 该笔的菜品明细，点「详情」时用。
  final Map<String, dynamic> _details = {};

  final TextEditingController _rechargeController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _monthShown = DateTime.now().month;
    _money = widget.user.u_money;
    _loadMonth(_monthShown);
    _refreshBalance();
  }

  @override
  void dispose() {
    _rechargeController.dispose();
    super.dispose();
  }

  /// 重新登录一次以拿到最新余额。
  ///
  /// 后端没有「查我的余额」接口，登录响应里的 u_money 是唯一来源。顺带换一个
  /// 新 token，会话时钟因此重新计时，不会用着用着突然过期。
  Future<void> _refreshBalance() async {
    final request = apiMultipart('$apiBase/user/login');
    request.fields.addAll({
      'u_name': widget.user.u_name,
      'u_password': widget.password,
    });
    final response = await sendApi(request);
    if (response.statusCode != 200) return;
    final body = json.decode(
      await response.stream.transform(utf8.decoder).join(),
    );
    if (!mounted || body["code"] != 0) return;
    AuthSession.begin(body["token"]);
    setState(() => _money = User.fromJson(body["data"]).u_money);
  }

  /// 拉全部记录后按月过滤。
  ///
  /// 后端 `/user/query/record/all` 一页只回 10 条且不按月过滤，所以这里拿到
  /// 什么就过滤什么 —— 记录多于 10 条时当月合计会偏小。真要修得让后端支持按
  /// 月查询，或在这里翻页拉完。
  Future<void> _loadMonth(int month) async {
    final request = apiRequest(
      'GET',
      '$apiBase/user/query/record/all/${widget.user.u_id}/1',
    );
    final response = await sendApi(request);
    if (response.statusCode != 200) return;
    final body = json.decode(
      await response.stream.transform(utf8.decoder).join(),
    );
    if (!mounted) return;

    if (body["code"] != 0) {
      setState(() {
        _costs = [];
        _monthTotal = 0;
      });
      return;
    }

    final List matched = [];
    double total = 0;
    for (final row in body["record"]) {
      if (DateTime.parse(row["r_create_time"]).month != month) continue;
      matched.add(row);
      total += double.parse(row["total_price"].toString());
    }
    setState(() {
      _costs = matched;
      _monthTotal = total;
    });
    for (final row in matched) {
      _loadDetail(row["r_create_time"]);
    }
  }

  /// 查某一天的记录。
  ///
  /// 后端的区间查询是闭区间且比较的是 DateTime，所以结束日期传次日零点才能
  /// 覆盖整天。用 DateTime 加一天而不是 `day + 1`，跨月/跨年才不会出错。
  Future<void> _loadDay(int month, int day) async {
    final start = DateTime(queryYear, month, day);
    final end = start.add(const Duration(days: 1));
    String fmt(DateTime d) => '${d.year}-${d.month}-${d.day}';

    final request = apiRequest(
      'GET',
      '$apiBase/user/query/record/range/${widget.user.u_id}'
          '/${fmt(start)}/${fmt(end)}/1',
    );
    final response = await sendApi(request);
    if (response.statusCode != 200) return;
    final body = json.decode(
      await response.stream.transform(utf8.decoder).join(),
    );
    if (!mounted) return;

    setState(() => _costs = body["code"] == 0 ? body["record"] : []);
    for (final row in _costs) {
      _loadDetail(row["r_create_time"]);
    }
  }

  Future<void> _loadDetail(String date) async {
    final request = apiRequest(
      'GET',
      '$apiBase/user/query/record/detail/${widget.user.u_id}/$date',
    );
    final response = await sendApi(request);
    if (response.statusCode != 200) return;
    final body = json.decode(
      await response.stream.transform(utf8.decoder).join(),
    );
    if (!mounted) return;
    setState(() => _details[date] = body["cuisine"]);
  }

  Future<void> _recharge(String amount) async {
    final request = apiMultipart('$apiBase/user/recharge');
    request.fields.addAll({
      'u_id': widget.user.u_id.toString(),
      'recharge': amount,
    });
    final response = await sendApi(request);
    if (response.statusCode != 200) {
      debugPrint('recharge failed: ${response.reasonPhrase}');
      return;
    }
    // 充完再拉一次余额，而不是本地加 —— 服务端才是账面的唯一真相。
    await _refreshBalance();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0x6FF3F3F4),
      body: Column(
        children: [
          _buildHeader(context),
          const SizedBox(height: 5.0),
          MonthDayPicker(
            year: queryYear,
            onMonthChanged: (m) {
              setState(() => _monthShown = m);
              _loadMonth(m);
            },
            onDayChanged: _loadDay,
          ),
          Expanded(child: _buildCard()),
        ],
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Stack(
      children: [
        Container(
          color: Colors.lightBlueAccent,
          width: double.infinity,
          height: 180,
        ),
        Positioned(
          top: 26,
          left: 10,
          child: Text(
            "hi,${widget.user.u_name}",
            style: const TextStyle(
              color: Colors.white,
              decoration: TextDecoration.none,
              fontSize: 22,
            ),
          ),
        ),
        const Positioned(
          top: 53,
          left: 10,
          child: Text(
            "钱包余额:",
            style: TextStyle(
              color: Colors.white,
              decoration: TextDecoration.none,
              fontSize: 18,
            ),
          ),
        ),
        Positioned(
          top: 80,
          left: 30,
          child: Text(
            "￥$_money",
            style: const TextStyle(
              color: Colors.white,
              decoration: TextDecoration.none,
              fontSize: 60,
            ),
          ),
        ),
        Positioned(
          right: 15,
          bottom: 27,
          child: ElevatedButton(
            style: ElevatedButton.styleFrom(
              shape: const StadiumBorder(
                side: BorderSide(style: BorderStyle.none),
              ),
            ),
            onPressed: _showRechargeDialog,
            child: const Text(
              "充值",
              style: TextStyle(color: Colors.white, fontSize: 20),
            ),
          ),
        ),
      ],
    );
  }

  Future<void> _showRechargeDialog() async {
    _rechargeController.clear();
    final String? amount = await showDialog<String>(
      barrierDismissible: true,
      context: context,
      builder: (dialogContext) => AlertDialog(
        elevation: 10,
        backgroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('请输入充值的金额'),
        icon: const Icon(Icons.money, size: 40),
        content: Padding(
          padding: const EdgeInsets.all(8.0),
          child: TextField(
            controller: _rechargeController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(border: OutlineInputBorder()),
          ),
        ),
        contentTextStyle: const TextStyle(color: Colors.black),
        actions: [
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: ElevatedButton(
              onPressed: () =>
                  Navigator.of(dialogContext).pop(_rechargeController.text),
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

    // 空值或非数字直接忽略：Decimal(recharge) 在后端会抛异常变成 500。
    if (amount == null) return;
    final parsed = double.tryParse(amount.trim());
    if (parsed == null || parsed <= 0) return;
    await _recharge(amount.trim());
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
              const Text('消费记录', style: TextStyle(fontSize: 20)),
              Expanded(
                child: Container(
                  margin: const EdgeInsets.fromLTRB(0, 0, 10, 0),
                  alignment: Alignment.centerRight,
                  child: Text(
                    "$_monthShown月消费总金额：￥${_monthTotal.toStringAsFixed(2)}",
                    style: const TextStyle(color: Color(0xff999999)),
                  ),
                ),
              ),
            ],
          ),
          Divider(color: Colors.grey.shade200, thickness: 1, height: 1),
          Expanded(
            child: _costs.isEmpty
                ? const Center(
                    child: Text('暂无消费记录', style: TextStyle(color: Colors.grey)),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.all(10.0),
                    itemExtent: 60.0,
                    itemCount: _costs.length,
                    itemBuilder: (context, i) => _buildRow(_costs[i]),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildRow(dynamic cost) {
    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(cost["a_store_name"], style: const TextStyle(fontSize: 18)),
            Text(
              "￥${cost["total_price"]}",
              style: const TextStyle(fontSize: 18),
            ),
          ],
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              cost["r_create_time"],
              style: TextStyle(color: Colors.grey.shade400),
            ),
            SizedBox(
              height: 33,
              child: TextButton(
                onPressed: () {
                  final detail = _details[cost["r_create_time"]];
                  if (detail == null) return; // 明细还没拉回来
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => CostDetailPage(
                        items: detail,
                        homeBuilder: (_) =>
                            Home_load(widget.user, widget.password),
                      ),
                    ),
                  );
                },
                child: Text(
                  "详情 >",
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
}
