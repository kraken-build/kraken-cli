from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from kraken.core.build_context import BuildContext
from kraken.core.build_graph import BuildGraph
from slap.core.cli import CliApp, Command

from . import __version__


class RunCommand(Command):
    """run a kraken build"""

    class Args:
        file: Path | None
        build_dir: Path
        verbose: bool
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
        parser.add_argument("-v", "--verbose", action="store_true", help="always show task output and logs")
        parser.add_argument("targets", metavar="target", nargs="*", help="one or more target to build")

    def execute(self, args: Args) -> int | None:
        from .executor import Executor

        if args.verbose:
            logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

        context = BuildContext(args.build_dir)
        context.load_project(args.file, Path.cwd())
        context.finalize()
        targets = context.resolve_tasks(args.targets or None)
        graph = BuildGraph(targets)
        graph.trim()
        if not graph:
            print("error: no tasks selected", file=sys.stderr)
            return 1

        Executor(graph, args.verbose).execute()
        return None


def _entrypoint() -> None:
    from kraken import core

    app = CliApp("kraken", f"cli: {__version__}, core: {core.__version__}", features=[])
    app.add_command("run", RunCommand())
    sys.exit(app.run())


if __name__ == "__main__":
    _entrypoint()
