import 'package:checkout_common/checkout_common.dart';
import 'package:flutter/material.dart';
import 'package:pay_system/main.dart';

import '../models/user.dart';

/// 顾客端「个人」页。
class Mine extends StatelessWidget {
  final User user;

  const Mine(this.user, {Key? key}) : super(key: key);

  static const double _appBarHeight = 180.0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: CustomScrollView(
        slivers: <Widget>[
          SliverAppBar(
            expandedHeight: _appBarHeight,
            backgroundColor: Colors.lightBlueAccent,
            flexibleSpace: FlexibleSpaceBar(
              collapseMode: CollapseMode.parallax,
              background: _buildHeader(),
            ),
          ),
          SliverList(
            delegate: SliverChildListDelegate(<Widget>[
              Container(
                color: Colors.white,
                margin: const EdgeInsets.only(top: 5.0),
                child: Column(
                  children: <Widget>[
                    MenuItems(
                      icon: Icons.star,
                      title: '我的收藏',
                      onPressed: () => _notImplemented(context),
                    ),
                    MenuItems(
                      icon: Icons.schedule,
                      title: '我的计划',
                      onPressed: () => _notImplemented(context),
                    ),
                    MenuItems(
                      icon: Icons.person,
                      title: '关于',
                      onPressed: () => _showAbout(context),
                    ),
                    const SizedBox(height: 20),
                    _buildLogoutButton(context),
                    const SizedBox(height: 20),
                  ],
                ),
              ),
            ]),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader() {
    return Container(
      color: Colors.lightBlueAccent,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        children: [
          Expanded(
            flex: 3,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(
                    top: 30.0,
                    left: 30.0,
                    bottom: 5.0,
                  ),
                  child: Text(
                    user.u_name,
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                      fontSize: 35.0,
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.only(left: 30.0),
                  child: Text(
                    "余额 ￥${user.u_money}",
                    style: const TextStyle(color: Colors.white, fontSize: 20.0),
                  ),
                ),
              ],
            ),
          ),
          const Expanded(
            flex: 1,
            child: Padding(
              padding: EdgeInsets.only(top: 40.0, right: 30.0),
              child: CircleAvatar(
                backgroundImage: AssetImage("img/touxiang.jpg"),
                minRadius: 30,
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _notImplemented(BuildContext context) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('该功能尚未开放')));
  }

  void _showAbout(BuildContext context) {
    showAboutDialog(
      context: context,
      applicationName: '智慧支付',
      applicationVersion: '1.0.0',
      children: const [Text('基于图像识别的智慧食堂结算平台 · 顾客端')],
    );
  }

  Widget _buildLogoutButton(BuildContext context) {
    return Align(
      child: SizedBox(
        height: 45,
        width: 270,
        child: ElevatedButton(
          style: ButtonStyle(
            shape: MaterialStateProperty.all(
              const StadiumBorder(side: BorderSide(style: BorderStyle.none)),
            ),
          ),
          onPressed: () {
            // 清掉 token 再回登录页。原来只是 push 一个新的 MyApp，token
            // 还留在内存里，而且旧页面全压在栈底，返回键能退回已登录界面。
            AuthSession.end();
            Navigator.of(context, rootNavigator: true).pushAndRemoveUntil(
              MaterialPageRoute(builder: (_) => const MyApp()),
              (route) => false,
            );
          },
          child: Text(
            '退出登录',
            style: Theme.of(context).primaryTextTheme.headlineSmall,
          ),
        ),
      ),
    );
  }
}
