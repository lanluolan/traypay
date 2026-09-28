import 'package:flutter_test/flutter_test.dart';
import 'package:admin_paysystem/models/review_cart.dart';

void main() {
  final dish = <String, dynamic>{
    'c_id': 1,
    'c_name': '番茄蛋',
    'c_price': '12.50'
  };
  test('unknown region blocks checkout until explicitly resolved', () {
    final cart = ReviewCart()
      ..token = 'draft'
      ..trayConfirmed = true;
    cart.items.add(ReviewItem(regionId: 0, status: 'unknown'));
    expect(cart.canCheckout, false);
    cart.items.single.select(dish);
    expect(cart.canCheckout, true);
  });
  test('ambiguous first candidate is not automatically selected', () {
    final item = ReviewItem.fromRegion({
      'region_id': 0,
      'box': [0, 0, 10, 10],
      'status': 'ambiguous',
      'selected': null,
      'candidates': [dish]
    });
    expect(item.resolved, false);
    expect(item.dish, null);
  });
  test('duplicates and manual quantity use exact cents', () {
    final cart = ReviewCart()
      ..token = 'draft'
      ..trayConfirmed = true;
    cart.items.addAll([
      ReviewItem(dish: dish, confirmed: true),
      ReviewItem(dish: dish, confirmed: true, quantity: 2)
    ]);
    expect(cart.portions, 3);
    expect(cart.total, '37.50');
    expect(priceInCents('0.10') + priceInCents('0.20'), 30);
  });
  test('ignored region is explicit and all-ignored tray cannot checkout', () {
    final cart = ReviewCart()
      ..token = 'draft'
      ..trayConfirmed = true;
    cart.items.add(ReviewItem(regionId: 0)..ignore());
    expect(cart.resolved, true);
    expect(cart.canCheckout, false);
    expect(cart.items.single.toJson()['quantity'], 0);
  });
  test('new recognition clears prior cart and confirmation', () {
    final cart = ReviewCart()
      ..token = 'old'
      ..trayConfirmed = true;
    cart.items.add(ReviewItem(dish: dish, confirmed: true));
    cart.clear();
    expect(cart.items, isEmpty);
    expect(cart.token, null);
    expect(cart.canCheckout, false);
    expect(cart.trayConfirmed, false);
  });
}
