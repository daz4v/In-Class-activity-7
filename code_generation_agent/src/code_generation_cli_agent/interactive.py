from __future__ import annotations

import shlex
import sys


INTRO = """\
Interactive CCA session
Type a normal cca command WITHOUT the leading 'cca'.

Examples:
  create "calculator app"
  create "web scraper" --planning detailed
  commit "my message" --repo output/my_project

Commands:
  help           Show this help
  exit | quit    Exit
  clear          Clear the screen
"""


def _clear_screen() -> None:
    # Works on most terminals without extra dependencies.
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def repl() -> int:
    """A minimal interactive shell for the existing argparse CLI."""
    from .cli import run

    _clear_screen()
    print(INTRO)

    while True:
        try:
            line = input("cca> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not line:
            continue

        low = line.lower()
        if low in {"exit", "quit"}:
            return 0
        if low == "help":
            print(INTRO)
            continue
        if low == "clear":
            _clear_screen()
            continue

        try:
            argv = shlex.split(line)
        except ValueError as e:
            print(f"Parse error: {e}", file=sys.stderr)
            continue

        # Run the existing CLI command.
        code = run(argv)
        if code:
            # Keep session alive on errors.
            continue


def main() -> None:
    raise SystemExit(repl())
