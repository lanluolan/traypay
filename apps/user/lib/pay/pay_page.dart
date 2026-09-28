import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../models/user.dart';

/// 付款码页：把 u_id 编成二维码给食堂端扫。
///
/// 二维码里只有用户 id，没有任何凭据 —— 扣款请求由**食堂端**带着自己的管理员
/// token 发出（`/admin/purchase`），后端凭那个 token 授权。所以这张码被拍照
/// 也不能用来扣别人的钱，只能标识"要扣谁"。
class payPage extends StatelessWidget {
  final User user;

  const payPage(this.user, {Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: '智慧支付',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: _PayBody(user: user),
    );
  }
}

class _PayBody extends StatelessWidget {
  const _PayBody({Key? key, required this.user}) : super(key: key);

  final User user;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            const SizedBox(height: 180),
            const Text('付款码', style: TextStyle(fontSize: 22)),
            const SizedBox(height: 20),
            QrImageView(data: user.u_id.toString(), size: 260),
            const SizedBox(height: 20),
            Text(user.u_name, style: const TextStyle(color: Colors.grey)),
          ],
        ),
      ),
    );
  }
}
