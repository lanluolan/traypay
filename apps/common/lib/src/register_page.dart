import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:fluttertoast/fluttertoast.dart';
import 'package:http/http.dart' as http;

import 'api_client.dart';
import 'api_config.dart';
import 'auth_session.dart';

class Register extends StatelessWidget {
  /// Builds the screen to return to when the back button is pressed.
  ///
  /// Each app passes its own root widget here. Previously this file did
  /// `import '../main.dart'` and hard-coded `MyApp()`, which is what kept two
  /// near-identical copies of this page from being shared.
  final WidgetBuilder loginPageBuilder;

  const Register({Key? key, required this.loginPageBuilder}) : super(key: key);

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
        title: const Text("注册", style: TextStyle(color: Colors.white)),
        backgroundColor: Colors.lightBlueAccent,
        elevation: 0,
      ),
      body: const _RegisterBody(),
    );
  }
}

class _RegisterBody extends StatefulWidget {
  const _RegisterBody({Key? key}) : super(key: key);

  @override
  State<_RegisterBody> createState() => _RegisterBodyState();
}

class _RegisterBodyState extends State<_RegisterBody> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  String _password = "";
  String _name = "";
  bool _submitting = false;

  /// Returns the backend's business code: 0 success, 1 name taken,
  /// 2 missing field, -1 transport failure.
  ///
  /// The caller must `await` this. The original fired it without awaiting and
  /// then read a `registe_code` field one line later, so it always saw the
  /// *previous* attempt's result — the first registration reported failure
  /// even when it succeeded.
  Future<int> _register(String name, String password) async {
    final request = apiMultipart('$apiBase/user/register');
    request.fields.addAll({'u_name': name, 'u_password': password});

    final http.StreamedResponse response = await sendApi(request);
    if (response.statusCode != 200) {
      debugPrint('register failed: ${response.reasonPhrase}');
      return -1;
    }
    // The stream may only be listened to once — read it exactly here.
    final String content = await response.stream.transform(utf8.decoder).join();
    final body = json.decode(content);
    if (body["code"] == 0) {
      // Registering logs you in, so the token comes back here too.
      AuthSession.begin(body["token"]);
    }
    return body["code"] as int;
  }

  Future<void> _submit() async {
    final form = _formKey.currentState;
    if (form == null || !form.validate()) return;
    form.save();

    setState(() => _submitting = true);
    final int code = await _register(_name, _password);
    if (!mounted) return;
    setState(() => _submitting = false);

    switch (code) {
      case 0:
        _toast("注册成功");
        Navigator.of(context).pop();
        break;
      case 1:
        _toast("用户已存在");
        break;
      default:
        _toast("注册失败");
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
    return Form(
      key: _formKey,
      autovalidateMode: AutovalidateMode.onUserInteraction,
      child: ListView(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        children: [
          const SizedBox(height: 30),
          _buildNameField(),
          const SizedBox(height: 20),
          _buildPasswordField(),
          const SizedBox(height: 20),
          MaterialButton(
            onPressed: _submitting ? null : _submit,
            color: Colors.grey,
            child: Text(_submitting ? "注册中…" : "注册"),
          ),
        ],
      ),
    );
  }

  Widget _buildNameField() {
    return TextFormField(
      onSaved: (v) => _name = v ?? "",
      validator: (v) => (v == null || v.isEmpty) ? '请输入用户名' : null,
      decoration: const InputDecoration(hintText: "请输入用户名"),
    );
  }

  Widget _buildPasswordField() {
    return TextFormField(
      obscureText: true,
      onSaved: (v) => _password = v ?? "",
      validator: (v) => (v == null || v.isEmpty) ? '请输入密码' : null,
      decoration: const InputDecoration(hintText: "请输入密码"),
    );
  }
}
