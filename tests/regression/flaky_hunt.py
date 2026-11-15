"""Виявлення нестабільних тестів: повторні, зворотні, випадкові та ізольовані запуски.

Запуск (з папки sut-b, з активованим .venv; Docker має працювати):
  python tests/regression/flaky_hunt.py --path tests/regression/order_regression_before.py   # до виправлень
  python tests/regression/flaky_hunt.py --path tests/regression/order_regression.py --repeat 5 # підтвердження стабільності

Що робить: запускає suite кілька разів у різних умовах і порівнює результат кожного тесту.
  default#N  — звичайний порядок, N повторів (виявляє недетермінованість: час, випадкові дані)
  reverse    — зворотний порядок (виявляє order dependency)
  random#S   — випадковий порядок із зерном S (виявляє залежність від порядку й спільного стану)
  alone      — кожен тест окремим запуском (виявляє залежність від інших тестів)
Тест, чиї результати різняться між запусками, — нестабільний; висновок про причину підказує, де саме він падає.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def run_pytest(target, env_extra):
    """Один запуск pytest; повертає (результати {тест: PASS|FAIL|SKIP}, код завершення, stderr+stdout)."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.xml"
        cmd = [sys.executable, "-m", "pytest", target, "-q", "--tb=no", "-p", "no:cacheprovider",
               "--junitxml", str(report)]
        proc = subprocess.run(cmd, env={**os.environ, **env_extra}, capture_output=True, text=True)
        results = {}
        if report.exists():
            for case in ET.parse(report).getroot().iter("testcase"):
                name = case.get("name")
                if case.find("failure") is not None or case.find("error") is not None:
                    results[name] = "FAIL"
                elif case.find("skipped") is not None:
                    results[name] = "SKIP"
                else:
                    results[name] = "PASS"
        return results, proc.returncode, proc.stdout + proc.stderr


def collect_node_ids(path):
    proc = subprocess.run([sys.executable, "-m", "pytest", path, "--collect-only", "-q", "-p", "no:cacheprovider"],
                          capture_output=True, text=True)
    ids = [line.strip() for line in proc.stdout.splitlines() if "::" in line and not line.startswith(" ")]
    if not ids:
        sys.exit("Не вдалося зібрати тести:\n" + proc.stdout + proc.stderr)
    return ids


def short(node_id):
    return node_id.split("::", 1)[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--path", default="tests/regression/order_regression.py")
    parser.add_argument("--repeat", type=int, default=3, help="скільки разів запустити у звичайному порядку")
    parser.add_argument("--seeds", type=int, nargs="*", default=[1, 2, 3], help="зерна випадкового порядку")
    parser.add_argument("--skip-alone", action="store_true", help="пропустити ізольовані запуски кожного тесту")
    args = parser.parse_args()

    runs = []   # (мітка, {тест: статус})

    def record(label, results, code, output):
        if not results:
            sys.exit(f"Запуск '{label}' не дав жодного результату (код {code}). Вивід pytest:\n{output[-2000:]}")
        runs.append((label, results))
        failed = [t for t, s in results.items() if s == "FAIL"]
        print(f"  {label:<14} пройшло {sum(s == 'PASS' for s in results.values())}, впало {len(failed)}", flush=True)

    print(f"Файл: {args.path}")
    for n in range(1, args.repeat + 1):
        record(f"default#{n}", *run_pytest(args.path, {"REGRESSION_ORDER": "default"}))
    record("reverse", *run_pytest(args.path, {"REGRESSION_ORDER": "reverse"}))
    for seed in args.seeds:
        record(f"random#{seed}", *run_pytest(args.path, {"REGRESSION_ORDER": "random", "REGRESSION_SEED": str(seed)}))

    alone = {}
    if not args.skip_alone:
        print("  ізольовані запуски (кожен тест окремо):", flush=True)
        for node_id in collect_node_ids(args.path):
            results, code, output = run_pytest(node_id, {"REGRESSION_ORDER": "default"})
            alone[short(node_id)] = results.get(short(node_id), "FAIL")
            print(f"    {short(node_id):<40} {alone[short(node_id)]}", flush=True)

    tests = list(runs[0][1])
    labels = [label for label, _ in runs] + (["alone"] if alone else [])
    symbol = {"PASS": "ok", "FAIL": "FAIL", "SKIP": "skip", None: "?"}
    print("\n| тест | " + " | ".join(labels) + " | висновок |")
    print("|---|" + "---|" * (len(labels) + 1))
    problems = 0
    for test in tests:
        row = {label: res.get(test) for label, res in runs}
        if alone:
            row["alone"] = alone.get(test)
        values = list(row.values())
        default_vals = [v for k, v in row.items() if k.startswith("default")]
        in_full = [v for k, v in row.items() if k != "alone"]
        if all(v == "PASS" for v in values):
            verdict = "стабільний"
        elif all(v == "FAIL" for v in values):
            verdict = "постійно падає (звичайна помилка, не flaky)"
            problems += 1
        else:
            problems += 1
            if len(set(default_vals)) > 1:
                verdict = "НЕСТАБІЛЬНИЙ: різний результат при однакових запусках (час / випадкові дані)"
            elif alone and row.get("alone") == "FAIL" and "PASS" in in_full:
                verdict = "FLAKY: падає окремо, проходить у наборі (залежить від іншого тесту — order dependency)"
            elif alone and row.get("alone") == "PASS" and "FAIL" in in_full:
                verdict = "FLAKY: проходить окремо, падає в наборі (спільний стан або порядок)"
            else:
                verdict = "FLAKY: результат залежить від порядку запуску"
        print(f"| {test} | " + " | ".join(symbol[row[l]] for l in labels) + f" | {verdict} |")

    print(f"\nПроблемних тестів: {problems} із {len(tests)}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
