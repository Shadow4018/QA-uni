"""Обчислює метрики з JTL-файлів JMeter і перевіряє ті самі критерії (thresholds), що й у k6.

Запуск (з папки sut-b):  python jmeter\\check_results.py
Читає jmeter\\results\\run-<тип>.jtl (CSV із заголовком — типовий формат JMeter).

Метрики: avg та p95 — за полем elapsed (мс); throughput = кількість запитів / тривалість від першого
запиту до завершення останнього; error rate = частка Sampler-ів із success=false (враховує Assertions).
p95 рахується за методом nearest-rank, тому може трохи відрізнятися від Dashboard JMeter.
"""
import csv
import math
import sys
from pathlib import Path

ORDER = ["baseline", "load", "stress", "spike"]
# Ті самі критерії, що в k6\store_load_test.js (checks-аналога в JMeter немає: його роль виконують Assertions)
CRITERIA = {
    "baseline": {"p95": 200, "err": 0.01},
    "load": {"p95": 500, "err": 0.01},
    "stress": {"p95": 1500, "err": 0.05},
    "spike": {"p95": 1500, "err": 0.05},
}
READ_LABEL = "GET /orders/{id}"


def analyze(path):
    elapsed, starts, ends, failed, scenarios = [], [], [], 0, 0
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ts, el = int(row["timeStamp"]), int(row["elapsed"])
            ok = row["success"].strip().lower() == "true"
            elapsed.append(el)
            starts.append(ts)
            ends.append(ts + el)
            if not ok:
                failed += 1
            elif row["label"] == READ_LABEL:
                scenarios += 1   # успішне читання = завершений бізнес-сценарій
    if not elapsed:
        raise ValueError(f"{path}: немає жодного запису")
    n = len(elapsed)
    elapsed.sort()
    p95 = elapsed[max(0, math.ceil(0.95 * n) - 1)]
    seconds = max((max(ends) - min(starts)) / 1000.0, 0.001)
    return {
        "samples": n,
        "avg": sum(elapsed) / n,
        "p95": p95,
        "max": elapsed[-1],
        "rps": n / seconds,
        "scn": scenarios / seconds,
        "err": failed / n,
    }


def load_all(results_dir):
    out = {}
    for name in ORDER:
        path = results_dir / f"run-{name}.jtl"
        if path.exists():
            out[name] = analyze(path)
    return out


def verdict(name, m):
    c = CRITERIA[name]
    return "виконано" if m["p95"] < c["p95"] and m["err"] < c["err"] else "ПОРУШЕНО"


def main():
    results = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "results"
    data = load_all(results)
    if not data:
        sys.exit(f"Не знайдено run-*.jtl у {results}")
    print("| тип | avg, мс | p95, мс | max, мс | запитів/с | сценаріїв/с | error rate | thresholds |")
    print("|---|---|---|---|---|---|---|---|")
    for name, m in data.items():
        print(f"| {name} | {m['avg']:.1f} | {m['p95']:.0f} | {m['max']:.0f} | {m['rps']:.1f} | "
              f"{m['scn']:.2f} | {m['err'] * 100:.2f}% | {verdict(name, m)} |")


if __name__ == "__main__":
    main()
