"""Replay framework-neutral prediction files through OutcomeBench."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .predictions import replay_predictions


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay predictions without executing agent code")
    parser.add_argument("scenario", type=Path)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    result = replay_predictions(args.scenario, args.protocol, args.predictions, args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
