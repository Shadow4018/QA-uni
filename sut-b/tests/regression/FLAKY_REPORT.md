# Лабораторна №8 — перелік проблем: симптом → причина → виправлення

Файли: `order_regression_before.py` (оригінал із репозиторію) і `order_regression.py` (виправлений).
Очікувані симптоми виведені з аналізу коду; точні повідомлення звірте з власним запуском і за потреби вставте їх у звіт.

| № | Тип | Симптом | Причина | Виправлення |
|---|-----|---------|---------|-------------|
| 1 | Order dependency | `test_return_order` проходить у загальному запуску, але падає окремо (`pytest ...::test_return_order`) і при зворотному порядку: `ValueError: Некоректне значення: Ідентифікатор замовлення` | Тест бере id із глобальної змінної `order_id`, яку заповнює інший тест `test_create_order`. Без нього `order_id == 0` | Тест створює власне замовлення (`place_order`) і працює з його id; глобальну змінну видалено |
| 2 | Shared state / dirty data | У повному запуску другий із тестів `test_product_stock` / `test_product_rate` падає: `UniqueViolation ... products_sku_key`; окремо кожен проходить | Обидва створюють товар із однаковим `sku="REGRESSION-PRODUCT"`, а `sku` має обмеження UNIQUE; БД спільна для всього модуля й дані не очищуються | Унікальний `sku` у кожному тесті (`uuid4`) і autouse-фікстура `clean_database`, що очищає таблиці перед кожним тестом |
| 3 | Fixed wait / timing | `test_order_after_policy_check` падає: `assert len(saved) == 1` (`0 == 1`); результат залежить від `REGRESSION_POLICY_DELAY_MS` і швидкодії машини | Тест чекає `time.sleep(0.05)` і припускає, що за цей час замовлення вже збережене, а перевірка купона триває 200 мс | Подія (`threading.Event`) та очікування завершення операції `operation.result(timeout=10)`; до відпускання перевірки купона перевіряється, що замовлення ще немає |
| 4 | Неявний порядок рядків | `test_order_selection` проходить за замовчуванням, але падає при `REGRESSION_REVERSE_FIXTURE=true`: `['x-B', 'x-A'] != ['x-A', 'x-B']` | SQL `SELECT ... JOIN` без `ORDER BY`: порядок рядків не гарантований і збігається з порядком вставки лише випадково | Додано `ORDER BY r.reference` |

## Smoke і regression

- smoke (3 тести): `test_create_order`, `test_return_order`, `test_stock_rejection`
- regression: усі 10 тестів файлу, smoke входять до нього

```
python -m pytest tests/regression/order_regression.py -m smoke
python -m pytest tests/regression/order_regression.py
```

## Підтвердження стабільності

```
python tests/regression/flaky_hunt.py --path tests/regression/order_regression.py --repeat 5
```
