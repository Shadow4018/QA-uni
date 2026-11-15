import uuid
import pytest
from store.models import OrderRequest
from store.service import OrderRejectedError
from unittest.mock import Mock


# 3.4 Repository <> Database

def test_product_create_and_find_repositoryState(product_repo, made_products):
    product = made_products(unit_price=15_000, stock=5, on_sale=False)

    fetched = product_repo.find_by_id(product.id)

    assert fetched == product


def test_product_update_changes_stock_repositoryState(product_repo, made_products):
    from dataclasses import replace
    product = made_products(stock=10)

    product_repo.update(replace(product, stock=3))

    assert product_repo.find_by_id(product.id).stock == 3


# 3.5–3.6 Service -> Repository -> Database

def test_place_order_success_serviceState(service, made_products, made_orders):
    product = made_products(unit_price=50_000, stock=10)
    request = OrderRequest(reference=f"ORD-{uuid.uuid4()}", product_id=product.id,
                            quantity=2, premium=False, coupon_claimed=False)

    order = made_orders(service.place_order(request))

    assert order.status.value == "CONFIRMED"
    assert order.total == 100_000


def test_place_order_rejected_over_quantity_limit_serviceState(service, made_products):
    product = made_products(stock=10)
    request = OrderRequest(reference=f"ORD-{uuid.uuid4()}", product_id=product.id,
                            quantity=5, premium=False, coupon_claimed=False)

    with pytest.raises(OrderRejectedError, match="Перевищено ліміт кількості"):
        service.place_order(request)


def test_place_order_persists_confirmed_order_persistedState(service, order_repo, made_products, made_orders):
    product = made_products(unit_price=60_000, stock=10)
    request = OrderRequest(reference=f"ORD-{uuid.uuid4()}", product_id=product.id,
                            quantity=2, premium=True, coupon_claimed=False)

    created = made_orders(service.place_order(request))

    persisted = order_repo.find_by_id(created.id)
    assert persisted is not None
    assert persisted.total == 120_000
    assert persisted.item.quantity == 2


# Персональне бізнес-правило: знижка 15% від 1200 грн і дійсного купона

def test_discount_applies_with_valid_coupon_and_threshold_serviceState(
    product_repo, order_repo, made_products, made_orders
):
    coupon = Mock()
    coupon.is_valid.return_value = True
    from store.service import OrderService
    coupon_service = OrderService(product_repo, order_repo, coupon)

    product = made_products(unit_price=120_000, stock=5)
    request = OrderRequest(reference=f"ORD-{uuid.uuid4()}", product_id=product.id,
                            quantity=1, premium=False, coupon_claimed=True)

    order = made_orders(coupon_service.place_order(request))

    assert order.coupon_valid is True
    assert order.total == 102_000


# Повернення: альтернативний/граничний сценарій

def test_return_order_rejected_after_7_days_serviceState(service, order_repo, made_products, made_orders):
    product = made_products(stock=5)
    request = OrderRequest(reference=f"ORD-{uuid.uuid4()}", product_id=product.id,
                            quantity=1, premium=False, coupon_claimed=False)
    order = made_orders(service.place_order(request))

    with pytest.raises(OrderRejectedError, match="Повернення не дозволене"):
        service.return_order(order.id, days_since_purchase=8)

    assert order_repo.find_by_id(order.id).status.value == "CONFIRMED"


# Контрольна вимога лабораторної: один навмисно невдалий тест, не виправляти

# def test_intentionally_failing_control_check():
#     assert False, "Навмисний FAILED-тест згідно з вимогою лабораторної роботи №4"