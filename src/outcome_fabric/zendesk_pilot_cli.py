"""Create an offline-verifiable private pilot package from a collected snapshot."""

import argparse
import json
from pathlib import Path

from .zendesk_pilot import assemble


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble private Zendesk pilot snapshot and declared sidecars")
    parser.add_argument("collection_dir", type=Path)
    parser.add_argument("pilot_config", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(assemble(args.collection_dir, args.pilot_config, args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
