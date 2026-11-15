"""Unit tests для OrderService (SUT B, варіант 04).

Без БД і мережі: репозиторії та перевірка купона замінено in-memory заглушками, тому набір
виконується за долі секунди й підходить для етапу «unit tests» у CI.

Персональні правила: ліміт кількості 4 (преміум — 8); знижка 15% від 1200 грн (120000 коп.)
із підтвердженим купоном; повернення протягом 7 днів, акційні товари не повертаються.
"""
from dataclasses import replace

import pytest

from store.models import Order, OrderRequest, OrderStatus, Product
from store.service import OrderRejectedError, OrderService


# ---------- Заглушки ----------
class FakeProducts:
    def __init__(self, *products):
        self.items = {p.id: p for p in products}

    def find_by_id(self, product_id):
        return self.items.get(product_id)


class FakeOrders:
    def __init__(self):
        self.items = {}
        self.next_id = 1
        self.create_calls = 0

    def create(self, order):
        self.create_calls += 1
        saved = replace(order, id=self.next_id, item=replace(order.item, id=self.next_id))
        self.items[saved.id] = saved
        self.next_id += 1
        return saved

    def find_by_id(self, order_id):
        return self.items.get(order_id)

    def update_status(self, order_id, status):
        self.items[order_id] = replace(self.items[order_id], status=status)


class FakeCoupons:
    def __init__(self, answer=True):
        self.answer = answer
        self.calls = []

    def is_valid(self, product, quantity):
        self.calls.append((product, quantity))
        return self.answer


def make_product(unit_price=10_000, stock=20, on_sale=False, product_id=1):
    return Product(product_id, f"SKU-{product_id}", unit_price, stock, on_sale)


def make_service(product=None, coupons=None):
    products = FakeProducts(product or make_product())
    orders = FakeOrders()
    coupons = coupons or FakeCoupons()
    return OrderService(products, orders, coupons), orders, coupons


def request(quantity=1, premium=False, coupon_claimed=False, product_id=1, reference="REF-1"):
    return OrderRequest(reference, product_id, quantity, premium, coupon_claimed)


# ---------- calculate_total ----------
@pytest.mark.parametrize("unit_price, quantity, coupon_valid, expected", [
    (60_000, 1, True, 60_000),     # підсумок нижче порога: знижки немає
    (59_999, 2, True, 119_998),    # 119998 < 120000: знижки немає навіть із купоном
    (60_000, 2, True, 102_000),    # рівно 120000 і купон: знижка 15%
    (60_000, 2, False, 120_000),   # без купона знижки немає
    (120_001, 1, True, 102_001),   # знижка округлюється донизу (18000.15 -> 18000)
])
def test_calculate_total_discount_rules(unit_price, quantity, coupon_valid, expected):
    service, _, _ = make_service()
    assert service.calculate_total(unit_price, quantity, coupon_valid) == expected


@pytest.mark.parametrize("unit_price, quantity, coupon_valid", [
    (99, 1, False),            # ціна нижче мінімуму
    (1_000_001, 1, False),     # ціна вище максимуму
    (100, 0, False),           # кількість нижче мінімуму
    (100, 21, False),          # кількість вище максимуму
    (True, 1, False),          # bool не є числом
    (100, True, False),
    (100, 1, 1),               # ознака купона має бути bool
])
def test_calculate_total_rejects_invalid_arguments(unit_price, quantity, coupon_valid):
    service, _, _ = make_service()
    with pytest.raises(ValueError):
        service.calculate_total(unit_price, quantity, coupon_valid)


def test_calculate_total_accepts_boundary_values():
    service, _, _ = make_service()
    assert service.calculate_total(100, 1, False) == 100
    assert service.calculate_total(1_000_000, 20, False) == 20_000_000


# ---------- place_order ----------
def test_place_order_saves_confirmed_order_with_copied_product_data():
    service, orders, _ = make_service(make_product(unit_price=15_000, on_sale=True))
    saved = service.place_order(request(quantity=2))
    assert saved.status == OrderStatus.CONFIRMED
    assert saved.total == 30_000
    assert (saved.item.quantity, saved.item.unit_price, saved.item.on_sale) == (2, 15_000, True)
    assert orders.find_by_id(saved.id) == saved


@pytest.mark.parametrize("premium, quantity, allowed", [
    (False, 4, True),
    (False, 5, False),
    (True, 8, True),
    (True, 9, False),
])
def test_place_order_quantity_limit_depends_on_premium(premium, quantity, allowed):
    service, orders, _ = make_service()
    if allowed:
        assert service.place_order(request(quantity=quantity, premium=premium)).status == OrderStatus.CONFIRMED
    else:
        with pytest.raises(OrderRejectedError):
            service.place_order(request(quantity=quantity, premium=premium))
        assert orders.create_calls == 0


def test_place_order_rejects_quantity_above_stock_but_accepts_equal():
    service, orders, _ = make_service(make_product(stock=3))
    assert service.place_order(request(quantity=3)).item.quantity == 3
    with pytest.raises(OrderRejectedError):
        service.place_order(request(quantity=4, reference="REF-2"))
    assert orders.create_calls == 1


def test_place_order_unknown_product_raises_value_error():
    service, orders, _ = make_service()
    with pytest.raises(ValueError):
        service.place_order(request(product_id=999))
    assert orders.create_calls == 0


def test_place_order_applies_discount_when_coupon_is_valid():
    service, _, coupons = make_service(make_product(unit_price=60_000), FakeCoupons(True))
    saved = service.place_order(request(quantity=2, coupon_claimed=True))
    assert saved.coupon_valid is True
    assert saved.total == 102_000
    assert len(coupons.calls) == 1


def test_place_order_without_discount_when_coupon_is_rejected():
    service, _, _ = make_service(make_product(unit_price=60_000), FakeCoupons(False))
    saved = service.place_order(request(quantity=2, coupon_claimed=True))
    assert saved.coupon_valid is False
    assert saved.total == 120_000


def test_place_order_does_not_call_coupon_validator_when_not_claimed():
    service, _, coupons = make_service()
    service.place_order(request(coupon_claimed=False))
    assert coupons.calls == []


def test_place_order_does_not_call_coupon_validator_after_local_rejection():
    service, _, coupons = make_service()
    with pytest.raises(OrderRejectedError):
        service.place_order(request(quantity=5, coupon_claimed=True))
    assert coupons.calls == []


def test_place_order_non_boolean_coupon_answer_aborts_without_saving():
    service, orders, _ = make_service(coupons=FakeCoupons("yes"))
    with pytest.raises(RuntimeError):
        service.place_order(request(coupon_claimed=True))
    assert orders.create_calls == 0


@pytest.mark.parametrize("reference", ["", "   ", "x" * 41])
def test_place_order_rejects_invalid_reference(reference):
    service, orders, _ = make_service()
    with pytest.raises(ValueError):
        service.place_order(request(reference=reference))
    assert orders.create_calls == 0


def test_place_order_accepts_reference_of_maximum_length():
    service, _, _ = make_service()
    assert service.place_order(request(reference="x" * 40)).reference == "x" * 40


@pytest.mark.parametrize("bad_request", [
    None,
    "not a request",
    OrderRequest("R", 0, 1, False, False),       # id має бути додатним
    OrderRequest("R", 1, 0, False, False),       # кількість мінімум 1
    OrderRequest("R", 1, 21, False, False),      # кількість максимум 20
    OrderRequest("R", 1, True, False, False),    # bool не є кількістю
    OrderRequest("R", 1, 1, 1, False),           # premium має бути bool
])
def test_place_order_rejects_malformed_requests(bad_request):
    service, orders, _ = make_service()
    with pytest.raises(ValueError):
        service.place_order(bad_request)
    assert orders.create_calls == 0


def test_service_requires_all_dependencies():
    with pytest.raises(ValueError):
        OrderService(None, FakeOrders(), FakeCoupons())


# ---------- return_order ----------
def confirmed_order(service, **kwargs):
    return service.place_order(request(**kwargs))


@pytest.mark.parametrize("days", [0, 7])
def test_return_order_allowed_up_to_seven_days_inclusive(days):
    service, orders, _ = make_service()
    saved = confirmed_order(service)
    returned = service.return_order(saved.id, days)
    assert returned.status == OrderStatus.RETURNED
    assert returned.total == saved.total
    assert orders.find_by_id(saved.id).status == OrderStatus.RETURNED


def test_return_order_rejected_after_seven_days():
    service, orders, _ = make_service()
    saved = confirmed_order(service)
    with pytest.raises(OrderRejectedError):
        service.return_order(saved.id, 8)
    assert orders.find_by_id(saved.id).status == OrderStatus.CONFIRMED


def test_return_order_rejected_for_on_sale_product():
    service, orders, _ = make_service(make_product(on_sale=True))
    saved = confirmed_order(service)
    with pytest.raises(OrderRejectedError):
        service.return_order(saved.id, 0)
    assert orders.find_by_id(saved.id).status == OrderStatus.CONFIRMED


def test_return_order_second_return_is_rejected():
    service, _, _ = make_service()
    saved = confirmed_order(service)
    service.return_order(saved.id, 1)
    with pytest.raises(OrderRejectedError):
        service.return_order(saved.id, 1)


def test_return_order_packaging_flag_does_not_affect_permission():
    service, _, _ = make_service()
    saved = confirmed_order(service)
    assert service.return_order(saved.id, 1, packaging_open=True).status == OrderStatus.RETURNED


def test_return_order_unknown_order_raises_value_error():
    service, _, _ = make_service()
    with pytest.raises(ValueError):
        service.return_order(12345, 0)


@pytest.mark.parametrize("order_id, days, packaging", [
    (0, 0, False),        # id має бути додатним
    (True, 0, False),     # bool не є id
    (1, -1, False),       # дні не можуть бути від'ємними
    (1, 36_501, False),   # дні не більше 36500
    (1, True, False),     # bool не є числом днів
    (1, 0, "open"),       # ознака пакування має бути bool
])
def test_return_order_rejects_invalid_arguments(order_id, days, packaging):
    service, _, _ = make_service()
    with pytest.raises(ValueError):
        service.return_order(order_id, days, packaging)


def test_return_order_does_not_call_coupon_validator():
    service, _, coupons = make_service()
    saved = confirmed_order(service, coupon_claimed=True)
    calls_after_order = len(coupons.calls)
    service.return_order(saved.id, 0)
    assert len(coupons.calls) == calls_after_order
