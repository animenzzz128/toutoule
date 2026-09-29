"""Command-line entry point. Run: uv run python -m toutoule.cli <command>"""

import argparse
import sys

from toutoule.config import ConfigError, get_settings


def check_config() -> int:
    """Validate settings and report the result. Returns the process exit code."""
    try:
        get_settings()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    print("Config OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m toutoule.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-config", help="validate settings in .env")

    args = parser.parse_args(argv)
    handlers = {"check-config": check_config}
    return handlers[args.command]()


if __name__ == "__main__":
    sys.exit(main())
