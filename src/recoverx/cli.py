"""Command-line interface entry point for RecoverX."""

import argparse
import sys

from recoverx._version import __version__


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="recoverx",
        description="Forensic-grade, non-destructive data recovery application",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    _ = args
    return 0


if __name__ == "__main__":
    sys.exit(main())
