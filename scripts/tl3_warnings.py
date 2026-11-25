"""CLI de avisos que viajan: list | render <subject>."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tradinglab.tl3 import warnings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avisos TL3 por subject")
    sub = parser.add_subparsers(dest="command", required=True)
    list_cmd = sub.add_parser("list", help="todos los avisos en JSON")
    list_cmd.add_argument("--db", default=None)
    render_cmd = sub.add_parser("render", help="markdown de un subject")
    render_cmd.add_argument("subject")
    render_cmd.add_argument("--db", default=None)
    args = parser.parse_args(argv)

    db_path = Path(args.db) if args.db else None
    if args.command == "list":
        items = (
            warnings.all_warnings(db_path=db_path)
            if db_path is not None
            else warnings.all_warnings()
        )
        print(json.dumps(items, ensure_ascii=False, indent=1, default=str))
        return 0
    text = (
        warnings.render(args.subject, db_path=db_path)
        if db_path is not None
        else warnings.render(args.subject)
    )
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
