"""One-command local OutcomeBench entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .outcomebench import run, verify


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or verify the local support outcome benchmark")
    parser.add_argument("command", choices=("run", "verify"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("scorecard", type=Path, nargs="?", help="Scorecard path for verification")
    parser.add_argument("--output", type=Path, help="Write run scorecard here")
    args = parser.parse_args()
    if args.command == "verify":
        if args.scorecard is None or args.output is not None:
            parser.error("verify requires scorecard path and does not accept --output")
        result = verify(args.manifest, args.protocol, json.loads(args.scorecard.read_text(encoding="utf-8")))
    else:
        if args.scorecard is not None:
            parser.error("run accepts only manifest and protocol paths")
        result = run(args.manifest, args.protocol)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
