import 'package:admin_paysystem/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('login screen renders its fields and button', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const MyApp());

    expect(find.text('管理员登录'), findsOneWidget);
    expect(find.text('管理员账号'), findsOneWidget);
    expect(find.text('密码'), findsOneWidget);
  });

  testWidgets('the canteen app offers no self-registration', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const MyApp());

    // There is no /admin/register endpoint. The old "点击注册" entry pointed
    // at the shared page, which posts to /user/register and would only
    // create a customer account that cannot log into this app.
    expect(find.text('点击注册'), findsNothing);
  });

  testWidgets('empty submit is rejected before any request goes out', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const MyApp());

    await tester.tap(find.widgetWithText(ElevatedButton, '管理员登录'));
    await tester.pump();

    expect(find.text('请输入账号'), findsOneWidget);
    expect(find.text('请输入密码'), findsOneWidget);
  });
}
