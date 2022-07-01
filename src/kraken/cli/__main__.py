from __future__ import annotations
from pathlib import Path
from . import __version__
import argparse
import sys
from typing import Optional
from kraken.core.build_context import BuildContext
from slap.core.cli import Command, CliApp


class RunCommand(Command):
    """run a kraken build"""

    class Args:
        file: Path | None
        build_dir: Path
        targets: list[str]

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("-f", "--file", metavar="PATH", type=Path, help="the kraken build script to load")
        parser.add_argument(
            "-b",
            "--build-dir",
            metavar="PATH",
            type=Path,
            default=Path(".build"),
            help="the build directory to write to [default: %(default)s]",
        )
        parser.add_argument("targets", metavar="target", nargs="*", help="one or more target to build")

    def execute(self, args: Args) -> None:
        context = BuildContext(args.build_dir)
        context.load_project(args.file)
        targets = context.resolve_tasks(args.targets or None)
        print(targets)


def _entrypoint() -> None:
    from kraken import core
    app = CliApp("kraken", f"cli: {__version__}, core: {core.__version__}")
    app.add_command("run", RunCommand())
    sys.exit(app.run())


if __name__ == "__main__":
    _entrypoint()
