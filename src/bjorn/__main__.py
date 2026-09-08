"""Command line entry point."""

from __future__ import annotations

import argparse
import sys

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bjorn", description="A terminal front end for Bear.")
    parser.add_argument("--version", action="version", version=f"bjorn {__version__}")
    parser.add_argument(
        "--tag", metavar="TAG", default=None,
        help="start scoped to this tag as the workspace (overrides config)",
    )
    parser.add_argument(
        "--config", metavar="PATH", default=None, help="config file to read instead of the default",
    )
    parser.add_argument(
        "--demo", action="store_true", help="run against a built-in fake bearcli with sample notes",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from .app import run

    return run(tag=args.tag, config_path=args.config, demo=args.demo)


if __name__ == "__main__":
    sys.exit(main())
