from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__
from .app import GitscopeApp


def main(argv: Sequence[str] | None = None) -> int: # accepting argv makes this entrypoint easy to test without patching sys.argv.
    """Run the gitscope Textual application."""

    parser = argparse.ArgumentParser(prog="gitscope") # Keeping prog="gitscope" ensures help output matches the installed CLI command.
    parser.add_argument("--version", action="store_true", help="print the gitscope version") # --version is handled manually instead of using argparse's action="version", which keeps main() returning 0 clearl.
    args = parser.parse_args(argv) # parse_args() can still raise SustemExit for --help or invalid arguments, so tests should account for that behaviour.

    if args.version: # Version handling exits before constructing the Textual app, which keeps gitscope --version fast and safe outside a git repository.
        print(f"gitscope {__version__}") # Printing the version from package metadata avoids duplicating the version string in the CLI layer.
        return 0

    GitscopeApp().run() # GitscopeApp.run() is intentionally the only app startup point, keeping CLI parsing seperate from UI logic.
    return 0 # Returning 0 after the app exits makes this compatible with console-script entrypoints and shell status checks.
