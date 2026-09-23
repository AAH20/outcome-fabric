"""Private OutcomeBench Field Lab pilot commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .fieldlab import preflight, run, verify


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight, run, or verify a private Field Lab pilot")
    parser.add_argument("command", choices=("preflight", "run", "verify"))
    parser.add_argument("pilot", type=Path)
    parser.add_argument("package", type=Path, nargs="?", help="Private package path for verification")
    parser.add_argument("--output", type=Path, help="Write a preflight report or private package")
    args = parser.parse_args()
    if args.command == "verify":
        if args.package is None or args.output is not None:
            parser.error("verify requires a package path and does not accept --output")
        result = verify(args.pilot, json.loads(args.package.read_text(encoding="utf-8")))
    else:
        if args.package is not None:
            parser.error("preflight and run accept only a pilot path")
        result = preflight(args.pilot) if args.command == "preflight" else run(args.pilot)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
