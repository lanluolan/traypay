class Admin {
  late int a_id;
  late String a_name;
  late String a_store_name;

  /// 后端允许 a_address 为 NULL，所以这里必须可空 —— 直接赋给 String 会在
  /// 地址留空的门店上抛 type 'Null' is not a subtype of type 'String'。
  String? a_address;

  Admin(this.a_id, this.a_name, this.a_store_name, this.a_address);

  Admin.fromJson(Map<String, dynamic> jsonStr) {
    a_id = jsonStr['a_id'];
    a_name = jsonStr['a_name'];
    a_store_name = jsonStr['a_store_name'];
    a_address = jsonStr['a_address'];
  }
}
