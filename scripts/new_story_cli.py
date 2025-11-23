#!/usr/bin/env python3
"""
Minimal CLI to drive new-story setup per slot.

Examples:
  # Start setup for slot 3 (creates thread, clears cache)
  python scripts/new_story_cli.py start --slot 3

  # Resume (prints cache)
  python scripts/new_story_cli.py resume --slot 3

  # Record drafts
  python scripts/new_story_cli.py record --slot 3 --setting '{"genre":"cyberpunk"}'

  # Reset setup
  python scripts/new_story_cli.py reset --slot 3
"""

import argparse
import json
from pprint import pprint

from nexus.api.new_story_flow import (
    start_setup,
    resume_setup,
    record_drafts,
    reset_setup,
)


def main():
    parser = argparse.ArgumentParser(description="New story setup CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start")
    p_start.add_argument("--slot", type=int, required=True)
    p_start.add_argument("--model", default="gpt-5.1")

    p_resume = sub.add_parser("resume")
    p_resume.add_argument("--slot", type=int, required=True)

    p_record = sub.add_parser("record")
    p_record.add_argument("--slot", type=int, required=True)
    p_record.add_argument("--setting", type=str)
    p_record.add_argument("--character", type=str)
    p_record.add_argument("--seed", type=str)
    p_record.add_argument("--location", type=str)
    p_record.add_argument("--base-timestamp", type=str)

    p_reset = sub.add_parser("reset")
    p_reset.add_argument("--slot", type=int, required=True)

    args = parser.parse_args()

    if args.command == "start":
        thread_id = start_setup(args.slot, model=args.model)
        print(f"Started thread {thread_id} for slot {args.slot}")
    elif args.command == "resume":
        cache = resume_setup(args.slot)
        pprint(cache)
    elif args.command == "record":
        record_drafts(
            args.slot,
            setting=json.loads(args.setting) if args.setting else None,
            character=json.loads(args.character) if args.character else None,
            seed=json.loads(args.seed) if args.seed else None,
            location=json.loads(args.location) if args.location else None,
            base_timestamp=args.base_timestamp,
        )
        print(f"Recorded drafts for slot {args.slot}")
    elif args.command == "reset":
        reset_setup(args.slot)
        print(f"Reset setup for slot {args.slot}")


if __name__ == "__main__":
    main()
