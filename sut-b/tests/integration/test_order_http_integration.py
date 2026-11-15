import uuid
import pytest
from store.models import OrderRequest
from store.service import OrderRejectedError
from store.http_coupon_validator import CouponValidationError
from wiremock_helpers import stub_coupon_response, wiremock_request_count


@pytest.fixture(autouse=True)
def isolate(clean_tables):
    pass


def make_product(product_repo, **kwargs):
    defaults = dict(sku=f"SKU-{uuid.uuid4()}", unit_price=120_000, stock=5, on_sale=False)
    defaults.update(kwargs)
    return product_repo.create(**defaults)


# 3.5 Позитивний сценарій
def test_place_order_with_valid_coupon_applies_discount(service, order_repo, product_repo, wiremock):
    stub_coupon_response(wiremock, status=200, body={"valid": True})
    product = make_product(product_repo, unit_price=120_000)
    request = OrderRequest(reference=f"ORD-{uuid.uuid4()}", product_id=product.id,
                            quantity=1, premium=False, coupon_claimed=True)

    order = service.place_order(request)

    assert order.coupon_valid is True
    assert order.total == 102_000  # 120000 - 15%
    persisted = order_repo.find_by_id(order.id)
    assert persisted is not None and persisted.total == 102_000
    assert wiremock_request_count(wiremock) == 1


# 3.6 Зовнішня відмова (адаптовано під домен): коректний 200, але невалідне поле valid
def test_place_order_rejects_malformed_coupon_response(service, order_repo, product_repo, wiremock):
    stub_coupon_response(wiremock, status=200, body={"valid": "true"})  # рядок, не bool
    product = make_product(product_repo)
    request = OrderRequest(reference=f"ORD-{uuid.uuid4()}", product_id=product.id,
                            quantity=1, premium=False, coupon_claimed=True)

    with pytest.raises(CouponValidationError):
        service.place_order(request)

    assert order_repo.find_all() == []
    assert wiremock_request_count(wiremock) == 1


# 3.7 Недоступність зовнішнього сервісу
def test_place_order_fails_when_coupon_service_unavailable(service, order_repo, product_repo, wiremock):
    stub_coupon_response(wiremock, status=503, body={"error": "unavailable"})
    product = make_product(product_repo)
    request = OrderRequest(reference=f"ORD-{uuid.uuid4()}", product_id=product.id,
                            quantity=1, premium=False, coupon_claimed=True)

    with pytest.raises(CouponValidationError):
        service.place_order(request)

    assert order_repo.find_all() == []
    assert wiremock_request_count(wiremock) == 1


# 3.8 Локальна відмова — HTTP взагалі не викликається
def test_place_order_rejects_locally_without_calling_coupon_service(service, order_repo, product_repo, wiremock):
    product = make_product(product_repo, stock=10)
    request = OrderRequest(reference=f"ORD-{uuid.uuid4()}", product_id=product.id,
                            quantity=5, premium=False, coupon_claimed=True)  # ліміт 4 без premium

    with pytest.raises(OrderRejectedError, match="Перевищено ліміт кількості"):
        service.place_order(request)

    assert order_repo.find_all() == []
    assert wiremock_request_count(wiremock) == 0