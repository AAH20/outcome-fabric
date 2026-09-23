"""Local Acceptance Ledger commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .acceptance_ledger import append_event, evaluate, verify


def main() -> None:
    parser = argparse.ArgumentParser(description="Record and verify local, unauthenticated review evidence")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("record", "evaluate", "verify", "serve"):
        part = sub.add_parser(command)
        part.add_argument("config", type=Path)
        part.add_argument("events", type=Path)
        if command == "record":
            part.add_argument("--task", required=True)
            part.add_argument("--reviewer", required=True)
            part.add_argument("--action", choices=("REVIEW", "ADJUDICATE"), required=True)
            part.add_argument("--decision", choices=("ACCEPT", "REJECT", "CORRECTION_REQUIRED"), required=True)
            part.add_argument("--minutes", type=int, required=True)
            part.add_argument("--note", default="")
            part.add_argument("--claim")
            part.add_argument("--severity", choices=("MATERIAL", "MINOR"))
            part.add_argument("--proposed-value")
        elif command == "verify":
            part.add_argument("passport", type=Path)
        elif command == "evaluate":
            part.add_argument("--output", type=Path)
        elif command == "serve":
            part.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.command == "record":
        if bool(args.claim) != bool(args.severity) or (args.proposed_value is not None and not args.claim):
            parser.error("--claim and --severity must be supplied together; --proposed-value needs a claim")
        findings = ([{"claim_id": args.claim, "severity": args.severity, "reason": args.note, "proposed_value": args.proposed_value}] if args.claim else [])
        result = append_event(args.config, args.events, args.task, args.reviewer, args.action, args.decision, args.minutes, args.note, findings=findings)
    elif args.command == "evaluate":
        result = evaluate(args.config, args.events)
    elif args.command == "verify":
        result = verify(args.config, args.events, json.loads(args.passport.read_text(encoding="utf-8")))
    else:
        from .acceptance_ledger_web import serve
        serve(args.config, args.events, args.port)
        return
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.command == "evaluate" and args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
