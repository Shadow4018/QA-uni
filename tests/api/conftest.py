import os
import uuid

import pytest
import requests

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8080")


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture
def create_product(base_url):
    def _create(unit_price=60_000, stock=10, on_sale=False, sku=None):
        payload = {
            "sku": sku or f"API-{uuid.uuid4().hex[:12]}",
            "unit_price": unit_price,
            "stock": stock,
            "on_sale": on_sale,
        }
        response = requests.post(f"{base_url}/products", json=payload, timeout=5)
        assert response.status_code == 201, response.text
        return response.json()

    return _create


@pytest.fixture
def create_order(base_url):
    def _create(product_id, quantity=1, premium=False, coupon_claimed=False, reference=None):
        payload = {
            "reference": reference or f"API-ORD-{uuid.uuid4().hex[:12]}",
            "product_id": product_id,
            "quantity": quantity,
            "premium": premium,
            "coupon_claimed": coupon_claimed,
        }
        return requests.post(f"{base_url}/orders", json=payload, timeout=5)

    return _create
