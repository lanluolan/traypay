import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pay_system/main.dart';

void main() {
  testWidgets('login screen renders its fields and buttons', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const MyApp());

    expect(find.text('登录'), findsOneWidget);
    expect(find.text('用户名'), findsOneWidget);
    expect(find.text('密码'), findsOneWidget);
    expect(find.text('忘记密码？'), findsOneWidget);
    expect(find.text('点击注册'), findsOneWidget);
  });

  testWidgets('empty submit is rejected before any request goes out', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const MyApp());

    await tester.tap(find.widgetWithText(ElevatedButton, '登录'));
    await tester.pump();

    // Form validation fires, so no network call is attempted — a request
    // with an empty name would just come back as "user does not exist".
    expect(find.text('请输入用户名'), findsOneWidget);
    expect(find.text('请输入密码'), findsOneWidget);
  });

  testWidgets('the password field starts obscured and toggles', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const MyApp());

    TextField passwordField() => tester.widget<TextField>(
      find.descendant(
        of: find.byType(TextFormField).last,
        matching: find.byType(TextField),
      ),
    );

    expect(passwordField().obscureText, isTrue);
    await tester.tap(find.byIcon(Icons.visibility_off));
    await tester.pump();
    expect(passwordField().obscureText, isFalse);
  });
}
