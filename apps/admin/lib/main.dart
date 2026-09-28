import 'dart:convert';

import 'package:admin_paysystem/home/home_load.dart';
import 'package:checkout_common/checkout_common.dart';
import 'package:flutter/material.dart';
import 'package:fluttertoast/fluttertoast.dart';
import 'package:http/http.dart' as http;

import 'models/admin.dart';

/// 食堂端入口。全局 navigatorKey 让 [AuthSession] 在 401 时能跳回登录页 ——
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

// 这里原本有个 buildRegisterText()：食堂端的「点击注册」入口。它从未被
// build() 调用（死代码），而且指向的是共享的 Register 页，打的是
// /user/register —— 后端没有 /admin/register，食堂端注册只会造出一个登不进
// 本 App 的顾客账号。已删除。食堂端账号由后端的 `flask --app manage init-db`
// 创建。
class _MyHomePageState extends State<MyHomePage> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  String _name = "";
  String _password = "";
  bool _isObscure = true;
  bool _submitting = false;

  /// Logs in and navigates on success. Awaited end to end — see the note in
  /// the customer app's main.dart for what the un-awaited version did.
  Future<void> _login(String name, String password) async {
    final request = apiMultipart('$apiBase/admin/login');
    request.fields.addAll({'a_name': name, 'a_password': password});

    final http.StreamedResponse response = await sendApi(request);
    if (!mounted) return;

    if (response.statusCode != 200) {
      debugPrint('login failed: ${response.reasonPhrase}');
      _toast("网络错误，请稍后重试");
      return;
    }

    final String content = await response.stream.transform(utf8.decoder).join();
    final body = json.decode(content);
    if (!mounted) return;

    if (body["code"] != 0) {
      _toast(body["code"] == 1 ? "管理员不存在" : "密码错误");
      return;
    }

    // Must happen before any other request: every endpoint beyond login
    // rejects a call without this token.
    AuthSession.begin(body["token"]);
    final admin = Admin.fromJson(body["admin"]);
    Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => Home_load(admin, password)));
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
            const SizedBox(height: 100),
            _buildIcon(),
            const SizedBox(height: 30),
            _buildNameField(),
            const SizedBox(height: 30),
            _buildPasswordField(context),
            const SizedBox(height: 60),
            _buildLoginButton(context),
          ],
        ),
      ),
    );
  }

  Widget _buildLoginButton(BuildContext context) {
    return Align(
      child: SizedBox(
        height: 45,
        width: 270,
        child: ElevatedButton(
          style: ElevatedButton.styleFrom(
            shape:
                const StadiumBorder(side: BorderSide(style: BorderStyle.none)),
          ),
          onPressed: _submitting ? null : _submit,
          child: Text(
            _submitting ? '登录中…' : '管理员登录',
            style: Theme.of(context).primaryTextTheme.headlineSmall,
          ),
        ),
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
      decoration: const InputDecoration(labelText: '管理员账号'),
      validator: (v) => (v == null || v.isEmpty) ? '请输入账号' : null,
      onSaved: (v) => _name = v ?? "",
    );
  }

  Widget _buildIcon() {
    return Image.asset(
      "img/shopping.png",
      width: 120,
      height: 120,
      errorBuilder: (_, __, ___) => const SizedBox(
          width: 120,
          height: 120,
          child: Icon(Icons.restaurant, size: 80, color: Colors.blue)),
    );
  }
}
