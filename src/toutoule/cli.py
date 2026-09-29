"""Command-line entry point. Run: uv run python -m toutoule.cli <command>"""

import argparse
import sys

from toutoule.config import ConfigError, get_settings
from toutoule.db import get_engine, init_db


def check_config() -> int:
    """Validate settings and report the result. Returns the process exit code."""
    try:
        get_settings()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    print("Config OK")
    return 0


def init_database() -> int:
    """Create any missing tables at DATABASE_URL and list them. Returns the exit code."""
    try:
        engine = get_engine()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    created = init_db(engine)
    if created:
        print("Created tables: " + ", ".join(created))
    else:
        print("All tables already exist.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m toutoule.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-config", help="validate settings in .env")
    commands.add_parser("init-db", help="create the database tables at DATABASE_URL")

    args = parser.parse_args(argv)
    handlers = {"check-config": check_config, "init-db": init_database}
    return handlers[args.command]()


if __name__ == "__main__":
    sys.exit(main())
