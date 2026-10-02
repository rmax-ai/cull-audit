"""Command-line interface for cull-audit.

Exit codes:
    EXIT_SUCCESS: The command completed successfully.
    EXIT_USAGE: The command line was invalid.
    EXIT_CONTRACT: Input or output did not satisfy a cull-audit contract.
    EXIT_IO: A local filesystem or image operation failed.
    EXIT_PROVIDER: A provider operation failed.
"""

import argparse
import sys
from typing import Sequence

from . import __version__

EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_CONTRACT = 3
EXIT_IO = 4
EXIT_PROVIDER = 5


def build_parser() -> argparse.ArgumentParser:
    """Build the T01 command-line parser."""
    parser = argparse.ArgumentParser(prog="cull-audit")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "audit", "demo"):
        subparsers.add_parser(command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and dispatch the currently scaffolded commands."""
    args = build_parser().parse_args(argv)
    print(f"{args.command}: not implemented yet", file=sys.stderr)
    return EXIT_CONTRACT
