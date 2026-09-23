"""Run the built-in synthetic support adapters."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .simulation import run_simulation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run synthetic support adapters and create a scorecard")
    parser.add_argument("scenario", type=Path)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_simulation(args.scenario, args.protocol, args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
