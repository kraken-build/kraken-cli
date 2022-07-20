from __future__ import annotations

import argparse
import sys

from kraken.core import BuildError, Context, Task, TaskGraph
from termcolor import colored

from .base import BuildGraphCommand, print


class RunCommand(BuildGraphCommand):
    class Args(BuildGraphCommand.Args):
        skip_build: bool

    def __init__(self, main_target: str | None = None) -> None:
        super().__init__()
        self._main_target = main_target

    def get_description(self) -> str:
        if self._main_target:
            return f'execute "{self._main_target}" tasks'
        else:
            return "execute one or more kraken tasks"

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("-s", "--skip-build", action="store_true", help="just load the project, do not build")

    def resolve_tasks(self, args: BuildGraphCommand.Args, context: Context) -> list[Task]:
        if self._main_target:
            targets = [self._main_target] + list(args.targets or [])
            return context.resolve_tasks(targets)
        return super().resolve_tasks(args, context)

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: Args) -> int | None:  # type: ignore
        if args.skip_build:
            print(colored("Skipped build due to %s flag" % (colored("-s,--skip-build", attrs=["bold"]),), "blue"))
        else:
            graph.trim()
            if not graph:
                print(colored("Error: no tasks were selected", "red"), file=sys.stderr)
                return 1
            try:
                context.execute(graph, args.verbose)
            except BuildError as exc:
                print(colored("Error: %s" % (exc,), "red"), file=sys.stderr)
                return 1
        return 0
