class ReviewItem {
  final int? regionId;
  final List<num>? box;
  final String status;
  final List<Map<String, dynamic>> candidates;
  Map<String, dynamic>? dish;
  int quantity;
  bool confirmed;

  ReviewItem(
      {this.regionId,
      this.box,
      this.status = 'manual',
      this.candidates = const [],
      this.dish,
      this.quantity = 1,
      this.confirmed = false});

  factory ReviewItem.fromRegion(Map<String, dynamic> row) => ReviewItem(
        regionId: row['region_id'] as int,
        box: (row['box'] as List).cast<num>(),
        status: row['status'] as String,
        candidates: (row['candidates'] as List).cast<Map<String, dynamic>>(),
        dish: row['selected'] as Map<String, dynamic>?,
        confirmed: row['status'] == 'accepted' && row['selected'] != null,
      );

  bool get ignored => confirmed && dish == null && quantity == 0;
  bool get resolved => confirmed && (ignored || dish != null && quantity > 0);
  void select(Map<String, dynamic> selected) {
    dish = selected;
    quantity = quantity > 0 ? quantity : 1;
    confirmed = true;
  }

  void ignore() {
    dish = null;
    quantity = 0;
    confirmed = true;
  }

  Map<String, dynamic> toJson() => {
        'region_id': regionId,
        'c_id': dish?['c_id'],
        'quantity': quantity,
        'confirmed': confirmed,
      };
}

int priceInCents(dynamic value) {
  final text = value.toString();
  if (!RegExp(r'^\d+(\.\d{1,2})?$').hasMatch(text)) {
    throw FormatException('菜品价格无效', text);
  }
  final parts = text.split('.');
  return int.parse(parts[0]) * 100 +
      (parts.length == 1 ? 0 : int.parse(parts[1].padRight(2, '0')));
}

class ReviewCart {
  final List<ReviewItem> items = [];
  String? token;
  bool trayConfirmed = false;
  void clear() {
    items.clear();
    token = null;
    trayConfirmed = false;
  }

  bool get resolved =>
      token != null && items.isNotEmpty && items.every((i) => i.resolved);
  int get portions =>
      items.where((i) => i.dish != null).fold(0, (n, i) => n + i.quantity);
  bool get canCheckout =>
      resolved && trayConfirmed && portions > 0 && portions <= 100;
  int get totalCents => items
      .where((i) => i.dish != null)
      .fold(0, (n, i) => n + priceInCents(i.dish!['c_price']) * i.quantity);
  String get total =>
      '${totalCents ~/ 100}.${(totalCents % 100).toString().padLeft(2, '0')}';
}
