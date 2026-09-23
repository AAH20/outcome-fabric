"""Regenerate the public synthetic results index."""

from __future__ import annotations

import argparse
from pathlib import Path

from .registry import write_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the synthetic OutcomeBench registry")
    parser.add_argument("repo_root", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    write_registry(args.repo_root, args.output_dir)


if __name__ == "__main__":
    main()
