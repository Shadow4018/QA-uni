"""Перетворює JUnit XML-звіти pytest на Markdown-таблицю для Job Summary в GitHub Actions.

Використання:  python .github/scripts/junit_summary.py "Назва етапу" reports/unit.xml [...] >> "$GITHUB_STEP_SUMMARY"
Скрипт лише показує результати; падіння job визначає сам pytest (код завершення не змінюється).
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    title, paths = sys.argv[1], [Path(p) for p in sys.argv[2:]]
    total = failed = skipped = 0
    seconds = 0.0
    failures = []
    for path in paths:
        if not path.exists():
            print(f"### {title}\n\nЗвіт `{path}` не створено: тести не були запущені (див. лог кроку вище).\n")
            return
        for case in ET.parse(path).getroot().iter("testcase"):
            total += 1
            seconds += float(case.get("time") or 0)
            problem = case.find("failure")
            if problem is None:
                problem = case.find("error")
            if problem is not None:
                failed += 1
                failures.append((f"{case.get('classname')}::{case.get('name')}", problem.get("message") or ""))
            elif case.find("skipped") is not None:
                skipped += 1
    status = "✅ пройдено" if failed == 0 and total else "❌ є помилки"
    print(f"### {title}: {status}\n")
    print("| Усього | Пройшло | Впало | Пропущено | Час, с |")
    print("|---|---|---|---|---|")
    print(f"| {total} | {total - failed - skipped} | {failed} | {skipped} | {seconds:.2f} |\n")
    if failures:
        print("**Тести, що впали:**\n")
        for name, message in failures:
            print(f"- `{name}` — {message.splitlines()[0][:200] if message else 'без повідомлення'}")
        print()


if __name__ == "__main__":
    main()
