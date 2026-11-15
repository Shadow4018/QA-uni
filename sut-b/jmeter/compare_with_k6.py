"""Порівняльна таблиця k6 та JMeter за тими самими профілями (для пункту 8 завдання).

Запуск (з папки sut-b):  python jmeter\\compare_with_k6.py
Потрібні: k6\\results\\summary-<тип>.json (k6 --summary-export) та jmeter\\results\\run-<тип>.jtl.
"""
import json
import sys
from pathlib import Path

import check_results as jm   # той самий каталог, що й цей скрипт

HERE = Path(__file__).parent
K6_DIR = HERE.parent / "k6" / "results"
JM_DIR = HERE / "results"


def k6_metrics(path):
    m = json.loads(path.read_text(encoding="utf-8"))["metrics"]
    return {
        "avg": m["http_req_duration"]["avg"],
        "p95": m["http_req_duration"]["p(95)"],
        "rps": m["http_reqs"]["rate"],
        "scn": m.get("full_scenarios_completed", {}).get("rate", 0.0),
        "err": m["http_req_failed"]["value"],
    }


jmeter = jm.load_all(JM_DIR)
rows = []
for name in jm.ORDER:
    k6_path = K6_DIR / f"summary-{name}.json"
    if name in jmeter and k6_path.exists():
        rows.append((name, k6_metrics(k6_path), jmeter[name]))

if not rows:
    sys.exit("Немає пар результатів: потрібні і k6\\results\\summary-*.json, і jmeter\\results\\run-*.jtl")

print("| профіль | інструмент | avg, мс | p95, мс | запитів/с | сценаріїв/с | error rate |")
print("|---|---|---|---|---|---|---|")
for name, k, j in rows:
    for tool, m in (("k6", k), ("JMeter", j)):
        print(f"| {name} | {tool} | {m['avg']:.1f} | {m['p95']:.0f} | {m['rps']:.1f} | "
              f"{m['scn']:.2f} | {m['err'] * 100:.2f}% |")
