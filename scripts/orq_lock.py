"""CLI de coordinación entre sesiones: acquire | release | status."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tradinglab.orq_lock import LockError, acquire, release, status

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _print(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Locks de coordinación entre sesiones")
    parser.add_argument("command", choices=("acquire", "release", "status"))
    parser.add_argument("--resource", required=False)
    parser.add_argument("--owner", required=False)
    parser.add_argument("--cola", default=None)
    parser.add_argument("--wait", type=float, default=0.0)
    parser.add_argument("--locks-dir", default=None)
    args = parser.parse_args(argv)

    locks_dir = Path(args.locks_dir) if args.locks_dir else None
    try:
        if args.command == "status":
            _print(status(locks_dir=locks_dir))
            return 0
        if not args.resource or not args.owner:
            parser.error(f"{args.command} exige --resource y --owner")
        if args.command == "acquire":
            _print(
                acquire(
                    args.resource,
                    args.owner,
                    wait_s=args.wait,
                    cola=args.cola,
                    locks_dir=locks_dir,
                )
            )
            return 0
        _print(release(args.resource, args.owner, locks_dir=locks_dir))
        return 0
    except LockError as exc:
        _print({"error": str(exc), "owner": getattr(exc, "owner", None)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
