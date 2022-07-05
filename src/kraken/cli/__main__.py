from __future__ import annotations

import argparse
import logging

# import profile
import sys
from pathlib import Path

from kraken.core.build_context import BuildContext
from kraken.core.build_graph import BuildGraph
from kraken.core.task import Task
from slap.core.cli import CliApp, Command

from . import __version__


class BaseCommand(Command):
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

    def resolve_tasks(self, args: Args, context: BuildContext) -> list[Task]:
        return context.resolve_tasks(args.targets or None)

    def execute(self, args: Args) -> int | None:
        if args.verbose:
            logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

        context = BuildContext(args.build_dir)
        context.load_project(args.file, Path.cwd())
        context.finalize()
        targets = self.resolve_tasks(args, context)
        graph = BuildGraph(targets)

        return self.execute_with_graph(context, graph, args)

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: Args) -> int | None:
        raise NotImplementedError


class RunCommand(BaseCommand):
    """run a kraken build"""

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: BaseCommand.Args) -> int | None:
        from .executor import Executor

        graph.trim()
        if not graph:
            print("error: no tasks selected", file=sys.stderr)
            return 1

        Executor(graph, args.verbose).execute()
        return None


class LsCommand(BaseCommand):
    """list targets in the build"""

    class Args(BaseCommand.Args):
        all: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("-a", "--all", action="store_true")

    def resolve_tasks(self, args: Args, context: BuildContext) -> list[Task]:  # type: ignore
        if args.all:
            tasks: list[Task] = []
            for project in context.iter_projects():
                tasks += project.tasks().values()
            return tasks
        return super().resolve_tasks(args, context)

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: BaseCommand.Args) -> None:
        for task in graph.execution_order():
            print(task)


def _main() -> None:
    from kraken import core

    app = CliApp("kraken", f"cli: {__version__}, core: {core.__version__}", features=[])
    app.add_command("run", RunCommand())
    app.add_command("ls", LsCommand())
    sys.exit(app.run())


def _entrypoint() -> None:
    _main()
    # prof = profile.Profile()
    # try:
    #     prof.runcall(_main)
    # finally:
    #     import pstats
    #     stats = pstats.Stats(prof)
    #     stats.sort_stats('cumulative')
    #     stats.print_stats(.1)


if __name__ == "__main__":
    _entrypoint()
