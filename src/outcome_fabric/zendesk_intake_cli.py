"""Offline Zendesk export intake into the Outcome Evidence Bridge."""

import argparse
import json
from pathlib import Path

from .zendesk_intake import run, verify


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile customer-supplied Zendesk export pages without contacting Zendesk")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "verify"):
        part = sub.add_parser(name)
        part.add_argument("config", type=Path)
        part.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    result = run(args.config, args.output_dir) if args.command == "run" else verify(args.config, args.output_dir)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
