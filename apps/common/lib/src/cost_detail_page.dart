import 'package:flutter/material.dart';

/// 单笔消费/销售的菜品明细页，两端共用。
///
/// 提取时逐字段确认过：这个页面从不读用户模型的任何东西 —— 原来那个 `user`
/// 字段只是被存下来，好在按返回键时重建各端的 app 外壳。所以这里把它换成注入
/// 一个 [homeBuilder]，页面本身就与 `User` / `Admin` 无关了 —— 和
/// `Forget_password` 的 `loginPageBuilder` 是同一个套路。
class CostDetailPage extends StatelessWidget {
  /// 后端返回的菜品列表，每项需含 `c_name` 与 `c_price`。
  final List items;

  /// 返回键跳回的页面 —— 各端自己的 `Home_load`。
  final WidgetBuilder homeBuilder;

  const CostDetailPage({
    Key? key,
    required this.items,
    required this.homeBuilder,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: '智慧支付',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: _CostDetailBody(items: items, homeBuilder: homeBuilder),
    );
  }
}

class _CostDetailBody extends StatelessWidget {
  const _CostDetailBody({
    Key? key,
    required this.items,
    required this.homeBuilder,
  }) : super(key: key);

  final List items;
  final WidgetBuilder homeBuilder;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          color: Colors.white,
          // 提取前就是 pushReplacement 而不是 pop：这个页面自带一层
          // MaterialApp，返回走的是内层 Navigator，得把外壳重新推上去。
          onPressed: () => Navigator.of(
            context,
          ).pushReplacement(MaterialPageRoute(builder: homeBuilder)),
          icon: const Icon(Icons.backspace),
        ),
        title: const Text("详情", style: TextStyle(color: Colors.white)),
        backgroundColor: Colors.lightBlueAccent,
        elevation: 0,
      ),
      body: ListView(
        children: [
          for (final item in items)
            Padding(
              padding: const EdgeInsets.all(12.0),
              child: Container(
                color: Colors.white,
                child: Column(
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          item["c_name"],
                          style: const TextStyle(fontSize: 18.0),
                        ),
                        Text(
                          "￥${item["c_price"]}",
                          style: const TextStyle(fontSize: 18.0),
                        ),
                      ],
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
