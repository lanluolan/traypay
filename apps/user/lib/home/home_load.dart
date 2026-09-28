import 'package:checkout_common/checkout_common.dart';
import 'package:flutter/material.dart';
import 'package:pay_system/home/home_page.dart';
import 'package:pay_system/person/mine.dart';

import '../models/user.dart';
import '../pay/pay_page.dart';

/// 顾客端的 app 外壳。外壳本身（MaterialApp + 底部导航 + 选中态）在
/// [HomeShell] 里两端共用，这里只提供顾客端自己的导航项与页面。
class Home_load extends StatelessWidget {
  final User user;
  final String password;

  const Home_load(this.user, this.password, {Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return HomeShell(
      items: const [
        BottomNavigationBarItem(icon: Icon(Icons.home), label: '首页'),
        BottomNavigationBarItem(icon: Icon(Icons.payment), label: '支付'),
        BottomNavigationBarItem(icon: Icon(Icons.person), label: '个人'),
      ],
      pages: [HomePage(user, password), payPage(user), Mine(user)],
    );
  }
}
