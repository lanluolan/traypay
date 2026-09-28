class User {
  late int u_id;
  late String u_name;

  /// 后端把 DECIMAL 序列化成字符串，这里保持字符串原样，不做 double 转换 ——
  /// 金额转 double 会引入二进制浮点误差。要算数时用 `double.parse` 就地转，
  /// 显示时直接用。
  late String u_money;

  User(this.u_id, this.u_name, this.u_money);

  User.fromJson(Map<String, dynamic> jsonStr) {
    u_id = jsonStr['u_id'];
    u_name = jsonStr['u_name'];
    u_money = jsonStr['u_money'].toString();
  }
}
