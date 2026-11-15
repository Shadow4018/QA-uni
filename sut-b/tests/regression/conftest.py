"""Налаштування regression suite: markers (smoke / regression) і керування порядком запуску.

Порядок керується змінними середовища (потрібно для виявлення order dependency):
  REGRESSION_ORDER=default   — порядок як у файлі (за замовчуванням)
  REGRESSION_ORDER=reverse   — зворотний порядок
  REGRESSION_ORDER=random    — випадковий порядок; зерно задає REGRESSION_SEED (за замовчуванням 1)
Дія обмежена тестами цієї папки і не зачіпає інші тести проєкту.
"""
import os
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent


def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: швидка перевірка критичних сценаріїв (підмножина regression)")
    config.addinivalue_line("markers", "regression: повний regression suite (включає всі smoke-тести)")


def _mode():
    return os.getenv("REGRESSION_ORDER", "default").strip().lower()


def pytest_report_header(config):
    mode = _mode()
    if mode == "random":
        return f"regression order: random (REGRESSION_SEED={os.getenv('REGRESSION_SEED', '1')})"
    return f"regression order: {mode}"


def pytest_collection_modifyitems(config, items):
    mode = _mode()
    if mode not in ("reverse", "random"):
        return
    positions = [n for n, item in enumerate(items) if HERE in Path(str(item.path)).resolve().parents]
    subset = [items[n] for n in positions]
    if mode == "reverse":
        subset.reverse()
    else:
        random.Random(int(os.getenv("REGRESSION_SEED", "1"))).shuffle(subset)
    for n, item in zip(positions, subset):
        items[n] = item
