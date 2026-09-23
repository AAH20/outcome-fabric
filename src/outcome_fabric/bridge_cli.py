"""Build and verify local Outcome Evidence Bridge packages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bridge import build, verify


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or verify a local evidence package")
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument("package", type=Path, nargs="?", help="Package path for verification")
    parser.add_argument("--output", type=Path, help="Write the built package here")
    args = parser.parse_args()
    if args.command == "verify":
        if args.package is None or args.output is not None:
            parser.error("verify requires a package path and does not accept --output")
        result = verify(args.manifest, json.loads(args.package.read_text(encoding="utf-8")))
    else:
        if args.package is not None:
            parser.error("build accepts only a manifest path")
        result = build(args.manifest)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
