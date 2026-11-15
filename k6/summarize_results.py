"""Зводить k6\\results\\summary-*.json у таблицю для звіту.

Запуск (з папки sut-b):  python k6\\summarize_results.py
Читає лише локальні файли summary-<тип>.json, створені командою k6 run --summary-export.
"""
import json
import sys
from pathlib import Path

ORDER = ["baseline", "load", "stress", "spike"]
RESULTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "results"


def thresholds_ok(metrics):
    """True, якщо жоден threshold не порушено (у summary-export 'False' = threshold НЕ порушено)."""
    for metric in metrics.values():
        for violated in metric.get("thresholds", {}).values():
            if violated:
                return False
    return True


def row(name, data):
    m = data["metrics"]
    dur = m["http_req_duration"]
    return {
        "тип": name,
        "avg, мс": f"{dur['avg']:.1f}",
        "p95, мс": f"{dur['p(95)']:.1f}",
        "max, мс": f"{dur['max']:.0f}",
        "запитів/с": f"{m['http_reqs']['rate']:.1f}",
        "всього запитів": str(m["http_reqs"]["count"]),
        "сценаріїв/с": f"{m.get('full_scenarios_completed', {}).get('rate', 0):.2f}",
        "error rate": f"{m['http_req_failed']['value'] * 100:.2f}%",
        "thresholds": "виконано" if thresholds_ok(m) else "ПОРУШЕНО",
    }


rows = []
for name in ORDER:
    path = RESULTS / f"summary-{name}.json"
    if path.exists():
        rows.append(row(name, json.loads(path.read_text(encoding="utf-8"))))

if not rows:
    sys.exit(f"Не знайдено summary-*.json у {RESULTS}")

headers = list(rows[0])
print("| " + " | ".join(headers) + " |")
print("|" + "|".join("---" for _ in headers) + "|")
for r in rows:
    print("| " + " | ".join(r[h] for h in headers) + " |")
