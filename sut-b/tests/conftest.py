import uuid
import pytest
from unittest.mock import Mock
from store.database import connect
from store.repositories import PostgresProductRepository, PostgresOrderRepository
from store.service import OrderService


@pytest.fixture
def connection():
    with connect() as conn:
        yield conn


@pytest.fixture
def product_repo(connection):
    return PostgresProductRepository(connection)


@pytest.fixture
def order_repo(connection):
    return PostgresOrderRepository(connection)


@pytest.fixture
def coupon_stub():
    stub = Mock()
    stub.is_valid.return_value = False
    return stub


@pytest.fixture
def service(product_repo, order_repo, coupon_stub):
    return OrderService(product_repo, order_repo, coupon_stub)


@pytest.fixture
def made_products(product_repo):
    created = []

    def factory(sku=None, unit_price=50_000, stock=10, on_sale=False):
        sku = sku or f"SKU-{uuid.uuid4()}"
        product = product_repo.create(sku, unit_price, stock, on_sale)
        created.append(product.id)
        return product

    yield factory
    for product_id in created:
        product_repo.delete(product_id)


@pytest.fixture
def made_orders(order_repo):
    created = []

    def register(order):
        created.append(order.id)
        return order

    yield register
    for order_id in created:
        order_repo.delete(order_id)