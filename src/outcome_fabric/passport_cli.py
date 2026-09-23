"""Generate or verify an offline Outcome Passport."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .passport import generate, verify


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or verify a local Outcome Passport")
    parser.add_argument("command", choices=("generate", "verify"))
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    result = generate(data) if args.command == "generate" else verify(data)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
