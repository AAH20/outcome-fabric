"""Command-line entry point for the offline reference case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import evaluate


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare AI service plans and emit an advisory receipt")
    parser.add_argument("case", type=Path, help="Path to a JSON case")
    parser.add_argument("--output", type=Path, help="Write JSON receipt here instead of stdout")
    args = parser.parse_args()
    case = json.loads(args.case.read_text(encoding="utf-8"))
    receipt = evaluate(case)
    result = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
