"""apps/common/cli.py -- the shared `--config`/`--list-configs` argparse
pair (Step 64, roadmap.md; dev/docs/architecture-30-apps-4-5-and-configs.md
SS30.5).

Not a subcommand framework -- ~30 lines of plain argparse, added to a
parser the app itself owns. An app calls `add_config_arg(parser,
default=...)` alongside its own app-specific flags (`--target`, `--mode`,
`--grid`, ...) on that same parser, parses as usual, then calls
`resolve_config(args)` to turn the parsed `--config`/`--list-configs` pair
into a `configs.Config` (or an early, successful exit for `--list-configs`).

Per Step 64's scope (D-33): Apps 2 and 3 (`select_conditions.py`,
`compare_motors.py`) do **not** get wired up to this CLI in this step --
it is built now so the new apps the next few steps add can use it from
day one. Migrating the existing two apps' entry points is a later step.
"""

from __future__ import annotations

import argparse

import configs
from configs.schema import Config


def add_config_arg(parser: argparse.ArgumentParser, default: str) -> None:
    """Add `--config NAME` (defaulting to `default`) and `--list-configs`
    to `parser`. The app adds its own flags to the same parser before
    calling `parser.parse_args()`."""
    parser.add_argument(
        "--config",
        default=default,
        metavar="NAME",
        help=f"named scenario from configs/ (default: {default!r}); "
        "see --list-configs",
    )
    parser.add_argument(
        "--list-configs",
        action="store_true",
        help="print every registered config name with its notes' first "
        "line, then exit",
    )


def resolve_config(args: argparse.Namespace) -> Config:
    """Resolve `args.config`/`args.list_configs` (as added by
    `add_config_arg`) into a `configs.Config`.

    If `--list-configs` was passed, prints `configs.names()` with each
    config's `notes` first line and exits successfully (`SystemExit(0)`)
    without resolving `args.config` at all -- the caller never sees a
    return value in that case, matching `argparse`'s own `--help`
    convention of exiting rather than returning.
    """
    if args.list_configs:
        for name in configs.names():
            notes = configs.get(name).notes
            first_line = notes.splitlines()[0] if notes else ""
            print(f"{name}: {first_line}" if first_line else name)
        raise SystemExit(0)
    return configs.get(args.config)
