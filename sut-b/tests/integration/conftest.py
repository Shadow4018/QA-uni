import os
import time
import requests
import pytest
import psycopg
from pathlib import Path
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:17-alpine") as pg:
        # Параметри — виключно з runtime-контейнера, нічого не захардкожено
        conninfo = dict(
            host=pg.get_container_host_ip(),
            port=pg.get_exposed_port(5432),
            dbname=pg.dbname,
            user=pg.username,
            password=pg.password,
        )
        with psycopg.connect(**conninfo, autocommit=True) as conn:
            for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
                conn.execute(migration.read_text())
        yield conninfo


@pytest.fixture(scope="session")
def wiremock_container():
    with DockerContainer("wiremock/wiremock:3.9.1-alpine").with_exposed_ports(8080) as wm:
        wait_for_logs(wm, "extensions:", timeout=30)
        host = wm.get_container_host_ip()
        port = wm.get_exposed_port(8080)
        yield f"http://{host}:{port}"


@pytest.fixture
def db_env(postgres_container, monkeypatch):
    """Перенаправляє store.database.connect() на контейнер замість локальної БД."""
    monkeypatch.setenv("DB_HOST", postgres_container["host"])
    monkeypatch.setenv("DB_PORT", str(postgres_container["port"]))
    monkeypatch.setenv("DB_NAME", postgres_container["dbname"])
    monkeypatch.setenv("DB_USER", postgres_container["user"])
    monkeypatch.setenv("DB_PASSWORD", postgres_container["password"])
    yield


@pytest.fixture
def connection(db_env):
    from store.database import connect
    with connect() as conn:
        yield conn


@pytest.fixture
def product_repo(connection):
    from store.repositories import PostgresProductRepository
    return PostgresProductRepository(connection)


@pytest.fixture
def order_repo(connection):
    from store.repositories import PostgresOrderRepository
    return PostgresOrderRepository(connection)


@pytest.fixture
def wiremock(wiremock_container):
    """Чистить mappings і request journal перед КОЖНИМ тестом (3.11)."""
    requests.post(f"{wiremock_container}/__admin/mappings/reset")
    requests.delete(f"{wiremock_container}/__admin/requests")
    return wiremock_container


@pytest.fixture
def clean_tables(connection):
    """Очищає змінні дані перед кожним тестом (3.11) — TRUNCATE швидше за новий контейнер."""
    connection.execute("TRUNCATE order_items, orders, products RESTART IDENTITY CASCADE")
    yield


@pytest.fixture
def service(product_repo, order_repo, wiremock):
    from store.service import OrderService
    from store.http_coupon_validator import HttpCouponValidator
    coupons = HttpCouponValidator(base_url=wiremock, timeout=2)
    return OrderService(product_repo, order_repo, coupons)