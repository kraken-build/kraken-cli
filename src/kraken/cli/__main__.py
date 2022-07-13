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
from termcolor import colored

from . import __version__


class BaseCommand(Command):
    class Args:
        file: Path | None
        build_dir: Path
        verbose: bool
        quiet: bool
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
        parser.add_argument("-q", "--quiet", action="store_true", help="show less logs")
        parser.add_argument("targets", metavar="target", nargs="*", help="one or more target to build")

    def resolve_tasks(self, args: Args, context: BuildContext) -> list[Task]:
        return context.resolve_tasks(args.targets or None)

    def execute(self, args: Args) -> int | None:
        logging.basicConfig(
            level=logging.INFO if args.verbose else logging.ERROR if args.quiet else logging.WARNING,
            format=f"{colored('%(levelname)7s', 'magenta')} | {colored('%(name)s', 'blue')} | "
            f"{colored('%(message)s', 'cyan')}",
        )

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

    class Args(BaseCommand.Args):
        skip_build: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("-s", "--skip-build", action="store_true", help="just load the project, do not build")

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: Args) -> int | None:  # type: ignore
        from .executor import Executor

        graph.trim()
        if not graph:
            print("error: no tasks selected", file=sys.stderr)
            return 1

        if not args.skip_build:
            return Executor(graph, args.verbose).execute()
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


class QueryCommand(BaseCommand):
    class Args(BaseCommand.Args):
        is_up_to_date: bool
        legend: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("--legend", action="store_true", help="print out a legend along with the query result")
        parser.add_argument("--is-up-to-date", action="store_true", help="query if the selected task(s) are up to date")

    def execute(self, args: BaseCommand.Args) -> int | None:
        args.quiet = True
        return super().execute(args)

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: Args) -> int | None:  # type: ignore
        from .executor import Executor, TaskStatus, get_task_status

        if args.is_up_to_date:
            tasks = list(graph.tasks(required_only=True))
            print(f"querying status of {len(tasks)} task(s)")
            print()

            need_to_run = 0
            up_to_date = 0
            for task in graph.execution_order():
                if task not in tasks:
                    continue
                status = get_task_status(task)
                print(" ", task.path, colored(status.name, Executor.COLORS_BY_STATUS[status]))
                if status in (TaskStatus.SKIPPABLE, TaskStatus.UP_TO_DATE):
                    up_to_date += 1
                else:
                    need_to_run += 1

            print()
            print(colored(f"{up_to_date} task(s) are up to date, need to run {need_to_run} task(s)", attrs=["bold"]))

            if args.legend:
                print()
                print("legend:")
                help_text = {
                    TaskStatus.SKIPPABLE: "the task reports that it can and will be skipped",
                    TaskStatus.UP_TO_DATE: "the task reports that it is up to date",
                    TaskStatus.OUTDATED: "the task reports that it is outdated",
                    TaskStatus.QUEUED: "the task needs to run always or it cannot determine its up to date status",
                }
                for status in TaskStatus:
                    print(colored(status.name.rjust(12), Executor.COLORS_BY_STATUS[status]) + ":", help_text[status])

            exit_code = 0 if need_to_run == 0 else 1
            print()
            print("exit code:", exit_code)
            sys.exit(exit_code)
        else:
            self.get_parser().error("missing query")


def _main() -> None:
    from kraken import core

    app = CliApp("kraken", f"cli: {__version__}, core: {core.__version__}", features=[])
    app.add_command("run", RunCommand())
    app.add_command("ls", LsCommand())
    app.add_command("query", QueryCommand())
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
