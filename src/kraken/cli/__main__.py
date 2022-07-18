from __future__ import annotations

import argparse
import logging

# import profile
import sys
from pathlib import Path
from typing import Any

from kraken.core.build_context import BuildContext
from kraken.core.build_graph import BuildGraph
from kraken.core.property import Property
from kraken.core.task import Task
from slap.core.cli import CliApp, Command, Group
from termcolor import colored

from kraken.cli.buildenv.environment import EnvironmentManager
from kraken.cli.buildenv.project import DefaultProjectImpl

from . import __version__

logger = logging.getLogger(__name__)


class BuildAwareCommand(Command):
    """Base class for commands that are aware of a build directory and the environment manager."""

    class Args:
        build_dir: Path

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("-v", "--verbose", action="store_true", help="always show task output and logs")
        parser.add_argument("-q", "--quiet", action="store_true", help="show less logs")
        parser.add_argument(
            "-b",
            "--build-dir",
            metavar="PATH",
            type=Path,
            default=Path(".build"),
            help="the build directory to write to [default: %(default)s]",
        )

    def get_environment_manager(self, args: Args) -> EnvironmentManager:
        return EnvironmentManager(args.build_dir / "buildenv", DefaultProjectImpl(Path.cwd()))

    def execute(self, args: Any) -> int | None:
        logging.basicConfig(
            level=logging.INFO if args.verbose else logging.ERROR if args.quiet else logging.WARNING,
            format=f"{colored('%(levelname)7s', 'magenta')} | {colored('%(name)s', 'blue')} | "
            f"{colored('%(message)s', 'cyan')}",
        )
        return None


class BuildGraphCommand(BuildAwareCommand):
    """Base class for commands that require the fully materialized Kraken build graph."""

    class Args(BuildAwareCommand.Args):
        file: Path | None
        verbose: bool
        quiet: bool
        targets: list[str]

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("targets", metavar="target", nargs="*", help="one or more target to build")

    def resolve_tasks(self, args: Args, context: BuildContext) -> list[Task]:
        return context.resolve_tasks(args.targets or None)

    def execute(self, args: Args) -> int | None:
        super().execute(args)
        manager = self.get_environment_manager(args)
        if not manager.are_we_in():
            if manager.check_outdated():
                manager.install()
            return manager.dispatch(sys.argv[1:])

        context = BuildContext(args.build_dir)
        context.load_project(None, Path.cwd())
        context.finalize()
        targets = self.resolve_tasks(args, context)
        graph = BuildGraph(targets)

        return self.execute_with_graph(context, graph, args)

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: Args) -> int | None:
        raise NotImplementedError


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

    def resolve_tasks(self, args: BuildGraphCommand.Args, context: BuildContext) -> list[Task]:
        if self._main_target:
            targets = [self._main_target] + list(args.targets or [])
            return context.resolve_tasks(targets)
        return super().resolve_tasks(args, context)

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: Args) -> int | None:  # type: ignore
        from .executor import Executor

        graph.trim()
        if not graph:
            print("error: no tasks selected", file=sys.stderr)
            return 1

        if not args.skip_build:
            return Executor(graph, args.verbose).execute()
        return None


class LsCommand(BuildGraphCommand):
    """list targets in the build"""

    class Args(BuildGraphCommand.Args):
        default: bool
        all: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument(
            "-d",
            "--default",
            action="store_true",
            help="trim non-default tasks (only without selected targets)",
        )

    def resolve_tasks(self, args: Args, context: BuildContext) -> list[Task]:  # type: ignore
        tasks: list[Task] = []
        if args.default:
            if args.targets:
                self.get_parser().error("cannot combine -d,--default with target selection")
            for project in context.iter_projects():
                for task in project.tasks().values():
                    if task.default:
                        tasks.append(task)
            return tasks
        if args.targets:
            return context.resolve_tasks(args.targets)
        for project in context.iter_projects():
            tasks += project.tasks().values()
        return tasks

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: BuildGraphCommand.Args) -> None:
        if len(graph) == 0:
            print("no tasks.", file=sys.stderr)
            sys.exit(1)

        longest_name = max(map(len, (task.path for task in graph.tasks()))) + 1
        print(colored("D " + "Task".ljust(longest_name + 1) + "Type", attrs=["bold"]))
        for task in graph.execution_order():
            print(
                colored("●", "cyan" if task.default else "grey"),
                task.path.ljust(longest_name),
                type(task).__module__ + "." + type(task).__name__,
            )


class QueryCommand(BuildGraphCommand):
    """perform queries on the build graph"""

    class Args(BuildGraphCommand.Args):
        is_up_to_date: bool
        legend: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("--legend", action="store_true", help="print out a legend along with the query result")
        parser.add_argument("--is-up-to-date", action="store_true", help="query if the selected task(s) are up to date")

    def execute(self, args: BuildGraphCommand.Args) -> int | None:
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


class DescribeCommand(BuildGraphCommand):
    """describe one or more tasks in detail"""

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: BuildGraphCommand.Args) -> None:
        tasks = list(graph.tasks(required_only=True))
        print("selected", len(tasks), "task(s)")
        print()

        for task in tasks:
            print("Task", colored(task.path, attrs=["bold", "underline"]))
            print("  Type".ljust(30), type(task).__module__ + "." + type(task).__name__)
            print("  File".ljust(30), colored(sys.modules[type(task).__module__].__file__ or "???", "cyan"))
            print("  Default".ljust(30), task.default)
            print("  Capture".ljust(30), task.capture)
            rels = list(task.get_relationships())
            print("  Relationships".ljust(30), len(rels))
            for rel in rels:
                print(
                    "".ljust(4),
                    colored(rel.other_task.path, attrs=["bold"]),
                    f"before={rel.before}, strict={rel.strict}",
                )
            print("  Properties".ljust(30), len(type(task).__schema__))
            for key in type(task).__schema__:
                prop: Property[Any] = getattr(task, key)
                print("".ljust(4), colored(key, attrs=["reverse"]), f'= {colored(prop.get_or("<unset>"), "blue")}')
            print()


class EnvStatusCommand(BuildAwareCommand):
    """ provide the status of the build environment"""

    def execute(self, args: Any) -> None:
        manager = self.get_environment_manager(args)
        if manager.are_we_in():
            self.get_parser().error("`kraken env` commands cannot be used inside managed enviroment")
        print('environment path:', manager.env_dir, "(does not exist)" if not manager.exists() else "")
        print("outdated" if manager.check_outdated() else "up to date")


class EnvInstallCommand(BuildAwareCommand):
    """ ensure the build environment is installed"""

    def execute(self, args: Any) -> None:
        manager = self.get_environment_manager(args)
        if manager.are_we_in():
            self.get_parser().error("`kraken env` commands cannot be used inside managed enviroment")
        if manager.exists() and not manager.check_outdated():
            print("build environment is up to date")
        else:
            print("updating" if manager.exists() else "creating", "build environment")
            manager.install(args.update)


class EnvUpdateCommand(BuildAwareCommand):
    """ update the build environment and the lock file"""

    def execute(self, args: Any) -> None:
        manager = self.get_environment_manager(args)
        if manager.are_we_in():
            self.get_parser().error("`kraken env` commands cannot be used inside managed enviroment")
        # TODO (@NiklasRosenstein): Use a slightly different wording to inform that we're updating it while
        #       ignoring the lock file?
        print("updating" if manager.exists() else "creating", "build environment")
        manager.install(True)


class EnvLockCommand(BuildAwareCommand):
    """ write the lock file"""

    def execute(self, args: Any) -> None:
        manager = self.get_environment_manager(args)
        if manager.are_we_in():
            self.get_parser().error("`kraken env` commands cannot be used inside managed enviroment")
        if not manager.exists():
            self.get_parser().error("build environment does not exist")
        if manager.check_outdated():
            logger.warning("build environment is outdated with requirement spec")
        manager.lock()


def _main() -> None:
    from kraken import core

    env = Group("manage the build environment")
    env.add_command("status", EnvStatusCommand())
    env.add_command("install", EnvInstallCommand())
    env.add_command("update", EnvUpdateCommand())
    env.add_command("lock", EnvLockCommand())

    app = CliApp("kraken", f"cli: {__version__}, core: {core.__version__}", features=[])
    app.add_command("run", RunCommand())
    app.add_command("fmt", RunCommand("fmt"))
    app.add_command("lint", RunCommand("lint"))
    app.add_command("build", RunCommand("build"))
    app.add_command("test", RunCommand("test"))
    app.add_command("ls", LsCommand())
    app.add_command("query", QueryCommand())
    app.add_command("describe", DescribeCommand())
    app.add_command("env", env)
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
