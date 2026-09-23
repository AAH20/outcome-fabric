"""Run and verify a local synthetic Outcome Exchange case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .outcome_exchange import run, verify


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic synthetic Laya-compatible outcome exchange")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("spec", type=Path)
    run_parser.add_argument("--output", type=Path)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("spec", type=Path)
    verify_parser.add_argument("report", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        result = run(args.spec)
        rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    else:
        result = verify(args.spec, json.loads(args.report.read_text(encoding="utf-8")))
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
