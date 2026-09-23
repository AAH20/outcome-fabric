"""Collect a private, minimal Zendesk export snapshot using an OAuth token."""

import argparse
import json
import os
from pathlib import Path

from .zendesk_fetch import collect


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Zendesk cursor export; OAuth token comes only from environment")
    parser.add_argument("--subdomain", required=True)
    parser.add_argument("--start-time", required=True, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = collect(args.subdomain, args.start_time, args.output_dir, os.environ.get("ZENDESK_OAUTH_TOKEN", ""))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
