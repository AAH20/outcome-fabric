"""Command-line runner for the offline finance workpaper reference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .finance_workpaper import build, verify


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or verify a finance workpaper Passport")
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("case", type=Path)
    parser.add_argument("passport", type=Path, nargs="?")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        if args.passport is None or args.output is not None:
            parser.error("verify requires a Passport path and does not accept --output")
        result = verify(args.case, json.loads(args.passport.read_text(encoding="utf-8")))
    else:
        if args.passport is not None:
            parser.error("build accepts only a case path")
        result = build(args.case)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
