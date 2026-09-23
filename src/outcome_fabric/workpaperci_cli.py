"""CLI for recorded-output finance workpaper regression checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .workpaperci import run, verify


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or verify a WorkpaperCI benchmark")
    parser.add_argument("command", choices=("run", "verify", "gate"))
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("scorecard", type=Path, nargs="?")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        if args.scorecard is None or args.output is not None:
            parser.error("verify requires a scorecard path and does not accept --output")
        result = verify(args.benchmark, json.loads(args.scorecard.read_text(encoding="utf-8")))
    else:
        if args.scorecard is not None:
            parser.error("run and gate accept only a benchmark path")
        result = run(args.benchmark)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.command == "gate" and result["gate"]["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
