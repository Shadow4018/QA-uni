import uuid

import pytest
import requests

NONEXISTENT_ID = 2**62


# 1. POST /products: 201, id, поля
def test_create_product_returns_201_and_persists_fields(base_url):
    response = requests.post(f"{base_url}/products", timeout=5, json={
        "sku": "API-CREATE-CHECK-" + uuid.uuid4().hex[:8],
        "unit_price": 50_000, "stock": 7, "on_sale": False})
    assert response.status_code == 201
    assert response.headers["Location"] == f"/products/{response.json()['id']}"
    product = response.json()
    assert product["id"] > 0
    assert product["unit_price"] == 50_000
    assert product["stock"] == 7
    assert product["on_sale"] is False


# 2. GET за id: 200, дані відповідають створеному
def test_get_product_by_id_returns_200_matching_created(base_url, create_product):
    product = create_product(unit_price=45_000, stock=3, on_sale=True)

    response = requests.get(f"{base_url}/products/{product['id']}", timeout=5)

    assert response.status_code == 200
    assert response.json() == product


# 3. GET неіснуючого ресурсу: 404, code/message
def test_get_missing_product_returns_404_with_error_contract(base_url):
    response = requests.get(f"{base_url}/products/{NONEXISTENT_ID}", timeout=5)

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert isinstance(body["message"], str) and body["message"]


def test_get_missing_order_returns_404_with_error_contract(base_url):
    response = requests.get(f"{base_url}/orders/{NONEXISTENT_ID}", timeout=5)

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert isinstance(body["message"], str) and body["message"]


# 1 (orders): POST /orders: 201, Location, поля
def test_create_order_returns_201_with_created_fields(create_product, create_order):
    product = create_product(unit_price=60_000, stock=10, on_sale=False)

    response = create_order(product["id"], quantity=1, coupon_claimed=False)

    assert response.status_code == 201
    assert response.headers["Location"] == f"/orders/{response.json()['id']}"
    body = response.json()
    assert body["id"] > 0
    assert body["status"] == "CONFIRMED"
    assert body["total"] == 60_000
    assert body["item"]["product_id"] == product["id"]


# 4. Action endpoint (return): 200, новий стан
def test_return_order_success_changes_status_to_returned(base_url, create_product, create_order):
    product = create_product(unit_price=60_000, stock=10, on_sale=False)
    order = create_order(product["id"], quantity=1).json()

    response = requests.post(f"{base_url}/orders/{order['id']}/return",
                             json={"days_since_purchase": 3, "packaging_open": False}, timeout=5)

    assert response.status_code == 200
    assert response.json()["status"] == "RETURNED"


# 5 + 6. Повторна дія: 409 і незмінність ресурсу після відхилення
def test_return_order_twice_returns_409_and_leaves_order_unchanged(base_url, create_product, create_order):
    product = create_product(unit_price=60_000, stock=10, on_sale=False)
    order = create_order(product["id"], quantity=1).json()

    first = requests.post(f"{base_url}/orders/{order['id']}/return",
                          json={"days_since_purchase": 1}, timeout=5)
    assert first.status_code == 200

    second = requests.post(f"{base_url}/orders/{order['id']}/return",
                           json={"days_since_purchase": 1}, timeout=5)
    assert second.status_code == 409
    assert second.json()["code"] == "ORDER_CONFLICT"
    assert second.json()["message"]

    after = requests.get(f"{base_url}/orders/{order['id']}", timeout=5)
    assert after.status_code == 200
    assert after.json() == first.json()


# 5 + 6 (заборонена дія): акційний товар не повертається, замовлення лишається CONFIRMED
def test_return_onsale_product_is_forbidden_with_409(base_url, create_product, create_order):
    product = create_product(unit_price=60_000, stock=10, on_sale=True)
    order = create_order(product["id"], quantity=1).json()

    response = requests.post(f"{base_url}/orders/{order['id']}/return",
                             json={"days_since_purchase": 1}, timeout=5)

    assert response.status_code == 409
    assert response.json()["code"] == "ORDER_CONFLICT"
    after = requests.get(f"{base_url}/orders/{order['id']}", timeout=5)
    assert after.json()["status"] == "CONFIRMED"


# 7. Персональне бізнес-правило: ліміт кількості 4 / 8 (параметризація)
@pytest.mark.parametrize("premium, quantity, expected_status", [
    (False, 4, 201),
    (False, 5, 409),
    (True, 8, 201),
    (True, 9, 409),
])
def test_quantity_limit_personal_business_rule(create_product, create_order, premium, quantity, expected_status):
    product = create_product(unit_price=50_000, stock=20, on_sale=False)

    response = create_order(product["id"], quantity=quantity, premium=premium)

    assert response.status_code == expected_status
    if expected_status == 409:
        assert response.json()["code"] == "ORDER_CONFLICT"


# 8. Workflow: POST -> GET -> action -> GET, id передається динамічно
def test_full_order_workflow_post_get_return_get(base_url, create_product, create_order):
    product = create_product(unit_price=70_000, stock=10, on_sale=False)

    created = create_order(product["id"], quantity=2, coupon_claimed=True)
    assert created.status_code == 201
    order_id = created.json()["id"]

    fetched = requests.get(f"{base_url}/orders/{order_id}", timeout=5)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "CONFIRMED"
    assert fetched.json()["total"] == 119_000  # 140000 - 15%

    returned = requests.post(f"{base_url}/orders/{order_id}/return",
                             json={"days_since_purchase": 2}, timeout=5)
    assert returned.status_code == 200
    assert returned.json()["status"] == "RETURNED"
    assert returned.json()["total"] == 119_000

    final = requests.get(f"{base_url}/orders/{order_id}", timeout=5)
    assert final.status_code == 200
    assert final.json()["status"] == "RETURNED"
