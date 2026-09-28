import 'package:flutter/material.dart';
import 'package:fluttertoast/fluttertoast.dart';

/// 忘记密码页。
///
/// **目前只有界面，没有实现。** 后端没有任何重置密码的接口（`/user/*` 只有
/// login / register / delete / recharge / query），所以「确认」按钮除了提示
/// 一句「功能尚未开放」之外什么也不做 —— 与其发一个 404 出去，不如把这件事
/// 说清楚。要做完整流程需要先在后端加：发验证码、校验、改密码三步。
///
/// 原文件里那个写死的 cpolar 内网穿透地址已删除：它声明后从未被使用，是一条
/// 早就失效的隧道残留。
class Forget_password extends StatelessWidget {
  /// Builds the screen to return to when the back button is pressed.
  ///
  /// Each app passes its own root widget here. Previously this file did
  /// `import '../main.dart'` and hard-coded `MyApp()`, which is what kept two
  /// byte-identical copies of this page from being shared.
  final WidgetBuilder loginPageBuilder;

  const Forget_password({Key? key, required this.loginPageBuilder})
    : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          color: Colors.white,
          onPressed: () {
            Navigator.of(
              context,
            ).pushReplacement(MaterialPageRoute(builder: loginPageBuilder));
          },
          icon: const Icon(Icons.backspace),
        ),
        title: const Text("忘记密码", style: TextStyle(color: Colors.white)),
        backgroundColor: Colors.lightBlueAccent,
        elevation: 0,
      ),
      body: const _ForgetPasswordBody(),
    );
  }
}

class _ForgetPasswordBody extends StatefulWidget {
  const _ForgetPasswordBody({Key? key}) : super(key: key);

  @override
  State<_ForgetPasswordBody> createState() => _ForgetPasswordBodyState();
}

class _ForgetPasswordBodyState extends State<_ForgetPasswordBody> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  String _email = "";
  String _password = "";

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      autovalidateMode: AutovalidateMode.onUserInteraction,
      child: ListView(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        children: [
          const SizedBox(height: kToolbarHeight),
          _buildIcon(),
          const SizedBox(height: 30),
          _buildEmailField(),
          const SizedBox(height: 30),
          _buildPasswordField(),
          const SizedBox(height: 30),
          _buildPasswordAgainField(),
          const SizedBox(height: 20),
          _buildConfirmButton(context),
        ],
      ),
    );
  }

  Widget _buildConfirmButton(BuildContext context) {
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
            if (!(_formKey.currentState?.validate() ?? false)) return;
            // 后端还没有重置密码的接口，见类注释。
            Fluttertoast.showToast(
              msg: "重置密码功能尚未开放，请联系食堂管理员",
              toastLength: Toast.LENGTH_SHORT,
              gravity: ToastGravity.BOTTOM,
            );
          },
          child: Text(
            '确认',
            style: Theme.of(context).primaryTextTheme.headlineSmall,
          ),
        ),
      ),
    );
  }

  Widget _buildIcon() {
    return Image.asset(
      "img/forgetpassword.png",
      width: 120,
      height: 120,
      package: 'checkout_common',
    );
  }

  Widget _buildEmailField() {
    return TextFormField(
      decoration: const InputDecoration(hintText: '请输入邮箱'),
      validator: (v) => (v == null || v.isEmpty) ? '请输入正确的邮箱' : null,
      onSaved: (v) => _email = v ?? "",
    );
  }

  Widget _buildPasswordField() {
    return TextFormField(
      obscureText: true,
      onChanged: (v) => _password = v,
      onSaved: (v) => _password = v ?? "",
      validator: (v) => (v == null || v.isEmpty) ? '请输入密码' : null,
      decoration: const InputDecoration(hintText: "请输入新密码"),
    );
  }

  Widget _buildPasswordAgainField() {
    return TextFormField(
      obscureText: true,
      validator: (v) {
        if (v == null || v.isEmpty) return '请输入正确的新密码';
        if (v != _password) return '两次输入的密码不一致';
        return null;
      },
      decoration: const InputDecoration(hintText: "请再次输入新密码"),
    );
  }
}
