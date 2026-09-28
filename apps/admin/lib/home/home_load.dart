import 'package:admin_paysystem/home/home_page.dart';
import 'package:admin_paysystem/person/mine.dart';
import 'package:checkout_common/checkout_common.dart';
import 'package:flutter/material.dart';

import '../models/admin.dart';
import '../pay/pay_page.dart';

/// 食堂端的 app 外壳。外壳本身（MaterialApp + 底部导航 + 选中态）在
/// [HomeShell] 里两端共用，这里只提供食堂端自己的导航项与页面。
class Home_load extends StatelessWidget {
  final Admin user;
  final String password;

  const Home_load(this.user, this.password, {Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return HomeShell(
      items: const [
        BottomNavigationBarItem(icon: Icon(Icons.sell), label: '销售额'),
        BottomNavigationBarItem(icon: Icon(Icons.payment), label: '支付'),
        BottomNavigationBarItem(icon: Icon(Icons.fastfood_sharp), label: '菜品库'),
      ],
      pages: [HomePage(user, password), payPage(user), Mine(user)],
    );
  }
}
