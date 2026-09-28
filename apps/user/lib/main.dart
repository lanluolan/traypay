import 'dart:convert';

import 'package:checkout_common/checkout_common.dart';
import 'package:flutter/material.dart';
import 'package:fluttertoast/fluttertoast.dart';
import 'package:http/http.dart' as http;
import 'package:pay_system/home/home_load.dart';

import 'models/user.dart';

/// 顾客端入口。全局 navigatorKey 让 [AuthSession] 在 401 时能跳回登录页 ——
/// `sendApi()` 是无 context 的工具函数，拿不到 Navigator（ISSUES.md A2）。
final GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();

void main() {
  AuthSession.onSessionExpired = () {
    navigatorKey.currentState?.pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const MyHomePage(title: '智慧支付')),
      (route) => false,
    );
  };
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: navigatorKey,
      debugShowCheckedModeBanner: false,
      title: '智慧支付',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: const MyHomePage(title: '智慧支付'),
    );
  }
}

class MyHomePage extends StatefulWidget {
  const MyHomePage({super.key, required this.title});

  final String title;

  @override
  State<MyHomePage> createState() => _MyHomePageState();
}

class _MyHomePageState extends State<MyHomePage> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  String _name = "";
  String _password = "";
  bool _isObscure = true;
  bool _submitting = false;

  static const List<Map<String, Object>> _loginMethod = [
    {"title": "wechat", "icon": Icons.wechat},
    {"title": "Apple", "icon": Icons.apple},
    {"title": "QQ", "icon": Icons.quora},
  ];

  /// Logs in and navigates on success.
  ///
  /// Awaited end to end. The original kicked this off without awaiting and
  /// then read a `login_code` field on the next line, so it branched on the
  /// *previous* attempt's result.
  Future<void> _login(String name, String password) async {
    final request = apiMultipart('$apiBase/user/login');
    request.fields.addAll({'u_name': name, 'u_password': password});

    final http.StreamedResponse response = await sendApi(request);
    if (!mounted) return;

    if (response.statusCode != 200) {
      debugPrint('login failed: ${response.reasonPhrase}');
      _toast("网络错误，请稍后重试");
      return;
    }

    // The stream may only be listened to once — read it exactly here.
    final String content = await response.stream.transform(utf8.decoder).join();
    final body = json.decode(content);
    if (!mounted) return;

    if (body["code"] != 0) {
      // code 1 = 用户不存在，code 2 = 密码错误。分开提示，否则用户不知道
      // 该去注册还是该重输密码。
      _toast(body["code"] == 1 ? "用户不存在" : "密码错误");
      return;
    }

    // Must happen before any other request: every endpoint beyond
    // login/register rejects a call without this token.
    AuthSession.begin(body["token"]);
    final user = User.fromJson(body["data"]);
    Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => Home_load(user, password)));
  }

  Future<void> _submit() async {
    final form = _formKey.currentState;
    if (form == null || !form.validate()) return;
    form.save();

    setState(() => _submitting = true);
    try {
      await _login(_name, _password);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
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
      body: Form(
        key: _formKey,
        autovalidateMode: AutovalidateMode.onUserInteraction,
        child: ListView(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          children: [
            const SizedBox(height: kToolbarHeight),
            const SizedBox(height: 50),
            _buildIcon(),
            const SizedBox(height: 30),
            _buildNameField(),
            const SizedBox(height: 30),
            _buildPasswordField(context),
            _buildForgetPasswordText(context),
            const SizedBox(height: 60),
            _buildLoginButton(context),
            const SizedBox(height: 40),
            _buildOtherLoginText(),
            _buildOtherMethod(context),
            _buildRegisterText(context),
          ],
        ),
      ),
    );
  }

  Widget _buildRegisterText(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text('没有账号?'),
            GestureDetector(
              child: const Text(
                '点击注册',
                style: TextStyle(color: Colors.lightBlueAccent),
              ),
              onTap: () {
                Navigator.push<int>(
                  context,
                  MaterialPageRoute(
                    builder: (_) =>
                        Register(loginPageBuilder: (_) => const MyApp()),
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildOtherMethod(BuildContext context) {
    // 第三方登录只是占位：后端没有对应接口，点了只弹一条提示。
    return OverflowBar(
      alignment: MainAxisAlignment.center,
      children: _loginMethod
          .map(
            (item) => IconButton(
              icon: Icon(
                item['icon'] as IconData,
                color: Theme.of(context).iconTheme.color,
              ),
              onPressed: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text('${item['title']}登录暂未开放'),
                    action: SnackBarAction(label: '取消', onPressed: () {}),
                  ),
                );
              },
            ),
          )
          .toList(),
    );
  }

  Widget _buildOtherLoginText() {
    return const Center(
      child: Text('其他账号登录', style: TextStyle(color: Colors.grey, fontSize: 14)),
    );
  }

  Widget _buildLoginButton(BuildContext context) {
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
          onPressed: _submitting ? null : _submit,
          child: Text(
            _submitting ? '登录中…' : '登录',
            style: Theme.of(context).primaryTextTheme.headlineSmall,
          ),
        ),
      ),
    );
  }

  Widget _buildForgetPasswordText(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          TextButton(
            onPressed: () {
              Navigator.push<int>(
                context,
                MaterialPageRoute(
                  builder: (_) =>
                      Forget_password(loginPageBuilder: (_) => const MyApp()),
                ),
              );
            },
            child: const Text(
              "忘记密码？",
              style: TextStyle(fontSize: 14, color: Colors.grey),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPasswordField(BuildContext context) {
    return TextFormField(
      obscureText: _isObscure,
      onSaved: (v) => _password = v ?? "",
      validator: (v) => (v == null || v.isEmpty) ? '请输入密码' : null,
      decoration: InputDecoration(
        labelText: "密码",
        suffixIcon: IconButton(
          icon: Icon(
            _isObscure ? Icons.visibility_off : Icons.visibility,
            color: _isObscure ? Colors.grey : Theme.of(context).iconTheme.color,
          ),
          onPressed: () => setState(() => _isObscure = !_isObscure),
        ),
      ),
    );
  }

  Widget _buildNameField() {
    return TextFormField(
      decoration: const InputDecoration(labelText: '用户名'),
      validator: (v) => (v == null || v.isEmpty) ? '请输入用户名' : null,
      onSaved: (v) => _name = v ?? "",
    );
  }

  Widget _buildIcon() {
    return Image.asset("img/shopping.png", width: 120, height: 120);
  }
}
