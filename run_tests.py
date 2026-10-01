# SPDX-License-Identifier: AGPL-3.0-only
"""Acceptance suite for all three comparison profiles."""
import json
from pathlib import Path
from self_test import run_self_test


def main():
    result = run_self_test()
    print(f"通过 {result['passed_count']}/{result['total_count']} 项")
    for check in result['checks']:
        if not check['ok']:
            print(json.dumps(check, ensure_ascii=False))
    destination = Path(__file__).parent / "output"
    destination.mkdir(exist_ok=True)
    (destination / "验收结果.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result['passed'] else 1


if __name__ == "__main__":
    raise SystemExit(main())
