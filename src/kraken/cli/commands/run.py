from __future__ import annotations

import argparse
import builtins
import sys
from functools import partial

from kraken.core import BuildError, Context, Task, TaskGraph
from kraken.core.executor import COLORS_BY_RESULT
from termcolor import colored

from .base import BuildGraphCommand


class RunCommand(BuildGraphCommand):
    class Args(BuildGraphCommand.Args):
        skip_build: bool
        allow_no_tasks: bool

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
        parser.add_argument("-0", "--allow-no-tasks", action="store_true", help="don't error if no tasks got selected")

    def resolve_tasks(self, args: BuildGraphCommand.Args, context: Context) -> list[Task]:
        if self._main_target:
            targets = [self._main_target] + list(args.targets or [])
            return context.resolve_tasks(targets)
        return super().resolve_tasks(args, context)

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: Args) -> int | None:  # type: ignore
        print = partial(builtins.print, flush=True)
        status_code = 0

        if args.skip_build:
            print(colored("Skipped build due to %s flag" % (colored("-s,--skip-build", attrs=["bold"]),), "blue"))
        else:
            graph.trim()
            if not graph:
                if args.allow_no_tasks:
                    print(colored("Note: no tasks were selected (--allow-no-tasks)", "blue"), file=sys.stderr)
                    return 0
                else:
                    print(colored("Error: no tasks were selected", "red"), file=sys.stderr)
                    return 1

            try:
                context.execute(graph, args.verbose > 0)
            except BuildError as exc:
                print()
                print(colored("Error: %s" % (exc,), "red"), file=sys.stderr, flush=True)
                status_code = 1

            print()
            print(colored("Build summary", "blue", attrs=["underline", "bold"]))
            print()
            tasks1 = {task: graph.get_status(task) for task in graph.tasks()}
            tasks = {task: status for task, status in tasks1.items() if status is not None}
            longest_path = max(map(len, (t.path for t in tasks)))
            for task, status in sorted(tasks.items(), key=lambda t: t[0].path):
                print(task.path.ljust(longest_path), colored(status.type.name, COLORS_BY_RESULT[status.type]))
            print()

        return status_code
