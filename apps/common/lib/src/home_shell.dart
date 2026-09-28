import 'package:flutter/material.dart';

/// 两端共用的 app 外壳：顶层 [MaterialApp] + 底部导航 + 选中态管理。
///
/// 因端而异的只有导航项和它们对应的页面（顾客端是 首页/支付/个人，食堂端是
/// 销售额/支付/菜品库），所以由各端的 `home/home_load.dart` 传进来；主题、
/// 标题、导航栏样式两端本来就一模一样。
class HomeShell extends StatelessWidget {
  /// 底部导航项，与 [pages] 一一对应、同序。
  final List<BottomNavigationBarItem> items;

  /// 与 [items] 同序的页面。任一时刻只有选中的那个在树里，切标签会销毁上一个
  /// 页面的 State —— 与提取前的行为一致。
  final List<Widget> pages;

  const HomeShell({Key? key, required this.items, required this.pages})
    : super(key: key);

  @override
  Widget build(BuildContext context) {
    assert(
      items.length == pages.length,
      'items 与 pages 必须一一对应：${items.length} vs ${pages.length}',
    );
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: '智慧支付',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: _HomeShellBody(items: items, pages: pages),
    );
  }
}

class _HomeShellBody extends StatefulWidget {
  const _HomeShellBody({Key? key, required this.items, required this.pages})
    : super(key: key);

  final List<BottomNavigationBarItem> items;
  final List<Widget> pages;

  @override
  State<_HomeShellBody> createState() => _HomeShellBodyState();
}

class _HomeShellBodyState extends State<_HomeShellBody> {
  int _currentIndex = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: widget.pages[_currentIndex],
      bottomNavigationBar: BottomNavigationBar(
        onTap: (int index) => setState(() => _currentIndex = index),
        currentIndex: _currentIndex,
        items: widget.items,
        iconSize: 25,
        fixedColor: Colors.lightBlue,
        selectedFontSize: 16,
        unselectedFontSize: 12,
        type: BottomNavigationBarType.fixed,
      ),
    );
  }
}
